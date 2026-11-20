# CLAUDE.md — SSS-Dataset-Aug-Studio

Physics-Informed Side-Scan Sonar Augmentation Studio: a standalone Python desktop
application (PySide6) that augments YOLO datasets of side-scan sonar (SSS) imagery so
detectors generalise from limited training data to real deployments. Every transform is
either the image-domain expression of an identified acoustic phenomenon or an exact
geometric symmetry of SSS acquisition.

Version 0.4.0. Python ≥ 3.10. No ROS dependency. **Optional module**: nothing in the chain depends on it.

Simulated results follow `../SIM_VALIDITY_CONDITIONS.md` (superproject root).

---

## Role in the wider project

This submodule supports the master thesis *Adaptive AI-Driven SSS Survey on a Small USV*
(BlueBoat + Cerulean Omniscan 450 kHz, shallow enclosed basins). It is an **offline data
tool** on the operator laptop, like every module of the project (nothing of ours runs on the
boat). It does not talk to the autopilot and is not part of the live perception loop.

Its outputs feed detector training (thesis deliverables D2 → D3). The scientific framing of
augmentation realism — what may be claimed from augmented data — is bounded by
`docs/DESIGN.md` Part 3 (scientific documentation).

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
| `sss_aug_dataset.yaml` (dataset root) | dataset author | any `AcquisitionMeta` field, **at the top level or inside `meta:` — the two positions are equivalent**; the top level wins on conflict |
| `{stem}.json` or `{stem}.meta.json` beside an image | acquisition/FBR pipeline | per-image metadata overriding dataset defaults |
| profile YAML | this tool or hand-written | pipeline configuration incl. per-parameter stochastic laws |
| generation config YAML | GUI export or hand-written | full `GenerationConfig` for the CLI |

Metadata resolution is a chain of responsibility (`datasets/metadata.py`): sidecar JSON →
dataset config → `AcquisitionMeta` built-in fallbacks. Earlier readers win field-by-field.
Add a source by implementing `read(image_path) -> dict | None` and inserting it into
`MetadataResolver` in `YoloDataset.__init__`.

`DatasetConfigReader` honours every `AcquisitionMeta` field at both positions in
`sss_aug_dataset.yaml` — top level and `meta:` block — with the top level winning where a
key appears in both. A key at either position that is not an `AcquisitionMeta` field is
ignored with a `UserWarning` naming it; the reader never raises, so a malformed or
non-conformant config still loads with no fields.

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

**Detail loads by itself:** each `.claude/rules/*.md` is a path-scoped rule that imports one `.claude/` topic
file when you read or edit a matching file; the tables below name the same files for reading by hand.

## Where the rest lives (moved verbatim on 2026-11-18)

| Before … | Read |
|---|---|
| changing the package layout, the core data model, a family, the GUI | `.claude/code-architecture.md` |
| adding an augmentation family (one file per family) | `.claude/code-architecture.md` "Extension contract" |
| running the app, the CLI, the tests, the release gates | `.claude/commands-testing.md`, superproject skill `module-gates` |
| the physics and the claims allowed from augmented data | `docs/DESIGN.md` |
| open items | `.claude/TODO.md` |

Superproject rules hold here: never `git commit`, `git push` or `git tag`.
