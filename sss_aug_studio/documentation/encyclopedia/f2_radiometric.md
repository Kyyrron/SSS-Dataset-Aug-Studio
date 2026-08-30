# F2 — Radiometric transfer (TVG residual, absorption, beam pattern)

## 1. Physical explanation
Received level obeys the sonar equation: two-way spreading and absorption
losses, elevation beam-pattern directivity, and grazing-angle-dependent
seabed backscattering strength. The receiver's time-varying gain (TVG)
attempts to invert these terms but never matches the true environment —
absorption at 450 kHz is ~0.1 dB/m (Francois & Garrison 1982) and varies
with temperature/salinity; the grazing-angle mapping depends on altitude,
which at 1–3 m in shallow water varies strongly (thesis contribution C4).
The residual appears as range-dependent brightness structure.

## 2. Mathematical model
```
ΔG(r) [dB] = a·log10(R/R_ref) + b·(R − R_ref) + c
           + 10·log10[ sin^p θ'(r) / sin^p θ(r) ]         (Lambertian term)
           + 10·log10[ B(θ'(r)) / B(θ(r)) ]               (beam pattern)
θ(r) = atan(h / r_g)   flat-seabed grazing angle,  θ' uses h' = h·altitude_factor
B(θ) = exp(−½((θ − θ_tilt)/σ_b)²)   Gaussian elevation main lobe
```
`a` = residual spreading (dB/decade), `b` = absorption error around the
Francois–Garrison nominal (dB/m), `c` = offset. Intensity model with
Lambert's law follows Coiras et al. (2007).

## 3. Implementation
Per side, per column: compute ground range and grazing angle from metadata
(altitude, resolution); build the dB gain curve; apply as a linear per-column
multiplicative gain. Nominal absorption is computed from the full
Francois–Garrison three-term model at the sonar frequency.

## 4. References
- Francois, R.E. & Garrison, G.R. (1982). *Sound absorption based on ocean
  measurements. Part II.* J. Acoust. Soc. Am. 72(6), 1879–1890.
- Coiras, E., Petillot, Y. & Lane, D.M. (2007). *Multiresolution 3-D
  reconstruction from side-scan sonar images.* IEEE Trans. Image Processing
  16(2), 382–390.
- Lurton, X. (2010). *An Introduction to Underwater Acoustics*, 2nd ed.,
  Springer (sonar equation, TVG).

## 5. Expected visual effect
Smooth range-dependent brightening or darkening per side; shifted near/far
range balance reproducing different gain settings, water properties and
altitudes.

## 6. Limitations
Flat-seabed grazing angles; the dB correction acts on approximately linear
8-bit intensities (the declared intensity mapping, inverted on load); no
azimuthal beam-pattern effects.

## 7. Validation
Mean-intensity-vs-range profiles: compare real images recorded at different
gain settings / altitudes (S1 sessions) against augmented outputs; report the
RMS dB residual between real and simulated range profiles.
