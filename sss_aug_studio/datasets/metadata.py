"""Modular acquisition-metadata readers.

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
import warnings
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
    """Dataset-level defaults from ``sss_aug_dataset.yaml``.

    Every :class:`AcquisitionMeta` field is honoured at the **top level** and
    inside the ``meta:`` block; the two positions are equivalent and the top
    level wins where a key appears in both.  A key at either level that is not
    an ``AcquisitionMeta`` field is ignored with a :class:`UserWarning` naming
    it, so a misspelling is visible rather than silently inert.  Reading never
    raises: a malformed or non-conformant config yields no fields.
    """

    def __init__(self, dataset_root: Path):
        self._fields: dict = {}
        cfg = dataset_root / DATASET_CONFIG_NAME
        if not cfg.exists():
            return
        try:
            doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            return
        if not isinstance(doc, dict):
            return
        block = doc.get("meta") or {}
        if not isinstance(block, dict):
            block = {}

        known = set(AcquisitionMeta.model_fields)
        # top level wins: seed from it, then fill the gaps from ``meta:``
        self._fields = {k: v for k, v in doc.items() if k in known}
        for k, v in block.items():
            if k in known:
                self._fields.setdefault(k, v)

        unknown = [k for k in doc if k not in known and k != "meta"]
        unknown += [k for k in block if k not in known]
        if unknown:
            warnings.warn(
                f"{cfg}: ignoring unrecognised key(s) {sorted(set(unknown))}; "
                f"expected an AcquisitionMeta field ({', '.join(sorted(known))}).",
                UserWarning,
                stacklevel=2,
            )

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
