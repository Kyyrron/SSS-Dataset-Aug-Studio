"""Modular acquisition-metadata readers (validated decision #2).

Metadata resolution is a chain of responsibility so new sources (EXIF, ROS
bag sidecars, SonarView exports) can be added without touching callers:

1. :class:`SidecarJsonReader` — ``{stem}.json`` or ``{stem}.meta.json`` next
   to the image (per-image physical metadata from the acquisition pipeline);
2. :class:`DatasetConfigReader` — dataset-level defaults and layout from
   ``sss_aug_dataset.yaml`` at the dataset root;
3. built-in fallbacks inside :class:`AcquisitionMeta` (normalized mode).

Later readers only fill fields the earlier ones left unset.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Protocol

import yaml

from ..core.meta import AcquisitionMeta

__all__ = ["MetadataReader", "SidecarJsonReader", "DatasetConfigReader", "MetadataResolver", "DATASET_CONFIG_NAME"]

DATASET_CONFIG_NAME = "sss_aug_dataset.yaml"


class MetadataReader(Protocol):
    """One metadata source; returns partial field dict or None."""

    def read(self, image_path: Path) -> Optional[dict]: ...


class SidecarJsonReader:
    """Per-image sidecar: ``image.png`` -> ``image.json`` / ``image.meta.json``."""

    def read(self, image_path: Path) -> Optional[dict]:
        for cand in (image_path.with_suffix(".json"), image_path.with_suffix(".meta.json")):
            if cand.exists():
                try:
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    return data if isinstance(data, dict) else None
                except (json.JSONDecodeError, OSError):
                    return None
        return None


class DatasetConfigReader:
    """Dataset-level defaults from ``sss_aug_dataset.yaml`` (layout, meta block)."""

    def __init__(self, dataset_root: Path):
        self._fields: dict = {}
        cfg = dataset_root / DATASET_CONFIG_NAME
        if cfg.exists():
            try:
                doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                self._fields = dict(doc.get("meta", {}))
                if "layout" in doc:
                    self._fields["layout"] = doc["layout"]
                if "intensity_mapping" in doc:
                    self._fields["intensity_mapping"] = doc["intensity_mapping"]
            except (yaml.YAMLError, OSError):
                self._fields = {}

    def read(self, image_path: Path) -> Optional[dict]:
        return dict(self._fields) if self._fields else None


class MetadataResolver:
    """Merge partial metadata from an ordered reader chain into AcquisitionMeta."""

    def __init__(self, readers: list[MetadataReader]):
        self.readers = readers

    def resolve(self, image_path: Path) -> AcquisitionMeta:
        merged: dict = {}
        for reader in self.readers:
            fields = reader.read(image_path)
            if fields:
                for k, v in fields.items():
                    merged.setdefault(k, v)
        known = set(AcquisitionMeta.model_fields)
        return AcquisitionMeta(**{k: v for k, v in merged.items() if k in known})
