# Physics-Informed SSS Augmentation Studio

Professional desktop software for **physically plausible augmentation of
YOLO side-scan sonar datasets**, built for the master thesis *Adaptive
AI-Driven Side-Scan Sonar Survey on a Small USV* (BlueBoat + Cerulean
Omniscan 450 kHz, shallow enclosed-basin regime). **Optional module** of the BlueBoat project: the headline
detector is trained on simulated datasets from BlueBoat-Perception, and nothing in the project chain depends on
this studio. Simulated data follow the superproject's `SIM_VALIDITY_CONDITIONS.md` (simulator frozen
2026-11-18, literal acceptance verdict NOT READY, used as a model-conditional tool).

Every augmentation corresponds to a real physical phenomenon of SSS
acquisition — with the governing equations, verified references, physical
units and validation recipes shipped inside the application (Help ▸
Scientific encyclopedia).

## Objectives

Support the master thesis *Adaptive AI-Driven Side-Scan Sonar Survey on a
Small USV* (BlueBoat + Cerulean Omniscan 450 kHz, shallow enclosed-basin
regime) by making YOLO detectors generalize from limited training data to
real sea deployments. The tool augments SSS datasets so that **every
generated image is a plausible alternative acquisition of the same scene** —
different sea state, altitude, gain, seabed, turbidity, survey direction or
basin multipath — with labels transformed consistently and full
reproducibility from a single seed. Every transform is grounded in an
identified physical phenomenon (or an exact acquisition symmetry), with
equations, verified references and validation recipes shipped in-app.

## Feature map

| Area | What you get |
|---|---|
| Dataset Explorer | YOLO datasets (flat or split layouts), class search, per-image acquisition metadata (physical-unit or normalized fallback mode) |
| Augmentation Library | 8 physics families as *science cards* (phenomenon, equation, references); multiple named instances per family |
| Parameters | auto-generated forms — sliders/spinboxes with physical units and bounds, probability, strength, live ~150 ms preview |
| Interactive Preview | 1–6 zoom-synced tiles: original / augmented / difference / before-after slider / histogram / intensity profile; label overlays; drag-reorder pipeline strip with "physical order" |
| Generation | reproducible-by-seed batch generation (byte-identical across worker counts), originals never modified, per-parameter sampling distributions, progress/ETA/cancel, manifest + statistics, YAML export + headless CLI |
| Profiles | six curated presets (calm sea, moderate waves, harbour inspection, river, turbid, fast survey) + save/load your own |

**Geometry section:** G1 across-track mirror · G2 along-track reversal —
exact, layout-aware acquisition symmetries with consistent labels.

**The 8 physics families:** speckle & reverberation statistics · radiometric
transfer (TVG/absorption/beam) · slant-range & altitude geometry · platform
motion (USV roll/heave/yaw/speed) · ping loss & sensor artifacts · shadow &
highlight modulation · seabed reflectivity & texture · shallow-water
multipath (wall echoes — the thesis C4 hard-negative generator).

Labels are first-class: geometric families move YOLO boxes through the exact
forward transform; the shadow family moves the down-range box edge; boxes
falling below 60 % retention are dropped and logged.

## Implemented augmentation families

**Geometry (exact symmetries):** G1 across-track mirror (layout-aware,
nadir-preserving) · G2 along-track reversal.

**Physics-informed:** F1 speckle & reverberation statistics (Rayleigh/K) ·
F2 radiometric transfer (TVG residual, Francois–Garrison absorption, beam
pattern) · F3 slant-range & altitude geometry (FBR error, gap breathing) ·
F4 platform motion (USV roll/heave/yaw/speed) · F5 ping loss & sensor
artifacts · F6 shadow & highlight modulation (convention-aware) · F7 seabed
reflectivity & texture · F8 shallow-water multipath (wall echoes — the
thesis hard-negative generator).

Per-family science: `AUGMENTATION_STRATEGIES.md` (with core code excerpts)
and the in-app encyclopedia (Help ▸ Scientific encyclopedia).

## Install & run

```bash
pip install -e ".[gui]"
sss-aug-studio [path/to/dataset]        # GUI (demo: sss-aug-studio demo_dataset)
sss-aug-generate config.yaml            # headless, reproducible generation
pip install -e ".[dev]" && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest   # 64 tests at v0.4.0
```

Requires Python ≥ 3.10. Core (everything except the GUI) has no Qt
dependency.

## Architecture in one paragraph

A **GUI-free core** (`core/`, `physics/`) defines the data model
(`SonarImage` in linear intensity, layout-agnostic per-side views,
bidirectional `FieldWarp`s so labels follow pixels exactly,
`AcquisitionMeta` in physical units) and a deterministic SeedSequence tree
(same seed ⇒ byte-identical datasets, independent of worker count).
Augmentations are **one-file plugins** (`augmentations/`) that self-register;
GUI forms, generation distributions, profiles and tests pick them up
automatically. On top sit application services (`datasets/` YOLO indexing +
modular metadata readers, `generation/` parallel batch engine + headless
CLI, `profiles/`) and a PySide6 GUI (`gui/`) with debounced, stage-cached
live preview. Details: `docs/DESIGN.md` Part 1.

## Configuration system

* **Dataset conventions** — `sss_aug_dataset.yaml` at the dataset root:
  `layout` (dual / single_port / single_starboard), `intensity_mapping`
  (declared, never inferred: linear | log | gamma; **default assumption when
  absent: log/dB**), `shadow_included` (boxes cover highlight + shadow;
  default true), plus the physical acquisition values. Every field is honoured
  at the top level or inside `meta:` — equivalent positions, top level winning
  on conflict — and an unrecognised key warns rather than vanishing. Per-image
  sidecar JSON overrides.
* **Profiles** — named pipeline configurations (YAML), six bundled presets.
  Every float parameter of an instance is either **fixed** or follows a
  **stochastic law** (uniform / normal / log-uniform), chosen directly in
  the Parameters form and stored with the instance; a profile is
  deterministic iff no parameter declares a law. Seeds reproduce datasets
  byte-for-byte in both cases.
* **Generation config** — exported YAML consumed by the GUI dialog or the
  `sss-aug-generate` CLI; every output dataset carries
  `generation_manifest.json` and `statistics.md`.

## Documentation

- `README.md` — this overview (merged with the former `PROJECT_OVERVIEW.md`, 2026-11-18)
- `docs/user_manual.md` — getting started in five minutes (the former `GETTING_STARTED.md`), workflow, metadata
  format, generation guide
- `AUGMENTATION_STRATEGIES.md` — per-family physics, math, code excerpts, rigor classification
- `docs/DESIGN.md` — Part 1 architecture (layering, determinism, extension contract), Part 2 developer guide (add
  a family in one file), Part 3 scientific documentation (fidelity boundaries, validation protocol), Part 4 the
  complete equation set, Part 5 bibliography (with `sss_aug_studio/documentation/bibliography.bib`), Part 6 future
  work
- `docs/HISTORY.md` — release deltas 0.2.0 to 0.3.0 and later dated events
- In-app: Help ▸ Scientific encyclopedia (per-family 7-section pages)

## Reproducibility guarantee

A generation config (YAML) + master seed reproduces a dataset
**byte-for-byte**, independent of the number of worker processes. Every
output dataset carries `generation_manifest.json` (full audit trail) and
`statistics.md`.
