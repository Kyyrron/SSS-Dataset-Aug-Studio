# Scientific Encyclopedia — Overview

Every augmentation in this studio corresponds to an identifiable physical
phenomenon of real side-scan sonar (SSS) acquisition. Each family page follows
the same contract:

1. **Physical explanation** — why the phenomenon appears in real acquisitions;
2. **Mathematical model** — the equations implemented;
3. **Implementation** — how the equations become image processing;
4. **Scientific references** — verified, with DOI where available;
5. **Expected visual effect** — what you should observe;
6. **Limitations** — when to use / not use the augmentation;
7. **Validation** — how realism can be checked against real acquisitions,
   with objective metrics.

## Image conventions

Along-track = rows (one row per ping); across-track = columns. Pixels are
float32 in [0, 1] in the **linear intensity** domain (the native domain of
multiplicative sonar physics). The export mapping is **declared** by the
acquisition pipeline (`intensity_mapping: linear | log | gamma`), never
inferred, and is exactly inverted on load; when no mapping is declared the
documented default assumption is **log** (dB waterfall export). dB-valued
effects convert via 10^(dB/10), so each computation runs in its physically
appropriate domain.

**Label convention** (`shadow_included: true`, dataset-level flag): a YOLO
box covers the object's complete acoustic signature — highlight **and**
acoustic shadow. F6 moves the down-range box edge with the shadow only under
this convention.

## Default physical order

scene reflectivity (F7) → shadow scene edit (F6) → platform-motion geometry
(F4) → slant/altitude geometry (F3) → radiometric transfer (F2) → multipath
additions (F8) → speckle (F1, multiplicative — commutes with gain) →
receiver-level artifacts (F5). The order is user-editable; this default
follows the causal chain of image formation.

## Deliberately excluded transformations

- **Rotations other than along-track flip** — a rotated SSS image is
  physically impossible: shadows must extend down-range.
- **Additive Gaussian noise** — envelope-detected sonar noise is
  multiplicative (see F1); providing additive noise would legitimize a
  physically wrong model.
- **Hue/color jitter** — SSS data is single-channel intensity; colormaps are
  display-only.
- **Elastic deformations, mixup/cutmix** — no physical counterpart; mixup may
  be added later strictly as a *comparison baseline*, never as a
  physics-informed augmentation.

Along-track flip (survey direction reversal) and across-track mirror are
physically valid **and are implemented** as the dedicated Geometry section
(G1 mirror, G2 reversal — see `g_geometry.md`): exact symmetries, not
phenomenon models, hence kept apart from F1–F8.
