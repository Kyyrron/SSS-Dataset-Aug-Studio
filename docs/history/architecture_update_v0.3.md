# Architecture update — v0.3.0

> **Historical.** Superseded by `docs/architecture.md`, which describes the
> current release. Kept as a record of what changed at this release; not
> maintained.

Delta only. Two corrections driven by usage feedback.

## 1. Preview rows: independent, user-resizable heights

Problem in v0.2.1: rows shared the stack's vertical space, so adding a row
rescaled every other row and image views could end up clipped on small
screens.

Changes (GUI layer, `gui/preview.py`):

* Every `PreviewRow` now has a **fixed height that the user adjusts** by
  dragging a **resize grip** along the row's bottom edge (clamped
  160–1400 px, default 340 px). Adding or removing a row therefore **never
  changes the size of existing rows** — the stack simply grows/shrinks
  inside the scroll area.
* When an image is assigned to a row (or the tile count changes), image
  tiles perform a one-shot **fit-to-view** so the waterfall and its label
  overlay are fully visible at any row height or screen size; wheel zoom /
  pan still work afterwards.
* Zoom/pan synchronization is now scoped **per row** instead of globally:
  tiles in one row show the same image and stay locked together; syncing
  transforms across rows of differently-sized images produced confusing
  offsets and is dropped.

## 2. Stochastic laws are a property of the augmentation instance

Problem in v0.2.x: distributions were edited only in the Generation dialog
and stored profile-side (`mode: deterministic | stochastic` chosen at save
time) — two places, unclear ownership.

New model — **one owner, defined where the augmentation is configured**:

* `AugmentationInstance` gains
  `distributions: dict[param_name, DistSpec dict]` (empty = fully fixed).
  A parameter is either *fixed* (its value in `params`, which also serves as
  the nominal preview value) or follows a *stochastic law* (uniform / normal
  / log-uniform), chosen **per parameter directly in the Augmentation
  Parameters form** via a law selector on each float-parameter row (a second
  line with the law's a/b values appears when stochastic).
* `config_hash()` **excludes** `distributions`: previews are deterministic
  renderings of the nominal values, so editing a law never invalidates the
  preview stage cache.
* **Generation** builds `InstanceGenSpec.param_distributions` directly from
  each enabled instance — the dialog's editable distribution table is
  replaced by a read-only *stochastic summary*; the engine and its
  reproducibility guarantees are unchanged.
* **Profiles** no longer carry an execution mode: saving stores the
  instances (laws included); the Save dialog reduces to name + description.
  A profile is de facto deterministic when no instance declares a law.
  **Backward compatibility:** loading a legacy `mode: stochastic` profile
  migrates its `distributions` block into the matching instances (legacy
  fields remain accepted, deprecated).

Removed: `MainWindow.session_distributions`, the Generation dialog's
distribution table and its prefill/persist callbacks, the mode selector in
the profile save dialog.
