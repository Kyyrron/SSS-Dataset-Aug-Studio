# Augmentation strategies

One section per implemented family. For each: **(1)** physical origin,
**(2)** mathematical model, references actually used (DOI when it exists),
**(3)** the core Python statements performing the transformation (excerpted
from the module named in the header — kept synchronized with the code),
**(4)** expected visual effect, **(5)** limitations, with an explicit
**rigor class**: ⚖️ *physically rigorous model* vs 🔧 *engineering
approximation*.

Conventions: linear intensity `[0,1]`, rows = pings, per-side canonical
range-increasing views; all randomness from the deterministic per-(image,
instance, copy) RNG. See `docs/math_appendix.md` for the complete equation
set and `sss_aug_studio/documentation/bibliography.bib` for full citations.

---

## G1 — Across-track mirror (`augmentations/geometric.py`) — ⚖️ exact

**Physical origin.** Reciprocal-track acquisition: the scene recorded by the
starboard channel is the exact column reversal of a port-side acquisition;
shadows remain strictly down-range on the swapped side.

**Model.** `I'(y,x) = I(y, W−1−x)`; layout `single_port ↔ single_starboard`;
dual nadir center `c → 1−c`; labels `cx → 1−cx`.
*Ref.* Blondel (2009), *Handbook of Sidescan Sonar*, ch. 2. DOI
10.1007/978-3-540-49886-5.

**Core code.**
```python
out = img.data[:, ::-1].copy()
warp = _flip_warp(h, w, axis=1)          # exact bidirectional column reversal
fields["layout"] = "single_starboard" if layout == "single_port" else "single_port"
fields["nadir_center_frac"] = 1.0 - img.meta.nadir_center_frac   # dual
meta = img.meta.model_copy(update=fields)
```

**Effect.** Mirrored waterfall, mirrored boxes, nadir preserved for centered
dual layouts. **Limitations.** Exact symmetry; hardware port/starboard gain
asymmetry is not mirrored (model with a radiometric instance if needed).

## G2 — Along-track reversal (`augmentations/geometric.py`) — ⚖️ exact

**Physical origin.** The survey line replayed in the opposite direction:
ping order reverses, every per-ping property preserved.

**Model.** `I'(y,x) = I(H−1−y, x)`; labels `cy → 1−cy`; heading `ψ → ψ+180°`.
*Ref.* Blondel (2009), ch. 2. DOI 10.1007/978-3-540-49886-5.

**Core code.**
```python
out = img.data[::-1, :].copy()
warp = _flip_warp(h, w, axis=0)
meta = img.meta.model_copy(update={"heading_deg": (img.meta.heading_deg + 180.0) % 360.0})
```

**Effect.** Vertically flipped waterfall, boxes follow. **Limitations.**
Exact for time-stationary scenes.

---

## F1 — Speckle & reverberation (`augmentations/speckle.py`) — ⚖️ model & marginals

**Physical origin.** Coherent summation of many unresolved scatterers →
Rayleigh envelope (exponential intensity); spatially structured shallow
seabeds modulate the local mean → K-distributed heavy tails. Multiplicative
by nature.

**Model.** `I' = I·T·G`, `G ~ Gamma(L, 1/L)` unit mean (Var 1/L);
`T ~ Gamma(ν, 1/ν)` unit mean, correlated over ℓ_T; Rayleigh regime `T ≡ 1`.
Both correlated gamma factors come from a memoryless nonlinear transformation
of a Gaussian process, `x = F⁻¹_Gamma(Φ(z))`, which leaves the marginal exact
at every shape and correlation length while the Gaussian kernel sets the
correlation. *Refs.* Abraham & Lyons (2002), IEEE JOE 27(4),
DOI 10.1109/JOE.2002.804324; Lyons & Abraham (1999), JASA 106(3),
DOI 10.1121/1.428034; Tough & Ward (1999), J. Phys. D 32(23),
DOI 10.1088/0022-3727/32/23/314; Ghosh & Henderson (2003), ACM TOMACS 13(3),
DOI 10.1145/937332.937336.

**Core code.**
```python
z = correlated_gaussian_field(rng, shape, 1.0, corr_px)       # unit-variance Gaussian
nodes = gamma.ppf(ndtr(z_nodes), a=k, scale=1.0 / k)          # tabulated F^-1 . Phi
x = np.interp(z, z_nodes, nodes)                              # exact Gamma(k, 1/k)
out = img.data * t * g                                        # k = nu for T, L for G
```

**Effect.** Multiplicative grain; K option adds patchy bright clutter.
**Limitations.** Stationary per image; no coherent facet glints. Both are
scope limits — the marginals are exact, and the correlation warping the
monotone map introduces is bounded (<10% of the length scale, ⚖️).

## F2 — Radiometric transfer (`augmentations/radiometric.py`) — ⚖️ sonar-equation terms

