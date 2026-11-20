# SSS-Dataset-Aug-Studio — design

*Merged on 2026-11-18 (session 11) from six documents, each kept **verbatim** as one part below with its headings
moved down one level, so a citation such as "`docs/architecture.md` §7" is now "`docs/DESIGN.md` Part 1, §7". The
per-family physics stays in `AUGMENTATION_STRATEGIES.md` (checked by `tools/docs_sync_check.py`) and in the in-app
encyclopedia (`sss_aug_studio/documentation/encyclopedia/`); the user workflow is in `docs/user_manual.md`; the
release history is in `docs/HISTORY.md`. The module is **optional**: nothing in the project chain depends on it.
Augmentation for the simulation-trained headline detector (level and per-ping gain, superproject
`SIM_VALIDITY_CONDITIONS.md` §5.7) is Perception's training step to define; this studio is one possible tool.*

| Part | Content |
|---|---|
| Part 1 | Architecture (was `docs/architecture.md`) |
| Part 2 | Extending the studio: developer guide (was `docs/developer_guide.md`) |
| Part 3 | Scientific documentation: fidelity boundaries, validation protocol (was `docs/scientific_documentation.md`) |
| Part 4 | Mathematical appendix: the implemented equation set (was `docs/math_appendix.md`) |
| Part 5 | Bibliography (was `docs/bibliography.md`) |
| Part 6 | Future work (was `docs/future_work.md`) |


## Part 1 — Architecture (was `docs/architecture.md`)

## Architecture — Physics-Informed SSS Augmentation Studio

Version 0.4.0.

### 0. How this document is maintained

`architecture.md` always describes the **current release**. Release deltas are
folded into it at the release commit; no new `architecture_update_*` file is
created. The superseded v0.2.0 / v0.2.1 / v0.3.0 delta documents are kept
in `docs/history/` as a record of what changed at each release, and are not
maintained. (2026-11-18: this part is now `docs/DESIGN.md` Part 1, and the deltas are `docs/HISTORY.md`.)

### 1. Layering

```
┌─────────────────────────────────────────────────────────────┐
│ gui/            PySide6: main window, docks, preview, forms │  GUI layer
├─────────────────────────────────────────────────────────────┤
│ generation/     batch engine, distributions, headless CLI   │
│ profiles/       named pipeline configurations + presets     │  application
│ datasets/       YOLO indexing, modular metadata readers     │  services
├─────────────────────────────────────────────────────────────┤
│ augmentations/  10 families, 9 modules: F1-F8 physics +     │
│                 G1/G2 geometry (1 module each; geometric.py │
│                 carries both G-families)                    │
├─────────────────────────────────────────────────────────────┤
│ core/           SonarImage, meta, warps, labels, pipeline,  │  GUI-free
│                 registry, deterministic RNG tree            │  core
│ physics/        acoustics, geometry, statistics, trajectory │
└─────────────────────────────────────────────────────────────┘
```

**The core is GUI-free.** Everything below `gui/` runs headless (the test
suite and `sss-aug-generate` exercise it without Qt). The GUI is a thin
observer/editor of core objects.

### 2. Core data model

