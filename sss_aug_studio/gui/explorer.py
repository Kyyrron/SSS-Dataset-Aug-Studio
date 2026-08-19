"""Dataset Explorer dock (Area 1)."""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..datasets.yolo import YoloDataset

__all__ = ["ExplorerPanel"]


class ExplorerPanel(QWidget):
    dataset_opened = Signal(object)   # YoloDataset
    item_selected = Signal(int)       # index into dataset.items

    def __init__(self):
        super().__init__()
        self.dataset: Optional[YoloDataset] = None
        self._rng = np.random.default_rng()
        lay = QVBoxLayout(self)

        self.btn_open = QPushButton("Open YOLO dataset…")
        self.btn_open.clicked.connect(self._open_dialog)
        lay.addWidget(self.btn_open)

        row = QHBoxLayout()
        row.addWidget(QLabel("Class:"))
        self.class_filter = QComboBox()
        self.class_filter.addItem("all", None)
        self.class_filter.currentIndexChanged.connect(lambda _: self._refill())
        row.addWidget(self.class_filter, 1)
        lay.addLayout(row)

        self.listw = QListWidget()
        self.listw.currentRowChanged.connect(self._row_changed)
        # re-clicking the already-selected image must still assign it to a
        # (possibly newly added) preview row
        self.listw.itemClicked.connect(lambda it: self._row_changed(self.listw.row(it)))
        lay.addWidget(self.listw, 1)

        nav = QHBoxLayout()
        for text, slot in (("◀ Prev", self.prev), ("Random", self.random), ("Next ▶", self.next)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            nav.addWidget(b)
        lay.addLayout(nav)

        lay.addWidget(QLabel("<b>Image metadata</b>"))
        self.meta_table = QTableWidget(0, 2)
        self.meta_table.setHorizontalHeaderLabels(["field", "value"])
        self.meta_table.horizontalHeader().setStretchLastSection(True)
        self.meta_table.verticalHeader().setVisible(False)
        self.meta_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.meta_table, 1)

    # -------------------------------------------------------------- dataset
    def _open_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select YOLO dataset root")
        if path:
            self.open_dataset(path)

    def open_dataset(self, path: str) -> None:
        self.dataset = YoloDataset(path)
        self.class_filter.blockSignals(True)
        self.class_filter.clear()
        self.class_filter.addItem("all", None)
        for cid in sorted({c for it in self.dataset.items for c in it.classes}):
            self.class_filter.addItem(f"{cid}: {self.dataset.class_name(cid)}", cid)
        self.class_filter.blockSignals(False)
        self._refill()
        self.dataset_opened.emit(self.dataset)
        if self.listw.count():
            self.listw.setCurrentRow(0)

    def _refill(self) -> None:
        self.listw.clear()
        if not self.dataset:
            return
        cls = self.class_filter.currentData()
        for idx in self.dataset.filter_by_class(cls):
            it = self.dataset.items[idx]
            item = QListWidgetItem(f"{it.rel_key}   [{len(it.classes)} cls]")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.listw.addItem(item)

    # ----------------------------------------------------------- navigation
    def _row_changed(self, row: int) -> None:
        if row < 0 or not self.dataset:
            return
        idx = self.listw.item(row).data(Qt.ItemDataRole.UserRole)
        self._show_meta(idx)
        self.item_selected.emit(idx)

    def next(self) -> None:
        if self.listw.count():
            self.listw.setCurrentRow((self.listw.currentRow() + 1) % self.listw.count())

    def prev(self) -> None:
        if self.listw.count():
            self.listw.setCurrentRow((self.listw.currentRow() - 1) % self.listw.count())

    def random(self) -> None:
        if self.listw.count():
            self.listw.setCurrentRow(int(self._rng.integers(0, self.listw.count())))

    # -------------------------------------------------------------- metadata
    def _show_meta(self, idx: int) -> None:
        assert self.dataset is not None
        item = self.dataset.items[idx]
        meta = self.dataset.meta_for(item)
        rows: list[tuple[str, str]] = [
            ("file", item.rel_key),
            ("split", item.split),
            ("layout", meta.layout),
            ("physical units", "yes" if meta.is_physical else "no (normalized fallback)"),
        ]
        for f in ("altitude_m", "slant_range_m", "res_across_m", "res_along_m", "speed_mps", "heading_deg", "depth_m", "frequency_khz", "timestamp"):
            v = getattr(meta, f)
            if v is not None:
                rows.append((f, str(v)))
        self.meta_table.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.meta_table.setItem(r, 0, QTableWidgetItem(k))
            self.meta_table.setItem(r, 1, QTableWidgetItem(v))
