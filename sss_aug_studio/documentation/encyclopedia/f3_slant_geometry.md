# F3 — Slant-range & altitude geometry

## 1. Physical explanation
Raw SSS pings are sampled in slant range; ground-range projection requires
the sonar altitude, estimated per ping by first-bottom-return (FBR) detection
(Al-Rawi et al. 2017 — the project's own FBR pipeline). Altitude estimation
errors, and real altitude variation over uneven shallow seabeds, produce a
nonlinear across-track remap that is strongest near nadir, and change the
nadir-gap width ("gap breathing") — a defining altitude-coupled effect of the
1–3 m shallow regime.

## 2. Mathematical model
A feature at true ground range r_t (slant R, true altitude h) re-projected
with erroneous altitude h_a = h + δ appears at
```
r_w = sqrt(R² − h_a²) = sqrt(r_t² − 2hδ − δ²)
```
so the output column at ground range r_out samples the input at
```
r_in(r_out; y) = sqrt(r_out² + 2·h·δ(y) + δ(y)²)
δ(y) = δ0 + δ1·y/H + n(y)   offset + drift + correlated noise (corr. length in m)
```

## 3. Implementation
Per-row 1-D across-track resampling within each side (canonical
range-increasing view), built analytically in both directions: the inverse
map feeds `cv2.remap`, the forward map moves YOLO box extents through the
identical model. δ is clipped to keep the square root defined near nadir.

## 4. References
- Al-Rawi, M. et al. (2017). *First-bottom-return detection for sidescan
  sonar imagery* (project reference base; altitude estimation).
- Blondel, P. (2009). *The Handbook of Sidescan Sonar*, Springer, ch. 3
  (slant-range correction geometry).

## 5. Expected visual effect
Across-track squeeze/stretch concentrated near the nadir edges; wobbling
nadir-gap width along track; far range nearly unaffected.

## 6. Limitations
Flat-seabed assumption; single altitude per ping (no across-track bathymetry);
large |δ| near nadir is clipped.

## 7. Validation
Compare with pairs of real images ground-projected with deliberately
perturbed FBR altitude in the project's own pipeline: the augmentation applied
to the correctly projected image should approximate the wrongly projected one
(pixel-wise correlation over the near-range half of each side).