**Physical origin.** TVG never exactly inverts two-way spreading +
absorption (Francois–Garrison, ≈0.1 dB/m at 450 kHz) + elevation beam
pattern + grazing-angle backscatter; the residual is range-structured gain.

**Model.** `ΔG(r)[dB] = a·log₁₀(R/R₀) + b·(R−R₀) + c +
10log₁₀[sin^pθ'/sin^pθ] + 10log₁₀[B(θ')/B(θ)]`, `I' = I·10^{ΔG/10}`.
*Refs.* Francois & Garrison (1982), JASA 72(6), DOI 10.1121/1.388673;
Coiras et al. (2007), IEEE TIP 16(2), DOI 10.1109/TIP.2006.888337;
Lurton (2010).

**Core code.**
```python
theta = np.arctan2(h_alt, r_g)                     # flat-seabed grazing angle
gain_db = (a * np.log10(R / R_ref) + b * (R - R_ref) + c
           + 10*np.log10(lambertian_gain(theta2, p) / lambertian_gain(theta, p))
           + 10*np.log10(elevation_beam_gain(theta2) / elevation_beam_gain(theta)))
view *= 10.0 ** (gain_db / 10.0)                   # per-column, per side
```

**Effect.** Smooth per-side range-dependent brightness changes.
**Limitations.** Flat-seabed grazing angles; the dB correction acts on
approximately linear intensities recovered by inverting the declared
intensity mapping, which is only approximately invertible (🔧); no azimuthal
beam-pattern effects.

## F3 — Slant-range & altitude geometry (`augmentations/slant_geometry.py`) — ⚖️ geometry, 🔧 flat seabed

**Physical origin.** Ground-range projection uses the FBR altitude
estimate; altitude error/variation δ produces a nonlinear across-track
remap strongest near nadir and nadir-gap "breathing".

**Model.** `r_in(r_out; y) = sqrt(r_out² + 2hδ(y) + δ(y)²)`,
`δ(y) = δ₀ + δ₁·y/H + n(y)` (correlated).
*Refs.* Al-Rawi et al. (2017) (FBR); Blondel (2009) ch. 3.

**Core code.**
```python
delta = offset + drift * (rows / h) + colored_noise_1d(rng, h, noise_std, corr_rows)
r_in = np.sqrt(np.maximum(r_out**2 + 2*h_alt*delta[:, None] + delta[:, None]**2, 0.0))
warp = per_side_column_remap(r_in / res)            # bidirectional FieldWarp
```

**Effect.** Near-nadir squeeze/stretch, wobbling gap width. **Limitations.**
Flat seabed, single altitude per ping (🔧).

## F4 — Platform motion (`augmentations/platform_motion.py`) — ⚖️ kinematics, 🔧 turn fan

**Physical origin.** Surface craft: wave roll/heave, control yaw/speed
variation. Along-track pitch = v/PRF; yaw slews footprints ∝ range; roll
rotates the elevation beam; heave modulates altitude. USV-critical per Lei
et al. (2026).

**Model.** One synthesized trajectory drives: monotone row remap
`P(y)=Σv·dt/res`; shear `s(y,r)=r·ψ(y)/res`; roll gain `B(θ∓φ)/B(θ)`;
heave → F3 remap with δ=Δh(y). *Refs.* Lei et al. (2026), arXiv 2604.19901;
Blondel (2009); Cocchi et al. (2024), DOI 10.3390/s24144544.

**Core code.**
```python
traj = synthesize_trajectory(rng, n_rows, meta, params)      # v, psi, phi, heave
row_map = np.interp(np.arange(n_out), cum_pitch, np.arange(n_rows))
shear_px = r_m[None, :] * traj.psi[:, None] / res_along      # range-prop. yaw shear
gain = elevation_beam_gain(theta - sign*traj.phi[:, None]) / elevation_beam_gain(theta)
warp = compose(row_remap, shear_warp, heave_remap)
```

**Effect.** Range-growing wobble, compression bands, turn curvature, roll
banding. **Limitations.** Kinematic ray model; integrated-heading shear
approximates the turn fan (🔧); small-angle yaw.

## F5 — Ping loss & sensor artifacts (`augmentations/ping_artifacts.py`) — 🔧 phenomenological, ⚖️ AR(1) stripes

**Physical origin.** Telemetry dropouts (black/hold/removed pings),
per-ping receiver gain jitter (correlated dB striping), external acoustic
interference.

**Model.** Bursts: Poisson events × geometric length; stripes: AR(1) in dB,
stationary std σ; interference: bright partial-range streaks.
*Refs.* Blondel (2009) ch. 5; Abraham (2019), DOI 10.1007/978-3-319-92983-5.

**Core code.**
```python
starts = rng.poisson(lam=rate * h / 100)                     # burst events
keep = np.setdiff1d(np.arange(h), removed)                   # 'remove' mode
warp = row_remap_warp(keep.astype(np.float32), h, w)          # labels follow exactly
g[y+1] = rho * g[y] + eps[y]                                  # AR(1) dB striping
out *= 10.0 ** (g[:, None] / 10.0)
```

