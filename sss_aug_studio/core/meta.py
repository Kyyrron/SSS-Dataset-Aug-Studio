"""Acquisition metadata attached to every sonar image.

Physical-unit parameterization (validated design decision #2): whenever the
acquisition pipeline (BlueBoat + Omniscan 450 + FBR altitude estimation)
provides metadata, augmentations operate in real physical units (m, m/s, deg,
dB, Hz).  When metadata is absent the studio falls back to *normalized mode*
using the documented defaults below; every default is conservative and clearly
flagged so generated manifests record whether physical or fallback values were
used.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Layout = Literal["single_port", "single_starboard", "dual"]
IntensityMapping = Literal["linear", "gamma", "log"]

#: Fallback values used in normalized mode (documented in the user manual).
FALLBACK_SLANT_RANGE_M = 30.0
FALLBACK_ALTITUDE_M = 2.0
FALLBACK_SPEED_MPS = 1.5
FALLBACK_RES_ALONG_M = 0.10
FALLBACK_DEPTH_M = 4.0


class AcquisitionMeta(BaseModel):
    """Physical acquisition context for one sonar image.

    All fields are optional except ``layout``; :meth:`resolved` returns a copy
    with fallbacks filled in and ``is_physical`` recording provenance.
    """

    model_config = ConfigDict(extra="ignore")

    layout: Layout = Field("dual", description="Waterfall layout (per-dataset setting).")
    altitude_m: Optional[float] = Field(None, ge=0.1, description="Sonar altitude above seabed (FBR estimate).")
    slant_range_m: Optional[float] = Field(None, gt=0, description="Configured max range per side.")
    res_across_m: Optional[float] = Field(None, gt=0, description="Across-track meters per pixel (ground range).")
    res_along_m: Optional[float] = Field(None, gt=0, description="Along-track meters per pixel.")
    speed_mps: Optional[float] = Field(None, ge=0, description="Vehicle speed over ground.")
    heading_deg: Optional[float] = Field(None, description="Vehicle heading.")
    prf_hz: Optional[float] = Field(None, gt=0, description="Ping repetition frequency.")
    frequency_khz: float = Field(450.0, gt=0, description="Sonar center frequency (Omniscan 450 default).")
    depth_m: Optional[float] = Field(None, gt=0, description="Water depth (for multipath geometry).")
    timestamp: Optional[str] = Field(None, description="Acquisition timestamp (ISO 8601).")

    shadow_included: bool = Field(
        True,
        description="Label convention: a YOLO box covers the complete acoustic signature "
        "(highlight + acoustic shadow). F6 moves the down-range box edge only when true.",
    )

    nadir_center_frac: float = Field(0.5, ge=0.0, le=1.0, description="Nadir band center as image-width fraction (dual layout).")
    nadir_halfwidth_frac: Optional[float] = Field(
        None, ge=0.0, le=0.4, description="Nadir band half-width fraction; None = auto-detect."
    )

    intensity_mapping: IntensityMapping = Field(
        "log",
        description="Display mapping applied at export by the acquisition software; inverted on load. "
        "The mapping is DECLARED by the acquisition pipeline, never inferred; when metadata is "
        "absent the documented default assumption is 'log' (dB waterfall export, log_range_db dynamic range).",
    )
    gamma: float = Field(2.2, gt=0.5, le=4.0, description="Gamma exponent when intensity_mapping='gamma'.")
    log_range_db: float = Field(40.0, gt=1.0, le=120.0, description="Dynamic range when intensity_mapping='log'.")

    # ----------------------------------------------------------------- helpers
    @property
    def is_physical(self) -> bool:
        """True when across-track scale is known in meters (metadata-driven mode)."""
        return self.res_across_m is not None or self.slant_range_m is not None

    def resolved_altitude_m(self) -> float:
        return self.altitude_m if self.altitude_m is not None else FALLBACK_ALTITUDE_M

    def resolved_depth_m(self) -> float:
        if self.depth_m is not None:
            return self.depth_m
        return self.resolved_altitude_m() + FALLBACK_DEPTH_M - FALLBACK_ALTITUDE_M

    def resolved_speed_mps(self) -> float:
        return self.speed_mps if self.speed_mps is not None else FALLBACK_SPEED_MPS

    def resolved_res_along_m(self) -> float:
        if self.res_along_m is not None:
            return self.res_along_m
        if self.speed_mps is not None and self.prf_hz is not None:
            return self.speed_mps / self.prf_hz
        return FALLBACK_RES_ALONG_M

    def resolved_res_across_m(self, side_width_px: int) -> float:
        if self.res_across_m is not None:
            return self.res_across_m
        rng = self.slant_range_m if self.slant_range_m is not None else FALLBACK_SLANT_RANGE_M
        return rng / max(side_width_px, 1)
