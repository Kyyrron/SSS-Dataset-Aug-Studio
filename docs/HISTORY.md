# SSS-Dataset-Aug-Studio — history

*Release deltas, newest last. Merged on 2026-11-18 (session 11) from `docs/history/*.md`, each kept **verbatim**
below (headings moved down one level). They are superseded by `docs/DESIGN.md` Part 1, which describes the
current release (0.4.0). One line per later event:*

- **2026-10-20.** Owner's decision (superproject CM-11): the headline detector is trained on simulated
  datasets from BlueBoat-Perception's dataset mode. The superproject lists this studio as **optional**: nothing
  in the chain depends on it.
- **2026-11-18.** The simulator was frozen (`sim-freeze-v1.0-2026-11-18`, literal verdict NOT READY, a
  model-conditional tool). Simulated results follow the superproject's `SIM_VALIDITY_CONDITIONS.md`. In
  session 11 the documentation was merged into `README.md`, `docs/DESIGN.md`, `docs/user_manual.md` and
  this file.

## Release 0.2.0 (was `docs/history/architecture_update_v0.2.md`)

## Architecture update — v0.2.0

> **Historical.** Superseded by `docs/architecture.md` (since 2026-11-18 `docs/DESIGN.md` Part 1), which describes the
> current release. Kept as a record of what changed at this release; not
> maintained.

Delta document only; `architecture.md` describes the base system. No layer is
redesigned — this release adds two conventions, one augmentation *section*,
one profile capability, and one bug-class fix.

### 1. Dataset conventions (now fixed)

#### 1.1 `shadow_included`
New boolean on `AcquisitionMeta` (default **true**), settable per dataset
(`sss_aug_dataset.yaml`) or per image (sidecar JSON). Semantics: a YOLO box
covers the object's complete acoustic signature — highlight **and** shadow.
Consumers:

* **F6** moves the down-range box edge when scaling shadow length **only if**
  `shadow_included` is true; with `false` it modifies pixels but never labels.
* Explorer metadata table displays the flag; generation manifests record it.

#### 1.2 Declared intensity mapping, dB-first
The mapping is *declared* by the acquisition pipeline, never inferred. The
internal processing domain stays **linear [0,1]** (unchanged — it is the
domain where multiplicative physics is native); loaders exactly invert the
declared export mapping, and dB-parameterized effects (F2/F5/F7/F8 gains)
convert via `10^(dB/10)` — i.e. each computation happens in its physically
appropriate domain by construction. What changes:

* **Default assumption when metadata is absent flips from `linear` to
  `log`** (`log_range_db` = 40 dB), matching how SSS software normally
  exports waterfalls. The old linear-approximation caveat is replaced by a
  documented dB-default.
* Batch export gains mapping `auto` (default): re-apply the input mapping so
  original↔augmented files live in the same domain.

### 2. New section: Geometry (G-families)

`Augmentation.section: ClassVar["physics"|"geometry"] = "physics"` — the
Library groups cards under two headers; registry, pipeline, profiles,
preview and generation are untouched (G-families are ordinary registered
families with `order_hint` 1–2, i.e. first in the physical order: they
represent the *acquisition direction choice*, logically prior to everything).

* **G1 `mirror_across_track`** — exact column-reversal `FieldWarp`
  (involution). Layout handling: `single_port ↔ single_starboard` via the new
  `AugResult.meta_override`; `dual` swaps sides, nadir metadata mirrored
  (`nadir_center_frac → 1 − c`; centered waterfalls keep the nadir in place).
  Because each side's canonical range axis maps onto the other side's range
  axis, shadows remain strictly down-range — physically consistent.
* **G2 `reverse_along_track`** — exact row-reversal `FieldWarp` (survey line
  replayed in the opposite direction); heading metadata rotated by 180° when
  present. All other physical properties preserved.

Pipeline extension: `AugResult.meta_override` (optional `AcquisitionMeta`);
when present the pipeline rebuilds the `SonarImage` with the new metadata
(also resetting the cached nadir band). One field + three lines — no
behavioral change for existing families.

### 3. Profile execution modes

`PipelineProfile` gains:

```yaml
mode: deterministic | stochastic     # default: deterministic
distributions:                       # only meaningful in stochastic mode
  <instance_id>: {<param>: {dist: uniform, low: …, high: …}, …}
```

* **deterministic** — fixed parameter values (reproducible experiments);
  distributions are ignored by the engine.
* **stochastic** — the generation dialog pre-fills its distribution table
  from the profile; per-copy sampling uses the existing RNG tree, so seeds
  remain fully reproducible (unchanged engine guarantee).