**Effect.** Black/held rows, subtle banding, streaks; `remove` compresses
along-track. **Limitations.** Independent of platform state (real link loss
correlates with distance/maneuvers).

## F6 — Shadow & highlight modulation (`augmentations/shadow.py`) — ⚖️ shadow geometry, 🔧 segmentation

**Physical origin.** Shadow length is deterministic geometry
`L_s = H·r/(h−H)`; contrast varies with turbidity/noise; surveying at a
different altitude rescales L_s. Under the `shadow_included` convention the
box's down-range edge follows.

**Model.** `κ = h/h'` ⇒ `L_s' ≈ L_s/κ` (H ≪ h); fill
`I' = (1−β)I + β·max(I, floor·μ_bg)`; penumbra blur.
*Refs.* Coiras et al. (2007), DOI 10.1109/TIP.2006.888337; Blondel (2009)
ch. 7; Zou et al. (2025), DOI 10.3390/jmse13010162.

**Core code.**
```python
seg = segment_shadow_in_box(patch, downrange_right)   # Otsu + confidence gate
if seg is None or seg["confidence"] < params.confidence_gate: skip
new_len = seg_len / kappa                              # altitude ratio κ = h/h'
patch = stretch_downrange(patch, mask, new_len)
if abs(dx_edge) > 0.5 and img.meta.shadow_included:    # convention gate
    nb = YoloBox.from_pixels(b.cls, x0, y0, x1 + dx_edge, y1, w, h)
```

**Effect.** Lighter/softer or longer/shorter shadows, box edge tracking.
**Limitations.** Needs in-box shadow contrast; the segmentation-confidence
gate skips a box rather than guessing; single dominant shadow per box; Otsu
segmentation is heuristic (🔧). The down-range box edge moves only where the
dataset's `shadow_included` flag is true.

## F7 — Seabed reflectivity & texture (`augmentations/seabed.py`) — ⚖️ level shift, 🔧 texture model

**Physical origin.** Bottom types differ by many dB in backscattering
strength and in spatial correlation; detectors overfit their training
background.

**Model.** `I' = I·10^{(ΔS + σ_f·F)/10}` with F an anisotropic correlated
unit-variance Gaussian field; optional background-only masking protects
target signatures. *Refs.* Jackson & Richardson (2007), DOI
10.1007/978-0-387-36945-7; Lyons & Abraham (1999), DOI 10.1121/1.428034.

**Core code.**
```python
F = correlated_gaussian_field(rng, shape, (l_along_px, l_across_px))
gain_db = shift_db + sigma_db * F
if params.background_only: gain_db *= (1.0 - smooth_box_mask(labels))
out = img.data * 10.0 ** (gain_db / 10.0)
```

**Effect.** Brighter/darker background, sediment-like patchiness.
**Limitations.** Log-normal context model, no bedforms/ripples (🔧; see
future work); the dB shift acts on approximately linear intensities recovered
by inverting the declared intensity mapping on load.

## F8 — Shallow-water multipath (`augmentations/multipath.py`) — 🔧 incoherent hard-negative generator

**Physical origin.** In 3–8 m basins, surface bounces, second bottom
returns and vertical quay walls arrive inside the recording window — the
dominant false-positive source of the thesis regime (C4).

**Model.** Ghost `I' = I + 10^{g/10}(K_σ*I)(x, r−Δr)`, `Δr ≈ D−h`; second
bottom at `2r`; wall = speckled Gaussian ridge at wandering distance
`r_w(x)`; nadir water-column noise. *Refs.* Blondel (2009) ch. 5; Lurton
(2010); Cocchi et al. (2024), DOI 10.3390/s24144544.

**Core code.**
```python
ghost[:, shift:] = src[:, :n-shift]                        # Δr ≈ depth − altitude
view += g * gaussian_filter1d(ghost, sig, axis=1)
profile = np.exp(-0.5*((cols - center[:,None]) / width_px)**2)   # wall ridge
view += amp * profile * gamma_speckle(rng, view.shape, looks=1.5)
```

**Effect.** Faint displaced copies, bright wandering wall ridge, noisy
nadir. **Limitations.** Incoherent, phenomenological wall (no ray tracing);
calibrated echo levels are out of scope (🔧 by design — it manufactures hard
negatives, not physics-grade echoes).

---

## Synchronization note

This document quotes the implementation as of v0.4.0. When a family module
changes, update the corresponding section here and the encyclopedia page in
the same commit (`docs/developer_guide.md` §conventions). This is enforced:
`tools/docs_sync_check.py`, run from `.githooks/pre-commit`, blocks a commit
that changes a file under `augmentations/` without both. It maps a module to
its section by reading the section headings below, so each heading must keep
naming its module as ``(`augmentations/<module>.py`)``.
