# CLAUDE.md — SSS-Dataset-Aug-Studio

Physics-Informed Side-Scan Sonar Augmentation Studio: a standalone Python desktop
application (PySide6) that augments YOLO datasets of side-scan sonar (SSS) imagery so
detectors generalise from limited training data to real deployments. Every transform is
either the image-domain expression of an identified acoustic phenomenon or an exact
geometric symmetry of SSS acquisition.

Version 0.3.0. Python ≥ 3.10. No ROS dependency.

---

## Role in the wider project

This submodule supports the master thesis *Adaptive AI-Driven SSS Survey on a Small USV*
(BlueBoat + Cerulean Omniscan 450 kHz, shallow enclosed basins). It is an **offline data
tool**. It does not run on the boat, does not talk to the autopilot, and is not part of the
live perception loop.

Its outputs feed detector training (thesis deliverables D2 → D3). The scientific framing of
augmentation realism — what may be claimed from augmented data — is bounded by
`docs/scientific_documentation.md`.

---

## Interface exposed by this module

**No ROS 2 topics, services, or actions.** This module publishes and subscribes to nothing.
Integration with the rest of the project happens entirely through files and CLI.

### Console entry points (declared in `pyproject.toml`)

| Command | Target | Purpose |
|---|---|---|
| `sss-aug-studio [DATASET_PATH]` | `sss_aug_studio.app.main:main` | GUI; optional dataset path opens it at launch |
| `sss-aug-generate CONFIG.yaml [--seed N] [--workers K]` | `sss_aug_studio.generation.cli:main` | Headless batch generation; `--seed`/`--workers` override the config |

### Files consumed

| File | Producer | Role |
|---|---|---|
| YOLO dataset (`images/`+`labels/`, flat or `train\|val\|test` splits) | acquisition + labelling pipeline | input, **read-only** |
| `data.yaml` / `dataset.yaml` / `data.yml` (`names:` map or list) | dataset author | class names |
| `sss_aug_dataset.yaml` (dataset root) | dataset author | `layout` and `intensity_mapping` at the top level; **every other field, `shadow_included` included, inside the `meta:` block** |
| `{stem}.json` or `{stem}.meta.json` beside an image | acquisition/FBR pipeline | per-image metadata overriding dataset defaults |
| profile YAML | this tool or hand-written | pipeline configuration incl. per-parameter stochastic laws |
| generation config YAML | GUI export or hand-written | full `GenerationConfig` for the CLI |

Metadata resolution is a chain of responsibility (`datasets/metadata.py`): sidecar JSON →
dataset config → `AcquisitionMeta` built-in fallbacks. Earlier readers win field-by-field.
Add a source by implementing `read(image_path) -> dict | None` and inserting it into
`MetadataResolver` in `YoloDataset.__init__`.

`DatasetConfigReader` lifts exactly two keys — `layout` and `intensity_mapping` — from the
top level of `sss_aug_dataset.yaml` and otherwise reads only the `meta:` block. Any other
key written at the top level is silently dropped, so a top-level `shadow_included: false`
leaves the value at its `True` default.

### Files produced (into a **new** output directory)

| File | Nature |
|---|---|
| originals, copied byte-for-byte | persistent input, never rewritten |
| `{stem}__aug{N}.{ext}` + matching `.txt` labels | generated |
| `generation_manifest.json` | audit trail: tool version, full config, per-output applied instances, sampled parameters, label provenance. Carries a wall-clock `generated_utc` |
| `statistics.md` | application counts, sampled parameter ranges, box budget (boxes in / out / dropped). Carries a wall-clock elapsed line |
| `data.yaml` / `dataset.yaml` / `data.yml`, `sss_aug_dataset.yaml` | copied from the source dataset |

---

## NON-NEGOTIABLE constraints

Violating any of these breaks another consumer of the data, the reproducibility guarantee,
or the scientific argument the thesis rests on.

1. **Originals are never modified.** Generation writes to a separate output directory and
   copies source images and labels verbatim. Input dataset directories are read-only.

2. **Byte-reproducibility is a release gate.** The same `GenerationConfig` + `master_seed`
   must produce an identical dataset regardless of worker count. Every random draw comes
   from `derive_rng(master_seed, image_key, instance_id, copy_index, purpose…)`
   (`core/random.py`). Never use `np.random.*` global state, a module-level `Generator`, or
   any RNG not derived from that tree inside an augmentation. What the gate compares:
   images, labels and `generation_manifest.json` **minus** its `generated_utc` stamp — a
   whole-tree hash also catches that stamp and the elapsed line in `statistics.md`, which
   differ between any two runs and are not part of the guarantee.

