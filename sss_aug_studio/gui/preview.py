"""Interactive preview area (Area 4), multi-row since v0.2.1.

A vertical stack of *preview rows*; each row shows one dataset image through
1-6 zoom-synchronized tiles (Original, Augmented, Difference map, Histogram,
Intensity profile, Before/After slider) — the tile count is shared by all
rows (columns).  Rows are selectable; the Dataset Explorer assigns its
clicked image to the selected row.  YOLO boxes are overlaid (green =
original labels, orange = warped labels).  The pipeline-order strip below
the rows is global: one pipeline, many images.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QScrollArea,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..core.labels import LabelSet
from ..core.pipeline import AugmentationPipeline
from .qt_images import difference_map, to_pixmap

TILE_MODES = ["Augmented", "Original", "Difference", "Before/After", "Histogram", "Intensity profile"]


class _SyncedView(QGraphicsView):
    """QGraphicsView with wheel zoom and cross-tile transform sync."""

    transformed = Signal(object)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setBackgroundBrush(QColor("#101418"))
        self._syncing = False

    def wheelEvent(self, ev) -> None:
        factor = 1.25 if ev.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)
        self.transformed.emit(self.transform())

    def apply_sync(self, transform) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.setTransform(transform)
        self._syncing = False


def _draw_boxes(scene: QGraphicsScene, labels: Optional[LabelSet], w: int, h: int, color: str) -> None:
    if not labels:
        return
    pen = QPen(QColor(color))
    pen.setWidthF(1.5)
    pen.setCosmetic(True)
    for b in labels.boxes:
        x0, y0, x1, y1 = b.to_pixels(w, h)
        scene.addRect(QRectF(x0, y0, x1 - x0, y1 - y0), pen)


class _HistogramWidget(QWidget):
    """64-bin intensity histogram, original vs augmented, log-count axis."""

    def __init__(self):
        super().__init__()
        self._orig: Optional[np.ndarray] = None
        self._aug: Optional[np.ndarray] = None
        self.setMinimumHeight(120)

    def set_data(self, orig: np.ndarray, aug: np.ndarray) -> None:
        self._orig, _ = np.histogram(orig, bins=64, range=(0, 1))
        self._aug, _ = np.histogram(aug, bins=64, range=(0, 1))
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101418"))
        if self._orig is None:
            return
        w, h = self.width(), self.height()
        for hist, color in ((self._orig, "#57d977"), (self._aug, "#ffab40")):
            vals = np.log1p(hist.astype(np.float64))
            vals = vals / max(vals.max(), 1e-9)
            pen = QPen(QColor(color))
            pen.setWidth(2)
            p.setPen(pen)
            poly = QPolygonF([QPointF(i / 63 * (w - 10) + 5, h - 5 - v * (h - 20)) for i, v in enumerate(vals)])
            p.drawPolyline(poly)
        p.setPen(QColor("#a5b0ba"))
        p.drawText(8, 14, "green = original   orange = augmented   (log counts)")


class _ProfileWidget(QWidget):
    """Across-track intensity profile of one row, original vs augmented."""

    def __init__(self):
        super().__init__()
        self._orig: Optional[np.ndarray] = None
        self._aug: Optional[np.ndarray] = None
        self._row_frac = 0.5
        self.setMinimumHeight(120)
        self.setToolTip("Click to select the row; across-track intensity profile.")

    def set_data(self, orig: np.ndarray, aug: np.ndarray) -> None:
        self._orig, self._aug = orig, aug
        self.update()

    def mousePressEvent(self, ev) -> None:
        self._row_frac = float(np.clip(ev.position().y() / max(self.height(), 1), 0, 1))
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101418"))
        if self._orig is None:
            return
        w, h = self.width(), self.height()
        for img, color in ((self._orig, "#57d977"), (self._aug, "#ffab40")):
            row = img[int(self._row_frac * (img.shape[0] - 1))]
            xs = np.linspace(5, w - 5, len(row))
            pen = QPen(QColor(color))
            pen.setWidthF(1.2)
            p.setPen(pen)
            poly = QPolygonF([QPointF(x, h - 5 - v * (h - 20)) for x, v in zip(xs, row)])
            p.drawPolyline(poly)
        p.setPen(QColor("#a5b0ba"))
        p.drawText(8, 14, f"row @ {self._row_frac:.0%} of image height (click to move)")


class _BeforeAfterWidget(QWidget):
    """Split before/after view with a draggable divider slider."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._canvas = _SplitCanvas()
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(50)
        self._slider.valueChanged.connect(self._canvas.set_split)
        lay.addWidget(self._canvas, 1)
        lay.addWidget(self._slider)

    def set_data(self, orig: np.ndarray, aug: np.ndarray) -> None:
        self._canvas.set_images(orig, aug)


