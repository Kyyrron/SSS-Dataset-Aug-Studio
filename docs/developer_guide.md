# Developer guide

## Setup

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

## Repository map

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
docs/history/      superseded architecture deltas, kept as a record
demo_dataset/      4-image synthetic demo (2 dual + both single sides, sidecar
                   metadata); see its README.md for provenance
```

## Adding an augmentation family (the 1-file contract)

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

## Adding a metadata source

Implement the `MetadataReader` protocol (`read(image_path) -> dict | None`)
in `datasets/metadata.py` and insert it into the `MetadataResolver` chain in
`YoloDataset.__init__` at the appropriate priority. Earlier readers win
field-by-field.

## Conventions

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

## Testing policy

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
