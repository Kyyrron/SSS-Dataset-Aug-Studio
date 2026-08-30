"""Underwater-acoustics models used by the radiometric augmentations.

References
----------
* Francois & Garrison (1982), *Sound absorption based on ocean measurements,
  Part II*, J. Acoust. Soc. Am. 72(6), 1879-1890 — absorption model.
* Lurton (2010), *An Introduction to Underwater Acoustics*, 2nd ed. — sonar
  equation, spreading loss, TVG.
* Coiras, Petillot & Lane (2007), IEEE Trans. Image Processing 16(2) —
  Lambertian cos^p grazing-angle model for SSS image formation.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "francois_garrison_alpha_db_per_km",
    "spreading_loss_db",
    "lambertian_gain",
    "elevation_beam_gain",
    "db_to_lin",
    "lin_to_db",
]


def db_to_lin(g_db: np.ndarray | float) -> np.ndarray | float:
    return 10.0 ** (np.asarray(g_db, dtype=np.float64) / 10.0)


def lin_to_db(g: np.ndarray | float) -> np.ndarray | float:
    return 10.0 * np.log10(np.maximum(np.asarray(g, dtype=np.float64), 1e-12))


def francois_garrison_alpha_db_per_km(
    f_khz: float,
    temp_c: float = 13.0,
    salinity_psu: float = 35.0,
    depth_m: float = 5.0,
    ph: float = 8.0,
) -> float:
    """Seawater absorption coefficient alpha (dB/km), Francois-Garrison (1982).

    Full three-term model (boric acid + magnesium sulfate + pure water).
    At 450 kHz in temperate shallow seawater this returns ~100-120 dB/km,
    i.e. ~0.1 dB/m — the dominant range-dependent loss for the Omniscan 450.
    """
    t, s = temp_c, salinity_psu
    f = f_khz
    c = 1412.0 + 3.21 * t + 1.19 * s + 0.0167 * depth_m  # sound speed (m/s)
    theta = t + 273.0

    # Boric acid
    a1 = (8.86 / c) * 10 ** (0.78 * ph - 5.0)
    p1 = 1.0
    f1 = 2.8 * np.sqrt(s / 35.0) * 10 ** (4.0 - 1245.0 / theta)

    # Magnesium sulfate
    a2 = 21.44 * (s / c) * (1.0 + 0.025 * t)
    p2 = 1.0 - 1.37e-4 * depth_m + 6.2e-9 * depth_m**2
    f2 = (8.17 * 10 ** (8.0 - 1990.0 / theta)) / (1.0 + 0.0018 * (s - 35.0))

    # Pure water
    if t <= 20.0:
        a3 = 4.937e-4 - 2.59e-5 * t + 9.11e-7 * t**2 - 1.50e-8 * t**3
    else:
        a3 = 3.964e-4 - 1.146e-5 * t + 1.45e-7 * t**2 - 6.5e-10 * t**3
    p3 = 1.0 - 3.83e-5 * depth_m + 4.9e-10 * depth_m**2

    alpha = (
        a1 * p1 * f1 * f**2 / (f1**2 + f**2)
        + a2 * p2 * f2 * f**2 / (f2**2 + f**2)
        + a3 * p3 * f**2
    )
    return float(alpha)


def spreading_loss_db(r_m: np.ndarray, k: float = 20.0, r_ref: float = 1.0) -> np.ndarray:
    """One-way spreading loss ``k * log10(r / r_ref)`` dB (k=20 spherical)."""
    return k * np.log10(np.maximum(np.asarray(r_m, dtype=np.float64), r_ref) / r_ref)


def lambertian_gain(grazing_rad: np.ndarray, p: float = 2.0) -> np.ndarray:
    """Lambertian-like backscatter law ``sin(grazing)^p`` (linear gain).

    Coiras et al. (2007) model SSS intensity with the Lambert diffuse law;
    expressed against grazing angle (angle between ray and seabed), the
    incident-flux term is sin(grazing) and typical fitted exponents lie in
    p in [1, 2].
    """
    return np.clip(np.sin(np.clip(grazing_rad, 0.0, np.pi / 2)), 0.0, 1.0) ** p


def elevation_beam_gain(elev_rad: np.ndarray, tilt_rad: float, width_rad: float) -> np.ndarray:
    """Two-way parametric elevation beam pattern (Gaussian main lobe, linear gain).

    ``elev_rad`` is the depression angle of each ray; the beam is centered on
    ``tilt_rad`` with -3 dB two-way full width ``width_rad``.
    """
    sigma = max(width_rad, 1e-3) / 2.355  # FWHM -> sigma
    return np.exp(-0.5 * ((elev_rad - tilt_rad) / sigma) ** 2)
