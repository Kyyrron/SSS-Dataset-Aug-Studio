# TODO — SSS-Dataset-Aug-Studio

Actionable items only. Current-state facts live in `CLAUDE.md`.
Ordered roughly by how much damage the item can do if left alone.

This module has no ROS 2 dependency and no colcon build, so nothing here is blocked on a
sourced ROS workspace. What *is* blocked is marked per item: **BLOCKED — field data**
(needs recorded Omniscan sessions), **BLOCKED — training run**, or **BLOCKED — macOS**.

---

## Defects found in the code (concrete, one-file fixes)

- [ ] **`open()` without `encoding="utf-8"` in `gui/generation_dialog.py:191`**
      (`_export_yaml`). This is the only text-IO site in the package that does not pass an
      explicit encoding, so it violates non-negotiable #5. It does not crash today only
      because `yaml.safe_dump` defaults to `allow_unicode=False` and escapes non-ASCII to
      `\uXXXX`; the moment someone adds `allow_unicode=True` (as `profiles/store.py`
      already does) a config carrying an em dash or `ν` fails on a cp1252 Windows default.
      Fix: `open(path, "w", encoding="utf-8")`.

- [ ] **`DatasetConfigReader` silently drops top-level keys other than `layout` and
      `intensity_mapping`.** `sss_aug_dataset.yaml` fields must sit inside the `meta:`
      block; a top-level `shadow_included: false` is ignored and the value stays `True`
      (verified both ways against `datasets/metadata.py`). `demo_dataset/sss_aug_dataset.yaml`
      declares `shadow_included: true` at the top level, where it has no effect — invisible
      only because it matches the default. Decide: either lift `shadow_included` (and any
      other `AcquisitionMeta` field) at the top level in the reader, or move the key into
      `meta:` in every dataset config and document the `meta:`-only rule.

- [ ] `.gitignore` covers no Python packaging artifacts. `pip install -e .` — the documented
      setup command — leaves an untracked `sss_aug_studio.egg-info/` in the repo root. Add
      `*.egg-info/`, `build/`, `dist/`, `.venv/`, `.pytest_cache/`.

- [ ] Stale docstrings that promise things the code does not do: `core/meta.py` documents a
      `resolved()` method returning a filled-in copy (only the per-field `resolved_*()`
      accessors exist), and `generation/engine.py`'s module docstring says `statistics.md`
      summarises class balance (it reports box counts and parameter ranges, not classes).

## Repository hygiene

- [ ] Decide whether `docs/architecture_update_v0.2.md`, `_v0.2.1.md` and `_v0.3.md` stay as
      separate deltas or get folded into `architecture.md`. Three delta files will keep
      accumulating one per release otherwise.

## Correctness / data-integrity risks

