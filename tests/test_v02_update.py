"""Tests for the v0.2 update: conventions, G-families, profile modes, UTF-8."""

from __future__ import annotations

import numpy as np
import pytest
import yaml

from sss_aug_studio.core.image import SonarImage
from sss_aug_studio.core.labels import LabelSet, YoloBox
from sss_aug_studio.core.meta import AcquisitionMeta
from sss_aug_studio.core.pipeline import AugmentationInstance, AugmentationPipeline
from sss_aug_studio.core import registry
from sss_aug_studio.profiles.store import PipelineProfile, bundled_presets, load_profile, save_profile


def _img(layout="dual", h=120, w=200) -> SonarImage:
    rng = np.random.default_rng(3)
    data = np.clip(0.3 + 0.1 * rng.standard_normal((h, w)), 0, 1).astype(np.float32)
    if layout == "dual":
        c = w // 2
        data[:, c - 3 : c + 3] = 0.01
    meta = AcquisitionMeta(layout=layout, altitude_m=2.0, slant_range_m=30.0, res_along_m=0.08, heading_deg=90.0)
    return SonarImage(data=data, meta=meta)


# --------------------------------------------------------------- G-families
def test_g1_mirror_pixels_labels_and_layout():
    img = _img(layout="single_starboard")
    labels = LabelSet(boxes=[YoloBox(0, 0.2, 0.5, 0.1, 0.2)])
    inst = AugmentationInstance(family="mirror_across_track", label="m", instance_id="g1t")
    res = AugmentationPipeline([inst]).apply(img, labels, 1, "k")
    assert np.array_equal(res.image.data, img.data[:, ::-1])
    assert res.image.meta.layout == "single_port"          # layout swapped
    assert res.labels.boxes[0].cx == pytest.approx(0.8, abs=0.02)  # cx mirrored
    assert res.labels.boxes[0].cy == pytest.approx(0.5, abs=1e-6)


def test_g1_mirror_is_involution_and_preserves_centered_nadir():
    img = _img(layout="dual")
    n_before = img.nadir_band()
    inst = AugmentationInstance(family="mirror_across_track", label="m", instance_id="g1i")
    pipe = AugmentationPipeline([inst, inst.model_copy(update={"instance_id": "g1i2"})])
    res = pipe.apply(img, LabelSet(), 1, "k")
    assert np.array_equal(res.image.data, img.data)        # double mirror = identity
    once = AugmentationPipeline([inst]).apply(img, LabelSet(), 1, "k")
    n_after = once.image.nadir_band()
    assert abs((n_after[0] + n_after[1]) / 2 - (n_before[0] + n_before[1]) / 2) <= 2  # centered nadir preserved


def test_g2_reversal_pixels_labels_heading():
    img = _img()
    labels = LabelSet(boxes=[YoloBox(0, 0.3, 0.25, 0.1, 0.1)])
    inst = AugmentationInstance(family="reverse_along_track", label="r", instance_id="g2t")
    res = AugmentationPipeline([inst]).apply(img, labels, 1, "k")
    assert np.array_equal(res.image.data, img.data[::-1, :])
    assert res.labels.boxes[0].cy == pytest.approx(0.75, abs=0.02)
    assert res.labels.boxes[0].cx == pytest.approx(0.3, abs=1e-6)
    assert res.image.meta.heading_deg == pytest.approx(270.0)


def test_g_families_registered_first_in_physical_order():
    assert registry.DEFAULT_ORDER[:2] == ["mirror_across_track", "reverse_along_track"]
    assert registry.get("mirror_across_track").section == "geometry"
    assert registry.get("speckle").section == "physics"


# ------------------------------------------------------------- conventions
def test_default_intensity_mapping_is_log():
    assert AcquisitionMeta().intensity_mapping == "log"


def test_display_roundtrip_log_default():
    img = _img()
    u8 = img.to_display("auto")  # auto = declared mapping = log by default
    back = SonarImage(
        data=np.zeros_like(img.data), meta=img.meta
    )  # decode manually via loader path
    from sss_aug_studio.core.image import _inverse_display_mapping

    lin = _inverse_display_mapping(u8.astype(np.float32) / 255.0, img.meta)
    assert np.abs(lin - img.data).mean() < 0.01  # inverse within quantization