3. **`AugmentationInstance.config_hash()` excludes `distributions`.** Previews render
   nominal parameter values, so a stochastic law must never invalidate the preview stage
   cache. It includes family, params, strength and enabled.

4. **`apply()` must not mutate its input.** Copy `img.data` before writing. The preview
   stage cache hands the same array to several stages.

5. **All text IO passes `encoding="utf-8"` explicitly.** Relying on the OS default codec
   crashes on Windows, where cp1252 cannot decode the shipped documentation.

6. **Physically invalid transforms stay out of the library.** No arbitrary rotations, no
   additive Gaussian noise (envelope-detected sonar noise is multiplicative), no hue/colour
   jitter (data is single-channel intensity; colormaps are display-only), no elastic
   deformation or mixup/cutmix. A rotated acoustic shadow is impossible; shipping one would
   teach a detector an invariance that does not exist at sea. The only valid flips are G1
   and G2, implemented as exact symmetries.

7. **Every scientific reference is verified against publisher metadata before being cited**,
   with DOI where one exists. Never cite from memory. Fabricated citations invalidate the
   thesis chapter this tool supports.

8. **Any approximation is stated in three places**: the module docstring, the encyclopedia
   page §Limitations, and `AUGMENTATION_STRATEGIES.md` with its rigor class (⚖️ rigorous vs
   🔧 engineering approximation).

9. **Label semantics follow `AcquisitionMeta.shadow_included`** (default `true`: a YOLO box
   covers highlight **and** acoustic shadow). F6 moves the down-range box edge only when it
   is true.

10. **Docs move with the code.** Changing a family means updating its encyclopedia page and
    its `AUGMENTATION_STRATEGIES.md` section in the same commit.

---

## Layout

```
pyproject.toml               # console scripts, extras [gui] / [equations] / [dev], package-data
sss_aug_studio/
  core/        image.py meta.py labels.py warp.py pipeline.py registry.py random.py
  physics/     acoustics.py geometry.py statistics.py trajectory.py
  augmentations/  base.py geometric.py speckle.py radiometric.py slant_geometry.py
                  platform_motion.py ping_artifacts.py shadow.py seabed.py multipath.py
  datasets/    yolo.py metadata.py
  generation/  engine.py distributions.py cli.py
  profiles/    store.py presets/*.yaml        (6 presets)
  documentation/  encyclopedia/*.md (10 pages) bibliography.bib
  gui/         main_window.py preview.py explorer.py library.py params_form.py
               generation_dialog.py encyclopedia.py qt_images.py style.qss
  app/main.py
  config/ utils/               # empty placeholder packages (bare __init__.py, no modules)
tests/         test_core_physics.py test_v02_update.py
docs/          architecture.md + architecture_update_v0.2.md / _v0.2.1.md / _v0.3.md,
               developer_guide.md user_manual.md scientific_documentation.md
               math_appendix.md bibliography.md future_work.md,
               demo_*.png (4 preset screenshots)
demo_dataset/  3-image fixture: two dual (`dual_shipwreck`, `dual_wreck2`, 2 boxes each)
               and one single-starboard via `images/port_wall.json` sidecar, whose label
               file is empty. `sss_aug_dataset.yaml` declares `intensity_mapping: linear`
README.md PROJECT_OVERVIEW.md GETTING_STARTED.md AUGMENTATION_STRATEGIES.md
```

The `[gui]` extra installs `PySide6-Essentials>=6.6`; `[equations]` adds matplotlib;
`[dev]` adds pytest and pytest-cov.

`core/` and `physics/` are **GUI-free** and must stay that way — the test suite and the
generation CLI import them without Qt.

Non-Python assets are shipped via `[tool.setuptools.package-data]`
(`documentation/encyclopedia/*.md`, `documentation/*.bib`, `profiles/presets/*.yaml`,
`gui/*.qss`). A new asset directory needs an entry there or it vanishes from installs.

---

## Core data model

- **`SonarImage`** — `float32` in `[0,1]`, **linear intensity** domain (native domain of
  multiplicative sonar physics). Rows = pings (along-track), columns = across-track.
  `sides()` yields per-side **canonical range-increasing views**, so augmentation code is
  written once for `dual`, `single_port` and `single_starboard`. `nadir_band()` auto-detects
  the dark nadir strip unless declared.
