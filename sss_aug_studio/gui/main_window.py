"""Main window: dockable professional layout (CloudCompare/QGC idiom).

Session state lives here: the open dataset, current item, the pipeline, the
master seed and the selected instance.  Preview recomputation runs in a
worker thread, debounced at 150 ms, with a per-stage cache: only stages at or
after the first changed instance are recomputed (design §7).
"""

from __future__ import annotations

from typing import Optional

import threading

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QToolBar,
)

from .. import __version__
from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..core.pipeline import AugmentationPipeline
from ..datasets.yolo import YoloDataset
from ..profiles.store import PipelineProfile, bundled_presets, load_profile, save_profile
from .encyclopedia import EncyclopediaDialog
from .explorer import ExplorerPanel
from .generation_dialog import GenerationDialog
from .library import LibraryPanel
from .params_form import ParamsForm
from .preview import PreviewArea

__all__ = ["MainWindow"]


class _ProfileSaveDialog(QDialog):
    """Name / description when saving a profile.  Since v0.3.0 there is no
    execution-mode choice: stochastic laws live on the instances, so the
    profile's nature is derived from what it contains."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Save profile")
        form = QFormLayout(self)
        self.name = QLineEdit("custom")
        self.desc = QLineEdit("")
        form.addRow("Name", self.name)
        form.addRow("Description", self.desc)
        hint = QLabel("Stochastic laws (if any) are saved with their augmentation instances —\n"
                      "configure them per parameter in the Augmentation Parameters form.")
        hint.setStyleSheet("color:#a5b0ba;")
        form.addRow(hint)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def values(self) -> tuple[str, str]:
        return self.name.text().strip(), self.desc.text().strip()


class _PreviewWorker(QThread):
    """Applies the pipeline off the GUI thread, one job slot per preview row,
    with per-stage caching (keys start with the image key, so rows cache
    independently)."""

    computed = Signal(str, object, object)  # row_id, SonarImage, LabelSet

    def __init__(self):
        super().__init__()
        self._jobs: dict[str, tuple] = {}   # row_id -> latest job for that row
        self._lock = threading.Lock()
        self._cache: dict[str, tuple] = {}  # cumulative hash -> (image, labels)

    def submit(self, row_id: str, img: SonarImage, labels: LabelSet, pipeline_snapshot: list, seed: int, key: str) -> None:
        with self._lock:
            self._jobs[row_id] = (img, labels, pipeline_snapshot, seed, key)
        if not self.isRunning():
            self.start()

    def invalidate(self) -> None:
        self._cache.clear()

    def run(self) -> None:
        while True:
            with self._lock:
                if not self._jobs:
                    return
                row_id, job = self._jobs.popitem()
            img, labels, snapshot, seed, key = job
            from ..core.pipeline import AugmentationInstance, AugmentationPipeline

            instances = [AugmentationInstance(**d) for d in snapshot]
            cur_img, cur_labels = img, labels
            cum = key
            start_idx = 0
            # longest cached prefix
            for i, inst in enumerate(instances):
                cum = cum + "|" + inst.config_hash()
                if cum in self._cache:
                    cur_img, cur_labels = self._cache[cum]
                    start_idx = i + 1
                else:
                    break
            cum = key
            for i, inst in enumerate(instances):
                cum = cum + "|" + inst.config_hash()
                if i < start_idx:
                    continue
                sub = AugmentationPipeline([inst])
                res = sub.apply(cur_img, cur_labels, seed, key)
                cur_img, cur_labels = res.image, res.labels
                self._cache[cum] = (cur_img, cur_labels)
            if len(self._cache) > 128:
                self._cache.clear()
            self.computed.emit(row_id, cur_img, cur_labels)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Physics-Informed SSS Augmentation Studio — v{__version__}")
        self.resize(1500, 940)

        self.pipeline = AugmentationPipeline()
        self.dataset: Optional[YoloDataset] = None

        # central preview
        self.preview = PreviewArea()
        self.setCentralWidget(self.preview)
        self.preview.strip.set_pipeline(self.pipeline)
        self.preview.strip.order_changed.connect(self._order_changed)
        self.preview.strip.instance_selected.connect(self._select_instance)
        self.preview.strip.btn_physical.clicked.connect(self._physical_order)

        # docks
        self.explorer = ExplorerPanel()
        self._dock("Dataset Explorer", self.explorer, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.library = LibraryPanel()
        self.library.set_pipeline(self.pipeline)
        self._dock("Augmentation Library", self.library, Qt.DockWidgetArea.RightDockWidgetArea)
        self.params = ParamsForm(self._params_changed)
        self._dock("Augmentation Parameters", self.params, Qt.DockWidgetArea.BottomDockWidgetArea)

        self.explorer.item_selected.connect(self._load_item)
        self.library.pipeline_changed.connect(self._pipeline_changed)
        self.library.instance_added.connect(self._select_instance)
        self.library.open_doc.connect(self._open_encyclopedia)

        # toolbar: seed
        tb = QToolBar("Session")
        self.addToolBar(tb)
        tb.addWidget(QLabel(" Master seed: "))
        self.seed = QSpinBox()
        self.seed.setRange(0, 2**31 - 1)
        self.seed.setValue(42)
        self.seed.setToolTip("Deterministic master seed for previews and generation.")
        self.seed.valueChanged.connect(lambda _: self._schedule_preview(invalidate=True))
        tb.addWidget(self.seed)

        # worker + debounce
        self.worker = _PreviewWorker()
        self.worker.computed.connect(self._preview_ready)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._compute_preview)

        self._build_menu()
        self.status = QLabel("Open a YOLO dataset to begin.")
        self.statusBar().addWidget(self.status, 1)

    # ----------------------------------------------------------------- UI
    def _dock(self, title: str, widget, area) -> None:
        d = QDockWidget(title, self)
        d.setWidget(widget)
        d.setObjectName(title)
        self.addDockWidget(area, d)

    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&File")
        m_file.addAction("Open dataset…", self.explorer._open_dialog)
        m_file.addSeparator()
        m_file.addAction("Quit", self.close)

        m_prof = self.menuBar().addMenu("&Profiles")
        presets = m_prof.addMenu("Load preset")
        for prof in bundled_presets():
            presets.addAction(prof.name, lambda p=prof: self._load_profile(p))
        m_prof.addAction("Load from file…", self._load_profile_file)
        m_prof.addAction("Save current as…", self._save_profile_file)

        m_gen = self.menuBar().addMenu("&Generate")
        m_gen.addAction("Generate augmented dataset…", self._open_generation)

        m_help = self.menuBar().addMenu("&Help")
        m_help.addAction("Scientific encyclopedia", lambda: self._open_encyclopedia(None))
        m_help.addAction(
            "About",
            lambda: QMessageBox.information(
                self,
                "About",
                f"Physics-Informed SSS Augmentation Studio v{__version__}\n"
                "Every augmentation corresponds to a physical phenomenon of real\n"
                "side-scan sonar acquisition; see Help > Scientific encyclopedia.",
            ),
        )

    # ------------------------------------------------------------- session
    def _load_item(self, idx: int) -> None:
        """Assign the clicked Explorer image to the selected preview row."""
        assert self.explorer.dataset is not None
        self.dataset = self.explorer.dataset
        item = self.dataset.items[idx]
        try:
            img = self.dataset.load_image(item)
        except FileNotFoundError as exc:
            self.status.setText(str(exc))
            return
        labels = item.load_labels()
        row = self.preview.assign_to_selected(idx, item.rel_key, img, labels)
        self.status.setText(
            f"{item.rel_key} → preview {row.row_id if row else '?'} — {img.width}x{img.height}, "
            f"layout={img.meta.layout}, "
            f"{'physical units' if img.meta.is_physical else 'normalized fallback'}"
        )
        self._schedule_preview()

    def _select_instance(self, instance_id: str) -> None:
        inst = next((i for i in self.pipeline.instances if i.instance_id == instance_id), None)
        self.params.set_instance(inst)

    def _params_changed(self) -> None:
        self.preview.strip.rebuild()
        self._schedule_preview()

    def _pipeline_changed(self) -> None:
        self.preview.strip.rebuild()
        self._schedule_preview()

    def _order_changed(self) -> None:
        order = self.preview.strip.current_order()
        by_id = {i.instance_id: i for i in self.pipeline.instances}
        self.pipeline.instances = [by_id[i] for i in order if i in by_id]
        self._schedule_preview()

    def _physical_order(self) -> None:
        self.pipeline.sort_physical()
        self.preview.strip.rebuild()
        self._schedule_preview()

    # ------------------------------------------------------------- preview
    def _schedule_preview(self, invalidate: bool = False) -> None:
        if invalidate:
            self.worker.invalidate()
        self._debounce.start()

    def _compute_preview(self) -> None:
        snapshot = [i.model_dump() for i in self.pipeline.instances]
        for row in self.preview.populated_rows():
            self.worker.submit(
                row.row_id, row.orig_img, row.orig_labels or LabelSet(), snapshot, self.seed.value(), row.image_key
            )

    def _preview_ready(self, row_id: str, image: SonarImage, labels: LabelSet) -> None:
        self.preview.set_row_result(row_id, image.data, labels)

    # ------------------------------------------------------------ profiles
    def _load_profile(self, profile: PipelineProfile) -> None:
        self.pipeline.instances = [i.model_copy(deep=True) for i in profile.instances]
        self.library.set_pipeline(self.pipeline)
        self.preview.strip.set_pipeline(self.pipeline)
        self.params.set_instance(None)
        kind = "stochastic" if profile.is_stochastic else "deterministic"
        self.status.setText(f"Profile loaded: {profile.name} [{kind}] — {profile.description.strip()}")
        self._schedule_preview(invalidate=True)

    def _load_profile_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load profile", "", "YAML (*.yaml *.yml)")
        if path:
            self._load_profile(load_profile(path))

    def _save_profile_file(self) -> None:
        dlg = _ProfileSaveDialog(self)
        if not dlg.exec():
            return
        name, desc = dlg.values()
        path, _ = QFileDialog.getSaveFileName(self, "Save profile", f"{name or 'profile'}.yaml", "YAML (*.yaml)")
        if path:
            prof = PipelineProfile.from_pipeline(name or "custom", desc, self.pipeline)
            save_profile(prof, path)
            kind = "stochastic" if prof.is_stochastic else "deterministic"
            self.status.setText(f"Profile saved [{kind}]: {path}")

    # ---------------------------------------------------------- generation
    def _open_generation(self) -> None:
        if self.dataset is None:
            QMessageBox.warning(self, "No dataset", "Open a YOLO dataset first.")
            return
        if not any(i.enabled for i in self.pipeline.instances):
            QMessageBox.warning(self, "Empty pipeline", "Add and enable at least one augmentation instance.")
            return
        GenerationDialog(self, str(self.dataset.root), self.pipeline, self.seed.value()).exec()

    def _open_encyclopedia(self, page: Optional[str]) -> None:
        EncyclopediaDialog(self, page).exec()
