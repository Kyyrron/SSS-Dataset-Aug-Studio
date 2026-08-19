"""F8 — Shallow-water multipath & water-column artifacts.

Physical phenomenon
    In shallow enclosed basins (the thesis regime), sound reaches the
    receiver by multiple paths: bottom-surface-receiver bounces produce
    delayed, attenuated *ghost* copies of the seabed return; strong
    reflectors near nadir generate *second bottom returns*; vertical
    quay/breakwater walls act as bright quasi-linear reflectors at a slant
    range equal to the horizontal wall distance.  Thesis contribution C4
    identifies wall multipath as a dominant driver of detector false
    positives in port environments — this family manufactures exactly those
    hard negatives.

Model (per side, ground-range approximation)
    ghost:        I' = I + g_m . (K_smear * I)(x, r - dr),
                  dr(surface bounce) ~ path difference / 2 from depth D and
                  altitude h; dr(second bottom) ~ slant range itself.
    wall echo:    bright speckled ridge at r_w(x) = wall distance (may drift
                  along track), Gaussian across-range profile.
    nadir noise:  additive noise band inside the nadir gap (water column).
"""

from __future__ import annotations

import numpy as np
from pydantic import Field
from scipy.ndimage import gaussian_filter1d

from ..core.registry import register
from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..physics.statistics import colored_noise_1d, gamma_speckle
from .base import AugParams, AugResult, Augmentation, ScienceCard, blend


class MultipathParams(AugParams):
    surface_ghost_gain_db: float = Field(-14.0, ge=-30.0, le=-4.0, description="Surface-bounce ghost level. [dB re direct]")
    surface_ghost_enabled: bool = Field(True, description="Enable the surface-bounce ghost.")
    second_bottom_gain_db: float = Field(-18.0, ge=-30.0, le=-6.0, description="Second bottom return level. [dB re direct]")
    second_bottom_enabled: bool = Field(False, description="Enable the second bottom return (near-nadir).")
    ghost_smear_m: float = Field(0.4, ge=0.05, le=2.0, description="Range smear of ghost returns. [m]")
    wall_enabled: bool = Field(True, description="Enable a synthetic wall echo (enclosed-basin regime).")
    wall_distance_m: float = Field(15.0, ge=1.0, le=100.0, description="Horizontal distance to the virtual wall. [m]")
    wall_distance_wander_m: float = Field(1.5, ge=0.0, le=10.0, description="Along-track wall-distance wander std. [m]")
    wall_gain_db: float = Field(6.0, ge=0.0, le=18.0, description="Wall-echo level above image mean. [dB]")
    wall_width_m: float = Field(0.6, ge=0.1, le=3.0, description="Across-range wall-echo width. [m]")
    wall_side: str = Field("port", description="Side carrying the wall echo: 'port' | 'starboard' | 'both'.")
    nadir_noise_level: float = Field(0.03, ge=0.0, le=0.3, description="Water-column noise level in the nadir band. [linear]")


@register
class MultipathAugmentation(Augmentation):
    key = "multipath"
    name = "Shallow-water multipath & water column"
    order_hint = 60
    Params = MultipathParams
    geometric = False
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="Surface-bounce ghosts, second bottom returns and quay-wall echoes characteristic of the "
        "shallow enclosed-basin regime; the dominant false-positive generator identified by the thesis (C4).",
        equation="I' = I + g_m (K*I)(x, r-dr) + wall ridge at r_w(x) + nadir noise",
        references=(
            "Blondel (2009), The Handbook of Sidescan Sonar, Springer, ch. 5 (multipath artifacts)",
            "Lurton (2010), An Introduction to Underwater Acoustics, 2nd ed. (multipath propagation)",
            "Cocchi et al. (2024), Sensors 24(14):4544 (harbor USV operations, regime precedent)",
        ),
        limitations="Incoherent geometric model (no phase interference); wall echo is phenomenological "
        "(bright speckled ridge), not ray-traced; ground-range approximation for ghost delay.",
        expected_effect="Faint displaced copies of strong seabed features; bright wandering quasi-linear ridge "
        "(the 'wall'); noisy nadir band — realistic hard negatives for the detector.",
        doc_page="f8_multipath.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: MultipathParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        h, w = img.data.shape
        out = img.data.copy()
        h_alt = img.meta.resolved_altitude_m()
        depth = img.meta.resolved_depth_m()
        info: dict = {}

        for side in img.sides():
            view = side.view(out)          # canonical: range increases with index
            src = side.view(img.data)
            res = side.res_across_m
            n = view.shape[1]

            # ---- surface-bounce ghost: extra path ~ 2*(D - h) near-vertical bounce,
            # mapped to ground-range shift dr ~ (D - h) (documented approximation)
            if params.surface_ghost_enabled:
                dr_m = max(depth - h_alt, 0.2)
                shift = int(round(dr_m / res))
                if 0 < shift < n:
                    g = 10.0 ** (params.surface_ghost_gain_db / 10.0)
                    ghost = np.zeros_like(src)
                    ghost[:, shift:] = src[:, : n - shift]
                    sig = params.ghost_smear_m / res
                    ghost = gaussian_filter1d(ghost, sigma=max(sig, 0.3), axis=1, mode="constant")
                    view += (g * ghost).astype(np.float32)
                    info["surface_ghost_shift_px"] = shift

            # ---- second bottom return: copy shifted by the slant range itself (r -> 2r approx)
            if params.second_bottom_enabled:
                g2 = 10.0 ** (params.second_bottom_gain_db / 10.0)
                idx = np.arange(n)
                src_idx = idx // 2  # feature at r appears again near 2r
                ghost2 = src[:, src_idx] * (idx % 2 == 0)[None, :]
                sig = params.ghost_smear_m / res
                ghost2 = gaussian_filter1d(ghost2.astype(np.float32), sigma=max(sig, 0.3), axis=1, mode="constant")
                view += (g2 * ghost2).astype(np.float32)

            # ---- wall echo
            wall_here = params.wall_enabled and params.wall_side in (side.name, "both")
            if wall_here:
                dist = params.wall_distance_m + colored_noise_1d(
                    rng, h, params.wall_distance_wander_m, max(h / 12, 1.0)
                )
                center = dist / res
                width_px = max(params.wall_width_m / res, 0.6)
                cols = np.arange(n, dtype=np.float32)[None, :]
                profile = np.exp(-0.5 * ((cols - center[:, None]) / width_px) ** 2)
                amp = max(float(img.data.mean()), 1e-3) * 10.0 ** (params.wall_gain_db / 10.0)
                ridge = amp * profile * gamma_speckle(rng, view.shape, looks=1.5)
                view += ridge.astype(np.float32)
                info[f"wall_{side.name}"] = True

        # ---- nadir-band water-column noise (dual layout only)
        n0, n1 = img.nadir_band()
        if params.nadir_noise_level > 1e-3 and 0 <= n0 < n1 <= w:
            band = out[:, n0:n1]
            noise = params.nadir_noise_level * gamma_speckle(rng, band.shape, looks=1.0)
            out[:, n0:n1] = np.clip(band + noise, 0, 1)

        out = np.clip(out, 0.0, 1.0).astype(np.float32)
        return AugResult(data=blend(img.data, out, strength), info=info)