def test_shadow_included_gates_f6_box_edit():
    """With shadow_included=False, F6 must never move label boxes."""
    rng = np.random.default_rng(0)
    h, w = 160, 240
    data = np.clip(0.45 + 0.05 * rng.standard_normal((h, w)), 0, 1).astype(np.float32)
    # bright highlight + dark shadow inside the box, starboard side of dual
    data[:, 116:124] = 0.01
    data[60:100, 150:165] = 0.9
    data[60:100, 165:205] = 0.05
    box = YoloBox.from_pixels(0, 148, 55, 207, 105, w, h)
    for flag, expect_move in ((True, True), (False, False)):
        meta = AcquisitionMeta(layout="dual", altitude_m=2.0, slant_range_m=30.0, shadow_included=flag)
        img = SonarImage(data=data.copy(), meta=meta)
        inst = AugmentationInstance(
            family="shadow",
            label="s",
            instance_id=f"f6_{flag}",
            params={"length_altitude_factor": 1.4, "confidence_gate": 0.0, "floor_level": 0.0, "floor_blend": 0.0},
        )
        res = AugmentationPipeline([inst]).apply(img, LabelSet(boxes=[box]), 2, "k")
        moved = abs(res.labels.boxes[0].w - box.w) > 1e-4 or abs(res.labels.boxes[0].cx - box.cx) > 1e-4
        assert moved == expect_move, f"shadow_included={flag}: moved={moved}"


# ----------------------------------------------------------- profile modes
def test_profile_instance_laws_roundtrip(tmp_path):
    """v0.3.0: stochastic laws live on the instances and survive profile IO."""
    law = {"looks": {"dist": "uniform", "low": 2.0, "high": 6.0}}
    inst = AugmentationInstance(family="speckle", label="s", instance_id="prof_i1", distributions=law)
    prof = PipelineProfile.from_pipeline("p", "d", AugmentationPipeline([inst]))
    path = tmp_path / "p.yaml"
    save_profile(prof, path)
    loaded = load_profile(path)
    assert loaded.is_stochastic
    assert loaded.instances[0].distributions == law


def test_legacy_stochastic_profile_migrates(tmp_path):
    """v0.2.x profiles (profile-level mode/distributions) migrate on load."""
    legacy = PipelineProfile(
        name="old",
        mode="stochastic",
        instances=[AugmentationInstance(family="speckle", label="s", instance_id="i1")],
        distributions={"i1": {"looks": {"dist": "uniform", "low": 2.0, "high": 6.0}}},
    )
    assert legacy.instances[0].distributions["looks"]["dist"] == "uniform"
    assert legacy.is_stochastic


def test_presets_are_deterministic():
    for p in bundled_presets():
        assert not p.is_stochastic


def test_distributions_excluded_from_config_hash():
    i = AugmentationInstance(family="speckle", label="s", instance_id="h1")
    h = i.config_hash()
    i.distributions = {"looks": {"dist": "uniform", "low": 1.0, "high": 2.0}}
    assert i.config_hash() == h


def test_stochastic_generation_reproducible(tmp_path):
    """Stochastic distributions + fixed seed -> identical sampled params."""
    from sss_aug_studio.core.random import derive_rng
    from sss_aug_studio.generation.distributions import sample_value

    spec = {"dist": "uniform", "low": 2.0, "high": 6.0}
    a = [sample_value(spec, derive_rng(9, "img", "i1", c, "params")) for c in range(4)]
    b = [sample_value(spec, derive_rng(9, "img", "i1", c, "params")) for c in range(4)]
    assert a == b and len(set(a)) > 1


# ------------------------------------------------------------------- UTF-8
def test_encyclopedia_pages_load_utf8():
    from sss_aug_studio.gui import encyclopedia as enc_mod

    # bypass Qt: exercise the loader function directly
    pages = enc_mod._pages()
    assert len(pages) >= 10  # 9 v0.1 pages + g_geometry
    for name, text in pages.items():
        assert isinstance(text, str) and len(text) > 100, name
    assert "g_geometry.md" in pages
