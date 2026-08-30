"""Unit tests for the physics layer, core contracts and determinism."""

from __future__ import annotations

import numpy as np
import pytest

from sss_aug_studio.core.image import SonarImage
from sss_aug_studio.core.labels import LabelSet, YoloBox
from sss_aug_studio.core.meta import AcquisitionMeta
from sss_aug_studio.core.pipeline import AugmentationInstance, AugmentationPipeline
from sss_aug_studio.core.random import derive_rng
from sss_aug_studio.core.warp import row_remap_warp
from sss_aug_studio.core import registry
from sss_aug_studio.physics.acoustics import francois_garrison_alpha_db_per_km, lambertian_gain
from sss_aug_studio.physics.geometry import (
    altitude_error_ground_remap,
    ground_to_slant,
    shadow_length_m,
    slant_to_ground,
)
from sss_aug_studio.physics.statistics import gamma_speckle, k_texture_field


# --------------------------------------------------------------- physics
def test_francois_garrison_450khz_magnitude():
    """At 450 kHz in temperate shallow seawater alpha ~ 0.08-0.15 dB/m."""
    alpha = francois_garrison_alpha_db_per_km(450.0, temp_c=13.0, salinity_psu=35.0, depth_m=5.0)
    assert 80.0 < alpha < 160.0


def test_francois_garrison_monotone_in_frequency():
    a1 = francois_garrison_alpha_db_per_km(100.0)
    a2 = francois_garrison_alpha_db_per_km(450.0)
    a3 = francois_garrison_alpha_db_per_km(900.0)
    assert a1 < a2 < a3


def test_slant_ground_roundtrip():
    r = np.linspace(0.5, 30, 50)
    h = 2.0
    assert np.allclose(slant_to_ground(ground_to_slant(r, h), h), r)


def test_shadow_length_grows_with_range_and_low_altitude():
    assert shadow_length_m(0.3, 20.0, 2.0) > shadow_length_m(0.3, 10.0, 2.0)
    assert shadow_length_m(0.3, 10.0, 1.5) > shadow_length_m(0.3, 10.0, 3.0)


def test_altitude_remap_identity_at_zero_error():
    r = np.linspace(0.1, 30, 100)
    assert np.allclose(altitude_error_ground_remap(r, 2.0, 0.0), r)


def test_lambertian_bounds():
    th = np.linspace(0, np.pi / 2, 50)
    g = lambertian_gain(th, 2.0)
    assert g.min() >= 0.0 and g.max() <= 1.0 and g[-1] == pytest.approx(1.0)


def test_gamma_speckle_moments():
    rng = np.random.default_rng(0)
    s = gamma_speckle(rng, (400, 400), looks=4.0)
    assert s.mean() == pytest.approx(1.0, abs=0.02)
    assert s.var() == pytest.approx(0.25, abs=0.03)


@pytest.mark.parametrize("nu", [1.0, 8.0])
def test_k_texture_moments(nu):
    """Unit mean and variance 1/nu, including the heavy-tail regime.

    The pre-copula smoothed-gamma construction failed this at nu=1 (mean 1.098,
    variance 0.714 against 1.0) because its 0.05 floor clipped after the moment
    restoration; the exact marginal needs no floor.
    """
    t = k_texture_field(np.random.default_rng(0), (320, 448), nu=nu, corr_px=(3.0, 3.0))
    assert t.mean() == pytest.approx(1.0, abs=0.05)
    assert t.var() == pytest.approx(1.0 / nu, rel=0.15)
    assert t.min() > 0.0, "gamma support is (0, inf); no clipping floor may survive"


def _gamma_ks_and_shape(x, k):
    """KS distance to Gamma(k, 1/k) and the ML-recovered shape."""
    from scipy import stats

    return (
        float(stats.kstest(x.ravel(), stats.gamma(a=k, scale=1.0 / k).cdf).statistic),
        float(stats.gamma.fit(x.ravel(), floc=0.0)[0]),
    )


