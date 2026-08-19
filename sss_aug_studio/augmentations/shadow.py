"""F6 — Shadow & highlight modulation (conservative, confidence-gated).

Physical phenomenon
    A proud object returns a bright highlight followed (down-range) by an
    acoustic shadow of ground length L_s = H_t r / (h - H_t).  Shadow
    *contrast* is set by the ambient noise/reverberation floor — in shallow
    multipath-rich water shadows are never black; shadow *length* is set by
    altitude/range geometry.  Detectors demonstrably exploit the
    highlight-shadow pair (Zou et al. 2025 and the classical MCM detection
    literature), so varying it within physically consistent bounds targets
    the exact cue the detector uses.

Model
    Inside each label box (convention: box = highlight + shadow, decision #3)
    the shadow region is segmented down-range of the highlight (Otsu within
    the box); modifications are applied only when segmentation confidence
    exceeds a gate (decision #5):
      floor:     I' = I (1 - beta) + beta F     (raise ambient floor F)
      softness:  range-directed blur of the shadow's inner boundary
      length:    L_s' = kappa L_s with kappa = h/h' — every scaling factor is
                 expressible as a plausible altitude change (consistency
                 guard); the down-range box edge moves with the shadow.
"""

from __future__ import annotations

import numpy as np
from pydantic import Field
from scipy.ndimage import gaussian_filter1d

from ..core.registry import register
from ..core.image import SonarImage
from ..core.labels import BoxProvenance, LabelSet, YoloBox
from .base import AugParams, AugResult, Augmentation, ScienceCard, blend


class ShadowParams(AugParams):
    floor_level: float = Field(0.06, ge=0.0, le=0.4, description="Ambient reverberation floor F filling shadows. [linear 0-1]")
    floor_blend: float = Field(0.5, ge=0.0, le=1.0, description="Floor blend beta (0 = untouched shadow). [-]")
    softness_m: float = Field(0.15, ge=0.0, le=1.0, description="Shadow edge penumbra width. [m]")
    length_altitude_factor: float = Field(
        1.0, ge=0.7, le=1.4, description="Altitude ratio h'/h; shadow length scales by h/h' (1 = off). [-]"
    )
    confidence_gate: float = Field(
        0.35, ge=0.0, le=0.9, description="Min shadow-segmentation confidence to modify a box (decision #5). [-]"
    )
    highlight_gain_db: float = Field(0.0, ge=-6.0, le=6.0, description="Highlight region gain. [dB]")


