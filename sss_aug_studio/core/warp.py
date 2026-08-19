"""Geometric warps with exact label propagation.

Every geometric augmentation expresses its model twice, analytically:

* an **inverse map** ``(map_x, map_y)`` — for each output pixel, the input
  coordinate to sample (consumed by ``cv2.remap``), and
* a **forward displacement** field ``(fwd_dx, fwd_dy)`` — where each input
  pixel lands in the output (consumed by the label transformer).

Both are stored in a single :class:`FieldWarp`, guaranteeing that YOLO boxes
travel through *exactly* the same physical model as the pixels (label policy,
design §5).  Warps are strength-scalable: displacements are multiplied by the
instance's global ``strength`` before use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

__all__ = ["FieldWarp", "row_remap_warp", "identity_grid"]


def identity_grid(h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return gx, gy


@dataclass
class FieldWarp:
    """Bidirectional dense warp.

    ``map_x/map_y``: input coords sampled for each output pixel (H, W) float32.
    ``fwd_dx/fwd_dy``: output-minus-input displacement of each *input* pixel.
    """

    map_x: np.ndarray
    map_y: np.ndarray
    fwd_dx: np.ndarray
    fwd_dy: np.ndarray
    border_value: float = 0.0

    def scaled(self, strength: float) -> "FieldWarp":
        """Scale all displacements by ``strength`` (1.0 = model as parameterized)."""
        if strength == 1.0:
            return self
        s = float(strength)
        gx, gy = identity_grid(*self.map_x.shape)
        return FieldWarp(
            map_x=gx + s * (self.map_x - gx),
            map_y=gy + s * (self.map_y - gy),
            fwd_dx=self.fwd_dx * s,
            fwd_dy=self.fwd_dy * s,
            border_value=self.border_value,
        )

    def apply_image(self, data: np.ndarray) -> np.ndarray:
        return cv2.remap(
            data,
            self.map_x,
            self.map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=self.border_value,
        )

    def forward_points(self, pts: np.ndarray) -> np.ndarray:
        """Map (N, 2) input-pixel points ``(x, y)`` to output coordinates.

        Bilinear sampling of the forward displacement field; points are
        clipped to the field domain before sampling.
        """
        h, w = self.fwd_dx.shape
        x = np.clip(pts[:, 0], 0, w - 1.001)
        y = np.clip(pts[:, 1], 0, h - 1.001)
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = (x - x0)[:, None], (y - y0)[:, None]
        x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)

        def bilerp(f: np.ndarray) -> np.ndarray:
            v00, v01 = f[y0, x0][:, None], f[y0, x1][:, None]
            v10, v11 = f[y1, x0][:, None], f[y1, x1][:, None]
            return (v00 * (1 - fx) + v01 * fx) * (1 - fy) + (v10 * (1 - fx) + v11 * fx) * fy

        dx = bilerp(self.fwd_dx)[:, 0]
        dy = bilerp(self.fwd_dy)[:, 0]
        return np.stack([pts[:, 0] + dx, pts[:, 1] + dy], axis=1)

    @staticmethod
    def compose(first: Optional["FieldWarp"], second: Optional["FieldWarp"]) -> Optional["FieldWarp"]:
        """Compose two warps (``first`` applied to the image before ``second``)."""
        if first is None:
            return second
        if second is None:
            return first
        # inverse: sample first's maps at second's sample locations
        map_x = cv2.remap(first.map_x, second.map_x, second.map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        map_y = cv2.remap(first.map_y, second.map_x, second.map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        # forward: displace by first, then sample second's forward field at the moved location
        h, w = first.fwd_dx.shape
        gx, gy = identity_grid(h, w)
        mid_x, mid_y = gx + first.fwd_dx, gy + first.fwd_dy
        pts = np.stack([mid_x.ravel(), mid_y.ravel()], axis=1)
        out = second.forward_points(pts)
        fwd_dx = out[:, 0].reshape(h, w) - gx
        fwd_dy = out[:, 1].reshape(h, w) - gy
        return FieldWarp(map_x, map_y, fwd_dx.astype(np.float32), fwd_dy.astype(np.float32), second.border_value)


def row_remap_warp(out_to_in_row: np.ndarray, h: int, w: int, border_value: float = 0.0) -> FieldWarp:
    """Build a warp from a monotone row mapping ``in_row = f(out_row)``.

    Used by along-track resampling (speed variation, removed pings).  The
    forward mapping is obtained by numerical inversion of the monotone map.
    """
    out_to_in_row = out_to_in_row.astype(np.float32)
    h_out = len(out_to_in_row)
    gx, _ = identity_grid(h_out, w)
    map_y = np.repeat(out_to_in_row[:, None], w, axis=1)
    # forward: in_row -> out_row by inverting the monotone sequence
    in_rows = np.arange(h, dtype=np.float32)
    fwd_rows = np.interp(in_rows, out_to_in_row, np.arange(len(out_to_in_row), dtype=np.float32))
    fwd_dy = np.repeat((fwd_rows - in_rows)[:, None], w, axis=1)
    zeros = np.zeros((h, w), dtype=np.float32)
    return FieldWarp(map_x=gx, map_y=map_y, fwd_dx=zeros, fwd_dy=fwd_dy.astype(np.float32), border_value=border_value)
