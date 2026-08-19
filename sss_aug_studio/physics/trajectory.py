"""Kinematic USV trajectory synthesis for platform-motion augmentation.

Generates physically parameterized per-ping time series (speed, heading
deviation, roll, altitude perturbation) for a surface vehicle, including an
optional coordinated turn.  Parameters are real physical units: m/s, degrees,
seconds, meters — the sample spacing is derived from the image's along-track
resolution and vehicle speed (metadata-driven mode) or from documented
fallbacks.

Reference: Lei et al. (2026, arXiv 2604.19901) motivate attitude-induced SSS
distortions as especially critical for surface platforms; the row-wise ray
model here follows the standard slant-geometry treatment (Blondel 2009).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .statistics import colored_noise_1d

__all__ = ["TrajectoryPerturbation", "synthesize"]


@dataclass
class TrajectoryPerturbation:
    """Per-ping perturbation series (length = number of image rows)."""

    dt_s: float
    speed_mps: np.ndarray          # instantaneous speed v(t)
    heading_dev_rad: np.ndarray    # heading deviation from mean course psi(t)
    roll_rad: np.ndarray           # roll angle phi(t)
    altitude_dev_m: np.ndarray     # heave-induced altitude deviation


def synthesize(
    rng: np.random.Generator,
    n_rows: int,
    base_speed_mps: float,
    res_along_m: float,
    *,
    speed_std_frac: float = 0.0,
    speed_corr_m: float = 10.0,
    yaw_std_deg: float = 0.0,
    yaw_corr_m: float = 5.0,
    roll_amp_deg: float = 0.0,
    roll_period_s: float = 4.0,
    heave_amp_m: float = 0.0,
    heave_period_s: float = 4.0,
    turn_radius_m: float = 0.0,
    turn_direction: int = 1,
    turn_center_frac: float = 0.5,
    turn_extent_frac: float = 0.3,
) -> TrajectoryPerturbation:
    """Synthesize a perturbed trajectory over ``n_rows`` pings.

    Wave-driven roll/heave are modeled as a dominant sinusoid at the wave
    period plus 30 % broadband residual; speed and yaw deviations as
    band-limited Gaussian processes with correlation lengths given in meters
    along track.  A turn of radius R contributes heading rate v/R over the
    selected row window (positive ``turn_direction`` = starboard).
    """
    v0 = max(base_speed_mps, 0.05)
    dt = res_along_m / v0
    t = np.arange(n_rows, dtype=np.float32) * dt

    def corr_rows(corr_m: float) -> float:
        return max(corr_m / max(res_along_m, 1e-6), 0.01)

    speed = v0 * (1.0 + colored_noise_1d(rng, n_rows, speed_std_frac, corr_rows(speed_corr_m)))
    speed = np.clip(speed, 0.1 * v0, 3.0 * v0)

    yaw = colored_noise_1d(rng, n_rows, np.deg2rad(yaw_std_deg), corr_rows(yaw_corr_m))

    if turn_radius_m > 0.5:
        i0 = int(np.clip((turn_center_frac - turn_extent_frac / 2) * n_rows, 0, n_rows - 1))
        i1 = int(np.clip((turn_center_frac + turn_extent_frac / 2) * n_rows, i0 + 1, n_rows))
        rate = float(turn_direction) * v0 / turn_radius_m  # rad/s
        dpsi = np.zeros(n_rows, dtype=np.float32)
        dpsi[i0:i1] = rate * dt
        heading = np.cumsum(dpsi)
        heading -= heading.mean()  # deviations around the mean course
        yaw = yaw + heading.astype(np.float32)

    phase_r = rng.uniform(0, 2 * np.pi)
    roll = np.deg2rad(roll_amp_deg) * (
        np.sin(2 * np.pi * t / max(roll_period_s, 0.5) + phase_r)
        + 0.3 * colored_noise_1d(rng, n_rows, 1.0, corr_rows(v0 * roll_period_s / 4))
    )

    phase_h = rng.uniform(0, 2 * np.pi)
    heave = heave_amp_m * (
        np.sin(2 * np.pi * t / max(heave_period_s, 0.5) + phase_h)
        + 0.3 * colored_noise_1d(rng, n_rows, 1.0, corr_rows(v0 * heave_period_s / 4))
    )

    return TrajectoryPerturbation(
        dt_s=dt,
        speed_mps=speed.astype(np.float32),
        heading_dev_rad=yaw.astype(np.float32),
        roll_rad=roll.astype(np.float32),
        altitude_dev_m=heave.astype(np.float32),
    )
