"""F4 — Platform motion distortion.

Physical phenomenon
    A surface vehicle (unlike a depth-stabilized AUV) experiences wave-driven
    roll/heave and control-driven yaw/speed variation; along-track pixel
    spacing is v/PRF, so speed variation compresses/stretches the image, yaw
    slews each ping footprint proportionally to range, turns fan the swath,
    and roll modulates the elevation beam-pattern illumination.  These
    surface-navigation degradations are the defining regime difference of the
    thesis (C4; Lei et al. 2026 flag attitude distortion as critical for
    surface platforms).

Model — one physically consistent trajectory drives all coupled terms:
    speed:  in_row = P^-1(out_row),  P = cumulative along-track distance / res
    yaw:    along-track shift  s(y, r) = r . psi(y) / res_along   (small angle)
    turn:   psi includes integrated v/R over the turn window (fan distortion)
    roll:   multiplicative beam-illumination gain  B(theta - phi(y)) / B(theta)
    heave:  per-row across-track altitude remap  r_in = sqrt(r_out^2 + 2 h dh + dh^2)
"""

from __future__ import annotations

import numpy as np
from pydantic import Field

from ..core.registry import register
from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..core.warp import FieldWarp, identity_grid
from ..physics.acoustics import elevation_beam_gain
from ..physics.geometry import grazing_angle
from ..physics.trajectory import synthesize
from .base import AugParams, AugResult, Augmentation, ScienceCard


class PlatformMotionParams(AugParams):
    speed_std_frac: float = Field(0.10, ge=0.0, le=0.5, description="Speed fluctuation std as fraction of mean. [-]")
    speed_corr_m: float = Field(8.0, ge=1.0, le=50.0, description="Speed fluctuation correlation length. [m]")
    yaw_std_deg: float = Field(2.0, ge=0.0, le=12.0, description="Heading deviation std. [deg]")
    yaw_corr_m: float = Field(5.0, ge=0.5, le=50.0, description="Heading deviation correlation length. [m]")
    roll_amp_deg: float = Field(4.0, ge=0.0, le=20.0, description="Wave-driven roll amplitude. [deg]")
    roll_period_s: float = Field(4.0, ge=0.5, le=12.0, description="Dominant wave (roll) period. [s]")
    heave_amp_m: float = Field(0.0, ge=0.0, le=1.0, description="Heave-driven altitude oscillation amplitude. [m]")
    heave_period_s: float = Field(4.0, ge=0.5, le=12.0, description="Heave period. [s]")
    turn_radius_m: float = Field(0.0, ge=0.0, le=200.0, description="Turn radius (0 = no turn). [m]")
    turn_direction: int = Field(1, ge=-1, le=1, description="+1 starboard turn, -1 port turn.")
    turn_center_frac: float = Field(0.5, ge=0.0, le=1.0, description="Turn window center (image-height fraction). [-]")
    turn_extent_frac: float = Field(0.3, ge=0.05, le=1.0, description="Turn window extent (image-height fraction). [-]")
    beam_width_deg: float = Field(50.0, ge=10.0, le=90.0, description="Two-way elevation beamwidth for roll gain. [deg]")


