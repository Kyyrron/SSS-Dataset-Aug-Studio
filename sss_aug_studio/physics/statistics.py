"""Stochastic models for sonar scattering statistics and environmental fields.

References
----------
* Abraham & Lyons (2002), IEEE J. Oceanic Eng. 27(4): K-distributed
  reverberation as gamma-modulated Rayleigh scattering (compound model).
* Lyons & Abraham (1999), JASA 106(3): shallow-water high-frequency seafloor
  backscatter statistics.
* Goodman (1976): fully developed speckle -> exponential intensity;
  L-look averaging -> Gamma(L, 1/L) multiplicative noise.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

__all__ = [
    "gamma_speckle",
    "k_texture_field",
    "correlated_gaussian_field",
    "colored_noise_1d",
]


def gamma_speckle(rng: np.random.Generator, shape: tuple[int, ...], looks: float) -> np.ndarray:
    """Unit-mean multiplicative speckle for an L-look intensity image.

    Fully developed speckle gives exponential intensity (L=1); incoherent
    averaging of L looks gives Gamma(L, 1/L) with variance 1/L.
    """
    looks = max(float(looks), 0.25)
    return rng.gamma(shape=looks, scale=1.0 / looks, size=shape).astype(np.float32)


def k_texture_field(
    rng: np.random.Generator,
    shape: tuple[int, int],
    nu: float,
    corr_px: tuple[float, float],
) -> np.ndarray:
    """Unit-mean gamma texture (the 'K' component) with spatial correlation.

    The compound (K) representation writes intensity as texture x speckle with
    texture ~ Gamma(nu, 1/nu); small ``nu`` = heavy tails (structured
    seabeds).  Spatial correlation is imposed by Gaussian smoothing of an
    uncorrelated gamma field followed by exact mean/variance restoration —
    the marginal is then only approximately gamma, an accepted approximation
    documented in the encyclopedia (the target is matching first- and
    second-order statistics relevant to detector robustness, not exact
    higher-order laws).
    """
    nu = max(float(nu), 0.3)
    field = rng.gamma(shape=nu, scale=1.0 / nu, size=shape).astype(np.float32)
    sy, sx = corr_px
    if sy > 0.3 or sx > 0.3:
        smoothed = gaussian_filter(field, sigma=(max(sy, 0.0), max(sx, 0.0)), mode="reflect")
        target_std = 1.0 / np.sqrt(nu)
        s_std = float(smoothed.std())
        if s_std > 1e-6:
            field = 1.0 + (smoothed - smoothed.mean()) * (target_std / s_std)
        else:
            field = np.ones(shape, dtype=np.float32)
    return np.clip(field, 0.05, None).astype(np.float32)


def correlated_gaussian_field(
    rng: np.random.Generator,
    shape: tuple[int, int],
    sigma_value: float,
    corr_px: tuple[float, float],
) -> np.ndarray:
    """Zero-mean Gaussian random field with given std and correlation lengths (px)."""
    white = rng.standard_normal(shape).astype(np.float32)
    sy, sx = max(corr_px[0], 0.01), max(corr_px[1], 0.01)
    f = gaussian_filter(white, sigma=(sy, sx), mode="reflect")
    std = float(f.std())
    if std < 1e-8:
        return np.zeros(shape, dtype=np.float32)
    return (f * (sigma_value / std)).astype(np.float32)


def colored_noise_1d(rng: np.random.Generator, n: int, sigma: float, corr_samples: float) -> np.ndarray:
    """Zero-mean band-limited (Gaussian-correlated) 1-D process of std ``sigma``.

    Used for yaw, speed and altitude perturbation time series along track;
    ``corr_samples`` is the correlation length expressed in samples (rows).
    """
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    white = rng.standard_normal(n).astype(np.float32)
    f = gaussian_filter(white, sigma=max(corr_samples, 0.01), mode="reflect")
    std = float(f.std())
    if std < 1e-8:
        return np.zeros(n, dtype=np.float32)
    return (f * (sigma / std)).astype(np.float32)
