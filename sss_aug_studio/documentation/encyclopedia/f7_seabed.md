# F7 — Seabed reflectivity & texture context

## 1. Physical explanation
Seabed type dominates the background statistics of SSS imagery: mud, sand,
gravel and vegetated bottoms differ by many dB in backscattering strength
(measured extensively at high frequencies by the APL-UW high-frequency
environmental acoustics program; Jackson & Richardson 2007) and in spatial
texture correlation. A detector trained over one bottom type overfits its
background; shifting mean reflectivity and adding correlated large-scale
patchiness simulates surveying a different (or spatially varying) seabed
while preserving target signatures.

## 2. Mathematical model
```
I'(x, r) = I(x, r) · 10^{(ΔS + σ_f · F(x, r)) / 10}
F: zero-mean, unit-variance Gaussian random field with anisotropic
   correlation lengths (ℓ_along, ℓ_across) in meters
ΔS: mean reflectivity shift [dB];  σ_f: patchiness strength [dB]
background_only: the field is masked out inside label boxes (smooth border)
```

## 3. Implementation
White Gaussian field filtered by an anisotropic Gaussian kernel (lengths
converted to pixels via along/across resolutions), exactly renormalized;
optional smooth box mask (protects target/shadow signatures, decision:
background-context mode). Applied multiplicatively in the linear domain.

## 4. References
- Jackson, D.R. & Richardson, M.D. (2007). *High-Frequency Seafloor
  Acoustics.* Springer (bottom-type backscatter levels).
- Lyons, A.P. & Abraham, D.A. (1999). JASA 106(3) (spatial statistics of
  shallow seafloor backscatter).

## 5. Expected visual effect
Overall brighter/darker background; slowly varying patchiness resembling
sediment transitions; with `background_only`, targets keep their original
contrast against the changed context.

## 6. Limitations
Log-normal texture is a context model, not a bedform simulator (no sand
ripples with directional shadowing — see future work); reflectivity shift is
spatially unstructured apart from the correlated field. The dB shift is
applied to approximately linear intensities recovered by inverting the
declared intensity mapping on load, so it is exact only to the extent that
mapping describes the export.

## 7. Validation
Compare background mean dB and autocovariance lengths against patches of
real imagery over known bottom types (S1 sessions over sand vs silt);
augmented parameter ranges should stay inside the observed real envelope.
