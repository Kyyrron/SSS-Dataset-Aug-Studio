"""F5 — Ping loss & sensor artifacts.

Physical phenomenon
    Receiver/link-level degradations: dropped or blanked pings (wireless-link
    loss on a basestation-computed USV, logger stalls), partial-line
    dropouts, per-ping gain fluctuation (AGC/TVG jitter) appearing as
    along-track striping, and sparse acoustic/electrical interference — the
    project's own USBL pinger is a documented in-band interference source.

Model
    Dropout events ~ Poisson(rate), burst length ~ Geometric(1/mean);
    modes: black (zeroed pings), hold (logger repeats last ping), remove
    (pings absent -> image shortens; labels remapped through the exact
    row mapping).  Striping: per-row gain g(y) = AR(1) process in dB.
    Interference: Poisson-count bright slanted segments, amplitude in dB
    above the local mean.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field

from ..core.registry import register
from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..core.warp import row_remap_warp
from .base import AugParams, AugResult, Augmentation, ScienceCard, blend


class PingArtifactsParams(AugParams):
    dropout_events_per_100_rows: float = Field(1.0, ge=0.0, le=20.0, description="Dropout burst rate. [events/100 pings]")
    dropout_burst_mean: float = Field(3.0, ge=1.0, le=50.0, description="Mean burst length. [pings]")
    dropout_mode: Literal["black", "hold", "remove"] = Field(
        "hold", description="black: zero pings; hold: repeat last ping; remove: delete pings (image shortens)."
    )
    partial_events_per_100_rows: float = Field(0.5, ge=0.0, le=20.0, description="Partial-line dropout rate. [events/100 pings]")
    partial_extent_frac: float = Field(0.4, ge=0.05, le=1.0, description="Max extent of a partial dropout (side-width fraction). [-]")
    stripe_sigma_db: float = Field(0.8, ge=0.0, le=4.0, description="Per-ping gain jitter std. [dB]")
    stripe_corr_rows: float = Field(1.5, ge=0.0, le=30.0, description="AR-like correlation of gain jitter. [pings]")
    interference_events: float = Field(1.0, ge=0.0, le=30.0, description="Mean interference streaks per image. [-]")
    interference_gain_db: float = Field(9.0, ge=3.0, le=25.0, description="Interference level above local mean. [dB]")


@register
class PingArtifactsAugmentation(Augmentation):
    key = "ping_artifacts"
    name = "Ping loss & sensor artifacts"
    order_hint = 80
    Params = PingArtifactsParams
    geometric = True  # only in 'remove' mode
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="Dropped/blanked pings (wireless link, logger), per-ping gain jitter (striping), sparse "
        "acoustic/electrical interference (incl. the mission's own USBL pinger).",
        equation="bursts ~ Poisson(lambda), len ~ Geom(1/L) ;  g(y) = AR(1) in dB ;  streaks ~ Poisson(N)",
        references=(
            "Blondel (2009), The Handbook of Sidescan Sonar, Springer, ch. 5 (acquisition artifacts)",
            "Cerulean Omniscan 450 documentation (project reference base, acquisition behavior)",
        ),
        limitations="Statistical, not mechanistic; parameters should be re-fit to real Omniscan logs "
        "(validation hook V3 in the encyclopedia).",
        expected_effect="Horizontal missing/held lines, fine along-track striping, occasional bright slanted "
        "streaks; 'remove' mode shortens the image and remaps labels.",
        doc_page="f5_ping_artifacts.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: PingArtifactsParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        h, w = img.data.shape
        out = img.data.copy()
        info: dict = {}

        # ---- striping (per-ping gain jitter)
        if params.stripe_sigma_db > 0.01:
            g_db = rng.standard_normal(h).astype(np.float32)
            if params.stripe_corr_rows > 0.2:
                from scipy.ndimage import gaussian_filter1d

                g_db = gaussian_filter1d(g_db, sigma=params.stripe_corr_rows, mode="reflect")
            std = float(g_db.std())
            if std > 1e-8:
                g_db *= params.stripe_sigma_db / std
            out *= (10.0 ** (g_db / 20.0))[:, None]

        # ---- interference streaks
        n_streaks = rng.poisson(params.interference_events)
        local_mean = max(float(img.data.mean()), 1e-3)
        amp = local_mean * 10.0 ** (params.interference_gain_db / 10.0)
        for _ in range(int(n_streaks)):
            y0 = rng.uniform(0, h)
            x0 = rng.uniform(0, w)
            length = rng.uniform(0.1, 0.8) * w
            angle = rng.uniform(-0.35, 0.35)  # near-horizontal (per-ping) streaks
            n = max(int(length), 2)
            xs = np.clip(x0 + np.arange(n) * np.cos(angle), 0, w - 1).astype(int)
            ys = np.clip(y0 + np.arange(n) * np.sin(angle), 0, h - 1).astype(int)
            dotted = rng.random(n) < rng.uniform(0.5, 1.0)
            out[ys[dotted], xs[dotted]] = np.clip(out[ys[dotted], xs[dotted]] + amp, 0, 1)
        info["interference_streaks"] = int(n_streaks)

        # ---- partial-line dropouts
        n_partial = rng.poisson(params.partial_events_per_100_rows * h / 100.0)
        for _ in range(int(n_partial)):
            y = int(rng.integers(0, h))
            x0 = int(rng.uniform(0, w))
            ext = int(rng.uniform(0.05, params.partial_extent_frac) * w)
            out[y, x0 : min(x0 + ext, w)] = 0.0
        info["partial_dropouts"] = int(n_partial)

        # ---- full ping dropouts
        n_events = rng.poisson(params.dropout_events_per_100_rows * h / 100.0)
        drop_mask = np.zeros(h, dtype=bool)
        for _ in range(int(n_events)):
            y = int(rng.integers(0, h))
            length = 1 + int(rng.geometric(1.0 / max(params.dropout_burst_mean, 1.0)))
            drop_mask[y : min(y + length, h)] = True
        info["dropped_pings"] = int(drop_mask.sum())

        if drop_mask.any():
            if params.dropout_mode == "black":
                out[drop_mask] = 0.0
            elif params.dropout_mode == "hold":
                idx = np.arange(h)
                last_good = np.maximum.accumulate(np.where(~drop_mask, idx, -1))
                last_good[last_good < 0] = int(np.argmax(~drop_mask)) if (~drop_mask).any() else 0
                out = out[last_good]
            else:  # remove
                keep = np.flatnonzero(~drop_mask)
                if len(keep) >= 2:
                    out = out[keep]
                    warp = row_remap_warp(keep.astype(np.float32), h, w)
                    blended = blend(img.data[keep], out, strength) if strength != 1.0 else out
                    return AugResult(
                        data=blended,
                        warp=warp,
                        out_size=(w, len(keep)),
                        info=info,
                    )

        return AugResult(data=blend(img.data, np.clip(out, 0, 1).astype(np.float32), strength), info=info)
