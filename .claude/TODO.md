# TODO — SSS-Dataset-Aug-Studio

Actionable items only. Current-state facts live in `CLAUDE.md`.
Ordered roughly by how much damage the item can do if left alone.

This module has no ROS 2 dependency and no colcon build, so nothing here is blocked on a
sourced ROS workspace. What *is* blocked is marked per item: **BLOCKED — field data**
(needs recorded Omniscan sessions), **BLOCKED — training run**, or **BLOCKED — macOS**.

---

## Correctness / data-integrity risks

- [ ] **No reader for the raw-float `.npz`.** The superproject `CLAUDE.md` §4.5 directs
      authors to train on the GCS `_world.npz` (raw `intensity_db`) rather than the PNG, but
      `SonarImage.load` (`core/image.py`) reads 8-bit images through `cv2.imread` only.
      Consuming the raw floats would sidestep the per-image percentile window the GCS applies
      at export and make the intensity mapping exact instead of approximate. Surfaced by the
      `intensity_mapping` audit in `.claude/specs/dataset-metadata-contract.md`.

- [ ] **BLOCKED — field data. Swap the synthetic `demo_dataset` for real beach imagery.**
      The fixture is currently rendered by `blueboat_sss_sim` (`tools/make_demo_dataset.py`),
      which settles provenance, licensing and label ground truth, so this no longer gates a
      public release. What it does not give is the target domain: the demo, and the four
      `docs/demo_*.png` figures, show simulated seabed. Substitute a small slice of real
      labelled beach imagery once a session provides one and its licensing is settled.

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

- [ ] **BLOCKED — field data.** Record measured wall-echo distance/width/level ranges from
      real port imagery and re-tune the F8 defaults to that envelope (currently
      `wall_distance_m: 15.0`, `wall_width_m: 0.6`, `wall_gain_db: 6.0`).

## Automation worth building (each recurred in practice)

No further Skill or subagent is justified yet — the remaining workflows have each happened
once. The docs-sync gate that used to sit here now exists as `tools/docs_sync_check.py`,
wired through `.githooks/pre-commit`.
