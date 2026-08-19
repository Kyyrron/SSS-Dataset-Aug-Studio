"""F7 — Seabed reflectivity & texture variation.

Physical phenomenon
    Sediment type sets mean backscattering strength (mud -> sand differs by
    ~5-10 dB at high frequency; APL-UW TR 9407 curves) and its spatial
    statistics; shallow port/nearshore seabeds show reflectivity patchiness
    (sediment patches, dredging scars, vegetation).  Training data from one
    site over-fits its sediment context; this family randomizes it.

Model (dB domain)
    I'_dB = I_dB + dS_b + mu(x, r),   mu = correlated Gaussian field
    (sigma_mu, correlation lengths l_along, l_across in meters).
    Optional background-only mode excludes dilated, feathered label boxes so
    object signatures keep their original photometry while context shifts.
"""

from __future__ import annotations

import numpy as np
from pydantic import Field
from scipy.ndimage import gaussian_filter

from ..core.registry import register
from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..physics.statistics import correlated_gaussian_field
from .base import AugParams, AugResult, Augmentation, ScienceCard, blend


class SeabedParams(AugParams):
    reflectivity_shift_db: float = Field(0.0, ge=-8.0, le=8.0, description="Global sediment reflectivity shift dS_b. [dB]")
    field_sigma_db: float = Field(1.5, ge=0.0, le=5.0, description="Reflectivity patchiness field std. [dB]")
    field_corr_along_m: float = Field(5.0, ge=0.2, le=50.0, description="Patch correlation length, along-track. [m]")
    field_corr_across_m: float = Field(2.0, ge=0.2, le=50.0, description="Patch correlation length, across-track. [m]")
    background_only: bool = Field(True, description="Exclude (dilated, feathered) label boxes from the change.")
    box_margin_m: float = Field(0.5, ge=0.0, le=3.0, description="Protection margin around boxes. [m]")


@register
class SeabedAugmentation(Augmentation):
    key = "seabed"
    name = "Seabed reflectivity & texture"
    order_hint = 10
    Params = SeabedParams
    geometric = False
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="Sediment type and patchiness set mean backscatter and its spatial statistics; single-site "
        "training data over-fits its sediment context.",
        equation="I'_dB = I_dB + dS_b + mu(x, r),  mu ~ correlated Gaussian field (sigma, l_along, l_across)",
        references=(
            "APL-UW TR 9407 (1994), High-Frequency Ocean Environmental Acoustic Models Handbook",
            "Lyons & Abraham (1999), J. Acoust. Soc. Am. 106(3):1307-1315 (shallow seafloor backscatter)",
        ),
        limitations="Does not synthesize organized bedforms (sand ripples) — listed as future work; dB shift on "
        "approximately linear intensities (decision #4).",
        expected_effect="Overall brighter/darker seabed and smooth patchy reflectivity variation; objects "
        "preserved when background-only mode is on.",
        doc_page="f7_seabed.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: SeabedParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        h, w = img.data.shape
        sides = list(img.sides())
        res_across = sides[0].res_across_m if sides else 0.05
        res_along = img.meta.resolved_res_along_m()
        field = correlated_gaussian_field(
            rng,
            (h, w),
            params.field_sigma_db,
            (params.field_corr_along_m / max(res_along, 1e-3), params.field_corr_across_m / max(res_across, 1e-3)),
        )
        g_db = params.reflectivity_shift_db + field
        gain = (10.0 ** (g_db / 10.0)).astype(np.float32)

        if params.background_only and labels.boxes:
            protect = np.zeros((h, w), dtype=np.float32)
            margin_px = params.box_margin_m / max(res_across, 1e-3)
            for b in labels.boxes:
                x0, y0, x1, y1 = b.to_pixels(w, h)
                x0 = int(np.clip(x0 - margin_px, 0, w))
                x1 = int(np.clip(x1 + margin_px, 0, w))
                y0 = int(np.clip(y0 - margin_px, 0, h))
                y1 = int(np.clip(y1 + margin_px, 0, h))
                protect[y0:y1, x0:x1] = 1.0
            protect = gaussian_filter(protect, sigma=max(margin_px / 2, 1.0))
            protect = np.clip(protect, 0.0, 1.0)
            gain = gain * (1.0 - protect) + protect  # feather toward unity inside boxes

        out = np.clip(img.data * gain, 0.0, 1.0).astype(np.float32)
        return AugResult(data=blend(img.data, out, strength), info={"background_only": params.background_only})