class _SplitCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._pm_o = self._pm_a = None
        self._split = 50

    def set_images(self, orig: np.ndarray, aug: np.ndarray) -> None:
        self._pm_o, self._pm_a = to_pixmap(orig), to_pixmap(aug)
        self.update()

    def set_split(self, v: int) -> None:
        self._split = v
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101418"))
        if self._pm_o is None:
            return
        r = self.rect()
        for pm, left in ((self._pm_o, True), (self._pm_a, False)):
            scaled = pm.scaled(r.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = (r.width() - scaled.width()) // 2
            y = (r.height() - scaled.height()) // 2
            sx = x + int(scaled.width() * self._split / 100)
            p.save()
            if left:
                p.setClipRect(x, y, sx - x, scaled.height())
            else:
                p.setClipRect(sx, y, x + scaled.width() - sx, scaled.height())
            p.drawPixmap(x, y, scaled)
            p.restore()
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.drawText(10, 20, "original")
        p.drawText(self.width() - 80, 20, "augmented")


class PreviewTile(QWidget):
    """One preview tile: mode selector + content."""

    def __init__(self, sync_cb: Callable[[object], None]):
        super().__init__()
        self._sync_cb = sync_cb
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        self.mode = QComboBox()
        self.mode.addItems(TILE_MODES)
        lay.addWidget(self.mode)
        self.view = _SyncedView()
        self.view.transformed.connect(self._sync_cb)
        self.hist = _HistogramWidget()
        self.profile = _ProfileWidget()
        self.split = _BeforeAfterWidget()
        for w in (self.view, self.hist, self.profile, self.split):
            lay.addWidget(w, 1)
        self.mode.currentTextChanged.connect(lambda _: self.refresh())
        self._data: Optional[tuple] = None
        self._fit_pending = False
        self.refresh()

    def set_data(
        self, orig: np.ndarray, aug: np.ndarray, labels_o: LabelSet, labels_a: LabelSet, fit: bool = False
    ) -> None:
        prev_shape = self._data[0].shape if self._data else None
        self._data = (orig, aug, labels_o, labels_a)
        if fit or prev_shape != orig.shape:
            self._fit_pending = True
        self.refresh()

    def refresh(self) -> None:
        mode = self.mode.currentText()
        self.view.setVisible(mode in ("Original", "Augmented", "Difference"))
        self.hist.setVisible(mode == "Histogram")
        self.profile.setVisible(mode == "Intensity profile")
        self.split.setVisible(mode == "Before/After")
        if self._data is None:
            return
        orig, aug, lo, la = self._data
        if mode in ("Original", "Augmented", "Difference"):
            scene = self.view.scene()
            scene.clear()
            if mode == "Original":
                pm = to_pixmap(orig)
                scene.addItem(QGraphicsPixmapItem(pm))
                _draw_boxes(scene, lo, orig.shape[1], orig.shape[0], "#57d977")
            elif mode == "Augmented":
                pm = to_pixmap(aug)
                scene.addItem(QGraphicsPixmapItem(pm))
                _draw_boxes(scene, la, aug.shape[1], aug.shape[0], "#ffab40")
            else:
                bgr = difference_map(orig, aug)
                rgb = np.ascontiguousarray(bgr[:, :, ::-1]).astype(np.float32) / 255.0
                # reuse to_pixmap grayscale path is wrong for color; build directly
                from PySide6.QtGui import QImage, QPixmap

                u8 = np.ascontiguousarray(bgr[:, :, ::-1])
                qi = QImage(u8.data, u8.shape[1], u8.shape[0], u8.strides[0], QImage.Format.Format_RGB888)
                scene.addItem(QGraphicsPixmapItem(QPixmap.fromImage(qi.copy())))
            scene.setSceneRect(scene.itemsBoundingRect())
            if self._fit_pending:
                self.view.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
                self._fit_pending = False
        elif mode == "Histogram":
            self.hist.set_data(orig, aug)
        elif mode == "Intensity profile":
            self.profile.set_data(orig, aug)
        else:
            self.split.set_data(orig, aug)

    def sync(self, transform) -> None:
        self.view.apply_sync(transform)


class PipelineStrip(QWidget):
    """Horizontal, drag-reorderable list showing the application order."""

    order_changed = Signal()
    instance_selected = Signal(str)

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.addWidget(QLabel("Order:"))
        self.list = QListWidget()
        self.list.setFlow(QListWidget.Flow.LeftToRight)
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list.setMaximumHeight(46)
        self.list.model().rowsMoved.connect(lambda *a: self.order_changed.emit())
        self.list.itemClicked.connect(lambda it: self.instance_selected.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.list.itemChanged.connect(self._toggled)
        lay.addWidget(self.list, 1)
        self.btn_physical = QPushButton("Physical order")
        self.btn_physical.setToolTip("Sort instances into the physical causal chain (scene -> geometry -> radiometry -> speckle -> receiver).")
        lay.addWidget(self.btn_physical)
        self._pipeline: Optional[AugmentationPipeline] = None
        self._building = False

    def set_pipeline(self, pipeline: AugmentationPipeline) -> None:
        self._pipeline = pipeline
        self.rebuild()

    def rebuild(self) -> None:
        self._building = True
        self.list.clear()
        if self._pipeline:
            for inst in self._pipeline.instances:
                it = QListWidgetItem(f"{inst.family}:{inst.label}")
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if inst.enabled else Qt.CheckState.Unchecked)
                it.setData(Qt.ItemDataRole.UserRole, inst.instance_id)
                it.setToolTip(f"p={inst.probability:.2f}, strength={inst.strength:.2f} — drag to reorder")
                self.list.addItem(it)
        self._building = False

    def _toggled(self, item: QListWidgetItem) -> None:
        if self._building or not self._pipeline:
            return
        iid = item.data(Qt.ItemDataRole.UserRole)
        for inst in self._pipeline.instances:
            if inst.instance_id == iid:
                inst.enabled = item.checkState() == Qt.CheckState.Checked
        self.order_changed.emit()

    def current_order(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]


ROW_DEFAULT_HEIGHT = 340
ROW_MIN_HEIGHT, ROW_MAX_HEIGHT = 160, 1400


class _RowResizeGrip(QFrame):
    """Drag handle along a row's bottom edge; adjusts that row's height only."""

    def __init__(self, row: "PreviewRow"):
        super().__init__()
        self._row = row
        self.setFixedHeight(7)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("Drag to resize this preview row")
        self.setStyleSheet("background: #2a333d; border-radius: 3px; margin: 0 40px;")
        self._start_y = 0.0
        self._start_h = 0

    def mousePressEvent(self, ev) -> None:
        self._start_y = ev.globalPosition().y()
        self._start_h = self._row.height()
        ev.accept()

    def mouseMoveEvent(self, ev) -> None:
        if ev.buttons() & Qt.MouseButton.LeftButton:
            dy = ev.globalPosition().y() - self._start_y
            self._row.set_row_height(int(self._start_h + dy))
            ev.accept()


class PreviewRow(QFrame):
    """One dataset image rendered through the shared tile columns.

    Owns its source state (dataset item index, image key, original image +
    labels) and its last computed result, so `MainWindow` needs no parallel
    per-row bookkeeping.
    """

    clicked = Signal(str)            # row_id
    remove_requested = Signal(str)   # row_id

    def __init__(self, row_id: str, n_tiles: int, sync_cb: Callable[[object], None] = None):
        super().__init__()
        self.row_id = row_id
        # v0.3.0: zoom/pan synchronization is scoped to THIS row (its tiles
        # show the same image); cross-row sync of differently-sized images
        # produced confusing offsets.
        self._sync_cb = self.sync
        self.setObjectName("previewRow")
        self.setFixedHeight(ROW_DEFAULT_HEIGHT)
        self.setProperty("selected", False)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        # source / result state
        self.item_idx: Optional[int] = None
        self.image_key: Optional[str] = None
        self.orig_img = None            # SonarImage
        self.orig_labels: Optional[LabelSet] = None
        self._last: Optional[tuple] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 4)
        head = QHBoxLayout()
        self.title = QLabel("<i>empty row — select an image in the Dataset Explorer</i>")
        self.title.setStyleSheet("color:#a5b0ba;")
        head.addWidget(self.title, 1)
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedWidth(24)
        self.btn_close.setToolTip("Remove this preview row")
        self.btn_close.clicked.connect(lambda: self.remove_requested.emit(self.row_id))
        head.addWidget(self.btn_close)
        lay.addLayout(head)

        self._tiles_host = QWidget()
        self._tiles_lay = QHBoxLayout(self._tiles_host)
        self._tiles_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._tiles_host, 1)
        lay.addWidget(_RowResizeGrip(self))
        self.tiles: list[PreviewTile] = []
        self.set_tile_count(n_tiles)

    def set_row_height(self, h: int) -> None:
        self.setFixedHeight(max(ROW_MIN_HEIGHT, min(ROW_MAX_HEIGHT, h)))

    # ------------------------------------------------------------ selection
    def mousePressEvent(self, ev) -> None:
        self.clicked.emit(self.row_id)
        super().mousePressEvent(ev)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    # ---------------------------------------------------------------- tiles
    def set_tile_count(self, n: int) -> None:
        for t in self.tiles:
            t.setParent(None)
            t.deleteLater()
        self.tiles = []
        for i in range(n):
            tile = PreviewTile(self._sync_cb)
            if i == 0 and n > 1:
                tile.mode.setCurrentText("Original")
            self._tiles_lay.addWidget(tile, 1)
            self.tiles.append(tile)
        if self._last:
            self.set_data(*self._last, fit=True)

    # ----------------------------------------------------------------- data
    def set_source(self, item_idx: int, image_key: str, orig_img, orig_labels: LabelSet) -> None:
        changed = image_key != self.image_key
        self.item_idx = item_idx
        self.image_key = image_key
        self.orig_img = orig_img
        self.orig_labels = orig_labels
        self.title.setText(f"<b>{image_key}</b>")
        if changed:
            for t in self.tiles:
                t._fit_pending = True  # newly assigned image: fit-to-view once

    def set_data(
        self, orig: np.ndarray, aug: np.ndarray, labels_o: LabelSet, labels_a: LabelSet, fit: bool = False
    ) -> None:
        self._last = (orig, aug, labels_o, labels_a)
        for t in self.tiles:
            t.set_data(orig, aug, labels_o, labels_a, fit=fit)

    def sync(self, transform) -> None:
        for t in self.tiles:
            t.sync(transform)


