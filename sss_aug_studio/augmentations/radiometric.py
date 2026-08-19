"""F2 — Radiometric transfer (TVG residual, absorption, beam pattern).

Physical phenomenon
    Received level follows the sonar equation; the receiver's time-varying
    gain (TVG) tries to invert spreading + absorption + angular terms but
    never matches the true environment, leaving range-dependent brightness
    residuals.  At 1-3 m altitude the grazing-angle mapping — and hence the
    Lambertian roll-off and beam-pattern illumination — is strongly
    altitude-coupled (thesis contribution C4).

Model (dB domain, per side, r = ground range)
    dG(r) = a.log10(R/R_ref) + b.(R - R_ref) + c
            + 10.log10[ sin^p(theta'(r)) / sin^p(theta(r)) ]
            + 10.log10[ B(eps'(r)) / B(eps(r)) ]
    with theta(r) = atan(h/r) perturbed by an altitude factor, and B a
    Gaussian elevation beam pattern with tilt/width offsets.
    Nominal absorption from Francois & Garrison (1982) at the sonar
    frequency; ``absorption_residual`` perturbs around it.
"""

from __future__ import annotations

import numpy as np
from pydantic import Field

from ..core.registry import register
from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..physics.acoustics import (
    elevation_beam_gain,
    francois_garrison_alpha_db_per_km,
    lambertian_gain,
)
from ..physics.geometry import grazing_angle, ground_to_slant
from .base import AugParams, AugResult, Augmentation, ScienceCard, blend


class RadiometricParams(AugParams):
    spread_residual_db_per_decade: float = Field(
        0.0, ge=-15.0, le=15.0, description="Residual spreading term a (TVG under/over-compensation). [dB/decade]"
    )
    absorption_residual_db_per_m: float = Field(
        0.02, ge=-0.15, le=0.15, description="Absorption error b around the Francois-Garrison nominal. [dB/m]"
    )
    gain_offset_db: float = Field(0.0, ge=-12.0, le=12.0, description="Global gain offset c. [dB]")
    lambert_p: float = Field(2.0, ge=0.5, le=3.0, description="Lambertian exponent p (Coiras 2007 uses 2). [-]")
    altitude_factor: float = Field(
        1.0, ge=0.5, le=2.0, description="Perturbed/nominal altitude ratio h'/h driving grazing-angle change. [-]"
    )
    beam_tilt_offset_deg: float = Field(0.0, ge=-15.0, le=15.0, description="Elevation beam tilt offset. [deg]")
    beam_width_deg: float = Field(50.0, ge=10.0, le=90.0, description="Two-way elevation beamwidth. [deg]")


@register
class RadiometricAugmentation(Augmentation):
    key = "radiometric"
    name = "Radiometric transfer (TVG / absorption / beam)"
    order_hint = 50
    Params = RadiometricParams
    geometric = False
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="Mismatch between applied TVG and true transmission loss; altitude-coupled grazing-angle "
        "roll-off and elevation beam-pattern illumination.",
        equation="dG(r) = a.log10(R/R0) + b.(R-R0) + c + 10.log10[sin^p th'/sin^p th] + 10.log10[B'/B]",
        references=(
            "Francois & Garrison (1982), J. Acoust. Soc. Am. 72(6):1879-1890 (absorption)",
            "Coiras, Petillot & Lane (2007), IEEE Trans. Image Process. 16(2):382-390 (Lambertian SSS model)",
            "Lurton (2010), An Introduction to Underwater Acoustics, 2nd ed., Springer (sonar equation, TVG)",
        ),
        limitations="Flat-seabed grazing angles; image-domain dB correction assumes approximately linear input "
        "intensity (documented approximation, decision #4).",
        expected_effect="Smooth range-dependent brightening/darkening per side; near-range vs far-range balance "
        "shifts reproducing different gain settings and altitudes.",
        doc_page="f2_radiometric.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: RadiometricParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        out = img.data.copy()
        h_alt = img.meta.resolved_altitude_m()
        alpha_nom = francois_garrison_alpha_db_per_km(img.meta.frequency_khz, depth_m=img.meta.resolved_depth_m()) / 1000.0
        r_ref = max(0.25 * (img.meta.slant_range_m or 30.0), 1.0)
        info = {"alpha_nominal_db_per_m": round(alpha_nom, 4), "physical_units": img.meta.is_physical}
        for side in img.sides():
            r = np.maximum(side.range_m(), 1e-3)
            slant = ground_to_slant(r, h_alt)
            g_db = (
                params.spread_residual_db_per_decade * np.log10(np.maximum(slant, 1.0) / r_ref)
                + params.absorption_residual_db_per_m * (slant - r_ref)
                + params.gain_offset_db
            )
            # grazing-angle (Lambertian) term under perturbed altitude
            th0 = grazing_angle(r, h_alt)
            th1 = grazing_angle(r, h_alt * params.altitude_factor)
            lam = lambertian_gain(th1, params.lambert_p) / np.maximum(lambertian_gain(th0, params.lambert_p), 1e-6)
            # elevation beam-pattern term (depression angle = grazing angle for flat seabed)
            width = np.deg2rad(params.beam_width_deg)
            tilt0 = np.deg2rad(30.0)
            tilt1 = tilt0 + np.deg2rad(params.beam_tilt_offset_deg)
            beam = elevation_beam_gain(th1, tilt1, width) / np.maximum(elevation_beam_gain(th0, tilt0, width), 1e-6)
            gain = (10.0 ** (g_db / 10.0)) * lam * beam  # linear per-column gain
            view = side.view(out)
            view *= gain[None, :].astype(np.float32)
        out = np.clip(out, 0.0, 1.0).astype(np.float32)
        return AugResult(data=blend(img.data, out, strength), info=info)
