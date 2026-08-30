# Mathematical appendix

Complete equation set implemented by the studio. Conventions: along-track
row index y (pings), across-track ground range r [m], slant range R [m],
altitude h [m], intensity I ∈ [0,1] linear.

## A. Geometry (physics/geometry.py)

Slant/ground:            R = sqrt(r² + h²),  r = sqrt(R² − h²)
Grazing angle (flat):    θ(r) = atan(h / r)
Shadow length:           L_s = H·r / (h − H)          (target height H < h)
Altitude-error remap:    r_in(r_out) = sqrt(r_out² + 2hδ + δ²)
                         (feature at true r_t appears at sqrt(r_t² − 2hδ − δ²))

## B. Acoustics (physics/acoustics.py)

Francois–Garrison absorption α(f, T, S, z, pH) [dB/km]: full three-term
model (boric acid + magnesium sulfate + pure water) as published (JASA 1982);
at 450 kHz, 13 °C, S 35, shallow: α ≈ 0.08–0.15 dB/m.

Lambertian backscatter:  BS(θ) ∝ sin^p θ  (p ≈ 2)
Elevation beam pattern:  B(θ) = exp(−½((θ − θ_tilt)/σ_b)²)

## C. Statistics (physics/statistics.py)

Speckle (L looks):       G ~ Gamma(L, 1/L),  E[G]=1, Var[G]=1/L
K texture:               T ~ Gamma(ν, 1/ν),  E[T]=1, Var[T]=1/ν
Correlated gamma:        X = F⁻¹_{Gamma(k,1/k)}(Φ(Z)),  Z the unit-variance
                         Gaussian field below — monotone and memoryless, so
                         the marginal is exact; 1/e length ≈ 1.95·σ_kernel
K composite:             I' = I·T·G  (heavy tails as ν → small)
Correlated field:        F = (K_ℓ * W)/std, W white Gaussian (anisotropic ℓ)
AR(1) dB stripes:        g_{y+1} = ρ g_y + ε,  ρ = exp(−res_along/ℓ),
                         Var[g] = σ² (stationary), applied as 10^{g/10}

## D. Radiometric residual (F2)

ΔG(r) [dB] = a·log₁₀(R/R_ref) + b·(R−R_ref) + c
           + 10·log₁₀[sin^p θ'(r)/sin^p θ(r)] + 10·log₁₀[B(θ')/B(θ)]
I' = I · 10^{ΔG/10}

## E. Platform motion (F4)

Along-track sampling:    row_pitch = v(t)/PRF;  P(y) = Σ v dt / res_along
Speed remap:             in_row = P⁻¹(out_row)   (monotone)
Yaw shear:               s(y, r) = r·ψ(y)/res_along   [px along-track]
Turn:                    ψ̇ = v₀/R_turn over the turn window (integrated)
Roll gain:               gain(y,r) = B(θ(r) ∓ φ(y))/B(θ(r))  per side
Heave:                   Δh(y) → across-track remap of §A with δ = Δh(y)

## F. Shadow scaling (F6)

Altitude κ = h/h′:       L_s' = L_s (h − H)/(κh − H) ≈ L_s/κ  for H ≪ h
Fill:                    I' = (1−β)I + β·max(I, floor·μ_bg)  inside mask
Box edit: down-range box edge displaced by (L_s' − L_s), clipped to image.

## G. Multipath (F8)

Surface ghost:           I' = I + 10^{g/10}·(K_σ * I)(y, r − Δr),  Δr ≈ D − h
Second bottom:           feature at r → additional return near 2r, gain g₂
Wall ridge:              A(y,r) = μ_I·10^{G_w/10}·exp(−(r−r_w(y))²/2w²)·G_speckle
                         r_w(y) = d_wall + correlated wander
