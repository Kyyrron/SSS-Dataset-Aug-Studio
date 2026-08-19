"""Augmentation pipeline: ordered, seeded, cache-friendly composition.

An :class:`AugmentationInstance` is a *named parameter set* of a family —
multiple instances of the same family ("Platform Motion / slow turn",
"Platform Motion / fast turn") are first-class (design §6).  The pipeline
holds instances, applies them in the user-visible order, derives one child
RNG per (image, instance, copy) triple, and propagates labels through every
geometric stage.

Preview mode applies every *enabled* instance regardless of its application
probability; generation mode draws the Bernoulli application decision from
the same deterministic RNG tree so datasets are reproducible bit-for-bit.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .image import SonarImage
from .labels import LabelSet
from .random import derive_rng
from . import registry

__all__ = ["AugmentationInstance", "AugmentationPipeline", "PipelineResult", "StageRecord"]


class AugmentationInstance(BaseModel):
    """One configured, named instance of an augmentation family."""

    model_config = ConfigDict(extra="forbid")

    family: str = Field(description="Registry key of the augmentation family.")
    label: str = Field(default="default", description="Human-readable instance name (e.g. 'slow turn').")
    instance_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    enabled: bool = True
    probability: float = Field(1.0, ge=0.0, le=1.0, description="Application probability during dataset generation.")
    strength: float = Field(1.0, ge=0.0, le=2.0, description="Global effect strength (1 = model as parameterized).")
    params: dict = Field(default_factory=dict, description="Family-specific physical parameters (nominal / preview values).")
    distributions: dict = Field(
        default_factory=dict,
        description="Per-parameter stochastic laws for generation: param name -> DistSpec dict "
        "(uniform/normal/loguniform). Empty = every parameter fixed. Previews always render "
        "the nominal values in `params`.",
    )

    def validated_params(self):
        cls = registry.get(self.family)
        return cls.Params(**self.params)

    def config_hash(self) -> str:
        # `distributions` is deliberately EXCLUDED: previews render nominal
        # values, so editing a stochastic law must not invalidate the
        # preview stage cache.
        payload = json.dumps(
            {"f": self.family, "p": self.params, "s": self.strength, "e": self.enabled},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha1(payload.encode()).hexdigest()[:16]


@dataclass
class StageRecord:
    instance_id: str
    family: str
    label: str
    applied: bool
    params: dict
    strength: float
    info: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    image: SonarImage
    labels: LabelSet
    stages: list[StageRecord]

    def manifest(self) -> dict:
        return {
            "stages": [
                {
                    "instance_id": s.instance_id,
                    "family": s.family,
                    "label": s.label,
                    "applied": s.applied,
                    "strength": s.strength,
                    "params": s.params,
                    "info": s.info,
                }
                for s in self.stages
            ],
            "boxes": [
                {"index": p.index, "kept": p.kept, "retention": round(p.retention, 4), "note": p.note}
                for p in self.labels.provenance
            ],
        }


class AugmentationPipeline:
    """Ordered list of instances with deterministic application."""

    def __init__(self, instances: Optional[list[AugmentationInstance]] = None, min_box_retention: float = 0.6):
        self.instances: list[AugmentationInstance] = instances or []
        self.min_box_retention = min_box_retention

    # ------------------------------------------------------------- editing
    def add(self, instance: AugmentationInstance) -> None:
        self.instances.append(instance)

    def remove(self, instance_id: str) -> None:
        self.instances = [i for i in self.instances if i.instance_id != instance_id]

    def move(self, instance_id: str, new_index: int) -> None:
        idx = next((k for k, i in enumerate(self.instances) if i.instance_id == instance_id), None)
        if idx is None:
            return
        inst = self.instances.pop(idx)
        self.instances.insert(int(np.clip(new_index, 0, len(self.instances))), inst)

    def sort_physical(self) -> None:
        order = {k: n for n, k in enumerate(registry.DEFAULT_ORDER)}
        self.instances.sort(key=lambda i: order.get(i.family, 99))

    # -------------------------------------------------------------- apply
    def apply(
        self,
        img: SonarImage,
        labels: LabelSet,
        master_seed: int,
        image_key: str,
        copy_index: int = 0,
        respect_probability: bool = False,
        upto_instance: Optional[str] = None,
    ) -> PipelineResult:
        """Run the pipeline.

        ``upto_instance``: stop after this instance id (preview stage cache).
        ``respect_probability``: generation mode Bernoulli gating.
        """
        cur_img, cur_labels = img, labels
        stages: list[StageRecord] = []
        for inst in self.instances:
            if not inst.enabled:
                stages.append(StageRecord(inst.instance_id, inst.family, inst.label, False, inst.params, inst.strength))
                if upto_instance == inst.instance_id:
                    break
                continue
            rng = derive_rng(master_seed, image_key, inst.instance_id, copy_index)
            applied = True
            if respect_probability and inst.probability < 1.0:
                applied = bool(rng.random() < inst.probability)
            if not applied:
                stages.append(StageRecord(inst.instance_id, inst.family, inst.label, False, inst.params, inst.strength))
                if upto_instance == inst.instance_id:
                    break
                continue
            fam = registry.get(inst.family)()
            params = inst.validated_params()
            res = fam.apply(cur_img, cur_labels, params, rng, strength=inst.strength)
            in_size = (cur_img.width, cur_img.height)
            out_size = res.out_size or (res.data.shape[1], res.data.shape[0])
            if res.labels_override is not None:
                cur_labels = res.labels_override
            elif res.warp is not None or out_size != in_size:
                cur_labels = cur_labels.warped(res.warp, in_size, out_size, self.min_box_retention)
            if res.meta_override is not None:
                cur_img = SonarImage(data=res.data, meta=res.meta_override, path=cur_img.path)
            else:
                cur_img = cur_img.copy_with(res.data)
            stages.append(
                StageRecord(inst.instance_id, inst.family, inst.label, True, inst.params, inst.strength, res.info)
            )
            if upto_instance == inst.instance_id:
                break
        return PipelineResult(image=cur_img, labels=cur_labels, stages=stages)