| Type | Responsibility |
|---|---|
| `AcquisitionMeta` (Pydantic) | physical acquisition context: layout (`dual`/`single_port`/`single_starboard`), altitude, slant range, resolutions, speed, depth, frequency, `intensity_mapping`, `shadow_included`. The per-field `resolved_*()` accessors return documented fallbacks when a field is absent (normalized mode); `is_physical` flags which mode is active. |
| `SonarImage` | float32 `[0,1]` array in the linear intensity domain; rows = pings. `sides()` yields per-side canonical **range-increasing views** so augmentation code is written once regardless of layout; `nadir_band()` auto-detects the dark nadir strip in dual layouts (declared value takes precedence). |
| `FieldWarp` | bidirectional geometric transform: inverse maps (`cv2.remap` for pixels) + analytic forward displacement (for labels). Supports composition and strength scaling. |
| `LabelSet` / `YoloBox` | YOLO labels as first-class citizens; `warped()` pushes an 8-point box hull through the forward map, re-hulls, drops boxes below the retention threshold (default 0.6) and records `BoxProvenance`. |
| `AugmentationInstance` | family key + label + enabled + probability + strength + `params` (nominal values) + `distributions` (per-parameter stochastic laws). `config_hash()` is the cache/repro key and **excludes `distributions`** — see §5. |
| `AugmentationPipeline` | ordered instance list; `apply()` produces `PipelineResult` (image, labels, per-stage records, manifest). Preview mode applies every enabled instance; generation mode draws per-instance Bernoulli gates. |

#### 2.1 Dataset conventions

Both are declared by the acquisition pipeline, never inferred, and are
honoured at dataset level (`sss_aug_dataset.yaml`) or per image (sidecar
JSON).

* **`shadow_included`** (default **true**) — a YOLO box covers the object's
  complete acoustic signature, highlight **and** shadow. F6 moves the
  down-range box edge when it rescales shadow length only if the flag is
  true; with `false` it modifies pixels and never touches labels. The
  Explorer metadata table displays the flag and generation manifests record
  it.
* **`intensity_mapping`** (`linear` / `gamma` / `log`) — see §6.

### 3. Determinism

All randomness flows from one **SeedSequence tree**:

```
derive_rng(master_seed, image_key, instance_id, copy_index, purpose…)
```

Keys are hashed (SHA-256) into `SeedSequence(entropy, spawn_key)`. Properties:

* same master seed ⇒ byte-identical datasets;
* independence across images/instances/copies ⇒ **worker-count independent**
  parallel generation;
* changing one instance's parameters does not perturb the noise of others.

Byte-reproducibility is a release gate, asserted end-to-end by
`tools/repro_gate.py` (one config run at 1 and at N workers, trees compared).
`generated_utc` in `generation_manifest.json` and the elapsed line in
`statistics.md` are wall-clock and sit outside the guarantee.

### 4. Extension contract — one file per family

A new augmentation family is a single module in `augmentations/`:

```python
class MyParams(AugParams):
    my_length_m: float = Field(1.0, ge=0.0, le=10.0, description="... [m]")

@register
class MyAug(Augmentation):
    key, name, order_hint = "my_key", "My name", 45
    section = "physics"            # or "geometry"
    Params, card = MyParams, ScienceCard(...)
    def apply(self, img, labels, params, rng, strength) -> AugResult: ...
```

Everything else is automatic: the science card appears in the Library, the
parameter form is generated from the Pydantic schema (bounds → slider range,
`[unit]` suffix → unit label, description → tooltip), each float parameter
gets a stochastic-law selector, profiles serialize it, and the
family-contract test (`test_family_contract`) covers it by iterating the
registry.

`AugResult` carries the four ways a family may act:

* geometric change → `warp=FieldWarp(...)`; labels follow automatically;
* direct label edit → `labels_override` (F6);
* layout / nadir / heading change → `meta_override`; the pipeline rebuilds
  the `SonarImage` with the new metadata and resets the cached nadir band
  (the G-families);
* photometric → pixels only, honouring `strength` via `blend()`.

#### 4.1 Sections: geometry vs physics

`Augmentation.section` is `"physics"` or `"geometry"`; the Library groups
cards under two headers. Registry, pipeline, profiles, preview and generation
treat both alike — the G-families are ordinary registered families with
`order_hint` 1–2, i.e. first in the physical order, because they represent
the *acquisition-direction choice*, logically prior to everything else.

* **G1 `mirror_across_track`** — exact column-reversal `FieldWarp`
  (involution). `single_port ↔ single_starboard` via `meta_override`; `dual`
  swaps sides with the nadir metadata mirrored (`nadir_center_frac → 1 − c`;
  centered waterfalls keep the nadir in place). Because each side's canonical
  range axis maps onto the other side's, shadows remain strictly down-range.
