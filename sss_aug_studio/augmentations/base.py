"""Augmentation base contract.

Every augmentation family is one self-contained module exposing:

* a Pydantic ``Params`` model — every field carries physical units, bounds
  and a description (the GUI auto-generates its parameter form from this
  schema; batch generation wraps each field in a sampling distribution);
* a :class:`ScienceCard` — name, phenomenon, key equation, verified
  references, limitations (rendered as the library card and linked to the
  encyclopedia page);
* :meth:`Augmentation.apply` — a pure function ``(image, labels, params,
  rng, strength) -> AugResult``.

Strength semantics (design §6): photometric families blend linearly between
input and full-effect output; geometric families scale their displacement
fields.  ``strength = 1`` is the model exactly as parameterized.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Optional, Type

import numpy as np
from pydantic import BaseModel, ConfigDict

from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..core.meta import AcquisitionMeta
from ..core.warp import FieldWarp

__all__ = ["AugParams", "ScienceCard", "AugResult", "Augmentation", "blend"]


class AugParams(BaseModel):
    """Base for all augmentation parameter models (strict: no unknown fields)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


@dataclass(frozen=True)
class ScienceCard:
    key: str
    name: str
    phenomenon: str            # one-line physical phenomenon
    equation: str              # key equation (plain-text math)
    references: tuple[str, ...]
    limitations: str
    expected_effect: str
    doc_page: str              # encyclopedia markdown filename


@dataclass
class AugResult:
    """Output of one augmentation application."""

    data: np.ndarray
    warp: Optional[FieldWarp] = None          # geometric label transform, if any
    out_size: Optional[tuple[int, int]] = None  # (w, h) if size changed (row removal)
    labels_override: Optional[LabelSet] = None  # families that edit labels directly (F6)
    meta_override: Optional["AcquisitionMeta"] = None  # G-families that change layout/nadir/heading
    info: dict = field(default_factory=dict)    # provenance for the manifest


def blend(original: np.ndarray, augmented: np.ndarray, strength: float) -> np.ndarray:
    """Linear-domain photometric blend used for strength scaling."""
    s = float(np.clip(strength, 0.0, 2.0))
    if s == 1.0:
        return augmented
    out = original + s * (augmented - original)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


class Augmentation(ABC):
    """Abstract augmentation family."""

    key: ClassVar[str]
    name: ClassVar[str]
    order_hint: ClassVar[int]  # default causal position (lower = earlier)
    Params: ClassVar[Type[AugParams]]
    card: ClassVar[ScienceCard]
    geometric: ClassVar[bool] = False
    #: GUI grouping: "physics" (F1-F8 phenomenon models) or "geometry" (pure
    #: geometric acquisition-direction operations, G-families).
    section: ClassVar[str] = "physics"

    @abstractmethod
    def apply(
        self,
        img: SonarImage,
        labels: LabelSet,
        params: AugParams,
        rng: np.random.Generator,
        strength: float = 1.0,
    ) -> AugResult:
        """Apply the augmentation. Must not mutate ``img`` or ``labels``."""
