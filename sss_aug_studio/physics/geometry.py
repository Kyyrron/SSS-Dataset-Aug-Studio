"""Side-scan imaging geometry (flat-seabed model).

References: Blondel (2009) *The Handbook of Sidescan Sonar*, ch. 2-3;
Al-Rawi et al. (2017) for first-bottom-return altitude estimation (the
project's own FBR pipeline provides the altitude metadata this module
consumes).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "slant_to_ground",
    "ground_to_slant",
    "grazing_angle",
    "shadow_length_m",
    "altitude_error_ground_remap",
]


def slant_to_ground(slant_m: np.ndarray, altitude_m: float) -> np.ndarray:
    """Ground range from slant range (flat seabed): r_g = sqrt(R^2 - h^2)."""
    s = np.asarray(slant_m, dtype=np.float64)
    return np.sqrt(np.maximum(s**2 - altitude_m**2, 0.0))


def ground_to_slant(ground_m: np.ndarray, altitude_m: float) -> np.ndarray:
    g = np.asarray(ground_m, dtype=np.float64)
    return np.sqrt(g**2 + altitude_m**2)


def grazing_angle(ground_m: np.ndarray, altitude_m: float) -> np.ndarray:
    """Grazing angle (rad) of the ray hitting ground range r_g: atan(h / r_g)."""
    g = np.maximum(np.asarray(ground_m, dtype=np.float64), 1e-6)
    return np.arctan2(altitude_m, g)


def shadow_length_m(target_height_m: float, ground_range_m: float, altitude_m: float) -> float:
    """Ground-projected acoustic shadow length behind a proud target.

    L_s = H_t * r_g / (h - H_t)  (similar triangles; ~ H_t * r_g / h for
    small targets).  Longer shadows at far range and low altitude — the
    defining signature geometry for small-object detection.
    """
    denom = max(altitude_m - target_height_m, 1e-3)
    return target_height_m * ground_range_m / denom


def altitude_error_ground_remap(r_out_m: np.ndarray, altitude_m: float, altitude_error_m: float) -> np.ndarray:
    """Across-track remap induced by an altitude-estimation error.

    The image was ground-projected assuming altitude ``h``; simulate the
    projection that a (wrong) FBR estimate ``h_a = h + delta`` would have
    produced.  A feature at true ground range ``r_t`` (slant R) appears at
    ``r_w = sqrt(R^2 - h_a^2) = sqrt(r_t^2 - 2 h delta - delta^2)``.
    For each output column at ``r_out`` (wrong image) this returns the input
    ground range ``r_in`` to sample:  r_in = sqrt(r_out^2 + 2 h delta + delta^2).
    """
    r = np.asarray(r_out_m, dtype=np.float64)
    return np.sqrt(np.maximum(r**2 + 2.0 * altitude_m * altitude_error_m + altitude_error_m**2, 0.0))
