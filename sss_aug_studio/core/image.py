"""Sonar image container.

Conventions (frozen in the validated design):

* along-track = **rows** (row index increases with successive pings),
* across-track = **columns**,
* pixel values are ``float32`` in ``[0, 1]`` in the **linear intensity**
  domain — the native domain of multiplicative sonar physics.  8-bit inputs
  are exactly inverse-mapped on load according to the *declared*
  :attr:`AcquisitionMeta.intensity_mapping`; when no mapping is declared the
  documented default assumption is ``log`` (dB waterfall export).  dB-valued
  effects convert via ``10^(dB/10)``, so every computation runs in its
  physically appropriate domain.

Layouts: ``single_port``, ``single_starboard`` and the
primary ``dual`` layout (port | nadir | starboard).  :meth:`SonarImage.sides`
exposes each side with a canonical *range-increases-with-index* view so all
physics code is layout-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterator, Optional

import cv2
import numpy as np

from .meta import AcquisitionMeta

__all__ = ["SonarImage", "Side", "detect_nadir_band"]


def detect_nadir_band(data: np.ndarray, center_frac: float = 0.5) -> tuple[int, int]:
    """Auto-detect the dark nadir band of a dual-side waterfall.

    Searches the central 40 % of columns for the widest contiguous run whose
    column-mean intensity is below 45 % of the global mean.  Falls back to a
    2 %-wide band around ``center_frac`` when no dark run is found.
    """
    w = data.shape[1]
    col_mean = data.mean(axis=0)
    lo, hi = int(w * (center_frac - 0.20)), int(w * (center_frac + 0.20))
    lo, hi = max(lo, 0), min(hi, w)
    window = col_mean[lo:hi]
    thresh = 0.45 * float(col_mean.mean())
    dark = window < thresh
    best_len, best_start, run_start = 0, -1, -1
    for i, d in enumerate(np.append(dark, False)):
        if d and run_start < 0:
            run_start = i
        elif not d and run_start >= 0:
            if i - run_start > best_len:
                best_len, best_start = i - run_start, run_start
            run_start = -1
    if best_len >= max(2, w // 200):
        return lo + best_start, lo + best_start + best_len
    c = int(w * center_frac)
    half = max(1, int(0.01 * w))
    return c - half, c + half


@dataclass(frozen=True)
class Side:
    """One sonar side in canonical orientation.

    ``cols`` slices the parent image; ``flip`` is True when the stored column
    order must be reversed so that range increases with the canonical index
    (port side of a dual waterfall stores far range at column 0).
    """

    name: str  # "port" | "starboard"
    cols: slice
    flip: bool
    res_across_m: float
    physical: bool

    @property
    def width(self) -> int:
        return (self.cols.stop or 0) - (self.cols.start or 0)

    def range_m(self) -> np.ndarray:
        """Ground range (m) of each canonical column (0 at inner/nadir edge)."""
        return (np.arange(self.width, dtype=np.float64) + 0.5) * self.res_across_m

    def view(self, data: np.ndarray) -> np.ndarray:
        """Canonical (range-increasing) writable view of this side."""
        v = data[:, self.cols]
        return v[:, ::-1] if self.flip else v


@dataclass
class SonarImage:
    """Float32 linear-intensity waterfall image plus acquisition metadata."""

    data: np.ndarray
    meta: AcquisitionMeta
    path: Optional[Path] = None
    _nadir: Optional[tuple[int, int]] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.data.ndim == 3:  # collapse accidental color input
            self.data = cv2.cvtColor(self.data, cv2.COLOR_BGR2GRAY)
        self.data = np.clip(self.data.astype(np.float32, copy=False), 0.0, 1.0)

    # ------------------------------------------------------------------ IO
    @classmethod
    def load(cls, path: str | Path, meta: AcquisitionMeta) -> "SonarImage":
        raw = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if raw is None:
            raise FileNotFoundError(f"Cannot read image: {path}")
        v = raw.astype(np.float32) / 255.0
        lin = _inverse_display_mapping(v, meta)
        return cls(data=lin, meta=meta, path=Path(path))

    def to_display(self, mapping: str | None = None) -> np.ndarray:
        """Export the linear image as uint8 with the chosen display mapping.

        ``mapping`` in {"linear", "gamma", "log"}; defaults to the input
        mapping, so round-trips are approximately identity: the declared
        intensity mapping is inverted on load and re-applied on export.
        """
        if mapping in (None, "auto"):
            mapping = self.meta.intensity_mapping
        v = np.clip(self.data, 0.0, 1.0)
        if mapping == "gamma":
            v = v ** (1.0 / self.meta.gamma)
        elif mapping == "log":
            d = self.meta.log_range_db
            v = np.log10(1.0 + v * (10 ** (d / 10.0) - 1.0)) / (d / 10.0)
        return (v * 255.0 + 0.5).astype(np.uint8)

    # ------------------------------------------------------------- geometry
    @property
    def height(self) -> int:
        return int(self.data.shape[0])

    @property
    def width(self) -> int:
        return int(self.data.shape[1])

    def nadir_band(self) -> tuple[int, int]:
        """(col_start, col_stop) of the nadir band; (w, w)/(0, 0) edges for single layouts."""
        if self._nadir is not None:
            return self._nadir
        if self.meta.layout == "single_port":
            nb = (self.width, self.width)  # nadir at right edge; range increases leftward
        elif self.meta.layout == "single_starboard":
            nb = (0, 0)  # nadir at left edge; range increases rightward
        elif self.meta.nadir_halfwidth_frac is not None:
            c = self.meta.nadir_center_frac * self.width
            hw = self.meta.nadir_halfwidth_frac * self.width
            nb = (int(round(c - hw)), int(round(c + hw)))
        else:
            nb = detect_nadir_band(self.data, self.meta.nadir_center_frac)
        self._nadir = nb
        return nb

    def sides(self) -> Iterator[Side]:
        """Yield each sonar side in canonical (range-increasing) orientation."""
        n0, n1 = self.nadir_band()
        if self.meta.layout == "single_port":
            w = self.width
            yield Side("port", slice(0, w), flip=True, res_across_m=self.meta.resolved_res_across_m(w), physical=self.meta.is_physical)
        elif self.meta.layout == "single_starboard":
            w = self.width
            yield Side("starboard", slice(0, w), flip=False, res_across_m=self.meta.resolved_res_across_m(w), physical=self.meta.is_physical)
        else:
            if n0 > 0:
                yield Side("port", slice(0, n0), flip=True, res_across_m=self.meta.resolved_res_across_m(n0), physical=self.meta.is_physical)
            if n1 < self.width:
                yield Side("starboard", slice(n1, self.width), flip=False, res_across_m=self.meta.resolved_res_across_m(self.width - n1), physical=self.meta.is_physical)

    def range_map_m(self) -> np.ndarray:
        """Per-pixel ground range from nadir (m), full image width. Nadir band -> 0."""
        r = np.zeros(self.width, dtype=np.float32)
        for s in self.sides():
            rr = s.range_m().astype(np.float32)
            r[s.cols] = rr[::-1] if s.flip else rr
        return np.broadcast_to(r, (self.height, self.width))

    def copy_with(self, data: np.ndarray) -> "SonarImage":
        img = replace(self, data=data)
        img._nadir = self._nadir
        return img


def _inverse_display_mapping(v: np.ndarray, meta: AcquisitionMeta) -> np.ndarray:
    """Invert the export display mapping back to approximate linear intensity."""
    if meta.intensity_mapping == "gamma":
        return np.clip(v, 0, 1) ** meta.gamma
    if meta.intensity_mapping == "log":
        d = meta.log_range_db
        return (10 ** (np.clip(v, 0, 1) * d / 10.0) - 1.0) / (10 ** (d / 10.0) - 1.0)
    return v