* **G2 `reverse_along_track`** — exact row-reversal `FieldWarp` (survey line
  replayed in the opposite direction); heading metadata rotated 180° when a
  heading was recorded.

Both are involutions, and their `strength` is intentionally binary (any value
> 0 applies the full transform); use `probability` to control frequency.

### 5. GUI architecture

* `MainWindow` owns session state (dataset, pipeline, master seed).
* Preview recomputation: 150 ms debounce → `_PreviewWorker` (QThread) holding
  a **lock-guarded per-row job map**, emitting `computed(row_id, image,
  labels)`. A **per-stage cache** keyed by the cumulative chain of
  `config_hash()`es recomputes only stages from the first change onward; keys
  start with the image key, so rows cache independently. Bounded at 128
  entries, cleared on seed change.
* **Preview (Area 4)** is a scrollable vertical stack of selectable
  `PreviewRow`s, each displaying one dataset image through 1–6 tiles (the
  tile count is shared across rows). Each row has its **own fixed height**,
  dragged via a bottom-edge grip and clamped 160–1400 px (default 340), so
  adding or removing a row never resizes the others. A newly assigned image
  fits to view once. Zoom/pan synchronization is scoped **per row** — tiles
  in a row share an image, while syncing across rows of differently-sized
  images produced misleading offsets. The pipeline order strip below the rows
  is global: one pipeline, many images.
* `ParamsForm` is generated per selection; edits mutate the shared
  `AugmentationInstance` and trigger the debounce. Each float parameter
  carries a law selector — *fixed*, *uniform*, *normal*, *loguniform* — whose
  values appear on a second line. Laws are stored on the instance and
  consumed by generation; the left-hand value stays the nominal value the
  preview renders. `config_hash()` excludes `distributions` precisely so that
  editing a law never invalidates the preview stage cache.
* `PipelineStrip` reorder = permutation of `pipeline.instances`;
  “Physical order” calls `pipeline.sort_physical()` (order_hint sort).
* The generation dialog builds a `GenerationConfig` — copying each enabled
  instance's laws into `InstanceGenSpec.param_distributions` and showing a
  read-only stochastic summary — and runs the same engine as the CLI in a
  worker thread (progress/ETA/cancel signals).
* **Profiles** store instances including their laws. There is no execution-mode
  selector: a profile is stochastic iff some parameter declares a law
  (`PipelineProfile.is_stochastic`). There are no profile-level
  `mode`/`distributions` fields, and `extra="forbid"` means a profile written
  before v0.4.0 — which still carries them — is rejected by name rather than
  loaded with its laws silently dropped.

### 6. Intensity-domain policy

Internal processing is linear `[0,1]` — the domain where multiplicative sonar
physics is native. The export mapping is **declared** by the acquisition
pipeline (`sss_aug_dataset.yaml: intensity_mapping`) and exactly inverted on
load; dB-parameterized effects (F2/F5/F7/F8 gains) convert via `10^(dB/10)`,
so each computation runs in its physically appropriate domain by
construction.

* When no mapping is declared the documented default assumption is **`log`**
  (dB waterfall export, `log_range_db` dynamic range, default 40 dB), which
  matches how SSS software normally exports waterfalls — and the GCS
  `intensity_db` export in particular. A dataset that is actually linear and
  does not say so is silently mis-inverted, which is why the field must be
  declared explicitly.
* Batch export takes mapping `auto` by default: re-apply the declared input
  mapping, so original and augmented files live in the same domain.

The inverse is exact only to the extent the declared mapping describes the
export; the residual approximation and its consequences are stated in
`docs/DESIGN.md` Part 3 (was `docs/scientific_documentation.md`).

### 7. Known approximations

