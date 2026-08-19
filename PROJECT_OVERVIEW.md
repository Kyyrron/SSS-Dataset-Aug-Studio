# Project overview — Physics-Informed SSS Augmentation Studio

Single entry point to the project. Detailed documents remain the reference —
this page tells you what exists and where to look.

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
live preview. Details: `docs/architecture.md`, delta:
`docs/architecture_update_v0.2.md`.

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

## Configuration system

* **Dataset conventions** — `sss_aug_dataset.yaml` at the dataset root:
  `layout` (dual / single_port / single_starboard), `intensity_mapping`
  (declared, never inferred: linear | log | gamma; **default assumption when
  absent: log/dB**), `shadow_included` (boxes cover highlight + shadow;
  default true), plus physical `meta` defaults. Per-image sidecar JSON
  overrides.
* **Profiles** — named pipeline configurations (YAML), six bundled presets.
  Every float parameter of an instance is either **fixed** or follows a
  **stochastic law** (uniform / normal / log-uniform), chosen directly in
  the Parameters form and stored with the instance; a profile is
  deterministic iff no parameter declares a law. Seeds reproduce datasets
  byte-for-byte in both cases.
* **Generation config** — exported YAML consumed by the GUI dialog or the
  `sss-aug-generate` CLI; every output dataset carries
  `generation_manifest.json` and `statistics.md`.

## Documentation index

| Document | Content |
|---|---|
| `GETTING_STARTED.md` | 5-minute quick start |
| `AUGMENTATION_STRATEGIES.md` | per-family physics + math + code + limits |
| `docs/user_manual.md` | full workflow, metadata formats, generation |
| `docs/architecture.md` (+ `architecture_update_v0.2.md`) | system design |
| `docs/developer_guide.md` | add a family in one file, conventions |
| `docs/scientific_documentation.md` | fidelity boundaries, validation protocol |
| `docs/math_appendix.md` | complete equation set |
| `docs/bibliography.md`, `sss_aug_studio/documentation/bibliography.bib` | verified references |
| `docs/future_work.md` | roadmap |
| In-app encyclopedia | per-family 7-section pages |
