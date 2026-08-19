# G — Geometry section: exact acquisition symmetries

Unlike the physics families (F1–F8), which *model phenomena*, the G-families
are **exact geometric symmetries** of side-scan sonar acquisition: they
produce images that a real survey *would* have produced under a different
acquisition direction, with zero approximation. They live in the dedicated
**Geometry** section of the Library and integrate with profiles, preview and
generation like any other family.

---

## G1 — Across-track mirror

### 1. Physical explanation
Surveying the same scene from the reciprocal track offset assigns the scene
to the opposite sonar channel: what the starboard channel recorded, a
port-side pass records as its exact column reversal. Since each side's
canonical range axis maps onto the other side's range axis, **acoustic
shadows remain strictly down-range** after mirroring — the transform is
physically consistent by construction (unlike arbitrary rotations, which are
excluded; see `00_overview.md`).

### 2. Mathematical model
```
I'(y, x) = I(y, W − 1 − x)
layout:  single_port ↔ single_starboard
dual:    port/starboard contents swap; nadir center c → 1 − c
labels:  cx → 1 − cx
```

### 3. Implementation
Exact column-reversal `FieldWarp` (an involution: applying twice is the
identity, covered by a test). Layout and declared-nadir metadata follow via
`AugResult.meta_override`. For the standard centered dual waterfall the
nadir position is preserved exactly; an off-center nadir mirrors with its
content, which is the geometrically correct behavior.

### 4. References
- Blondel (2009), *The Handbook of Sidescan Sonar*, Springer, ch. 2
  (acquisition geometry). DOI 10.1007/978-3-540-49886-5.

### 5. Expected visual effect
Left/right swapped waterfall; boxes mirrored; single-side images change
their declared side (visible in the Explorer metadata table).

### 6. Limitations
None geometric — the symmetry is exact. Real port/starboard *hardware*
asymmetries (transducer gain imbalance) are not mirrored; add a per-side
radiometric instance if that matters for your dataset.

### 7. Validation
Self-validating: involution test (mirror ∘ mirror = identity) and label
mirror-consistency test run in CI (`test_v02_update.py`).

---

## G2 — Along-track reversal

### 1. Physical explanation
The same survey line run in the opposite direction records the identical
scene with reversed ping order. Every per-ping physical property — range
geometry, radiometry, shadow direction (across-track!) — is preserved
exactly; only the along-track ordering and the vehicle heading change.

### 2. Mathematical model
```
I'(y, x) = I(H − 1 − y, x);   labels: cy → 1 − cy;   heading ψ → ψ + 180°
```

### 3. Implementation
Exact row-reversal `FieldWarp` (involution); heading metadata rotated by
180° when present (`meta_override`).

### 4. References
- Blondel (2009), *The Handbook of Sidescan Sonar*, Springer, ch. 2
  (survey line geometry). DOI 10.1007/978-3-540-49886-5.

### 5. Expected visual effect
Vertically flipped waterfall; boxes follow; across-track structure
untouched.

### 6. Limitations
Exact for time-stationary scenes. Along-track-asymmetric artifacts already
burned into the source image (e.g. a turn fan) reverse with the pixels —
which is exactly what the reversed acquisition would have recorded.

### 7. Validation
Involution + label consistency tests in CI; heading update covered by test.