- **`AcquisitionMeta`** — physical acquisition context in field units (m, deg, m/s, kHz).
  `resolved_*()` accessors return documented fallbacks; `is_physical` says whether real
  metadata or normalized fallbacks are in force.
- **`FieldWarp`** — bidirectional: `map_x`/`map_y` inverse maps drive `cv2.remap` for
  pixels, `fwd_dx`/`fwd_dy` analytic forward displacements move labels. Composable,
  strength-scalable.
- **`LabelSet` / `YoloBox`** — `warped()` pushes an 8-point box hull through the forward
  map, re-hulls, drops boxes below the retention threshold (default 0.6) and records
  `BoxProvenance`.
- **`AugmentationInstance`** — family + label + enabled + probability + strength + `params`
  (nominal values) + `distributions` (per-parameter stochastic laws).
- **`AugmentationPipeline.apply()`** → `PipelineResult` (image, labels, per-stage records,
  manifest). Preview mode applies every enabled instance; generation mode draws per-instance
  Bernoulli gates.

**Intensity domain policy.** The export mapping is *declared* by the acquisition pipeline
(`intensity_mapping: linear | log | gamma`) and exactly inverted on load; when absent the
documented default assumption is **`log`** (dB waterfall export). dB-valued effects convert
via `10^(dB/10)`, so each computation runs in its physically appropriate domain. Export
mapping `auto` re-applies the declared input mapping.

---

## Augmentation families

Registered under two sections. `section = "geometry"` families are exact symmetries and are
grouped separately in the GUI from the phenomenon models.

**Geometry** (`augmentations/geometric.py`, `order_hint` 1–2, first in physical order —
they represent the acquisition-direction choice):

- **G1 `mirror_across_track`** — exact column reversal, which swaps the two sides of a dual
  waterfall in the pixels. `AugResult.meta_override` follows: `single_port ↔
  single_starboard` for single layouts, `nadir_center_frac → 1 − c` for dual (gated by the
  `update_layout_metadata` param). Shadows stay strictly down-range because each side's
  range axis maps onto the other's.
- **G2 `reverse_along_track`** — exact row reversal; heading rotated 180° via
  `meta_override`, and only when a heading was recorded (gated by `update_heading_metadata`).

Both are involutions. `strength` is intentionally **binary** for them (any value > 0 applies
the full transform); use `probability` to control frequency.

**Physics-informed** (`order_hint` orders the default physical chain
seabed → shadow → motion → slant → radiometric → multipath → speckle → ping artifacts):

`seabed` (F7) · `shadow` (F6) · `platform_motion` (F4) · `slant_geometry` (F3) ·
`radiometric` (F2) · `multipath` (F8) · `speckle` (F1) · `ping_artifacts` (F5).

Per-family physics, equations, DOI-verified references, core code excerpts and limitations
live in `AUGMENTATION_STRATEGIES.md` and the in-app encyclopedia pages.

### Known approximations carried by the implementation

- F1 K-texture: smoothed-gamma field — exact first/second moments, approximate marginal.
- F4 turn geometry: integrated-heading shear, not a full polar resample.
- F6: Otsu-based in-box shadow segmentation, confidence-gated (skips rather than guesses).
- F8: incoherent and phenomenological — a hard-negative generator, not calibrated echo
  levels.

---

## Extension contract — one file per family

A new family is a single module in `augmentations/`:

```python
class MyParams(AugParams):
    my_length_m: float = Field(1.0, ge=0.0, le=10.0, description="… [m]")

@register
class MyAug(Augmentation):
    key, name, order_hint = "my_key", "My name", 45
    section = "physics"            # or "geometry"
    Params, card = MyParams, ScienceCard(...)
    def apply(self, img, labels, params, rng, strength) -> AugResult: ...
```

Everything else is automatic: the Library card, the parameter form (Pydantic bounds → slider
range, trailing `[unit]` in the description → unit label, description → tooltip), the
generation distributions, profile serialisation, and the parametrized family-contract test.
Write no per-family GUI code.

Inside `apply()`: use `img.sides()` for layout independence; draw randomness only from the
passed `rng`; geometric change → return `warp=FieldWarp(...)`; direct label edit → return
`labels_override`; layout/nadir/heading change → return `meta_override`; photometric →
pixels only, honouring `strength` via `blend()`.

