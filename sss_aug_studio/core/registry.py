"""Plugin registry for augmentation families.

Families self-register via the :func:`register` decorator; the GUI, batch
generator and encyclopedia all consume the same registry, so adding a new
family is one module with zero GUI code (design §6).

``DEFAULT_ORDER`` encodes the physical causal chain (design principle #4):
scene reflectivity -> shadow scene edit -> platform-motion geometry ->
slant/altitude geometry -> radiometric transfer -> multipath additions ->
speckle (multiplicative, commutes with gain) -> receiver-level artifacts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Type

if TYPE_CHECKING:  # pragma: no cover
    from ..augmentations.base import Augmentation

_REGISTRY: Dict[str, Type["Augmentation"]] = {}

DEFAULT_ORDER = [
    "mirror_across_track",   # G1 (acquisition-direction choice)
    "reverse_along_track",   # G2
    "seabed",          # F7
    "shadow",          # F6
    "platform_motion", # F4
    "slant_geometry",  # F3
    "radiometric",     # F2
    "multipath",       # F8
    "speckle",         # F1
    "ping_artifacts",  # F5
]


def register(cls: Type["Augmentation"]) -> Type["Augmentation"]:
    if not getattr(cls, "key", None):
        raise ValueError(f"Augmentation {cls.__name__} must define a class-level 'key'.")
    _REGISTRY[cls.key] = cls
    return cls


def get(key: str) -> Type["Augmentation"]:
    _ensure_loaded()
    return _REGISTRY[key]


def all_families() -> Dict[str, Type["Augmentation"]]:
    _ensure_loaded()
    return dict(sorted(_REGISTRY.items(), key=lambda kv: kv[1].order_hint))


def _ensure_loaded() -> None:
    """Import all built-in family modules exactly once."""
    if _REGISTRY:
        return
    from ..augmentations import (  # noqa: F401
        geometric,
        speckle,
        radiometric,
        slant_geometry,
        platform_motion,
        ping_artifacts,
        shadow,
        seabed,
        multipath,
    )
