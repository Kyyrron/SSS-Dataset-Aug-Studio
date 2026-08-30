#!/usr/bin/env python3
"""Regenerate the ``docs/demo_*.png`` preset comparison figures.

Each figure is one ``demo_dataset`` image shown as ORIGINAL | AUGMENTED under
a named preset, in the GUI's amber sonar colormap, so the documentation shows
what a preset actually does to the shipped fixture.

Run from the repository root, after ``tools/make_demo_dataset.py``::

    python tools/make_demo_images.py

Deterministic: the master seed is fixed, so re-running reproduces the figures
byte-for-byte.  Not packaged -- a maintenance script.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # LUT import only

import cv2
import numpy as np

from sss_aug_studio.datasets.yolo import YoloDataset
from sss_aug_studio.gui.qt_images import apply_sonar_colormap
from sss_aug_studio.profiles.store import bundled_presets

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "demo_dataset"
DOCS = REPO_ROOT / "docs"

MASTER_SEED = 1234
GAP = 8            # px between the two panels
BAR = 22           # px title bar height

# (image stem, preset name) -- one figure each.
FIGURES = [
    ("dual_basin_01", "Harbour inspection"),
    ("dual_basin_01", "Moderate waves"),
    ("dual_basin_02", "Highly turbid environment"),
    ("port_leg_01", "Fast survey"),
]


def _panel(gray_u8: np.ndarray, title: str) -> np.ndarray:
    """Amber-mapped image with a title bar above it."""
    body = apply_sonar_colormap(gray_u8)
    h, w = body.shape[:2]
    out = np.zeros((h + BAR, w, 3), dtype=np.uint8)
    out[BAR:] = body
    out[:BAR] = (24, 24, 24)
    cv2.putText(out, title, (6, BAR - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                (235, 235, 235), 1, cv2.LINE_AA)
    return out


def main() -> int:
    ds = YoloDataset(DEMO)
    by_stem = {it.image_path.stem: it for it in ds.items}
    presets = {p.name: p for p in bundled_presets()}

    for stem, preset_name in FIGURES:
        item, preset = by_stem[stem], presets[preset_name]
        img = ds.load_image(item)
        result = preset.to_pipeline().apply(
            img, item.load_labels(), master_seed=MASTER_SEED, image_key=stem)

        left = _panel(img.to_display(), f"{stem} - ORIGINAL")
        right = _panel(result.image.to_display(), f"AUGMENTED - preset: {preset_name}")

        h = max(left.shape[0], right.shape[0])
        canvas = np.zeros((h, left.shape[1] + GAP + right.shape[1], 3), np.uint8)
        canvas[: left.shape[0], : left.shape[1]] = left
        canvas[: right.shape[0], left.shape[1] + GAP:] = right

        slug = preset_name.lower().replace(" ", "_")
        out = DOCS / f"demo_{stem}_{slug}.png"
        cv2.imwrite(str(out), canvas)
        print(f"  {out.relative_to(REPO_ROOT)}  {canvas.shape[1]}x{canvas.shape[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
