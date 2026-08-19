"""Image conversion helpers for the Qt GUI (display-only; colormaps never
enter the processing pipeline — SSS data is single-channel intensity)."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap

__all__ = ["to_pixmap", "apply_sonar_colormap", "difference_map"]

# Classic amber sonar palette (display only)
_LUT = None


def _sonar_lut() -> np.ndarray:
    global _LUT
    if _LUT is None:
        x = np.linspace(0, 1, 256)
        r = np.clip(x * 2.0, 0, 1)
        g = np.clip(x * 1.25 - 0.10, 0, 1) * 0.75
        b = np.clip(x * 1.6 - 1.0, 0, 1) * 0.5
        _LUT = (np.stack([b, g, r], axis=1) * 255).astype(np.uint8)  # BGR
    return _LUT


def apply_sonar_colormap(gray_u8: np.ndarray) -> np.ndarray:
    lut = _sonar_lut()
    return lut[gray_u8]


def to_pixmap(img: np.ndarray, colormap: bool = True) -> QPixmap:
    """float [0,1] or uint8 grayscale -> QPixmap (optionally amber-mapped)."""
    if img.dtype != np.uint8:
        img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    if colormap:
        bgr = apply_sonar_colormap(img)
        rgb = np.ascontiguousarray(bgr[:, :, ::-1])
        qimg = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888)
    else:
        img = np.ascontiguousarray(img)
        qimg = QImage(img.data, img.shape[1], img.shape[0], img.strides[0], QImage.Format.Format_Grayscale8)
    return QPixmap.fromImage(qimg.copy())


def difference_map(original: np.ndarray, augmented: np.ndarray) -> np.ndarray:
    """Signed difference rendered as a diverging color image (BGR uint8)."""
    h = min(original.shape[0], augmented.shape[0])
    w = min(original.shape[1], augmented.shape[1])
    d = augmented[:h, :w].astype(np.float32) - original[:h, :w].astype(np.float32)
    scale = max(float(np.abs(d).max()), 1e-6)
    u8 = ((d / scale) * 127 + 128).astype(np.uint8)
    return cv2.applyColorMap(u8, cv2.COLORMAP_COOL)
