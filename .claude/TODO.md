# TODO — SSS-Dataset-Aug-Studio

Actionable items only. Current-state facts live in `CLAUDE.md`.
Ordered roughly by how much damage the item can do if left alone.

This module has no ROS 2 dependency and no colcon build, so nothing here is blocked on a
sourced ROS workspace. What *is* blocked is marked per item: **BLOCKED — field data**
(needs recorded Omniscan sessions), **BLOCKED — training run**, or **BLOCKED — macOS**.

---

## Correctness / data-integrity risks

- [ ] **GCS seabed pictures are inverted on an approximation.** Recorded 2026-09-15
      from the superproject review (`project_review.md` Part 4, gap G12); **no code change
      here by decision** — the bridge was not selected for the 2026-09-15 update. The
      GCS pictures' JSON carries a `display_model` block (TL parameters, per-side curves
      in `r/h`, `hi_db`, `gamma`, since 2026-09-15 also `transfer` — `power` or
      `db_window` — `window_db` and per-row `gain_port_db`/`gain_stbd_db`) that inverts
      the PNG losslessly, but `AcquisitionMeta.intensity_mapping` knows only
      `linear|gamma|log`, so the studio still inverts GCS pictures with the fixed
      `log_range_db` approximation and no `sss_aug_dataset.yaml` is written by the GCS.
      Reading that block would make the physics-domain augmentations exact for GCS
      datasets. Until then, GCS datasets should be declared `intensity_mapping: log`
      explicitly and the residual scale error accepted.

- [ ] **`tools/make_demo_dataset.py` no longer runs.** It imports the simulator's
      `dataset/` and `mission/` packages, deleted in the 2026-09 simulator rework, so the
      demo fixture cannot be regenerated from the current tree (untracked developer
      script, not part of the installed package). Recorded 2026-09-15; fix or retire
      when the fixture is next rebuilt.

- [x] ~~No reader for the raw-float `.npz`.~~ **Resolved by decision, 2026-09-01:
      the AI feed is pictures + metadata.** The project settled that detector training
      consumes the GCS seabed PNGs (raw native slant-bin waterfall) with their JSON
      metadata; the `_world.npz` is an auxiliary georeferencing/analysis record, not a
      training input, so `SonarImage.load`'s 8-bit reader is the intended interface.
      Superproject `CLAUDE.md` §4.5 was updated the same day. (The earlier
      direction — the raw-float `.npz` as the training input — was recorded in
      a `.claude/specs/` note that went with that directory on 2026-09-18; what
      it established and is still in force is the contract itself: the reader
      honours **any** `AcquisitionMeta` field at either position and warns on an
      unrecognised key, and `intensity_mapping` must be declared explicitly
      because its absent-default (`log`) mis-inverts a linear dataset.)

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
