"""Augmentation profiles: named, editable, exportable pipeline configurations.

A profile stores the full instance list (family, label, enabled, probability,
strength, physical parameters).  Bundled presets live in
``profiles/presets/*.yaml``; user profiles can be saved anywhere.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core.pipeline import AugmentationInstance, AugmentationPipeline

__all__ = ["PipelineProfile", "load_profile", "save_profile", "bundled_presets"]


class PipelineProfile(BaseModel):
    """Named pipeline configuration.

    Since v0.3.0 stochastic laws live **on the instances themselves**
    (``AugmentationInstance.distributions``): a profile is de facto
    deterministic when no instance declares a law.  The legacy profile-level
    ``mode``/``distributions`` fields are still accepted and migrated into
    the instances on load (deprecated).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    mode: Literal["deterministic", "stochastic"] = "deterministic"  # deprecated (v0.2.x)
    instances: list[AugmentationInstance] = Field(default_factory=list)
    distributions: dict[str, dict] = Field(default_factory=dict)     # deprecated (v0.2.x)

    @model_validator(mode="after")
    def _migrate_legacy_distributions(self) -> "PipelineProfile":
        if self.mode == "stochastic" and self.distributions:
            by_id = {i.instance_id: i for i in self.instances}
            for iid, dists in self.distributions.items():
                if iid in by_id and not by_id[iid].distributions:
                    by_id[iid].distributions = dict(dists)
        return self

    @property
    def is_stochastic(self) -> bool:
        return any(i.distributions for i in self.instances)

    def to_pipeline(self) -> AugmentationPipeline:
        return AugmentationPipeline([i.model_copy(deep=True) for i in self.instances])

    @classmethod
    def from_pipeline(cls, name: str, description: str, pipeline: AugmentationPipeline, **_legacy) -> "PipelineProfile":
        return cls(name=name, description=description,
                   instances=[i.model_copy(deep=True) for i in pipeline.instances])


def save_profile(profile: PipelineProfile, path: str | Path) -> None:
    Path(path).write_text(yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=False, allow_unicode=True), encoding="utf-8")


def load_profile(path: str | Path) -> PipelineProfile:
    return PipelineProfile(**(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}))


def bundled_presets() -> list[PipelineProfile]:
    """Load the presets shipped with the package (sorted by name)."""
    out: list[PipelineProfile] = []
    pkg = resources.files("sss_aug_studio.profiles") / "presets"
    try:
        for entry in sorted(pkg.iterdir(), key=lambda e: e.name):  # type: ignore[attr-defined]
            if entry.name.endswith(".yaml"):
                out.append(PipelineProfile(**(yaml.safe_load(entry.read_text(encoding="utf-8")) or {})))
    except (FileNotFoundError, NotADirectoryError):
        pass
    return out
