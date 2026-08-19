"""F3 — Slant-range & altitude geometry.

Physical phenomenon
    Ground-range projection of raw slant-range pings requires the sonar
    altitude from first-bottom-return (FBR) detection (Al-Rawi et al. 2017;
    the project's own FBR pipeline).  Altitude estimation errors — and real
    altitude changes at 1-3 m over uneven shallow seabeds — warp the
    across-track axis nonlinearly (strongest near nadir) and change the
    nadir-gap width ("gap breathing"), an altitude-coupled swath effect the
    thesis singles out for the shallow regime (C4).

Model (per side, r = ground range of the output column)
    r_in(r_out; y) = sqrt( r_out^2 + 2 h d(y) + d(y)^2 ),
    d(y) = d0 + d1 . y/H + n(y)   (offset + drift + correlated noise),
    nadir edge shifts with the same mapping.
"""

from __future__ import annotations

import numpy as np
from pydantic import Field

from ..core.registry import register
from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..core.warp import FieldWarp, identity_grid
from ..physics.statistics import colored_noise_1d
from .base import AugParams, AugResult, Augmentation, ScienceCard


class SlantGeometryParams(AugParams):
    altitude_offset_m: float = Field(0.15, ge=-1.5, le=1.5, description="Constant altitude-estimation error d0. [m]")
    altitude_drift_m: float = Field(0.0, ge=-1.5, le=1.5, description="Linear altitude drift over the image d1. [m]")
    altitude_noise_m: float = Field(0.05, ge=0.0, le=0.5, description="Correlated altitude noise std. [m]")
    altitude_noise_corr_m: float = Field(5.0, ge=0.5, le=50.0, description="Altitude noise correlation length. [m]")


@register
class SlantGeometryAugmentation(Augmentation):
    key = "slant_geometry"
    name = "Slant-range & altitude geometry"
    order_hint = 40
    Params = SlantGeometryParams
    geometric = True
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="FBR altitude-estimation error / real altitude change warps the ground-range projection "
        "(strongest near nadir) and breathes the nadir gap.",
        equation="r_in = sqrt(r_out^2 + 2 h d(y) + d(y)^2),  d(y) = d0 + d1 y/H + n(y)",
        references=(
            "Al-Rawi et al. (2017), first-bottom-return detection for sidescan imagery (project pipeline)",
            "Blondel (2009), The Handbook of Sidescan Sonar, Springer, ch. 3 (slant-range correction)",
        ),
        limitations="Flat-seabed model; extreme negative d clipped to keep the remap defined near nadir.",
        expected_effect="Across-track squeeze/stretch concentrated near the nadir edges; wobbling nadir-gap "
        "width along track.",
        doc_page="f3_slant_geometry.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: SlantGeometryParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        h, w = img.data.shape
        h_alt = img.meta.resolved_altitude_m()
        res_along = img.meta.resolved_res_along_m()
        corr_rows = params.altitude_noise_corr_m / max(res_along, 1e-6)
        d = (
            params.altitude_offset_m
            + params.altitude_drift_m * (np.arange(h, dtype=np.float32) / max(h - 1, 1))
            + colored_noise_1d(rng, h, params.altitude_noise_m, corr_rows)
        )
        d = np.clip(d, -0.8 * h_alt, 2.0 * h_alt)  # keep sqrt argument sane near nadir

        gx, gy = identity_grid(h, w)
        map_x = gx.copy()
        fwd_dx = np.zeros((h, w), dtype=np.float32)

        for side in img.sides():
            r = side.range_m().astype(np.float32)  # canonical output ranges
            res = side.res_across_m
            arg = r[None, :] ** 2 + 2.0 * h_alt * d[:, None] + d[:, None] ** 2
            r_in = np.sqrt(np.maximum(arg, 0.0))
            col_in = r_in / res - 0.5  # canonical input index
            # forward: input canonical index j -> output index sqrt(r_j^2 - 2 h d - d^2)/res
            r_j = r[None, :]
            arg_f = r_j**2 - 2.0 * h_alt * d[:, None] - d[:, None] ** 2
            col_out = np.sqrt(np.maximum(arg_f, 0.0)) / res - 0.5
            cols = np.arange(side.cols.start or 0, side.cols.stop or w)
            canon = cols[::-1] if side.flip else cols
            if side.flip:
                map_x[:, canon] = (side.cols.stop - 1) - col_in
                fwd_dx[:, canon] = -(col_out - np.arange(len(r))[None, :])
            else:
                map_x[:, canon] = (side.cols.start or 0) + col_in
                fwd_dx[:, canon] = col_out - np.arange(len(r))[None, :]

        warp = FieldWarp(
            map_x=map_x.astype(np.float32),
            map_y=gy,
            fwd_dx=fwd_dx,
            fwd_dy=np.zeros((h, w), dtype=np.float32),
        ).scaled(strength)
        out = warp.apply_image(img.data)
        return AugResult(data=out, warp=warp, info={"altitude_m": round(h_alt, 3), "physical_units": img.meta.is_physical})
