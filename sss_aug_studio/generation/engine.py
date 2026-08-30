"""Batch dataset generation engine.

Guarantees (frozen requirements):

* **Originals are never modified** — they are copied verbatim into the
  output dataset alongside the newly generated samples.
* **Bit-reproducible** — the same :class:`GenerationConfig` (including
  ``master_seed``) produces a byte-identical dataset regardless of worker
  count, because every random draw comes from the deterministic seed tree
  keyed by (image, instance, copy).
* **Auditable** — ``generation_manifest.json`` records tool version, full
  config, and per-output applied instances, sampled parameters and label
  provenance; ``statistics.md`` summarizes source/augmented/total image
  counts, the box budget (boxes in / out / dropped), elapsed time,
  per-instance application counts and sampled parameter ranges
  (n / min / mean / max).

The engine is GUI-free; the Qt dialog and the CLI both drive it through
progress callbacks.
"""

from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .. import __version__
from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..core.pipeline import AugmentationInstance, AugmentationPipeline
from ..core.random import derive_rng
from ..datasets.yolo import YoloDataset
from .distributions import sample_value

__all__ = ["InstanceGenSpec", "GenerationConfig", "GenerationEngine", "GenerationStats"]

import cv2


class InstanceGenSpec(BaseModel):
    """One augmentation instance plus per-parameter sampling distributions."""

    model_config = ConfigDict(extra="forbid")

    instance: AugmentationInstance
    param_distributions: dict = Field(
        default_factory=dict,
        description="field name -> DistSpec dict; fields not listed use the instance's fixed value.",
    )


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_path: str
    output_path: str
    master_seed: int = 42
    copies_per_image: int = Field(1, ge=1, le=20, description="Augmented copies generated per original image.")
    specs: list[InstanceGenSpec] = Field(default_factory=list)
    allow_combination: bool = Field(True, description="If False, at most one instance is applied per copy.")
    min_box_retention: float = Field(0.6, ge=0.1, le=1.0)
    export_mapping: str = Field(
        "auto",
        description="Output intensity mapping: auto (= same as the declared input mapping) | linear | gamma | log.",
    )
    workers: int = Field(0, ge=0, le=64, description="Process workers; 0 = auto (CPU count - 1).")
    include_splits: list[str] = Field(default_factory=list, description="Splits to process; empty = all.")


@dataclass
class GenerationStats:
    images_in: int = 0
    images_out: int = 0
    augmented: int = 0
    boxes_in: int = 0
    boxes_out: int = 0
    boxes_dropped: int = 0
    per_instance_applied: dict[str, int] = None  # type: ignore[assignment]
    param_samples: dict[str, list[float]] = None  # type: ignore[assignment]
    elapsed_s: float = 0.0

    def __post_init__(self) -> None:
        self.per_instance_applied = self.per_instance_applied or {}
        self.param_samples = self.param_samples or {}


# ------------------------------------------------------------------ worker
def _process_one(args: dict) -> dict:
    """Worker: generate all copies for one dataset item (pure function of args)."""
    cfg = GenerationConfig(**args["config"])
    root, out_root = Path(cfg.dataset_path), Path(cfg.output_path)
    rel_img = Path(args["rel_image"])
    rel_lbl = Path(args["rel_label"])
    key = args["rel_key"]

    ds_meta = args["meta"]
    from ..core.meta import AcquisitionMeta

    meta = AcquisitionMeta(**ds_meta)
    img = SonarImage.load(root / rel_img, meta)
    labels = LabelSet.load(root / rel_lbl) if (root / rel_lbl).exists() else LabelSet()

    out_img_dir = out_root / rel_img.parent
    out_lbl_dir = out_root / rel_lbl.parent
    out_img_dir.mkdir(parents=True, exist_ok=True)
    out_lbl_dir.mkdir(parents=True, exist_ok=True)

    # 1) copy the original verbatim (never modified)
    shutil.copy2(root / rel_img, out_img_dir / rel_img.name)
    if (root / rel_lbl).exists():
        shutil.copy2(root / rel_lbl, out_lbl_dir / rel_lbl.name)

    records: list[dict] = []
    applied_counts: dict[str, int] = {}
    samples: dict[str, list[float]] = {}
    boxes_out = 0
    boxes_dropped = 0

    for copy_idx in range(cfg.copies_per_image):
        # sample per-copy parameters through the deterministic tree
        instances: list[AugmentationInstance] = []
        for spec in cfg.specs:
            inst = spec.instance.model_copy(deep=True)
            prng = derive_rng(cfg.master_seed, key, inst.instance_id, copy_idx, "params")
            new_params = dict(inst.params)
            for field_name, dist in spec.param_distributions.items():
                val = sample_value(dist, prng)
                new_params[field_name] = val
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    samples.setdefault(f"{inst.family}/{inst.label}/{field_name}", []).append(float(val))
            inst.params = new_params
            instances.append(inst)

        pipeline = AugmentationPipeline(instances, min_box_retention=cfg.min_box_retention)
        if not cfg.allow_combination and len(instances) > 1:
            # exclusive mode: pick one enabled instance by probability weights
            crng = derive_rng(cfg.master_seed, key, copy_idx, "exclusive")
            enabled = [i for i in instances if i.enabled]
            if enabled:
                weights = np.array([i.probability for i in enabled], dtype=np.float64)
                weights = weights / weights.sum() if weights.sum() > 0 else np.full(len(enabled), 1 / len(enabled))
                chosen = enabled[int(crng.choice(len(enabled), p=weights))]
                for i in instances:
                    i.enabled = i.instance_id == chosen.instance_id
                for i in instances:
                    i.probability = 1.0

        result = pipeline.apply(
            img, labels, cfg.master_seed, key, copy_index=copy_idx, respect_probability=cfg.allow_combination
        )
        stem = rel_img.stem + f"__aug{copy_idx}"
        out_img = out_img_dir / (stem + rel_img.suffix)
        cv2.imwrite(str(out_img), result.image.to_display(cfg.export_mapping))
        result.labels.save(out_lbl_dir / (stem + ".txt"))

        for s in result.stages:
            if s.applied:
                applied_counts[f"{s.family}/{s.label}"] = applied_counts.get(f"{s.family}/{s.label}", 0) + 1
        boxes_out += len(result.labels.boxes)
        boxes_dropped += sum(1 for p in result.labels.provenance if not p.kept)
        records.append({"output": str(Path(rel_img.parent) / (stem + rel_img.suffix)), **result.manifest()})

    return {
        "key": key,
        "copies": cfg.copies_per_image,
        "boxes_in": len(labels.boxes),
        "boxes_out": boxes_out,
        "boxes_dropped": boxes_dropped,
        "applied": applied_counts,
        "samples": samples,
        "records": records,
    }