@pytest.mark.parametrize("nu", [1.0, 8.0])
def test_k_texture_gamma_marginal(nu):
    """The correlated texture is exactly Gamma(nu, 1/nu), not merely moment-matched.

    Measured against the pre-copula implementation, which scored KS 0.124 (nu=1)
    and 0.046 (nu=8) and recovered nu-hat 0.98 / 6.43.  KS is taken on a grid
    subsampled at 2.5 kernel sigma so the sample is effectively independent.
    """
    corr = 3.0
    t = k_texture_field(np.random.default_rng(4), (320, 448), nu=nu, corr_px=(corr, corr))
    step = int(round(2.5 * corr))
    ks, _ = _gamma_ks_and_shape(t[::step, ::step], nu)
    _, nu_hat = _gamma_ks_and_shape(t, nu)
    assert ks < 0.04, f"marginal KS {ks:.4f} too large"
    assert nu_hat == pytest.approx(nu, rel=0.05), f"recovered nu {nu_hat:.3f} vs nominal {nu}"


def test_gamma_speckle_correlated_marginal():
    """The speckle factor keeps its exact marginal once correlated, and emits no zeros.

    At the shipped defaults the pre-copula smooth-renormalise-clip path drove
    1.73% of pixels to exactly zero -- a physically impossible echo -- and
    recovered L-hat 2.70 for a nominal 3.
    """
    looks = 3.0
    g = gamma_speckle(np.random.default_rng(5), (320, 448), looks=looks, corr_px=(0.7, 0.7))
    assert g.min() > 0.0, "no pixel may be clipped to a zero echo"
    _, looks_hat = _gamma_ks_and_shape(g, looks)
    assert looks_hat == pytest.approx(looks, rel=0.05), f"recovered L {looks_hat:.3f} vs nominal {looks}"


def _acorr_length_px(field, axis):
    """1/e length of the normalised autocovariance along ``axis``, in pixels."""
    x = np.asarray(field, dtype=np.float64)
    x = x - x.mean()
    n = x.shape[axis]
    spec = np.fft.rfft(x, n=2 * n, axis=axis)
    ac = np.fft.irfft(spec * np.conj(spec), axis=axis)
    ac = np.moveaxis(ac, axis, 0)[:n].mean(axis=1)
    ac /= ac[0]
    k = int(np.argmax(ac < np.exp(-1.0)))
    assert k > 0
    return k - 1 + (ac[k - 1] - np.exp(-1.0)) / (ac[k - 1] - ac[k])


@pytest.mark.parametrize("sigma_y,sigma_x", [(2.0, 8.0), (10.0, 2.0)])
def test_k_texture_correlation_anisotropy(sigma_y, sigma_x):
    """``corr_px`` is a Gaussian kernel sigma per axis; the 1/e length is ~1.95 sigma.

    Guards the correlation structure the copula transform must not disturb: the
    two axes are set independently, and the achieved length tracks the requested
    sigma with the same factor the smoothed-gamma implementation produced.
    """
    t = k_texture_field(np.random.default_rng(7), (512, 512), nu=8.0, corr_px=(sigma_y, sigma_x))
    assert _acorr_length_px(t, 0) / sigma_y == pytest.approx(1.95, rel=0.15)
    assert _acorr_length_px(t, 1) / sigma_x == pytest.approx(1.95, rel=0.15)


# ------------------------------------------------------------------ core
def _make_image(h=200, w=300, layout="dual") -> SonarImage:
    rng = np.random.default_rng(1)
    data = np.clip(0.3 + 0.1 * rng.standard_normal((h, w)), 0, 1).astype(np.float32)
    if layout == "dual":
        c = w // 2
        data[:, c - 4 : c + 4] = 0.01
    meta = AcquisitionMeta(layout=layout, altitude_m=2.0, slant_range_m=30.0, res_along_m=0.08, speed_mps=1.5, depth_m=5.0)
    return SonarImage(data=data, meta=meta)


def test_nadir_autodetect():
    img = _make_image()
    n0, n1 = img.nadir_band()
    assert 140 <= n0 < 150 and 150 < n1 <= 160


def test_sides_cover_layouts():
    assert [s.name for s in _make_image(layout="dual").sides()] == ["port", "starboard"]
    assert [s.name for s in _make_image(layout="single_port").sides()] == ["port"]
    assert [s.name for s in _make_image(layout="single_starboard").sides()] == ["starboard"]


