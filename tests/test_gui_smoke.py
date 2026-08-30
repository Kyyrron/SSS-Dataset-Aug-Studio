"""Offscreen GUI smoke suite.

Replaces the ad-hoc ``QT_QPA_PLATFORM=offscreen`` script that was written and
re-written by hand for every GUI release (v0.1, v0.2, v0.2.1, v0.3.0).  The
assertions are the ones that script made pass, in the same order: window
construction, dataset indexing, pipeline mutation, preview-worker caching,
per-row height independence, encyclopedia pages, bundled presets, and the
generation dialog's config round-trip.

The module selects the offscreen Qt platform itself, so it does not depend on
the caller's environment, and skips wholesale where PySide6 is unavailable.

Dataset-dependent assertions are written against the dataset's own index
rather than hard-coded counts, so replacing ``demo_dataset`` does not break
them.
"""

from __future__ import annotations

import os

# Must precede any Qt import: QApplication picks its platform plugin at import
# of QtGui/QtWidgets, and there is no display in CI-less headless runs.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from pathlib import Path

import yaml
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from sss_aug_studio.core.pipeline import AugmentationInstance
from sss_aug_studio.generation.engine import GenerationConfig
from sss_aug_studio.gui import encyclopedia as enc_mod
from sss_aug_studio.gui import generation_dialog as gen_dlg_mod
from sss_aug_studio.gui.generation_dialog import GenerationDialog
from sss_aug_studio.gui.main_window import MainWindow
from sss_aug_studio.gui.preview import ROW_MAX_HEIGHT, ROW_MIN_HEIGHT
from sss_aug_studio.profiles.store import bundled_presets

pytestmark = pytest.mark.gui

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "demo_dataset"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """One QApplication per process — Qt forbids a second one."""
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp: QApplication) -> MainWindow:
    w = MainWindow()
    w.show()
    yield w
    w.close()


def _demo_image_count() -> int:
    return sum(1 for p in (DEMO / "images").iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def _spin(qapp: QApplication, until, timeout_ms: int = 10_000) -> bool:
    """Drive the real event loop until ``until()`` holds or the deadline passes.

    The preview is debounced through a 150 ms QTimer and computed on a worker
    QThread, so a blind sleep is both slower and flakier than pumping the loop.
    """
    loop = QEventLoop()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if until() else None)
    deadline.start(timeout_ms)
    poll.start()
    while not until() and deadline.isActive():
        loop.exec()
    poll.stop()
    deadline.stop()
    return until()


# ------------------------------------------------------------------- 1, 2
def test_main_window_constructs_and_shows(win: MainWindow) -> None:
    assert win.isVisible()
    assert win.pipeline.instances == []
    assert win.dataset is None


def test_open_dataset_indexes_demo(win: MainWindow) -> None:
    win.explorer.open_dataset(str(DEMO))
    ds = win.explorer.dataset

    assert ds is not None
    assert len(ds) == _demo_image_count()
    assert ds.class_names, "data.yaml must yield a non-empty class map"
    # opening selects row 0, which populates the first preview row
    assert win.preview.populated_rows()


# ---------------------------------------------------------------------- 3
def test_instances_add_to_pipeline(win: MainWindow) -> None:
    win.pipeline.add(AugmentationInstance(family="speckle", label="speckle", instance_id="smoke-speckle"))
    win.pipeline.add(AugmentationInstance(family="shadow", label="shadow", instance_id="smoke-shadow"))

    assert [i.instance_id for i in win.pipeline.instances] == ["smoke-speckle", "smoke-shadow"]


# ---------------------------------------------------------------------- 4
def test_schedule_preview_populates_worker_cache(qapp: QApplication, win: MainWindow) -> None:
    win.explorer.open_dataset(str(DEMO))
    win.pipeline.add(AugmentationInstance(family="speckle", label="speckle", instance_id="smoke-speckle"))

    win._schedule_preview(invalidate=True)

    assert _spin(qapp, lambda: bool(win.worker._cache)), "preview worker cache stayed empty"
    win.worker.wait(5_000)


