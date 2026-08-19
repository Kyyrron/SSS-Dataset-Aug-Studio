# F1 — Speckle & reverberation statistics

## 1. Physical explanation
The echo from an unresolved seabed patch is the coherent sum of contributions
from many random scatterers within the resolution cell. Under fully developed
conditions the envelope is Rayleigh distributed (exponential intensity). For
high-resolution sonars over spatially structured shallow seabeds, the local
mean backscatter itself fluctuates from patch to patch, producing
heavier-than-Rayleigh tails; the K-distribution — a gamma-modulated Rayleigh
process — is the standard physical model (Abraham & Lyons 2002; measured on
shallow seafloors by Lyons & Abraham 1999). Speckle is **multiplicative**:
its magnitude scales with the local mean intensity.

## 2. Mathematical model
```
I'(x, r) = I(x, r) · T(x, r) · G(x, r)
G ~ Gamma(L, 1/L)      unit-mean speckle, L effective looks (Var = 1/L)
T ~ Gamma(ν, 1/ν)      unit-mean texture (K component), spatially correlated
                        over length ℓ_T; T ≡ 1 in the Rayleigh regime
```
Small ν ⇒ heavy tails (structured seabed); L→∞ ⇒ noiseless.

## 3. Implementation
Per-pixel Gamma sampling (`numpy.random.Generator.gamma`), optional small
Gaussian kernel for resolution-cell correlation with exact mean/variance
restoration; the texture field is an uncorrelated Gamma field smoothed to the
correlation length ℓ_T (converted from meters using across-track resolution)
and renormalized. Applied in the linear domain, after gain stages (valid:
multiplicative noise commutes with multiplicative gain).

## 4. References
- Abraham, D.A. & Lyons, A.P. (2002). *Novel physical interpretations of
  K-distributed reverberation.* IEEE J. Oceanic Eng. 27(4), 800–813.
  DOI 10.1109/JOE.2002.804324.
- Lyons, A.P. & Abraham, D.A. (1999). *Statistical characterization of
  high-frequency shallow-water seafloor backscatter.* J. Acoust. Soc. Am.
  106(3), 1307–1315. DOI 10.1121/1.428034.

## 5. Expected visual effect
Fine multiplicative grain; with the K option, patchy clusters of bright
clutter that resemble textured/rough seabed and stress detector
false-positive behavior.

## 6. Limitations
Statistics are stationary per image (no mixed-sediment segmentation); no
coherent facet glints; the smoothed-gamma texture matches first- and
second-order statistics but is only approximately gamma-marginal.

## 7. Validation
Fit Rayleigh/K to homogeneous background patches of real Omniscan imagery and
of augmented output; compare shape parameter ν, Kolmogorov–Smirnov distance,
and tail exceedance P(I > kμ) for k ∈ {2, 3, 5}. Augmented ν should fall
inside the envelope of ν values measured across real sessions.
