# F4 — Platform motion distortion

## 1. Physical explanation
A surface vehicle experiences wave-driven roll and heave and control-driven
yaw and speed variation — unlike a depth-stabilized AUV. Along-track pixel
spacing equals v/PRF, so speed variation locally compresses or stretches the
waterfall; heading deviation slews the ping footprint along-track
proportionally to range; turns fan the swath (inner-side compression); roll
rotates the elevation beam, modulating illumination per side; heave modulates
altitude (delegated to the F3 remap machinery). Attitude-induced distortion
is identified as *especially critical for USVs* by Lei et al. (2026), and is
the defining regime difference of the thesis (C4).

## 2. Mathematical model
One kinematic trajectory drives all coupled terms (physical units):
```
v(t):  band-limited process, std = speed_std_frac·v0, corr. length in m
ψ(t):  heading deviation, band-limited (yaw_std_deg, yaw_corr_m)
       + integrated turn rate v0/R over the turn window
φ(t):  roll = A_φ sin(2πt/T_wave + ϕ) + 30 % broadband residual
h(t):  altitude = h0 + heave(t) (same spectral form as roll)

speed:  in_row = P⁻¹(out_row),  P(y) = Σ v·dt / res_along  (monotone remap)
yaw:    along-track shift  s(y, r) = r·ψ(y)/res_along       (small angle)
roll:   gain(y, r) = B(θ(r) − ±φ(y)) / B(θ(r))              (per side sign)
heave:  per-row across-track remap  r_in = sqrt(r² + 2hΔh + Δh²)
```

## 3. Implementation
The trajectory synthesizer produces per-ping series; a single bidirectional
`FieldWarp` combines the row remap, range-proportional shear and heave column
remap (inverse maps for pixels, analytic forward displacements for labels);
the roll term is a separate multiplicative gain. Strength scales the
displacement field.

## 4. References
- Lei et al. (2026). *Geometric correction of SSS images with
  image-consistent attitude refinement.* arXiv 2604.19901.
- Blondel, P. (2009). *The Handbook of Sidescan Sonar*, Springer
  (motion artifacts).
- Cocchi, L. et al. (2024). *CORAL…* Sensors 24(14), 4544.
  DOI 10.3390/s24144544 (USV regime precedent).

## 5. Expected visual effect
Wavy along-track wobble growing with range; local compression/stretch bands;
coherently curved features during turns; periodic per-side intensity banding
from roll.

## 6. Limitations
Kinematic ray model (no intra-ping Doppler or beamforming); turn fan
approximated by integrated-heading shear; small-angle yaw; rigid sonar mount
(true for the BlueBoat installation).

## 7. Validation
Along-track power spectral density of mean intensity: real recordings in
known sea states (S1/S2 sessions with logged IMU) exhibit wave-band peaks;
augmented imagery generated with the logged roll period/amplitude should
reproduce peak frequency and relative power. Additionally, replaying logged
BlueBoat attitude through the model and comparing against the actually
recorded waterfall gives a direct, per-run validation.