# ---------------------------------------------------------------------- 5
def test_add_row_leaves_existing_row_height_unchanged(win: MainWindow) -> None:
    first = win.preview.rows[0]
    target = 500
    assert ROW_MIN_HEIGHT < target < ROW_MAX_HEIGHT
    first.set_row_height(target)

    win.preview.add_row()

    # PreviewRow uses setFixedHeight, which sets both bounds; height() alone
    # would depend on when the layout ran.
    assert first.minimumHeight() == target
    assert first.maximumHeight() == target
    assert len(win.preview.rows) == 2


# ------------------------------------------------------------------- 6, 7
def test_encyclopedia_pages_present() -> None:
    pages = enc_mod._pages()

    assert len(pages) == 10, sorted(pages)
    assert "00_overview.md" in pages and "g_geometry.md" in pages


def test_bundled_presets_present() -> None:
    presets = bundled_presets()

    assert len(presets) == 6, [p.name for p in presets]
    assert all(p.instances for p in presets)


# ---------------------------------------------------------------------- 8
def test_generation_dialog_builds_config(win: MainWindow) -> None:
    win.explorer.open_dataset(str(DEMO))
    win.pipeline.add(AugmentationInstance(family="speckle", label="speckle", instance_id="smoke-speckle"))

    dlg = GenerationDialog(win, str(DEMO), win.pipeline, master_seed=1234)
    try:
        cfg = dlg._build_config()
    finally:
        dlg.close()

    assert isinstance(cfg, GenerationConfig)
    assert cfg.master_seed == 1234
    assert [s.instance.instance_id for s in cfg.specs] == ["smoke-speckle"]


# ---------------------------------------------------------------------- 9
def test_generation_config_export_is_utf8(win: MainWindow, tmp_path, monkeypatch) -> None:
    """The exported config is utf-8 and keeps non-ASCII text intact.

    Guards non-negotiable #5 at the one site that used to violate it.  The
    instance label and the output path both carry non-ASCII, because those are
    the two fields that actually reach the file: parameter descriptions are not
    serialized, and a Windows profile path (``C:\\Users\\Müller\\…``) is the
    likeliest real-world trigger.

    ``allow_unicode=True`` is what makes this load-bearing rather than latent —
    with it, a bare ``open(path, "w")`` raises ``UnicodeEncodeError`` wherever
    the platform default codec is not utf-8 (cp1252 on Windows).
    """
    label = "turn — slow ν"
    out_dir = tmp_path / "sortie_Müller"
    export = tmp_path / "generation_config.yaml"

    win.explorer.open_dataset(str(DEMO))
    win.pipeline.add(AugmentationInstance(family="speckle", label=label, instance_id="utf8-speckle"))

    class _StubFileDialog:
        @staticmethod
        def getSaveFileName(*_a, **_kw):
            return str(export), "YAML (*.yaml)"

    monkeypatch.setattr(gen_dlg_mod, "QFileDialog", _StubFileDialog)

    dlg = GenerationDialog(win, str(DEMO), win.pipeline, master_seed=1234)
    try:
        dlg.out_path.setText(str(out_dir))
        dlg._export_yaml()
    finally:
        dlg.close()

    # 1. decodes as utf-8, with the non-ASCII text written literally
    raw = export.read_bytes()
    text = raw.decode("utf-8")
    assert "—" in text and "ν" in text
    assert "Müller" in text

    # 2. no \uXXXX escaping fell back in
    assert "\\u" not in text

    # 3. round-trips through the same load path generation/cli.py uses
    cfg = GenerationConfig(**yaml.safe_load(export.read_text(encoding="utf-8")))
    assert [s.instance.label for s in cfg.specs] == [label]
    assert cfg.output_path == str(out_dir)