def test_row_remap_warp_label_roundtrip():
    """Removing rows must shift boxes by the exact number of removed rows above them."""
    h, w = 100, 50
    keep = np.array([r for r in range(h) if not (20 <= r < 30)], dtype=np.float32)
    warp = row_remap_warp(keep, h, w)
    ls = LabelSet(boxes=[YoloBox(0, 0.5, 0.6, 0.2, 0.2)])  # rows 50-70 -> shift up by 10
    out = ls.warped(warp, (w, h), (w, len(keep)))
    assert len(out.boxes) == 1
    b = out.boxes[0]
    y0 = (b.cy - b.h / 2) * len(keep)
    assert y0 == pytest.approx(40.0, abs=1.5)


def test_label_drop_on_offimage():
    h, w = 100, 100
    keep = np.arange(0, 50, dtype=np.float32)  # bottom half removed
    warp = row_remap_warp(keep, h, w)
    ls = LabelSet(boxes=[YoloBox(0, 0.5, 0.9, 0.2, 0.15)])
    out = ls.warped(warp, (w, h), (w, 50))
    assert len(out.boxes) == 0 and out.provenance[0].kept is False


def test_derive_rng_stability():
    a = derive_rng(42, "img.png", "inst", 0).random(5)
    b = derive_rng(42, "img.png", "inst", 0).random(5)
    c = derive_rng(42, "img.png", "inst", 1).random(5)
    assert np.array_equal(a, b) and not np.array_equal(a, c)


# ---------------------------------------------------- family contracts
@pytest.mark.parametrize("family", list(registry.all_families()))
def test_family_contract(family):
    """Every family: valid output range/dtype, determinism, no input mutation."""
    img = _make_image()
    before = img.data.copy()
    labels = LabelSet(boxes=[YoloBox(0, 0.25, 0.5, 0.15, 0.2)])
    inst = AugmentationInstance(family=family, label="t", instance_id=f"t_{family}")
    pipe = AugmentationPipeline([inst])
    r1 = pipe.apply(img, labels, 7, "k")
    r2 = pipe.apply(img, labels, 7, "k")
    assert np.array_equal(img.data, before), f"{family} mutated its input"
    assert r1.image.data.dtype == np.float32
    assert 0.0 <= r1.image.data.min() and r1.image.data.max() <= 1.0
    assert np.array_equal(r1.image.data, r2.image.data), f"{family} not deterministic"
    assert not np.array_equal(r1.image.data, before), f"{family} default params are a no-op"


def test_strength_zero_is_identity_for_photometric():
    img = _make_image()
    labels = LabelSet()
    for family in ("speckle", "radiometric", "seabed", "multipath"):
        inst = AugmentationInstance(family=family, label="t", instance_id=f"s0_{family}", strength=0.0)
        r = AugmentationPipeline([inst]).apply(img, labels, 3, "k")
        assert np.allclose(r.image.data, img.data, atol=1e-5), family


def test_pipeline_order_and_probability_gating():
    img = _make_image()
    insts = [
        AugmentationInstance(family="speckle", label="a", instance_id="ordA", probability=0.0),
        AugmentationInstance(family="radiometric", label="b", instance_id="ordB", probability=1.0),
    ]
    r = AugmentationPipeline(insts).apply(img, LabelSet(), 5, "k", respect_probability=True)
    applied = {s.instance_id: s.applied for s in r.stages}
    assert applied == {"ordA": False, "ordB": True}


def test_geometric_family_moves_labels_consistently():
    """A strong slant-geometry warp must move a far-range box inward like the pixels."""
    img = _make_image()
    labels = LabelSet(boxes=[YoloBox(0, 0.9, 0.5, 0.1, 0.2)])  # far starboard range
    inst = AugmentationInstance(
        family="slant_geometry",
        label="t",
        instance_id="geoT",
        params={"altitude_offset_m": 0.8, "altitude_noise_m": 0.0, "altitude_drift_m": 0.0},
    )
    r = AugmentationPipeline([inst]).apply(img, labels, 1, "k")
    assert len(r.labels.boxes) == 1
    # positive altitude error compresses ranges outward sampling -> features move toward nadir
    assert r.labels.boxes[0].cx < 0.9
