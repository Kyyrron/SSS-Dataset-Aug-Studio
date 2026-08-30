"""Tests for the ``sss_aug_dataset.yaml`` contract and the metadata reader chain.

The contract: every :class:`AcquisitionMeta` field is honoured at the top level
and inside ``meta:``, the top level winning on conflict; an unrecognised key at
either level warns instead of vanishing; reading never raises.
"""

from __future__ import annotations

import json
import warnings
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from sss_aug_studio.core.meta import AcquisitionMeta
from sss_aug_studio.datasets.metadata import DatasetConfigReader
from sss_aug_studio.datasets.yolo import YoloDataset


def _dataset(root: Path, config: dict, sidecar: dict | None = None) -> Path:
    """Minimal one-image YOLO dataset carrying the given ``sss_aug_dataset.yaml``."""
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "labels").mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(root / "images" / "t.png"), np.zeros((16, 24), np.uint8))
    (root / "labels" / "t.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (root / "sss_aug_dataset.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    if sidecar is not None:
        (root / "images" / "t.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return root


def _meta(root: Path) -> AcquisitionMeta:
    ds = YoloDataset(root)
    assert len(ds) == 1
    return ds.meta_for(ds.items[0])


@contextmanager
def _no_user_warning():
    """pytest.warns(None) was removed in pytest 8; assert the absence directly."""
    with warnings.catch_warnings(record=True) as log:
        warnings.simplefilter("always")
        yield
    offenders = [w for w in log if issubclass(w.category, UserWarning)]
    assert not offenders, f"unexpected warnings: {[str(w.message) for w in offenders]}"


# ------------------------------------------------------- both positions work
def test_top_level_acquisition_field_is_honoured(tmp_path):
    """A top-level key other than layout/intensity_mapping must reach AcquisitionMeta."""
    _dataset(tmp_path, {"layout": "dual", "shadow_included": False, "altitude_m": 3.0})
    meta = _meta(tmp_path)
    assert meta.shadow_included is False
    assert meta.altitude_m == 3.0


def test_meta_block_field_is_honoured(tmp_path):
    _dataset(tmp_path, {"layout": "dual", "meta": {"shadow_included": False, "altitude_m": 3.0}})
    meta = _meta(tmp_path)
    assert meta.shadow_included is False
    assert meta.altitude_m == 3.0


def test_top_level_wins_on_conflict(tmp_path):
    """Preserves the pre-existing precedence for layout / intensity_mapping."""
    _dataset(
        tmp_path,
        {
            "layout": "dual",
            "intensity_mapping": "linear",
            "shadow_included": False,
            "meta": {"layout": "single_port", "intensity_mapping": "log", "shadow_included": True},
        },
    )
    meta = _meta(tmp_path)
    assert meta.layout == "dual"
    assert meta.intensity_mapping == "linear"
    assert meta.shadow_included is False


# ------------------------------------------------------------- unknown keys
def test_unrecognised_key_warns_and_does_not_raise(tmp_path):
    """A misspelling is the same failure class as the silent drop: make it visible."""
    _dataset(
        tmp_path,
        {"layout": "dual", "shadow_incuded": False, "nonsense": 1, "meta": {"bogus_m": 2.0}},
    )
    with pytest.warns(UserWarning) as rec:
        meta = _meta(tmp_path)
    text = str(rec[0].message)
    for key in ("shadow_incuded", "nonsense", "bogus_m"):
        assert key in text
    assert meta.shadow_included is True  # the misspelled key is never applied
    assert meta.layout == "dual"  # everything recognised still resolves


def test_conformant_config_does_not_warn(tmp_path):
    """The structural ``meta`` key is not an AcquisitionMeta field and must stay quiet."""
    _dataset(tmp_path, {"layout": "dual", "intensity_mapping": "linear", "meta": {"altitude_m": 2.0}})
    with _no_user_warning():
        assert _meta(tmp_path).altitude_m == 2.0


def test_malformed_config_does_not_raise(tmp_path):
    (tmp_path / "images").mkdir(parents=True)
    (tmp_path / "labels").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "images" / "t.png"), np.zeros((16, 24), np.uint8))
    (tmp_path / "labels" / "t.txt").write_text("", encoding="utf-8")
    (tmp_path / "sss_aug_dataset.yaml").write_text("layout: [unclosed\n", encoding="utf-8")
    assert DatasetConfigReader(tmp_path).read(tmp_path / "images" / "t.png") is None
    assert _meta(tmp_path).layout == "dual"  # falls back to the model default


# -------------------------------------------------------------- chain order
def test_sidecar_beats_dataset_config(tmp_path):
    """Guards the reader order in YoloDataset.__init__ (sidecar first)."""
    _dataset(
        tmp_path,
        {"layout": "dual", "shadow_included": False, "altitude_m": 3.0},
        sidecar={"layout": "single_starboard", "shadow_included": True},
    )
    meta = _meta(tmp_path)
    assert meta.layout == "single_starboard"
    assert meta.shadow_included is True
    assert meta.altitude_m == 3.0  # unset in the sidecar, filled from the dataset config


# ------------------------------------------------------------- demo fixture
def test_demo_dataset_declares_a_live_shadow_included():
    """demo_dataset's top-level shadow_included must actually reach AcquisitionMeta."""
    root = Path(__file__).resolve().parent.parent / "demo_dataset"
    fields = DatasetConfigReader(root).read(root / "images" / "dual_basin_01.png")
    assert fields is not None
    assert "shadow_included" in fields
    assert fields["intensity_mapping"] == "log"