- [ ] **Audit existing datasets for a declared `intensity_mapping`.** The default assumption
      changed from `linear` to `log` at v0.2. Any dataset lacking the key is now decoded as
      a dB export; if it was actually linear, every dB-domain effect is applied through a
      wrong inverse. `demo_dataset` declares `linear` explicitly and is fine; the datasets
      that need checking live outside this repo (beach-labelled real imagery, and anything
      the simulator's `dataset_recorder_node` has written).

- [ ] **Replace the `demo_dataset` fixture.** Its three images came from ad-hoc uploads with
      unestablished provenance/licensing, and the labels were hand-drawn approximations, not
      ground truth — `labels/port_wall.txt` is empty, so one of the three images carries no
      boxes at all. Substitute a small slice of real labelled beach imagery before any
      public release of this repo.

- [ ] **BLOCKED — macOS.** Windows is now covered: editable install, `pytest` (39 passed),
      both console scripts, `sss-aug-generate` end-to-end on `demo_dataset`, offscreen Qt
      (dataset open, preview worker, encyclopedia pages, presets, generation dialog) all
      run on Windows 11 / CPython 3.12. macOS has never been exercised.

## Scientific validation (the substantive backlog)

- [ ] **BLOCKED — field data. Fit parameter envelopes from real Omniscan session logs**
      rather than shipping hand-chosen defaults: looks and ν per seabed, stripe σ, dropout
      λ/μ, roll spectra, wall-echo geometry. Each encyclopedia page §7 already names the
      statistic to measure. This converts defaults into measurements and is the single
      highest-value item for the thesis chapter.

- [ ] **BLOCKED — field data. Replay validation harness** for F3/F4: drive the models with
      logged BlueBoat attitude/altitude over a transect and score the synthesised waterfall
      against the recorded one. Doubles as a regression test with real ground truth.

- [ ] **BLOCKED — training run. Detector-level ablation** (the experiment this tool exists
      to enable): train under no augmentation / standard augmentation / physics-informed /
      both, evaluate on held-out **real** imagery stratified by condition. Until this runs,
      the tool's benefit is asserted, not measured.

- [ ] Tighten F1's K-texture from smoothed-gamma to an exact gamma-copula sample if the
      marginal mismatch turns out to matter for background statistics fits.
      (`physics/statistics.py: k_texture_field` — Gaussian-smoothed gamma field with exact
      mean/variance restoration.)

- [ ] **BLOCKED — field data.** Record measured wall-echo distance/width/level ranges from
      real port imagery and re-tune the F8 defaults to that envelope (currently
      `wall_distance_m: 15.0`, `wall_width_m: 0.6`, `wall_gain_db: 6.0`).

## Deprecations and cleanup

- [ ] Set a removal release for the legacy profile fields `PipelineProfile.mode` and
      `.distributions`, their `_migrate_legacy_distributions` validator, and the `**_legacy`
      kwarg in `from_pipeline` (`profiles/store.py`). Keep them until no v0.2-era profile
      YAML remains in use.

- [ ] `docs/architecture.md:16` still describes `augmentations/` as "8 physics-informed
      families"; there are 10 registered (8 physics + G1/G2). This is the only stale count
      left in the prose — the rest of the docs say "F1–F8" plus the G-families, which is
      correct.

- [ ] Docstrings and docs still cite v0.1 design-review decision numbers (#1–#5) instead of
      naming the mechanism. 13 sites: `core/image.py:15,121`, `core/labels.py:3`,
      `core/meta.py:3`, `datasets/metadata.py:1`, `datasets/yolo.py:6`,
      `augmentations/radiometric.py:73`, `augmentations/seabed.py:57`,
      `augmentations/shadow.py:14,17,45`, `documentation/encyclopedia/f2_radiometric.md:47`,
      `documentation/encyclopedia/f6_shadow.md:11,24`, `docs/architecture.md:94`.

## Tooling not yet present

- [ ] No lint or type-check configuration exists (no ruff/black/mypy, nothing in
      `pyproject.toml` beyond `[tool.pytest.ini_options]`). The codebase is fully annotated
      and Pydantic-modelled, so mypy would likely pay off immediately; pick one and wire it
      into `[dev]`.

- [ ] No CI (no `.github/`, no other runner config). The reproducibility gate (identical
      output tree across worker counts) and the family-contract suite are exactly the things
      that should run on every push.

## Automation worth building (each recurred in practice)

- [ ] **Promote the offscreen GUI smoke test into `tests/test_gui_smoke.py`.** An ad-hoc
      `QT_QPA_PLATFORM=offscreen` script was written and re-written by hand for v0.1, v0.2,
      v0.2.1 and v0.3.0 — every GUI release, and again this session. The assertions that
      have been made to pass, in order: `MainWindow()` constructs and shows;
      `explorer.open_dataset("demo_dataset")` indexes 3 items with `{0: 'object'}`;
      instances add to `win.pipeline`; `_schedule_preview` populates `win.worker._cache`;
      `preview.add_row()` leaves the first row's height unchanged; `gui.encyclopedia._pages()`
      returns 10 pages; `bundled_presets()` returns the 6 presets; `GenerationDialog`
      constructs and `_build_config()` returns a `GenerationConfig`. Mark it
      `@pytest.mark.gui` so it can be skipped where Qt is unavailable.

- [ ] **A docs-sync check (hook or Skill).** Every release required manually updating an
      encyclopedia page, `AUGMENTATION_STRATEGIES.md`, the user manual and the version string
      alongside a code change, and each time something was nearly missed. A pre-commit hook
      that flags "a file under `augmentations/` changed but its encyclopedia page and
      strategies section did not" would enforce non-negotiable #10 mechanically.

- [ ] **A reproducibility gate script.** Generating the same config at 1 vs N workers and
      comparing tree hashes was run by hand at v0.1, v0.2, v0.3 and again this session
      (3 images × 3 copies, mirror + speckle + platform_motion + shadow, laws on `looks` and
      `yaw_std_deg`, seed 1234): images, labels and manifest matched exactly at 1 and 4
      workers. The script must exclude `generated_utc` from `generation_manifest.json` and
      the elapsed line from `statistics.md`, which differ between any two runs — a naive
      whole-tree hash reports a false failure. Make it a single invocable command so it can
      run in CI and before releases.

Beyond these three, no further Skill or subagent is justified yet — the remaining workflows
have each happened once.
