"""F1 — Speckle & reverberation statistics.

Physical phenomenon
    The echo from an unresolved seabed patch is the coherent sum of many
    random scatterer contributions.  Fully developed conditions give
    Rayleigh-envelope / exponential-intensity speckle; high-resolution sonars
    over structured shallow seabeds show heavier tails, well described by the
    K-distribution: intensity = texture x speckle with gamma-distributed
    texture (Abraham & Lyons 2002; Lyons & Abraham 1999).  Speckle is
    **multiplicative** — additive Gaussian noise is physically wrong for
    envelope-detected sonar and deliberately not provided.

Model
    I' = I . T . G,  G ~ Gamma(L, 1/L)  (unit-mean speckle, L looks),
                     T ~ Gamma(nu, 1/nu) spatially correlated texture
                     (T = 1 for the pure Rayleigh/Gamma regime).

    Both gamma factors are correlated by a memoryless nonlinear transformation
    of a Gaussian field (Tough & Ward 1999), so the marginal stays exactly
    gamma at every shape and correlation length.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field

from ..core.registry import register
from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..physics.statistics import gamma_speckle, k_texture_field
from .base import AugParams, AugResult, Augmentation, ScienceCard, blend


class SpeckleParams(AugParams):
    distribution: Literal["rayleigh", "k"] = Field(
        "k", description="'rayleigh': pure L-look Gamma speckle; 'k': gamma texture x speckle (heavy tails)."
    )
    looks: float = Field(3.0, ge=0.5, le=16.0, description="Effective number of looks L (variance 1/L). [looks]")
    k_shape_nu: float = Field(8.0, ge=0.5, le=50.0, description="K-distribution shape nu; small = heavier tails. [-]")
    texture_corr_m: float = Field(0.5, ge=0.0, le=5.0, description="Texture correlation length. [m]")
    speckle_corr_px: float = Field(0.7, ge=0.0, le=3.0, description="Resolution-cell speckle correlation. [px]")


@register
class SpeckleAugmentation(Augmentation):
    key = "speckle"
    name = "Speckle & reverberation noise"
    order_hint = 70
    Params = SpeckleParams
    geometric = False
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="Coherent interference of unresolved scatterers; non-Rayleigh (K) clutter over structured seabeds.",
        equation="I' = I . T . G,   G ~ Gamma(L, 1/L),   T ~ Gamma(nu, 1/nu)",
        references=(
            "Abraham & Lyons (2002), IEEE J. Oceanic Eng. 27(4):800-813, DOI 10.1109/JOE.2002.804324",
            "Lyons & Abraham (1999), J. Acoust. Soc. Am. 106(3):1307-1315, DOI 10.1121/1.428034",
            "Tough & Ward (1999), J. Phys. D: Appl. Phys. 32(23):3075-3084, DOI 10.1088/0022-3727/32/23/314",
        ),
        limitations="Stationary statistics per image (no mixed-sediment segmentation); no coherent facet "
        "glints. Both gamma factors carry an exact marginal at every shape and correlation length.",
        expected_effect="Grain-level multiplicative noise; with the K option, patchy bright clutter clusters "
        "that stress detector false-positive behavior.",
        doc_page="f1_speckle.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: SpeckleParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        h, w = img.data.shape
        c = params.speckle_corr_px
        noise = gamma_speckle(rng, (h, w), params.looks, corr_px=(c, c))
        if params.distribution == "k":
            # texture correlation in pixels; isotropic in ground units when metadata present
            sides = list(img.sides())
            res = sides[0].res_across_m if sides else 0.05
            corr_px = params.texture_corr_m / max(res, 1e-3)
            t = k_texture_field(rng, (h, w), params.k_shape_nu, (corr_px, corr_px))
            noise = noise * t
        out = np.clip(img.data * noise, 0.0, 1.0).astype(np.float32)
        return AugResult(data=blend(img.data, out, strength), info={"distribution": params.distribution})