@register
class ShadowAugmentation(Augmentation):
    key = "shadow"
    name = "Shadow & highlight modulation"
    order_hint = 20
    Params = ShadowParams
    geometric = False  # edits labels directly instead of via a warp
    card = ScienceCard(
        key=key,
        name=name,
        phenomenon="Shadow contrast set by the ambient reverberation floor; shadow length by altitude/range "
        "geometry (L_s = H r / (h - H)); detectors rely on the highlight-shadow pair.",
        equation="I' = I(1-beta) + beta.F  ;  L_s' = (h/h') L_s",
        references=(
            "Blondel (2009), The Handbook of Sidescan Sonar, Springer (shadow geometry & interpretation)",
            "Zou et al. (2025), J. Mar. Sci. Eng. 13(1):162, DOI 10.3390/jmse13010162 (small-object SSS detection)",
            "Coiras, Petillot & Lane (2007), IEEE Trans. Image Process. 16(2) (image-formation model)",
        ),
        limitations="Requires label boxes and reliable in-box shadow segmentation; gated conservative by "
        "default; length scaling assumes a single dominant shadow per box; flat seabed.",
        expected_effect="Shadows fill toward the ambient floor and blur at edges; optional altitude-consistent "
        "shadow lengthening/shortening with the box edge following (convention: shadow in box).",
        doc_page="f6_shadow.md",
    )

    def apply(self, img: SonarImage, labels: LabelSet, params: ShadowParams, rng: np.random.Generator, strength: float = 1.0) -> AugResult:
        h, w = img.data.shape
        out = img.data.copy()
        new_boxes: list[YoloBox] = []
        prov: list[BoxProvenance] = []
        n_modified = 0

        # Map each column to its side (for down-range direction & resolution)
        side_of_col: dict[str, tuple[slice, bool, float]] = {}
        for s in img.sides():
            side_of_col[s.name] = (s.cols, s.flip, s.res_across_m)

        for i, b in enumerate(labels.boxes):
            x0, y0, x1, y1 = (int(round(v)) for v in b.to_pixels(w, h))
            x0, y0 = max(x0, 0), max(y0, 0)
            x1, y1 = min(x1, w), min(y1, h)
            if x1 - x0 < 4 or y1 - y0 < 3:
                new_boxes.append(b)
                prov.append(BoxProvenance(i, True, 1.0, "F6 skipped: tiny box"))
                continue
            # which side is this box on? -> down-range = away from nadir
            cx = (x0 + x1) / 2
            side = None
            for name, (cols, flip, res) in side_of_col.items():
                if (cols.start or 0) <= cx < (cols.stop or w):
                    side = (name, flip, res)
                    break
            if side is None:
                new_boxes.append(b)
                prov.append(BoxProvenance(i, True, 1.0, "F6 skipped: box in nadir band"))
                continue
            name, flip, res = side
            downrange_right = not flip  # starboard: range grows rightward

            patch = out[y0:y1, x0:x1]
            seg = _segment_shadow(patch, downrange_right)
            if seg is None or seg["confidence"] < params.confidence_gate:
                new_boxes.append(b)
                prov.append(BoxProvenance(i, True, 1.0, "F6 skipped: low shadow confidence"))
                continue
            n_modified += 1
            mask = seg["mask"]

            # highlight gain
            if abs(params.highlight_gain_db) > 0.05:
                hgain = 10.0 ** (params.highlight_gain_db / 10.0)
                hl = seg["highlight_mask"]
                patch[hl] = np.clip(patch[hl] * hgain, 0, 1)

            # shadow floor
            beta = params.floor_blend
            patch[mask] = np.clip(patch[mask] * (1 - beta) + beta * params.floor_level, 0, 1)

            # length scaling (altitude-consistent)
            kappa = 1.0 / params.length_altitude_factor
            dx_edge = 0.0
            if abs(kappa - 1.0) > 0.01:
                dx_edge = _rescale_shadow_length(patch, mask, downrange_right, kappa)

            # softness (range-directed blur across the shadow boundary)
            if params.softness_m > 0.005:
                sig_px = params.softness_m / max(res, 1e-3)
                sm = gaussian_filter1d(patch, sigma=max(sig_px, 0.3), axis=1, mode="nearest")
                edge = _boundary_band(mask, width=max(int(sig_px * 2), 1))
                patch[edge] = sm[edge]

            out[y0:y1, x0:x1] = patch

            # move the down-range box edge with the shadow — only under the
            # shadow_included label convention (box = highlight + shadow)
            if abs(dx_edge) > 0.5 and img.meta.shadow_included:
                if downrange_right:
                    x1n = float(np.clip(x1 + dx_edge, x0 + 4, w))
                    nb = YoloBox.from_pixels(b.cls, x0, y0, x1n, y1, w, h)
                else:
                    x0n = float(np.clip(x0 - dx_edge, 0, x1 - 4))
                    nb = YoloBox.from_pixels(b.cls, x0n, y0, x1, y1, w, h)
                new_boxes.append(nb)
                prov.append(BoxProvenance(i, True, 1.0, f"F6: shadow edge moved {dx_edge:+.1f}px"))
            else:
                new_boxes.append(b)
                prov.append(BoxProvenance(i, True, 1.0, "F6: photometric only"))

        data = blend(img.data, out, strength)
        return AugResult(
            data=data,
            labels_override=LabelSet(boxes=new_boxes, provenance=prov),
            info={"boxes_modified": n_modified, "boxes_total": len(labels.boxes)},
        )


