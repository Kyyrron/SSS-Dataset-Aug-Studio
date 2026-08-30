# F6 — Shadow & highlight modulation

## 1. Physical explanation
Acoustic shadows are the *most diagnostic* cue for object detection in SSS:
a proud target blocks the beam, leaving an unsonified region whose length is
a deterministic function of target height, range and sonar altitude. Shadow
contrast varies with volume reverberation (turbidity), noise floor and
processing; shadow *length* varies with acquisition altitude — the same
target surveyed at 1.5 m vs 3 m altitude in the shallow regime casts a very
different shadow. Under the dataset convention `shadow_included: true` (labels cover
highlight + acoustic shadow — the `shadow_included` dataset flag),
altering shadow length moves the down-range edge of the box; with
`shadow_included: false` F6 modifies pixels only and never touches labels.

## 2. Mathematical model
```
Shadow length:  L_s = H · r_g / (h − H)      (target height H, altitude h)
Altitude ratio: h' = κ·h  ⇒  L_s' = L_s · (h − H)/(κh − H) ≈ L_s / κ  (H ≪ h)
Fill:           I'(x,r) = (1−β)·I(x,r) + β·max(I, floor·μ_bg)   in shadow mask
Softening:      penumbra Gaussian blur of the mask edge (softness in m)
```

## 3. Implementation
Confidence-gated: inside each label box the down-range dark
region is segmented (Otsu on the box's range profile); a gate rejects boxes
whose shadow contrast or geometry is implausible (no edit rather than a wrong
edit). Enabled operations: floor filling (turbidity), penumbra softening and
length scaling by κ = h/h′ with down-range mask stretch/compression; the box
down-range edge follows via `labels_override`.

## 4. References
- Coiras, E. et al. (2007). IEEE Trans. Image Processing 16(2) (shadow
  geometry in SSS image formation).
- Blondel, P. (2009). *The Handbook of Sidescan Sonar*, ch. 7 (shadows and
  target geometry).
- Zou, F. et al. (2025). J. Mar. Sci. Eng. 13(1):162.
  DOI 10.3390/jmse13010162 (shadow cue importance for detection).

## 5. Expected visual effect
Shadows become lighter/softer (turbid conditions) or longer/shorter
(different acquisition altitude); bounding boxes track the modified shadow
extent.

## 6. Limitations
Requires visible in-box shadow contrast (the gate skips otherwise); assumes
shadow extends down-range from the highlight within the same box; single
shadow region per box.

## 7. Validation
Measured L_s vs the geometric prediction over targets of known height in the
S2 ground-truth basin; after κ-scaling, re-measured shadow lengths must match
the L_s(h′) prediction within segmentation tolerance. Detector-level: mAP on
real low/high altitude test slices should improve when training includes
altitude-scaled shadows.
