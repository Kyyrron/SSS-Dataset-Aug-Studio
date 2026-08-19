"""G-families — pure geometric acquisition-direction operations.

Unlike F1–F8 (physical phenomenon models), these are *exact* geometric
symmetries of side-scan sonar acquisition and therefore live in a dedicated
**Geometry** section of the interface (``section = "geometry"``):

* **G1 — across-track mirror**: the mirrored survey.  A port-side acquisition
  of the scene is the exact column reversal of a starboard-side acquisition
  and vice versa; a dual waterfall swaps its two sides.  Because each side's
  canonical range axis maps onto the other side's range axis, acoustic
  shadows remain strictly down-range — the transform is physically consistent
  by construction.  Layout metadata follows (``single_port`` ↔
  ``single_starboard``; dual nadir band mirrored, i.e. preserved for the
  standard centered waterfall).

* **G2 — along-track reversal**: the survey line replayed in the opposite
  direction.  Ping order (rows) reverses; heading rotates by 180°; every
  other physical property of the acquisition is preserved.

Both are involutions implemented as bidirectional :class:`FieldWarp`s, so
YOLO labels flow through the standard pipeline machinery.  ``strength`` is
intentionally **binary** for geometric symmetries: any value > 0 applies the
full transform (a "half mirror" has no physical meaning); use ``probability``
to control how often they apply during generation.
"""

from __future__ import annotations

import numpy as np
from pydantic import Field

from ..core.image import SonarImage
from ..core.labels import LabelSet
from ..core.meta import AcquisitionMeta
from ..core.registry import register
from ..core.warp import FieldWarp, identity_grid
from .base import AugParams, AugResult, Augmentation, ScienceCard


def _flip_warp(h: int, w: int, axis: int) -> FieldWarp:
    """Exact column (axis=1) or row (axis=0) reversal as a bidirectional warp."""
    gx, gy = identity_grid(h, w)
    if axis == 1:
        map_x, map_y = (w - 1.0) - gx, gy
        fwd_dx, fwd_dy = (w - 1.0) - 2.0 * gx, np.zeros_like(gy)
    else:
        map_x, map_y = gx, (h - 1.0) - gy
        fwd_dx, fwd_dy = np.zeros_like(gx), (h - 1.0) - 2.0 * gy
    return FieldWarp(map_x=map_x.astype(np.float32), map_y=map_y.astype(np.float32),
                     fwd_dx=fwd_dx.astype(np.float32), fwd_dy=fwd_dy.astype(np.float32))


class MirrorParams(AugParams):
    update_layout_metadata: bool = Field(
        True,
        description="Swap single_port/single_starboard and mirror the declared nadir band metadata.",
    )


@register
class MirrorAcrossTrack(Augmentation):
    key = "mirror_across_track"
    name = "G1 — Across-track mirror"
    order_hint = 1  # acquisition-direction choice: logically prior to all physics
    Params = MirrorParams
    geometric = True
    section = "geometry"
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="The mirrored survey: a port-side acquisition equals the exact column reversal of a "
        "starboard-side acquisition of the same scene (dual waterfalls swap sides). An exact symmetry "
        "of SSS image formation — shadows remain strictly down-range on the swapped side.",
        equation="I'(y, x) = I(y, W−1−x);  layout port ↔ starboard;  nadir c → 1 − c",
        references=(
            "Blondel (2009), The Handbook of Sidescan Sonar, Springer, ch. 2 (acquisition geometry)",
        ),
        limitations="Exact symmetry — no approximation. Any residual port/starboard hardware asymmetry "
        "(transducer gain imbalance) is not mirrored; model it with a radiometric instance if needed.",
        expected_effect="Left/right swapped waterfall; boxes mirrored; nadir preserved for centered dual "
        "layouts; single-side images change their declared side.",
        doc_page="g_geometry.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: MirrorParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        if strength <= 0.0:
            return AugResult(data=img.data.copy())
        h, w = img.data.shape
        warp = _flip_warp(h, w, axis=1)
        out = img.data[:, ::-1].copy()
        meta: AcquisitionMeta | None = None
        if params.update_layout_metadata:
            fields: dict = {}
            if img.meta.layout == "single_port":
                fields["layout"] = "single_starboard"
            elif img.meta.layout == "single_starboard":
                fields["layout"] = "single_port"
            else:
                fields["nadir_center_frac"] = 1.0 - img.meta.nadir_center_frac
            meta = img.meta.model_copy(update=fields)
        return AugResult(data=out, warp=warp, meta_override=meta,
                         info={"mirrored": True, "layout_out": (meta or img.meta).layout})


class ReversalParams(AugParams):
    update_heading_metadata: bool = Field(
        True, description="Rotate the recorded heading by 180° (reversed survey line)."
    )


@register
class ReverseAlongTrack(Augmentation):
    key = "reverse_along_track"
    name = "G2 — Along-track reversal"
    order_hint = 2
    Params = ReversalParams
    geometric = True
    section = "geometry"
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="The same survey line run in the opposite direction: ping order reverses while every "
        "per-ping physical property (range geometry, radiometry, shadows) is preserved exactly.",
        equation="I'(y, x) = I(H−1−y, x);  heading ψ → ψ + 180°",
        references=(
            "Blondel (2009), The Handbook of Sidescan Sonar, Springer, ch. 2 (survey line geometry)",
        ),
        limitations="Exact for time-stationary scenes; along-track asymmetric effects of the original run "
        "(e.g. a turn fan already burned into the image) reverse with the pixels, which is consistent.",
        expected_effect="Vertically flipped waterfall; boxes follow; across-track structure untouched.",
        doc_page="g_geometry.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: ReversalParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        if strength <= 0.0:
            return AugResult(data=img.data.copy())
        h, w = img.data.shape
        warp = _flip_warp(h, w, axis=0)
        out = img.data[::-1, :].copy()
        meta: AcquisitionMeta | None = None
        if params.update_heading_metadata and img.meta.heading_deg is not None:
            meta = img.meta.model_copy(update={"heading_deg": (img.meta.heading_deg + 180.0) % 360.0})
        return AugResult(data=out, warp=warp, meta_override=meta, info={"reversed": True})
