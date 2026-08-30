# Scientific documentation

## Purpose and epistemic stance

Standard image augmentation (rotations, color jitter, additive Gaussian
noise) violates the physics of side-scan sonar image formation and can teach
a detector invariances that do not exist at sea (a rotated shadow is
impossible; sonar noise is multiplicative). This studio takes the opposite
stance: **every transform is the image-domain expression of an identified
physical phenomenon**, parameterized in physical units, referenced to
verified literature, and bounded to ranges observable in the thesis regime
(small USV, 450 kHz SSS, 1–3 m altitude, shallow enclosed basins).

The intended effect on the detector is domain generalization across the
factors that actually vary between training data and deployment: sea state,
altitude, gain/water properties, seabed type, turbidity, link quality, and
basin multipath.

## Family summary

| # | Family | Phenomenon | Key parameters (units) | Labels |
|---|--------|-----------|------------------------|--------|
| F1 | Speckle & reverberation | Rayleigh/K multiplicative envelope statistics | looks, ν, ℓ_T (m) | unchanged |
| F2 | Radiometric transfer | TVG residual, absorption error, Lambert/beam pattern | dB/decade, dB/m, altitude factor | unchanged |
| F3 | Slant & altitude geometry | FBR altitude error → across-track remap, gap breathing | δ offset/drift/noise (m) | warped |
| F4 | Platform motion | speed/yaw/roll/heave of a surface craft | std fractions, deg, m, s, turn radius (m) | warped |
| F5 | Ping loss & artifacts | link dropouts, gain striping, interference | events/100 rows, burst, dB | warped (remove mode) |
| F6 | Shadow modulation | turbidity fill, penumbra, altitude-scaled length | floor, softness (m), κ = h/h′ | down-range edge moved |
| F7 | Seabed reflectivity | bottom-type level + correlated patchiness | ΔS (dB), σ_f (dB), ℓ (m) | unchanged (background-only mask) |
| F8 | Shallow multipath | surface ghosts, 2nd bottom, wall echoes, nadir noise | gains (dB), wall distance/width (m) | unchanged |
| G1 | Across-track mirror | reciprocal-track acquisition (exact symmetry) | — | mirrored |
| G2 | Along-track reversal | reversed survey line (exact symmetry) | — | reversed |

Physical application order (default): F7 → F6 → F4 → F3 → F2 → F8 → F1 → F5 —
scene properties first, then acquisition geometry, then the radiometric
chain, then propagation additions, and receiver-level statistics last.

## Fidelity boundaries (read before trusting)

* **Declared intensity mapping**: the export mapping is declared by the
  acquisition pipeline (`intensity_mapping: linear | log | gamma`) and is
  exactly inverted on load, so dB-domain operations (F2, F7, F5 striping)
  run in the correct domain by construction. When no mapping is declared the
  documented default assumption is **log/dB** (the normal SSS waterfall
  export); if a dataset was actually exported linearly, declare it —
  otherwise the inversion introduces a monotone contrast error.
* F1's two gamma factors carry exact marginals; what is approximate is the
  correlation function, which the memoryless map warps by under 10% of the
  length scale.
* F3/F4 use flat-seabed, kinematic ray geometry — no bathymetry, no
  intra-ping effects.
* F8 is incoherent and phenomenological (no ray tracing) — designed to
  produce *hard negatives*, not calibrated echo levels.

Each limitation is restated on the corresponding encyclopedia page with its
validation recipe.

## Validation protocol (thesis experiments)

1. **Statistical realism** (per family): match measurable statistics between
   augmented output and real Omniscan 450 imagery — background K/Rayleigh
   fits (F1), mean-intensity-vs-range profiles (F2), along-track PSD wave
   peaks against logged IMU (F4), dropout/burst histograms from ping counters
   (F5), shadow length vs geometric prediction on ground-truth targets (F6),
   wall-echo geometry vs surveyed basin walls (F8).
2. **Replay validation** (strongest, F3/F4): drive the models with *logged*
   BlueBoat attitude/altitude and compare against the actually recorded
   waterfall of the same transect.
3. **Detector-level ablation**: train YOLO under (a) no augmentation,
   (b) standard augmentation, (c) physics-informed (this tool), (d) b + c;
   evaluate on held-out **real** imagery stratified by condition (calm vs
   waves, open vs near-wall). Primary metric mAP@50; secondary: per-condition
   recall and false positives per hectare near walls (thesis metric).
4. **Reproducibility**: every generated dataset ships its manifest; any
   reviewer can regenerate it byte-for-byte from config + seed.

## Relation to the thesis

The studio operationalizes contribution **C4** (regime-specific effects:
wall multipath, altitude-coupled swath, surface-attitude distortions) as a
data-generation capability, supports **C2** (detector robustness across the
baseline ladder's varying conditions), and its manifest/statistics artifacts
feed the open-release contribution **C5**.
