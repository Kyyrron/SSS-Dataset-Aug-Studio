"""Dataset Generation dialog (Area 5).

Configures and runs the batch engine: output folder, master seed, copies per
image, combination policy, export mapping.  Per-parameter stochastic laws
are **not edited here** since v0.3.0 — they belong to each augmentation
instance (Augmentation Parameters form) and are shown here as a read-only
summary.  Runs in a worker thread with progress bar, ETA and cancel; the
full configuration can be exported as YAML for headless/CI reproduction via
``sss-aug-generate``.
"""

from __future__ import annotations

import json
from typing import Optional

import yaml
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from ..core.pipeline import AugmentationPipeline
from ..generation.engine import GenerationConfig, GenerationEngine, InstanceGenSpec

__all__ = ["GenerationDialog"]

class _Worker(QThread):
    progressed = Signal(int, int, float)
    finished_stats = Signal(object)
    failed = Signal(str)

    def __init__(self, config: GenerationConfig):
        super().__init__()
        self.config = config
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            stats = GenerationEngine(self.config).run(
                progress=lambda d, t, e: self.progressed.emit(d, t, e),
                cancel=lambda: self._cancel,
            )
            self.finished_stats.emit(stats)
        except Exception as exc:  # surface engine failures to the UI
            self.failed.emit(str(exc))


class GenerationDialog(QDialog):
    def __init__(self, parent, dataset_path: str, pipeline: AugmentationPipeline, master_seed: int):
        super().__init__(parent)
        self.setWindowTitle("Generate augmented dataset")
        self.resize(900, 680)
        self._pipeline = pipeline
        self._worker: Optional[_Worker] = None

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.in_path = QLineEdit(dataset_path)
        self.in_path.setReadOnly(True)
        form.addRow("Input dataset", self.in_path)
        out_row = QHBoxLayout()
        self.out_path = QLineEdit(dataset_path.rstrip("/\\") + "_augmented")
        btn_browse = QPushButton("…")
        btn_browse.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_path, 1)
        out_row.addWidget(btn_browse)
        form.addRow("Output folder", out_row)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2**31 - 1)
        self.seed.setValue(master_seed)
        self.seed.setToolTip("Master seed — the same seed reproduces the identical dataset byte-for-byte.")
        form.addRow("Master seed", self.seed)
        self.copies = QSpinBox()
        self.copies.setRange(1, 20)
        self.copies.setValue(2)
        form.addRow("Augmented copies per image", self.copies)
        self.combine = QCheckBox("allow multiple augmentations per copy (per-instance probabilities apply)")
        self.combine.setChecked(True)
        form.addRow("Combination", self.combine)
        self.mapping = QComboBox()
        self.mapping.addItems(["auto", "linear", "gamma", "log"])
        self.mapping.setToolTip("Output intensity mapping at export; 'auto' re-applies the declared input mapping.")
        form.addRow("Export intensity mapping", self.mapping)
        self.workers = QSpinBox()
        self.workers.setRange(0, 64)
        self.workers.setValue(0)
        self.workers.setToolTip("0 = auto (CPU count - 1). Reproducibility is worker-count independent.")
        form.addRow("Worker processes", self.workers)
        lay.addLayout(form)

        lay.addWidget(QLabel("<b>Stochastic laws</b> (read-only — edit them per parameter in the "
                             "Augmentation Parameters form)"))
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        lay.addWidget(self.summary, 1)
        self._fill_summary()

        self.progress = QProgressBar()
        self.eta = QLabel("")
        prow = QHBoxLayout()
        prow.addWidget(self.progress, 1)
        prow.addWidget(self.eta)
        lay.addLayout(prow)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        lay.addWidget(self.log)

        btns = QHBoxLayout()
        self.btn_export = QPushButton("Export config YAML")
        self.btn_export.clicked.connect(self._export_yaml)
        self.btn_run = QPushButton("Generate")
        self.btn_run.clicked.connect(self._run)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        btns.addWidget(self.btn_export)
        btns.addStretch()
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_run)
        lay.addLayout(btns)

    # ------------------------------------------------------ stochastic summary
    def _fill_summary(self) -> None:
        lines: list[str] = []
        for inst in self._pipeline.instances:
            if not inst.enabled:
                continue
            for pname, spec in (inst.distributions or {}).items():
                kind = spec.get("dist", "?")
                if kind == "normal":
                    args = f"mean={spec.get('mean')}, std={spec.get('std')}"
                else:
                    args = f"low={spec.get('low')}, high={spec.get('high')}"
                lines.append(f"{inst.family}:{inst.label}  ·  {pname}  ~  {kind}({args})")
        if lines:
            self.summary.setPlainText("\n".join(lines))
        else:
            self.summary.setPlainText(
                "No stochastic laws declared — every parameter is fixed (deterministic generation).\n"
                "To make a parameter stochastic, select it in the Augmentation Parameters form and "
                "choose a law (uniform / normal / loguniform) on its row."
            )

    def _build_config(self) -> GenerationConfig:
        specs = [
            InstanceGenSpec(
                instance=inst.model_copy(deep=True),
                param_distributions=dict(inst.distributions or {}),
            )
            for inst in self._pipeline.instances
            if inst.enabled
        ]
        return GenerationConfig(
            dataset_path=self.in_path.text(),
            output_path=self.out_path.text(),
            master_seed=self.seed.value(),
            copies_per_image=self.copies.value(),
            specs=specs,
            allow_combination=self.combine.isChecked(),
            export_mapping=self.mapping.currentText(),
            workers=self.workers.value(),
        )

    # ---------------------------------------------------------------- run
    def _browse_out(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if path:
            self.out_path.setText(path)

    def _export_yaml(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export generation config", "generation_config.yaml", "YAML (*.yaml)")
        if path:
            cfg = self._build_config()
            with open(path, "w") as fh:
                yaml.safe_dump(json.loads(cfg.model_dump_json()), fh, sort_keys=False)
            self.log.append(f"Config exported: {path} — reproduce with:  sss-aug-generate {path}")

    def _run(self) -> None:
        cfg = self._build_config()
        self._worker = _Worker(cfg)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finished_stats.connect(self._on_done)
        self._worker.failed.connect(lambda msg: self.log.append(f"ERROR: {msg}"))
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.log.append("Generation started…")
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.log.append("Cancelling…")

    def _on_progress(self, done: int, total: int, elapsed: float) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        self.eta.setText(f"ETA {eta:5.0f} s")

    def _on_done(self, stats) -> None:
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.log.append(
            f"Done: {stats.augmented} augmented copies from {stats.images_in} originals; "
            f"boxes {stats.boxes_in} -> {stats.boxes_out} ({stats.boxes_dropped} dropped); "
            f"{stats.elapsed_s:.1f} s. Manifest + statistics.md written."
        )
