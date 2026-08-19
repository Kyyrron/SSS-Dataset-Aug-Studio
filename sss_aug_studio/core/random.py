"""Deterministic random-number management.

Every stochastic element of the studio draws from a :class:`numpy.random.Generator`
derived from a *master seed* through a reproducible tree of
:class:`numpy.random.SeedSequence` spawns keyed by stable string identifiers
(image name, augmentation instance id, copy index).  Re-running any operation
with the same master seed therefore reproduces bit-identical results,
independent of iteration order or process count.
"""

from __future__ import annotations

import hashlib

import numpy as np

__all__ = ["derive_rng", "stable_key_entropy"]


def stable_key_entropy(*keys: str | int) -> list[int]:
    """Map arbitrary string/int keys to a stable list of 32-bit words.

    Uses SHA-256 so the mapping is platform- and run-independent (unlike
    Python's salted ``hash``).
    """
    h = hashlib.sha256()
    for k in keys:
        h.update(str(k).encode("utf-8"))
        h.update(b"\x1f")  # separator to avoid concatenation collisions
    digest = h.digest()
    return [int.from_bytes(digest[i : i + 4], "little") for i in range(0, 32, 4)]


def derive_rng(master_seed: int, *keys: str | int) -> np.random.Generator:
    """Derive an independent Generator from ``master_seed`` and stable keys.

    Parameters
    ----------
    master_seed:
        The user-visible master seed of the session / generation run.
    keys:
        Stable identifiers, e.g. ``(image_relpath, instance_id, copy_index)``.
    """
    ss = np.random.SeedSequence([master_seed & 0xFFFFFFFF, *stable_key_entropy(*keys)])
    return np.random.Generator(np.random.PCG64(ss))
