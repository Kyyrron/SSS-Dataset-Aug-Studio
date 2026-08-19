# Developer guide

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[gui,dev]"
pytest              # 24 tests: physics, core contracts, determinism
sss-aug-studio demo_dataset      # launch GUI on the bundled demo
```

Headless environments: `QT_QPA_PLATFORM=offscreen sss-aug-studio` for GUI
smoke tests; the generation CLI needs no display at all.

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
tests/             pytest suite
docs/              handover documentation (this folder)
demo_dataset/      3-image demo (dual + single-side, sidecar metadata)
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
4. `pytest` — the parametrized family-contract test picks up the new family
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
* Any approximation must be stated in the module docstring **and** the
  encyclopedia page §Limitations.
* References: verify against publisher metadata before citing. Never cite
  from memory.

## Testing policy

* Physics functions: closed-form/moment checks (e.g. Francois–Garrison
  magnitude at 450 kHz, speckle mean/variance, slant↔ground roundtrip).
* Every family: the shared contract test + targeted tests for label-moving
  behavior (see `test_geometric_family_moves_labels_consistently`).
* Generation: byte-reproducibility across worker counts is a release gate.