Save flow: *Profiles ▸ Save current as…* now asks name/description/**mode**;
stochastic saves capture the session's current distribution table (edited in
the generation dialog, persisted back to the session on build/export/run).
Bundled presets are explicitly `mode: deterministic`.

### 4. Cross-platform text IO (bug fix)

Root cause of the reported `UnicodeDecodeError`: `read_text()` /
`write_text()` without `encoding=` use the OS-default codec (cp1252 on
Windows) while all shipped files are UTF-8. Fix: **every** text read/write in
the package now passes `encoding="utf-8"` (encyclopedia loader, profiles,
presets, dataset config/sidecars, labels, generation outputs, CLI, QSS
loader). Enforced by a regression test that loads every encyclopedia page.

### 5. Documentation delta

New root-level: `PROJECT_OVERVIEW.md`, `GETTING_STARTED.md`,
`AUGMENTATION_STRATEGIES.md` (per-family: physical origin, math, DOI-verified
references, core code excerpt, expected effect, limitations, rigor class).
Updated: user manual (§conventions, §geometry, §profile modes), scientific
documentation (intensity policy), encyclopedia `00_overview` (flips are now
implemented as G1/G2, dB default), `f6_shadow` (`shadow_included`), new
`g_geometry.md`. Version bumped to 0.2.0.

## Release 0.2.1 (was `docs/history/architecture_update_v0.2.1.md`)

## Architecture update — v0.2.1

> **Historical.** Superseded by `docs/architecture.md` (since 2026-11-18 `docs/DESIGN.md` Part 1), which describes the
> current release. Kept as a record of what changed at this release; not
> maintained.

Delta only. Scope: the Interactive Preview (Area 4) becomes **multi-row**;
no change to core, physics, datasets, generation, profiles or families.

### 1. Behavior

* Default state is unchanged: **one row, two tiles** (Original | Augmented).
* **“＋ Add row”** appends a preview row. Each row displays one image of the
  open dataset; **every row has the same number of tiles** — the existing
  “Tiles” selector now sets the *column count for all rows*.
* Rows are **selectable** (click anywhere on the row; blue border marks the
  selection). Clicking an image in the Dataset Explorer **assigns that image
  to the selected row**. A newly added row is auto-selected and shows a
  “select an image in the Explorer” placeholder until assigned.
* Rows other than the last remaining one can be removed (✕ in the row
  header). Zoom/pan stays synchronized across *all* tiles of *all* rows,
  which is the point of multi-row comparison.

### 2. Design changes (GUI layer only)

| Component | Change |
|---|---|
| `PreviewRow` (new, `gui/preview.py`) | One image's tile strip: header (name + ✕), horizontal run of `PreviewTile`s, and the row's **source state** (`item_idx`, `image_key`, original `SonarImage` + `LabelSet`) and last computed result. Emits `clicked(row_id)` / `remove_requested(row_id)`. `PreviewTile` itself is unchanged. |
| `PreviewArea` | Grid replaced by a scrollable vertical stack of `PreviewRow`s + “＋ Add row”. Owns selection (`selected_row_id`), `assign_to_selected(...)`, `set_row_result(row_id, …)`, and propagates the global tile count to every row. The pipeline `Order strip` remains global below the rows (one pipeline, many images — by design). |
| `_PreviewWorker` (`gui/main_window.py`) | Single latest-job slot becomes a **per-row job map** guarded by a lock; the worker drains it and emits `computed(row_id, image, labels)`. The existing per-stage cache needs no change: cache keys already start with the image key, so rows cache independently (bound raised 64 → 128). |
| `MainWindow` | Explorer clicks route to `preview.assign_to_selected(...)` instead of a single current image; pipeline/seed edits schedule recomputation of **all populated rows** (debounce unchanged). Explorer additionally emits on `itemClicked` so re-clicking the already-highlighted image still fills a newly selected row. |
| `style.qss` | Selected-row border rule (`QFrame#previewRow[selected="true"]`). |

Rationale: per-row state lives in the row widget (single owner, no parallel
bookkeeping in `MainWindow`); the one-pipeline-many-images model preserves
the tool's purpose — judging one augmentation configuration across several
dataset images simultaneously.

## Release 0.3.0 (was `docs/history/architecture_update_v0.3.md`)

## Architecture update — v0.3.0

> **Historical.** Superseded by `docs/architecture.md` (since 2026-11-18 `docs/DESIGN.md` Part 1), which describes the
> current release. Kept as a record of what changed at this release; not
> maintained.

Delta only. Two corrections driven by usage feedback.

### 1. Preview rows: independent, user-resizable heights

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

### 2. Stochastic laws are a property of the augmentation instance

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