Then add the encyclopedia page and BibTeX entries. The eight physics pages follow a
7-section contract: physical explanation, mathematical model, implementation, verified
references, expected effect, limitations, validation metrics. The two geometry families
share one page (`g_geometry.md`), which is organised per family rather than by those
sections; `00_overview.md` carries the conventions, the default physical order and the
list of deliberately excluded transforms.

---

## GUI architecture

`MainWindow` owns session state (dataset, pipeline, master seed). Preview recomputation is
debounced 150 ms into `_PreviewWorker`, a `QThread` holding a **lock-guarded per-row job
map** and emitting `computed(row_id, image, labels)`. A per-stage cache keyed by the
cumulative chain of `config_hash()`es recomputes only stages from the first change onward;
keys start with the image key, so preview rows cache independently (bound 128 entries,
cleared on seed change).

**Preview (Area 4)** is a scrollable stack of selectable `PreviewRow`s, each showing one
dataset image through 1–6 tiles (tile count shared across rows). Each row has its **own
fixed height**, dragged via a bottom-edge grip, clamped 160–1400 px — adding or removing a
row never resizes the others. Newly assigned images fit-to-view once. Zoom/pan sync is
scoped **per row** (tiles in a row share an image; cross-row sync of differently-sized
images produced misleading offsets). The pipeline order strip below is global: one pipeline,
many images.

**Parameters form** auto-generates from the Pydantic schema. Each float parameter carries a
law selector — *fixed*, *uniform*, *normal*, *loguniform* — whose values appear on a second
line. Laws are stored on the instance and consumed by generation; the left-hand value stays
the nominal value the preview renders. `generation/distributions.py` also defines a
`choice` law, which the form does not expose — it is reachable only from a hand-written
generation config. Laws reach the engine as `InstanceGenSpec.param_distributions`, which
`GenerationDialog` copies from `AugmentationInstance.distributions`; a law naming a field
the family's `Params` model does not declare raises `extra_forbidden` when that stage runs,
not when the config is loaded.

**Profiles** store instances including their laws. There is no execution-mode selector: a
profile is stochastic iff some parameter declares a law (`PipelineProfile.is_stochastic`).
Legacy v0.2 profiles carrying a profile-level `mode: stochastic` + `distributions` block are
migrated into the instances by a `model_validator` on load; those fields remain accepted and
deprecated.

---

## Commands

```bash
# setup
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[gui]"          # core + PySide6
pip install -e ".[dev]"          # + pytest

# test
pytest                            # 39 tests at v0.3.0
python3 -m pytest tests -q

# run
sss-aug-studio                    # GUI
sss-aug-studio demo_dataset       # GUI on the bundled fixture
sss-aug-generate config.yaml
sss-aug-generate config.yaml --seed 7 --workers 4

# headless GUI exercise (no display; used for smoke-testing GUI changes)
QT_QPA_PLATFORM=offscreen python3 -c "..."
```

`pip` inside restricted sandboxes needs `--break-system-packages`. No lint, type-check or
CI configuration exists in this repo (no ruff/black/mypy, no `.github/`).

All of the above run on Windows as well as Linux: `pip install -e ".[dev]"`, `pytest`
(39 passed), both console scripts, `sss-aug-generate` end-to-end on `demo_dataset`, and the
offscreen GUI exercise are verified on Windows 11 with CPython 3.12. An editable install
leaves an untracked `sss_aug_studio.egg-info/` in the repo root — `.gitignore` does not
cover it.

---

## Testing conventions

- Physics functions are tested by closed form or moments — Francois–Garrison magnitude at
  450 kHz, speckle mean/variance, slant↔ground roundtrip, shadow geometry.
- `test_family_contract` is parametrized over `registry.all_families()`, so a newly
  registered family is covered automatically: output range and dtype, determinism,
  no input mutation, and not-a-no-op under default parameters.
- Label transforms get targeted tests (row-removal roundtrip, off-image drop, geometric
  consistency, G1/G2 involution and mirroring).
- Reproducibility is asserted at the RNG level only: `test_stochastic_generation_reproducible`
  checks that repeated `derive_rng` + `sample_value` draws agree for a fixed seed. No test
  runs `GenerationEngine`, hashes an output tree, or varies the worker count — that
  comparison is a manual pre-release procedure.

GUI behaviour is currently exercised by ad-hoc `QT_QPA_PLATFORM=offscreen` scripts rather
than pytest.
