# SSS-Dataset-Aug-Studio — commands and testing conventions

*Moved verbatim from `CLAUDE.md` on 2026-11-18 (session 11), which keeps a short summary and points here. Lines marked "(2026-11-18)" were corrected after the move.*

## Commands

```bash
# setup
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[gui]"          # core + PySide6
pip install -e ".[dev]"          # + pytest, ruff

# test
pytest                            # 64 tests at v0.4.0 (10 marked `gui`), all passing
pytest -m "not gui"               # skip the Qt suite
ruff check .                      # lint — clean at ruff 0.16.5

# release gate: byte-reproducibility across worker counts
python tools/repro_gate.py
python tools/repro_gate.py --config generation_config.yaml --workers 8

# docs-sync gate (also runs from .githooks/pre-commit on the staged snapshot)
./.githooks/install.sh            # once per clone: core.hooksPath -> .githooks
python tools/docs_sync_check.py               # the staged change
python tools/docs_sync_check.py --commit HEAD
python tools/docs_sync_check.py --range <base>..HEAD

# rebuild the demo fixture and its docs figures (deterministic; ~3 min)
python tools/make_demo_dataset.py
python tools/make_demo_images.py

# run
sss-aug-studio                    # GUI
sss-aug-studio demo_dataset       # GUI on the bundled fixture
sss-aug-generate config.yaml
sss-aug-generate config.yaml --seed 7 --workers 4
```

`tools/make_demo_dataset.py` is the one thing here that reaches outside this repository:
it imports the sibling submodule `BlueBoat-SSS-Sim` (read-only, ROS-free offline path),
putting `../BlueBoat-SSS-Sim/blueboat_sss_sim` on `sys.path` and exiting with a message if
that directory is absent. Nothing in the installed package imports it, so the module itself
keeps its no-ROS, no-sibling-dependency property.

**In a ROS-sourced shell, bare `pytest` fails before collection**: plugin autoload pulls
`launch_testing` from `/opt/ros/jazzy/lib/python3.12/site-packages`, which imports `lark`,
absent from this module's venv. Run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest`, or from a
shell that has not sourced the workspace. Nothing in the module depends on ROS; the
collision is purely pytest's plugin discovery.

`pip` inside restricted sandboxes needs `--break-system-packages`. Lint is `ruff check .`,
configured in `pyproject.toml` against ruff's own default rule set with an enumerated
baseline of ignores (whole-codebase restylings only — every rule that catches a defect is
enabled). There is no type-checker and no CI configuration, both declined; the release
checklist runs `pytest`, `ruff` and `tools/repro_gate.py`.

**Not verifiable from this repository — needs a Windows machine.** The claim on record is
that `pip install -e ".[dev]"`, `pytest`, both console scripts, `sss-aug-generate`
end-to-end on `demo_dataset` and the offscreen GUI exercise all ran on Windows 11 with
CPython 3.12. That run predates `test_gui_smoke.py`, `tools/repro_gate.py` and the ruff
gate, and it also predates the current `demo_dataset`; nothing in the tree records it, and
it cannot be re-checked from Linux. Everything above is verified on Linux.

---

## Testing conventions

- Physics functions are tested by closed form or moments — Francois–Garrison magnitude at
  450 kHz, speckle mean/variance, slant↔ground roundtrip, shadow geometry. The two gamma
  fields are additionally tested by distribution, not just moments: KS distance to
  Gamma(k, 1/k) on a decorrelated subsample, the shape parameter recovered by ML fit
  against its nominal value, and the achieved 1/e autocorrelation length per axis.
- `test_family_contract` is parametrized over `registry.all_families()`, so a newly
  registered family is covered automatically: output range and dtype, determinism,
  no input mutation, and not-a-no-op under default parameters.
- Label transforms get targeted tests (row-removal roundtrip, off-image drop, geometric
  consistency, G1/G2 involution and mirroring).
- The `sss_aug_dataset.yaml` contract has its own suite, `tests/test_dataset_metadata.py`:
  a field honoured at the top level, the same field honoured inside `meta:`, the top level
  winning on conflict, an unrecognised key warning without raising, a conformant config
  warning not at all, a malformed config yielding no fields, the sidecar beating the dataset
  config, and `demo_dataset` declaring a `shadow_included` that actually reaches
  `AcquisitionMeta`.
- Reproducibility has two layers. `test_stochastic_generation_reproducible` asserts it at
  the RNG level (repeated `derive_rng` + `sample_value` draws agree for a fixed seed);
  `tools/repro_gate.py` asserts it end-to-end by running one `GenerationConfig` at 1 and at
  N workers and comparing the trees. The gate builds its config **once** and varies only
  `workers` and `output_path` — `AugmentationInstance.instance_id` defaults to a random UUID
  and keys `derive_rng`, so a config constructed twice would seed the two runs differently.
  It hard-compares images, labels and `generation_manifest.json` (minus `generated_utc` and
  the two varied config keys); `statistics.md` is a warning only, its `mean=` figures being
  summed in completion order. The gate is not a pytest test — it is one command, run before
  a release.
- GUI behaviour is covered by `tests/test_gui_smoke.py`, marked `gui`. The module selects
  `QT_QPA_PLATFORM=offscreen` itself and skips wholesale without PySide6, so a no-Qt
  environment runs the suite green. Its dataset assertions are written against the dataset's
  own index rather than hard-coded counts, so replacing `demo_dataset` does not break them.
- Non-negotiable #10 is enforced mechanically by `tools/docs_sync_check.py`, run from
  `.githooks/pre-commit` against the **staged** snapshot: a file under `augmentations/` may
  not change unless its encyclopedia page and its `AUGMENTATION_STRATEGIES.md` section change
  with it. Both mappings are read out of the tree — the module's `ScienceCard.doc_page` and
  the strategies heading that names the module — so a new family needs no edit to the check,
  and a family the check cannot map is itself a failure. The section test is line-ranged, so
  an unrelated edit elsewhere in the strategies file does not satisfy it. It is stdlib-only
  and imports nothing from the package, so it runs with no venv. Escape hatch:
  `git commit --no-verify`, or `SSS_AUG_SKIP_DOCS_SYNC=1`. Hooks are versioned in
  `.githooks/` because `core.hooksPath` is local config and this repo is a submodule, so its
  real hooks directory sits outside the worktree; `./.githooks/install.sh` wires it.
