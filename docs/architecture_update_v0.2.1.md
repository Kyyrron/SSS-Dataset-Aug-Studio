# Architecture update — v0.2.1

Delta only. Scope: the Interactive Preview (Area 4) becomes **multi-row**;
no change to core, physics, datasets, generation, profiles or families.

## 1. Behavior

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

## 2. Design changes (GUI layer only)

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
