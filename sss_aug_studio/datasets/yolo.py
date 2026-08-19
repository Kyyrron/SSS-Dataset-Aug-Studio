"""YOLO dataset discovery and indexing.

Accepts the common Ultralytics layouts: ``images/``+``labels/`` at the root
or under ``train|val|test`` splits, with ``data.yaml`` (or ``dataset.yaml``)
providing class names.  Per-image :class:`AcquisitionMeta` is resolved
through the modular reader chain (decision #2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
import yaml

from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..core.meta import AcquisitionMeta
from .metadata import DatasetConfigReader, MetadataResolver, SidecarJsonReader

__all__ = ["DatasetItem", "YoloDataset"]

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


@dataclass
class DatasetItem:
    image_path: Path
    label_path: Path
    split: str
    rel_key: str
    classes: set[int] = field(default_factory=set)

    def load_labels(self) -> LabelSet:
        return LabelSet.load(self.label_path)


class YoloDataset:
    """Indexed YOLO dataset with class search and metadata resolution."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.exists():
            raise FileNotFoundError(f"Dataset root not found: {self.root}")
        self.class_names: dict[int, str] = self._read_class_names()
        self._resolver = MetadataResolver([SidecarJsonReader(), DatasetConfigReader(self.root)])
        self.items: list[DatasetItem] = list(self._index())
        for it in self.items:
            it.classes = it.load_labels().classes()

    # ---------------------------------------------------------------- index
    def _read_class_names(self) -> dict[int, str]:
        for name in ("data.yaml", "dataset.yaml", "data.yml"):
            p = self.root / name
            if p.exists():
                try:
                    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                    names = doc.get("names")
                    if isinstance(names, dict):
                        return {int(k): str(v) for k, v in names.items()}
                    if isinstance(names, list):
                        return {i: str(n) for i, n in enumerate(names)}
                except (yaml.YAMLError, OSError):
                    pass
        return {}

    def _image_dirs(self) -> Iterator[tuple[Path, str]]:
        direct = self.root / "images"
        if direct.is_dir():
            subsplits = [d for d in direct.iterdir() if d.is_dir() and d.name in ("train", "val", "test")]
            if subsplits:
                for d in subsplits:
                    yield d, d.name
            else:
                yield direct, "all"
        for split in ("train", "val", "test"):
            d = self.root / split / "images"
            if d.is_dir():
                yield d, split

    def _index(self) -> Iterator[DatasetItem]:
        seen: set[Path] = set()
        for img_dir, split in self._image_dirs():
            for p in sorted(img_dir.rglob("*")):
                if p.suffix.lower() not in IMAGE_EXTS or p in seen:
                    continue
                seen.add(p)
                label = Path(str(p.parent).replace("images", "labels")) / (p.stem + ".txt")
                yield DatasetItem(
                    image_path=p,
                    label_path=label,
                    split=split,
                    rel_key=str(p.relative_to(self.root)),
                )

    # ----------------------------------------------------------------- API
    def __len__(self) -> int:
        return len(self.items)

    def class_name(self, cls: int) -> str:
        return self.class_names.get(cls, f"class {cls}")

    def meta_for(self, item: DatasetItem) -> AcquisitionMeta:
        return self._resolver.resolve(item.image_path)

    def load_image(self, item: DatasetItem) -> SonarImage:
        return SonarImage.load(item.image_path, self.meta_for(item))

    def filter_by_class(self, cls: Optional[int]) -> list[int]:
        """Indices of items containing class ``cls`` (None = all)."""
        if cls is None:
            return list(range(len(self.items)))
        return [i for i, it in enumerate(self.items) if cls in it.classes]

    def random_index(self, rng: np.random.Generator, cls: Optional[int] = None) -> Optional[int]:
        idxs = self.filter_by_class(cls)
        return int(rng.choice(idxs)) if idxs else None