def _segment_shadow(patch: np.ndarray, downrange_right: bool) -> dict | None:
    """Otsu-split the box into highlight / shadow; confidence from contrast & layout."""
    p = patch if downrange_right else patch[:, ::-1]
    v = p.ravel()
    if v.size < 32 or float(v.std()) < 1e-3:
        return None
    thr = _otsu(v)
    dark = p < thr
    bright = p >= thr
    if dark.mean() < 0.05 or dark.mean() > 0.95:
        return None
    # shadow should sit down-range (right in canonical view) of the highlight
    xs = np.arange(p.shape[1])
    dark_c = float((dark * xs[None, :]).sum() / max(dark.sum(), 1))
    bright_c = float((bright * xs[None, :]).sum() / max(bright.sum(), 1))
    layout_ok = dark_c > bright_c
    contrast = float(np.clip((p[bright].mean() - p[dark].mean()) / max(p[bright].mean(), 1e-3), 0, 1))
    confidence = contrast * (1.0 if layout_ok else 0.3)
    # keep only the down-range dark component as shadow
    shadow = dark & (xs[None, :] > bright_c)
    mask = shadow if downrange_right else shadow[:, ::-1]
    hmask = bright if downrange_right else bright[:, ::-1]
    return {"mask": mask, "highlight_mask": hmask, "confidence": confidence}


def _rescale_shadow_length(patch: np.ndarray, mask: np.ndarray, downrange_right: bool, kappa: float) -> float:
    """Stretch/compress the shadow region along range by kappa; return edge shift (px)."""
    cols = np.flatnonzero(mask.any(axis=0))
    if len(cols) < 3:
        return 0.0
    c0, c1 = int(cols.min()), int(cols.max()) + 1
    length = c1 - c0
    new_len = max(int(round(length * kappa)), 2)
    if not downrange_right:
        c0, c1 = patch.shape[1] - c1, patch.shape[1] - c0
        seg = patch[:, ::-1][:, c0:c1]
    else:
        seg = patch[:, c0:c1]
    import cv2

    stretched = cv2.resize(seg, (new_len, seg.shape[0]), interpolation=cv2.INTER_LINEAR)
    if downrange_right:
        avail = patch.shape[1] - c0
        nl = min(new_len, avail)
        patch[:, c0 : c0 + nl] = stretched[:, :nl]
        if nl < length:  # shadow shortened: fill the tail with pre-shadow background stats
            bg = float(np.median(patch[:, max(c0 - 3, 0) : c0])) if c0 > 0 else float(np.median(patch))
            patch[:, c0 + nl : c0 + length] = bg
    else:
        view = patch[:, ::-1]
        avail = view.shape[1] - c0
        nl = min(new_len, avail)
        view[:, c0 : c0 + nl] = stretched[:, :nl]
        if nl < length:
            bg = float(np.median(view[:, max(c0 - 3, 0) : c0])) if c0 > 0 else float(np.median(view))
            view[:, c0 + nl : c0 + length] = bg
    return float(new_len - length)


def _boundary_band(mask: np.ndarray, width: int) -> np.ndarray:
    from scipy.ndimage import binary_dilation, binary_erosion

    outer = binary_dilation(mask, iterations=width)
    inner = binary_erosion(mask, iterations=width)
    return outer & ~inner


def _otsu(v: np.ndarray) -> float:
    hist, edges = np.histogram(v, bins=64, range=(0.0, 1.0))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 0.5
    centers = (edges[:-1] + edges[1:]) / 2
    wsum = (hist * centers).sum()
    best_t, best_var, w_b, sum_b = 0.5, -1.0, 0.0, 0.0
    for i in range(64):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += hist[i] * centers[i]
        m_b, m_f = sum_b / w_b, (wsum - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best_var:
            best_var, best_t = var, centers[i]
    return best_t