1. **Equation rendering**: encyclopedia equations are fenced code blocks, not
   pre-rendered SVG (matplotlib mathtext). Rationale: zero extra runtime
   dependency and no rendering failure modes; the `equations` extra and a
   renderer hook remain planned (see Part 6, future work).
2. **Turn geometry** (F4): integrated-heading shear approximation of the
   swath fan rather than full polar resampling — documented in
   `f4_platform_motion.md` §6.
3. **Shadow segmentation** (F6): Otsu-based in-box segmentation behind a
   confidence gate, which skips a box rather than guessing — documented in
   `f6_shadow.md` §6.
4. **Multipath** (F8): incoherent and phenomenological — a hard-negative
   generator, not calibrated echo levels — documented in `f8_multipath.md` §6.

### 8. Cross-platform text IO

**Every** text read and write in the package passes `encoding="utf-8"`
explicitly (encyclopedia loader, profiles, presets, dataset config and
sidecars, labels, generation outputs, CLI, QSS loader). Relying on the OS
default codec raises `UnicodeDecodeError` on Windows, where cp1252 cannot
decode the shipped documentation. A regression test that loads every
encyclopedia page enforces it.

## Part 2 — Extending the studio: developer guide (was `docs/developer_guide.md`)

## Developer guide

### Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[gui,dev]"
pytest              # 55 tests: physics, core contracts, determinism, GUI smoke
ruff check .        # lint
sss-aug-studio demo_dataset      # launch GUI on the bundled demo
./.githooks/install.sh           # once per clone: wire the pre-commit gate
```

Headless environments: the GUI tests set `QT_QPA_PLATFORM=offscreen` themselves
and skip where PySide6 is absent (`pytest -m "not gui"` deselects them
explicitly); the generation CLI needs no display at all.

Before a release, run the reproducibility gate as well:

```bash
python tools/repro_gate.py          # known-good case at 1 vs 4 workers
python tools/repro_gate.py --config my_generation_config.yaml
python tools/docs_sync_check.py --range <last-release-tag>..HEAD
```

### Repository map

```
sss_aug_studio/
  core/            data model, pipeline, RNG tree, registry  (GUI-free)
  physics/         reusable acoustic/geometric/statistical building blocks
  augmentations/   one module per family — the extension point
  datasets/        YOLO index + metadata reader chain
  generation/      batch engine + distributions + CLI
  profiles/        profile model + presets/*.yaml
  documentation/   encyclopedia/*.md + bibliography.bib (shipped in package)
  gui/             PySide6 layer
tests/             pytest suite (test_gui_smoke.py is marked `gui`)
tools/             repro_gate.py — the byte-reproducibility release gate;
                   docs_sync_check.py — the docs-sync gate (pre-commit);
                   make_demo_dataset.py / make_demo_images.py — rebuild the fixture
.githooks/         versioned git hooks + install.sh (core.hooksPath)
docs/              handover documentation (this folder)
                   (2026-11-18: DESIGN.md, user_manual.md, HISTORY.md — the deltas)
demo_dataset/      4-image synthetic demo (2 dual + both single sides, sidecar
                   metadata); see its README.md for provenance
```

### Adding an augmentation family (the 1-file contract)

1. Create `sss_aug_studio/augmentations/my_family.py`:
   * a `Params(AugParams)` model — **physical units in the description with a
     trailing `[unit]`**, bounds via `Field(ge=…, le=…)`;
   * a `ScienceCard` — phenomenon, equation, **verified** references,
     limitations, expected effect, `doc_page`;
   * an `Augmentation` subclass with `key`, `name`, `order_hint`, decorated
     with `@register`, implementing
     `apply(img, labels, params, rng, strength) -> AugResult`.
2. Rules inside `apply()`:
   * never mutate `img.data` — copy;
   * use `img.sides()` canonical views so all three layouts work;
   * draw randomness **only** from the passed `rng`;
   * geometric changes → return `warp=FieldWarp(...)`; direct label edits →
     `labels_override`; photometric → pixels only;
   * output float32 in `[0,1]`; respect `strength` via `blend()` (photometric)
     or `warp.scaled(strength)` (geometric).
3. Write the encyclopedia page `documentation/encyclopedia/my_family.md`
   following the 7-section contract, add BibTeX entries.
4. Add the matching `AUGMENTATION_STRATEGIES.md` section, whose heading must
   name the module — ``## Fn — Title (`augmentations/my_family.py`) — ⚖️/🔧`` —
   with its rigor class. The docs-sync gate derives the family→section mapping
   from that heading, so a family with no such heading fails the check.
5. `pytest` — the parametrized family-contract test picks up the new family
   automatically (range, dtype, determinism, no-mutation, not-a-no-op).

Nothing else: no GUI code, no generation code, no profile code.

### Adding a metadata source

Implement the `MetadataReader` protocol (`read(image_path) -> dict | None`)
in `datasets/metadata.py` and insert it into the `MetadataResolver` chain in
`YoloDataset.__init__` at the appropriate priority. Earlier readers win
field-by-field.

### Conventions

* Python ≥ 3.10, full type annotations, Pydantic v2 models everywhere a
  human or a file supplies values.
* Rows = pings (along-track), columns = across-track; per-side views are
  always range-increasing.
* All physical parameters in SI-ish field units: m, deg, dB, m/s, kHz, s.
* Any approximation must be stated in **three** places (non-negotiable #8):
  the module docstring, the encyclopedia page §Limitations, and its
  `AUGMENTATION_STRATEGIES.md` section with its rigor class (⚖️ rigorous vs
  🔧 engineering approximation).
* References: verify against publisher metadata before citing. Never cite
  from memory.

### Testing policy

* Physics functions: closed-form/moment checks (e.g. Francois–Garrison
  magnitude at 450 kHz, speckle mean/variance, slant↔ground roundtrip).
* Every family: the shared contract test + targeted tests for label-moving
  behavior (see `test_geometric_family_moves_labels_consistently`).
* Generation: byte-reproducibility across worker counts is a release gate,
  enforced by `tools/repro_gate.py`. It hard-compares images, labels and
  `generation_manifest.json` (minus `generated_utc` and the `workers` /
  `output_path` it varies on purpose); `statistics.md` is reported as a warning
  only, because its `mean=` figures are summed in completion order.
* Docs sync: `tools/docs_sync_check.py` enforces non-negotiable #10 — a file
  under `augmentations/` may not change unless its encyclopedia page and its
  `AUGMENTATION_STRATEGIES.md` section change with it. It runs from
  `.githooks/pre-commit` (install once with `./.githooks/install.sh`) against
  the **staged** snapshot, and takes `--commit REF` / `--range A..B` for a
  review after the fact. Both mappings are read out of the tree — the module's
  `ScienceCard.doc_page` and the strategies heading — so a new family needs no
  edit here. Escape hatch for a genuine no-doc-change edit: `git commit
  --no-verify`, or `SSS_AUG_SKIP_DOCS_SYNC=1` in a script.
* Lint: `ruff check .` must be clean. The rule set is ruff's default; the
  baseline of ignores in `pyproject.toml` is enumerated with a reason per
  entry, and is not to be widened without one.

## Part 3 — Scientific documentation: fidelity boundaries, validation protocol (was `docs/scientific_documentation.md`)

## Scientific documentation

### Purpose and epistemic stance

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

### Family summary

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

### Fidelity boundaries (read before trusting)

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

### Validation protocol (thesis experiments)

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

### Relation to the thesis

The studio operationalizes contribution **C4** (regime-specific effects:
wall multipath, altitude-coupled swath, surface-attitude distortions) as a
data-generation capability, supports **C2** (detector robustness across the
baseline ladder's varying conditions), and its manifest/statistics artifacts
feed the open-release contribution **C5**.

## Part 4 — Mathematical appendix: the implemented equation set (was `docs/math_appendix.md`)

## Mathematical appendix

Complete equation set implemented by the studio. Conventions: along-track
row index y (pings), across-track ground range r [m], slant range R [m],
altitude h [m], intensity I ∈ [0,1] linear.

### A. Geometry (physics/geometry.py)

Slant/ground:            R = sqrt(r² + h²),  r = sqrt(R² − h²)
Grazing angle (flat):    θ(r) = atan(h / r)
Shadow length:           L_s = H·r / (h − H)          (target height H < h)
Altitude-error remap:    r_in(r_out) = sqrt(r_out² + 2hδ + δ²)
                         (feature at true r_t appears at sqrt(r_t² − 2hδ − δ²))

### B. Acoustics (physics/acoustics.py)

Francois–Garrison absorption α(f, T, S, z, pH) [dB/km]: full three-term
model (boric acid + magnesium sulfate + pure water) as published (JASA 1982);
at 450 kHz, 13 °C, S 35, shallow: α ≈ 0.08–0.15 dB/m.

Lambertian backscatter:  BS(θ) ∝ sin^p θ  (p ≈ 2)
Elevation beam pattern:  B(θ) = exp(−½((θ − θ_tilt)/σ_b)²)

### C. Statistics (physics/statistics.py)

Speckle (L looks):       G ~ Gamma(L, 1/L),  E[G]=1, Var[G]=1/L
K texture:               T ~ Gamma(ν, 1/ν),  E[T]=1, Var[T]=1/ν
Correlated gamma:        X = F⁻¹_{Gamma(k,1/k)}(Φ(Z)),  Z the unit-variance
                         Gaussian field below — monotone and memoryless, so
                         the marginal is exact; 1/e length ≈ 1.95·σ_kernel
K composite:             I' = I·T·G  (heavy tails as ν → small)
Correlated field:        F = (K_ℓ * W)/std, W white Gaussian (anisotropic ℓ)
AR(1) dB stripes:        g_{y+1} = ρ g_y + ε,  ρ = exp(−res_along/ℓ),
                         Var[g] = σ² (stationary), applied as 10^{g/10}

### D. Radiometric residual (F2)

ΔG(r) [dB] = a·log₁₀(R/R_ref) + b·(R−R_ref) + c
           + 10·log₁₀[sin^p θ'(r)/sin^p θ(r)] + 10·log₁₀[B(θ')/B(θ)]
I' = I · 10^{ΔG/10}

### E. Platform motion (F4)

Along-track sampling:    row_pitch = v(t)/PRF;  P(y) = Σ v dt / res_along
Speed remap:             in_row = P⁻¹(out_row)   (monotone)
Yaw shear:               s(y, r) = r·ψ(y)/res_along   [px along-track]
Turn:                    ψ̇ = v₀/R_turn over the turn window (integrated)
Roll gain:               gain(y,r) = B(θ(r) ∓ φ(y))/B(θ(r))  per side
Heave:                   Δh(y) → across-track remap of §A with δ = Δh(y)

### F. Shadow scaling (F6)

Altitude κ = h/h′:       L_s' = L_s (h − H)/(κh − H) ≈ L_s/κ  for H ≪ h
Fill:                    I' = (1−β)I + β·max(I, floor·μ_bg)  inside mask
Box edit: down-range box edge displaced by (L_s' − L_s), clipped to image.

### G. Multipath (F8)

Surface ghost:           I' = I + 10^{g/10}·(K_σ * I)(y, r − Δr),  Δr ≈ D − h
Second bottom:           feature at r → additional return near 2r, gain g₂
Wall ridge:              A(y,r) = μ_I·10^{G_w/10}·exp(−(r−r_w(y))²/2w²)·G_speckle
                         r_w(y) = d_wall + correlated wander

## Part 5 — Bibliography (was `docs/bibliography.md`)

## Bibliography

Human-readable form of `sss_aug_studio/documentation/bibliography.bib`
(all entries verified against publisher metadata; DOIs given where they exist).

### Reverberation statistics
- Abraham & Lyons (2002), IEEE J. Oceanic Eng. 27(4):800–813. DOI 10.1109/JOE.2002.804324.
- Lyons & Abraham (1999), JASA 106(3):1307–1315. DOI 10.1121/1.428034.
- Abraham (2019), *Underwater Acoustic Signal Processing*, Springer. DOI 10.1007/978-3-319-92983-5.
- Tough & Ward (1999), J. Phys. D: Appl. Phys. 32(23):3075–3084. DOI 10.1088/0022-3727/32/23/314.
- Ghosh & Henderson (2003), ACM Trans. Model. Comput. Simul. 13(3):276–294. DOI 10.1145/937332.937336.

### Propagation & image formation
- Francois & Garrison (1982), JASA 72(6):1879–1890. DOI 10.1121/1.388673.
- Coiras, Petillot & Lane (2007), IEEE Trans. Image Process. 16(2):382–390. DOI 10.1109/TIP.2006.888337.
- Blondel (2009), *The Handbook of Sidescan Sonar*, Springer/Praxis. DOI 10.1007/978-3-540-49886-5.
- Lurton (2010), *An Introduction to Underwater Acoustics*, 2nd ed., Springer.
- Jackson & Richardson (2007), *High-Frequency Seafloor Acoustics*, Springer. DOI 10.1007/978-0-387-36945-7.

### Regime & platform precedents
- Cocchi et al. (2024), Sensors 24(14):4544. DOI 10.3390/s24144544. (CORAL harbor USV.)
- Lei et al. (2026), arXiv 2604.19901. (Attitude-driven SSS geometric distortion — USV-critical.)
- Al-Rawi et al. (2017). First-bottom-return detection (project FBR pipeline basis).

### Detection & datasets
- Zou et al. (2025), J. Mar. Sci. Eng. 13(1):162. DOI 10.3390/jmse13010162. (YOLOv11 SSS small objects.)
- Sethuraman et al. (2024), IJRR. (Thunder Bay shipwreck dataset — open-release model for thesis C5.)

## Part 6 — Future work (was `docs/future_work.md`)

## Future work

Ordered by expected thesis value per unit effort.

1. **Omniscan log parameter fitting** — estimate per-family parameter
   envelopes (looks, ν, stripe σ, dropout λ/μ, roll spectra) automatically
   from real session logs, shipping a "fitted profile" per campaign site.
   Turns defaults into measurements; strengthens the C4 narrative.
2. **Replay validation harness** — drive F3/F4 with logged BlueBoat
   attitude/altitude and score against the recorded waterfall (§validation);
   natural thesis experiment and regression test.
3. **On-the-fly training adapter** — a `torch.utils.data` wrapper applying
   the pipeline at load time (same RNG tree keyed by epoch), avoiding
   dataset materialization for large sweeps.
4. **Bedform synthesis for F7** — directional sand-ripple fields with
   consistent highlight/shadow micro-structure (Jackson & Richardson
   morphologies); the current correlated field is context-only.
5. **GAN/diffusion comparison arm** — style-transfer augmentation baseline
   (per Wei et al. 2024 domain-adaptive line) to compare against
   physics-informed augmentation in the detector ablation — an attractive
   thesis side-experiment.
6. **Equation rendering** — pre-rendered mathtext SVG in science cards and
   encyclopedia (`.[equations]` extra already reserved).
7. **Coherent multipath upgrade** — image-derived reflector map + two-ray
   incoherent summation for wall echoes with correct level falloff.
8. **Per-pixel provenance masks** — export augmentation masks alongside
   images for explainability analyses of detector failures.