# ------------------------------------------------------------------ engine
class GenerationEngine:
    """Drives batch generation with progress reporting."""

    def __init__(self, config: GenerationConfig):
        self.config = config

    def run(
        self,
        progress: Optional[Callable[[int, int, float], None]] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> GenerationStats:
        cfg = self.config
        ds = YoloDataset(cfg.dataset_path)
        items = [
            it
            for it in ds.items
            if not cfg.include_splits or it.split in cfg.include_splits
        ]
        out_root = Path(cfg.output_path)
        out_root.mkdir(parents=True, exist_ok=True)
        self._copy_dataset_config(ds, out_root)

        jobs = [
            {
                "config": json.loads(cfg.model_dump_json()),
                "rel_image": str(it.image_path.relative_to(ds.root)),
                "rel_label": str(it.label_path.relative_to(ds.root)) if it.label_path.is_absolute() else str(it.label_path),
                "rel_key": it.rel_key,
                "meta": json.loads(ds.meta_for(it).model_dump_json()),
            }
            for it in items
        ]
        # normalize label rel path (may not be under root when labels dir missing)
        for j, it in zip(jobs, items):
            try:
                j["rel_label"] = str(it.label_path.relative_to(ds.root))
            except ValueError:
                j["rel_label"] = str(Path("labels") / (Path(j["rel_image"]).stem + ".txt"))

        stats = GenerationStats(images_in=len(items))
        manifest_records: list[dict] = []
        t0 = time.time()
        workers = cfg.workers or max((__import__("os").cpu_count() or 2) - 1, 1)

        def consume(res: dict) -> None:
            stats.augmented += res["copies"]
            stats.boxes_in += res["boxes_in"]
            stats.boxes_out += res["boxes_out"]
            stats.boxes_dropped += res["boxes_dropped"]
            for k, v in res["applied"].items():
                stats.per_instance_applied[k] = stats.per_instance_applied.get(k, 0) + v
            for k, v in res["samples"].items():
                stats.param_samples.setdefault(k, []).extend(v)
            manifest_records.extend(res["records"])

        done = 0
        if workers <= 1 or len(jobs) <= 2:
            for job in jobs:
                if cancel and cancel():
                    break
                consume(_process_one(job))
                done += 1
                if progress:
                    progress(done, len(jobs), time.time() - t0)
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_process_one, job) for job in jobs]
                for fut in as_completed(futures):
                    if cancel and cancel():
                        pool.shutdown(cancel_futures=True)
                        break
                    consume(fut.result())
                    done += 1
                    if progress:
                        progress(done, len(jobs), time.time() - t0)

        stats.images_out = done * (1 + cfg.copies_per_image)
        stats.elapsed_s = time.time() - t0
        manifest_records.sort(key=lambda r: r.get("output", ""))  # order-independent output
        self._write_outputs(ds, out_root, stats, manifest_records)
        return stats

    # ------------------------------------------------------------- outputs
    def _copy_dataset_config(self, ds: YoloDataset, out_root: Path) -> None:
        for name in ("data.yaml", "dataset.yaml", "data.yml", "sss_aug_dataset.yaml"):
            src = ds.root / name
            if src.exists():
                shutil.copy2(src, out_root / name)

    def _write_outputs(self, ds: YoloDataset, out_root: Path, stats: GenerationStats, records: list[dict]) -> None:
        manifest = {
            "tool": "sss-aug-studio",
            "version": __version__,
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "config": json.loads(self.config.model_dump_json()),
            "images": records,
        }
        (out_root / "generation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        lines = [
            "# Generation statistics",
            "",
            f"- source images: **{stats.images_in}**",
            f"- augmented copies: **{stats.augmented}**",
            f"- total output images (originals + augmented): **{stats.images_out}**",
            f"- boxes in / out / dropped: **{stats.boxes_in} / {stats.boxes_out} / {stats.boxes_dropped}**",
            f"- elapsed: **{stats.elapsed_s:.1f} s**",
            "",
            "## Applications per instance",
            "",
        ]
        for k, v in sorted(stats.per_instance_applied.items()):
            lines.append(f"- `{k}`: {v}")
        lines += ["", "## Sampled parameter ranges", ""]
        for k, vals in sorted(stats.param_samples.items()):
            a = np.asarray(vals)
            lines.append(f"- `{k}`: n={len(a)}, min={a.min():.4g}, mean={a.mean():.4g}, max={a.max():.4g}")
        (out_root / "statistics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
