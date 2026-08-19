# F8 — Shallow-water multipath & water-column artifacts

## 1. Physical explanation
In deep water the direct bottom return dominates; in a 3–8 m enclosed basin
(the thesis regime) the surface and vertical structures are close enough
that multiply reflected paths arrive within the recording window:
bottom→surface→receiver ghosts (delayed, attenuated copies of the seabed
return), second bottom returns near nadir, and quay/breakwater wall echoes
that appear as bright quasi-linear features at a slant range equal to the
horizontal wall distance. Thesis contribution C4 identifies wall multipath
as the dominant false-positive driver in port surveys; this family
manufactures those hard negatives deliberately.

## 2. Mathematical model
```
ghost:    I' = I + g_m · (K_σ * I)(x, r − Δr)
          surface bounce: Δr ≈ (D − h)      (near-vertical bounce, ground-range approx.)
          second bottom:  feature at r echoes near 2r, gain g_2
wall:     ridge at r_w(x) = d_wall + w(x)  (wander w: correlated, std in m)
          across-range Gaussian profile (width in m), speckled amplitude
          A = μ_img · 10^{G_w/10}
nadir:    additive water-column speckle noise inside the nadir band
```
All gains in dB relative to the direct return / image mean.

## 3. Implementation
Ghosts: range-shifted copies smeared by a 1-D Gaussian (smear in m),
added incoherently; second bottom uses index r→2r mapping. Wall echo: a
per-row Gaussian ridge at the (wandering) wall distance filled with
low-look gamma speckle; side selectable (port/starboard/both). Nadir noise
uses the detected/declared nadir band (dual layout).

## 4. References
- Blondel, P. (2009). *The Handbook of Sidescan Sonar*, Springer, ch. 5
  (multipath artifacts in shallow water).
- Lurton, X. (2010). *An Introduction to Underwater Acoustics*, 2nd ed.,
  Springer (multipath propagation).
- Cocchi, L. et al. (2024). Sensors 24(14):4544 (harbor USV operations).

## 5. Expected visual effect
Faint displaced copies of strong seabed features; a bright, slightly
wandering near-linear ridge (the wall); noisier nadir band. These are
exactly the structures that fool detectors in enclosed basins.

## 6. Limitations
Incoherent geometric model (no phase interference or ray tracing); the wall
echo is phenomenological; the surface-ghost delay uses a ground-range
approximation of the bounce geometry.

## 7. Validation
Catalogue wall-echo instances in real S1 port imagery: measure ridge
distance vs known wall geometry, ridge width and excess level; tune
parameter defaults to the measured ranges. Detector-level: false-positive
rate near real walls should drop for models trained with F8-augmented data
(thesis experiment E3/C4).
