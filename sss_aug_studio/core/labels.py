"""YOLO label handling with exact warp propagation.

Dataset convention (``AcquisitionMeta.shadow_included``, default true):
every YOLO box encloses the
**complete object signature — highlight *and* acoustic shadow**.  Geometric
augmentations therefore warp the whole box through the same displacement
field as the pixels; the shadow-modulation family (F6) may additionally move
the down-range box edge when it rescales shadow length, keeping the
convention intact.

Boxes whose visible-area retention after warping and clipping falls below a
configurable threshold are dropped, and every drop is recorded in the label
provenance so generated datasets remain auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .warp import FieldWarp

__all__ = ["YoloBox", "LabelSet", "BoxProvenance"]


@dataclass
class YoloBox:
    """One normalized YOLO box (class, center-x, center-y, width, height)."""

    cls: int
    cx: float
    cy: float
    w: float
    h: float

    def to_pixels(self, img_w: int, img_h: int) -> tuple[float, float, float, float]:
        """Return (x0, y0, x1, y1) in pixel coordinates."""
        return (
            (self.cx - self.w / 2) * img_w,
            (self.cy - self.h / 2) * img_h,
            (self.cx + self.w / 2) * img_w,
            (self.cy + self.h / 2) * img_h,
        )

    @classmethod
    def from_pixels(cls, c: int, x0: float, y0: float, x1: float, y1: float, img_w: int, img_h: int) -> "YoloBox":
        return cls(c, (x0 + x1) / 2 / img_w, (y0 + y1) / 2 / img_h, (x1 - x0) / img_w, (y1 - y0) / img_h)


@dataclass
class BoxProvenance:
    """Audit record for one original box through the pipeline."""

    index: int
    kept: bool
    retention: float
    note: str = ""


@dataclass
class LabelSet:
    boxes: list[YoloBox] = field(default_factory=list)
    provenance: list[BoxProvenance] = field(default_factory=list)

    # ------------------------------------------------------------------ IO
    @classmethod
    def load(cls, path: str | Path) -> "LabelSet":
        p = Path(path)
        boxes: list[YoloBox] = []
        if p.exists():
            for line in p.read_text(encoding="utf-8").strip().splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    boxes.append(YoloBox(int(float(parts[0])), *map(float, parts[1:5])))
        return cls(boxes=boxes)

    def save(self, path: str | Path) -> None:
        lines = [f"{b.cls} {b.cx:.6f} {b.cy:.6f} {b.w:.6f} {b.h:.6f}" for b in self.boxes]
        Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def classes(self) -> set[int]:
        return {b.cls for b in self.boxes}

    # -------------------------------------------------------------- warping
    def warped(
        self,
        warp: Optional[FieldWarp],
        in_size: tuple[int, int],
        out_size: Optional[tuple[int, int]] = None,
        min_retention: float = 0.6,
    ) -> "LabelSet":
        """Propagate boxes through ``warp`` (label policy, design §5).

        Eight boundary points per box (corners + edge midpoints) are pushed
        through the forward displacement field; the axis-aligned hull is
        clipped to the output image.  ``retention`` = clipped area / warped
        hull area; boxes under ``min_retention`` (or degenerate) are dropped.
        """
        w_in, h_in = in_size
        w_out, h_out = out_size or in_size
        if warp is None and (w_out, h_out) == (w_in, h_in):
            return LabelSet(
                boxes=list(self.boxes),
                provenance=[BoxProvenance(i, True, 1.0) for i in range(len(self.boxes))],
            )
        out_boxes: list[YoloBox] = []
        prov: list[BoxProvenance] = []
        for i, b in enumerate(self.boxes):
            x0, y0, x1, y1 = b.to_pixels(w_in, h_in)
            xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
            pts = np.array(
                [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [xm, y0], [xm, y1], [x0, ym], [x1, ym]],
                dtype=np.float32,
            )
            if warp is not None:
                pts = warp.forward_points(pts)
            nx0, ny0 = float(pts[:, 0].min()), float(pts[:, 1].min())
            nx1, ny1 = float(pts[:, 0].max()), float(pts[:, 1].max())
            hull_area = max(nx1 - nx0, 1e-6) * max(ny1 - ny0, 1e-6)
            cx0, cy0 = max(nx0, 0.0), max(ny0, 0.0)
            cx1, cy1 = min(nx1, float(w_out)), min(ny1, float(h_out))
            clip_area = max(cx1 - cx0, 0.0) * max(cy1 - cy0, 0.0)
            retention = clip_area / hull_area
            if retention < min_retention or clip_area < 4.0:
                prov.append(BoxProvenance(i, False, retention, "dropped: low retention"))
                continue
            out_boxes.append(YoloBox.from_pixels(b.cls, cx0, cy0, cx1, cy1, w_out, h_out))
            prov.append(BoxProvenance(i, True, retention))
        return LabelSet(boxes=out_boxes, provenance=prov)