@register
class PlatformMotionAugmentation(Augmentation):
    key = "platform_motion"
    name = "Platform motion distortion"
    order_hint = 30
    Params = PlatformMotionParams
    geometric = True
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="USV surge/yaw/roll/heave from waves and control; turns. Along-track sampling = v/PRF; "
        "ping footprint slews with heading; roll modulates beam illumination.",
        equation="s(y,r) = r.psi(y)/res ;  in_row = P^-1(out_row) ;  gain = B(th - phi(y))/B(th)",
        references=(
            "Lei et al. (2026), arXiv 2604.19901 (attitude-induced SSS distortion, critical for USVs)",
            "Blondel (2009), The Handbook of Sidescan Sonar, Springer (geometry & motion artifacts)",
            "Cocchi et al. (2024), Sensors 24(14):4544, DOI 10.3390/s24144544 (USV regime)",
        ),
        limitations="Kinematic ray model (no Doppler/beamforming); turn fan approximated by integrated-heading "
        "shear; small-angle yaw; rigid sonar mount (true for the BlueBoat).",
        expected_effect="Wavy along-track distortion growing with range, local compression/stretch, curved "
        "features during turns, periodic roll-driven intensity banding.",
        doc_page="f4_platform_motion.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: PlatformMotionParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        h, w = img.data.shape
        res_along = img.meta.resolved_res_along_m()
        v0 = img.meta.resolved_speed_mps()
        traj = synthesize(
            rng,
            h,
            v0,
            res_along,
            speed_std_frac=params.speed_std_frac,
            speed_corr_m=params.speed_corr_m,
            yaw_std_deg=params.yaw_std_deg,
            yaw_corr_m=params.yaw_corr_m,
            roll_amp_deg=params.roll_amp_deg,
            roll_period_s=params.roll_period_s,
            heave_amp_m=params.heave_amp_m,
            heave_period_s=params.heave_period_s,
            turn_radius_m=params.turn_radius_m,
            turn_direction=params.turn_direction,
            turn_center_frac=params.turn_center_frac,
            turn_extent_frac=params.turn_extent_frac,
        )

        # ---- 1. speed variation: monotone row remap (recorded ping -> position)
        pos_rows = np.cumsum(traj.speed_mps * traj.dt_s) / res_along  # position (rows) of each ping
        pos_rows -= pos_rows[0]
        scale = (h - 1) / max(pos_rows[-1], 1e-6)  # keep image height constant
        out_to_in_row = np.interp(np.arange(h), pos_rows * scale, np.arange(h)).astype(np.float32)

        # ---- 2. yaw / turn: range-proportional along-track shear per row
        r_m = img.range_map_m()[0]  # per-column ground range (m)
        psi = traj.heading_dev_rad
        shift_rows = np.outer(psi, r_m / res_along).astype(np.float32)  # (h, w)

        gx, gy = identity_grid(h, w)
        map_y = out_to_in_row[:, None] + shift_rows
        map_x = gx.copy()

        # ---- 3. heave: per-row across-track altitude remap (within each side)
        if params.heave_amp_m > 0.005:
            h_alt = img.meta.resolved_altitude_m()
            for side in img.sides():
                r = side.range_m()
                cols = np.arange(side.cols.start or 0, side.cols.stop or w)
                canon = cols[::-1] if side.flip else cols
                res_across = side.res_across_m
                dh = traj.altitude_dev_m[:, None]
                r_in = np.sqrt(np.maximum(r[None, :] ** 2 + 2.0 * h_alt * dh + dh**2, 0.0))
                col_in = r_in / res_across - 0.5
                # canonical index -> image column
                if side.flip:
                    map_x[:, canon] = (side.cols.stop - 1) - col_in
                else:
                    map_x[:, canon] = (side.cols.start or 0) + col_in

        # ---- forward displacements (labels)
        fwd_rows = np.interp(np.arange(h, dtype=np.float32), out_to_in_row, np.arange(h, dtype=np.float32))
        # feature at input row y appears at output row fwd(y) minus the shear it acquires there
        fwd_dy = (fwd_rows[:, None] - gy) - shift_rows
        fwd_dx = gx - map_x  # across-track: inverse shift ~ symmetric for small heave remap

        warp = FieldWarp(
            map_x=map_x.astype(np.float32),
            map_y=map_y.astype(np.float32),
            fwd_dx=fwd_dx.astype(np.float32),
            fwd_dy=fwd_dy.astype(np.float32),
        ).scaled(strength)
        out = warp.apply_image(img.data)

        # ---- 4. roll: multiplicative beam-illumination modulation (radiometric)
        if params.roll_amp_deg > 0.05:
            h_alt = img.meta.resolved_altitude_m()
            width = np.deg2rad(params.beam_width_deg)
            tilt = np.deg2rad(30.0)
            gain = np.ones((h, w), dtype=np.float32)
            for side in img.sides():
                th = grazing_angle(side.range_m(), h_alt)
                sign = -1.0 if side.name == "port" else 1.0  # roll tilts one side up, the other down
                b0 = elevation_beam_gain(th, tilt, width)
                for_side = elevation_beam_gain(th[None, :], tilt + sign * traj.roll_rad[:, None], width)
                g = (for_side / np.maximum(b0[None, :], 1e-6)).astype(np.float32)
                sview = side.view(gain)
                sview *= g
            roll_gain = 1.0 + float(np.clip(strength, 0, 2)) * (gain - 1.0)
            out = np.clip(out * roll_gain, 0.0, 1.0).astype(np.float32)

        info = {
            "res_along_m": round(res_along, 4),
            "base_speed_mps": round(v0, 3),
            "physical_units": img.meta.is_physical,
            "turn": params.turn_radius_m > 0.5,
        }
        return AugResult(data=out, warp=warp, info=info)