class PreviewArea(QWidget):
    """Area 4: shared tile-count selector + selectable preview rows + order strip."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Tiles:"))
        self.count = QComboBox()
        self.count.addItems([str(i) for i in range(1, 7)])
        self.count.setCurrentText("2")
        self.count.setToolTip("Number of tiles per row (shared by all rows).")
        self.count.currentTextChanged.connect(self._tile_count_changed)
        top.addWidget(self.count)
        self.btn_add_row = QPushButton("＋ Add row")
        self.btn_add_row.setToolTip("Add a preview row; assign an image to it by clicking one in the Dataset Explorer.")
        self.btn_add_row.clicked.connect(lambda: self.add_row())
        top.addWidget(self.btn_add_row)
        top.addStretch()
        lay.addLayout(top)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._rows_host = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.addStretch()
        self._scroll.setWidget(self._rows_host)
        lay.addWidget(self._scroll, 1)

        self.strip = PipelineStrip()
        lay.addWidget(self.strip)

        self.rows: list[PreviewRow] = []
        self.selected_row_id: Optional[str] = None
        self._row_counter = 0
        self.add_row()  # default: one row (two tiles)

    # ----------------------------------------------------------------- rows
    def add_row(self) -> "PreviewRow":
        self._row_counter += 1
        row = PreviewRow(f"row{self._row_counter}", int(self.count.currentText()))
        row.clicked.connect(self.select_row)
        row.remove_requested.connect(self.remove_row)
        self._rows_lay.insertWidget(self._rows_lay.count() - 1, row)
        self.rows.append(row)
        self.select_row(row.row_id)   # new row receives the next Explorer click
        self._update_close_buttons()
        return row

    def remove_row(self, row_id: str) -> None:
        if len(self.rows) <= 1:
            return
        row = self._row(row_id)
        if row is None:
            return
        self.rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        if self.selected_row_id == row_id:
            self.select_row(self.rows[-1].row_id)
        self._update_close_buttons()

    def select_row(self, row_id: str) -> None:
        self.selected_row_id = row_id
        for r in self.rows:
            r.set_selected(r.row_id == row_id)

    def selected_row(self) -> Optional["PreviewRow"]:
        return self._row(self.selected_row_id) if self.selected_row_id else None

    def _row(self, row_id: Optional[str]) -> Optional["PreviewRow"]:
        return next((r for r in self.rows if r.row_id == row_id), None)

    def _update_close_buttons(self) -> None:
        for r in self.rows:
            r.btn_close.setEnabled(len(self.rows) > 1)

    # ----------------------------------------------------------------- data
    def assign_to_selected(self, item_idx: int, image_key: str, orig_img, orig_labels: LabelSet) -> Optional["PreviewRow"]:
        row = self.selected_row() or (self.rows[0] if self.rows else None)
        if row is not None:
            row.set_source(item_idx, image_key, orig_img, orig_labels)
        return row

    def set_row_result(self, row_id: str, aug: np.ndarray, labels_a: LabelSet) -> None:
        row = self._row(row_id)
        if row is not None and row.orig_img is not None:
            row.set_data(row.orig_img.data, aug, row.orig_labels or LabelSet(), labels_a)

    def populated_rows(self) -> list["PreviewRow"]:
        return [r for r in self.rows if r.orig_img is not None]

    # -------------------------------------------------------------- helpers
    def _tile_count_changed(self, _text: str) -> None:
        n = int(self.count.currentText())
        for r in self.rows:
            r.set_tile_count(n)

