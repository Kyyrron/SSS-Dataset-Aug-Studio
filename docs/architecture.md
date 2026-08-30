# Architecture — Physics-Informed SSS Augmentation Studio

Version 0.4.0.

## 0. How this document is maintained

`architecture.md` always describes the **current release**. Release deltas are
folded into it at the release commit; no new `architecture_update_*` file is
created. The superseded v0.2.0 / v0.2.1 / v0.3.0 delta documents are kept
in `docs/history/` as a record of what changed at each release, and are not
maintained.

## 1. Layering

```
┌─────────────────────────────────────────────────────────────┐
│ gui/            PySide6: main window, docks, preview, forms │  GUI layer
├─────────────────────────────────────────────────────────────┤
│ generation/     batch engine, distributions, headless CLI   │
│ profiles/       named pipeline configurations + presets     │  application
│ datasets/       YOLO indexing, modular metadata readers     │  services
├─────────────────────────────────────────────────────────────┤
│ augmentations/  10 families, 9 modules: F1-F8 physics +     │
│                 G1/G2 geometry (1 module each; geometric.py │
│                 carries both G-families)                    │
├─────────────────────────────────────────────────────────────┤
│ core/           SonarImage, meta, warps, labels, pipeline,  │  GUI-free
│                 registry, deterministic RNG tree            │  core
│ physics/        acoustics, geometry, statistics, trajectory │
└─────────────────────────────────────────────────────────────┘
```

**The core is GUI-free.** Everything below `gui/` runs headless (the test
suite and `sss-aug-generate` exercise it without Qt). The GUI is a thin
observer/editor of core objects.

## 2. Core data model

| Type | Responsibility |
|---|---|
| `AcquisitionMeta` (Pydantic) | physical acquisition context: layout (`dual`/`single_port`/`single_starboard`), altitude, slant range, resolutions, speed, depth, frequency, `intensity_mapping`, `shadow_included`. The per-field `resolved_*()` accessors return documented fallbacks when a field is absent (normalized mode); `is_physical` flags which mode is active. |
| `SonarImage` | float32 `[0,1]` array in the linear intensity domain; rows = pings. `sides()` yields per-side canonical **range-increasing views** so augmentation code is written once regardless of layout; `nadir_band()` auto-detects the dark nadir strip in dual layouts (declared value takes precedence). |
| `FieldWarp` | bidirectional geometric transform: inverse maps (`cv2.remap` for pixels) + analytic forward displacement (for labels). Supports composition and strength scaling. |
| `LabelSet` / `YoloBox` | YOLO labels as first-class citizens; `warped()` pushes an 8-point box hull through the forward map, re-hulls, drops boxes below the retention threshold (default 0.6) and records `BoxProvenance`. |
| `AugmentationInstance` | family key + label + enabled + probability + strength + `params` (nominal values) + `distributions` (per-parameter stochastic laws). `config_hash()` is the cache/repro key and **excludes `distributions`** — see §5. |
| `AugmentationPipeline` | ordered instance list; `apply()` produces `PipelineResult` (image, labels, per-stage records, manifest). Preview mode applies every enabled instance; generation mode draws per-instance Bernoulli gates. |

### 2.1 Dataset conventions

Both are declared by the acquisition pipeline, never inferred, and are
honoured at dataset level (`sss_aug_dataset.yaml`) or per image (sidecar
JSON).

* **`shadow_included`** (default **true**) — a YOLO box covers the object's
  complete acoustic signature, highlight **and** shadow. F6 moves the
  down-range box edge when it rescales shadow length only if the flag is
  true; with `false` it modifies pixels and never touches labels. The
  Explorer metadata table displays the flag and generation manifests record
  it.
* **`intensity_mapping`** (`linear` / `gamma` / `log`) — see §6.

## 3. Determinism

All randomness flows from one **SeedSequence tree**:

```
derive_rng(master_seed, image_key, instance_id, copy_index, purpose…)
```

Keys are hashed (SHA-256) into `SeedSequence(entropy, spawn_key)`. Properties:

* same master seed ⇒ byte-identical datasets;
* independence across images/instances/copies ⇒ **worker-count independent**
  parallel generation;
* changing one instance's parameters does not perturb the noise of others.

Byte-reproducibility is a release gate, asserted end-to-end by
`tools/repro_gate.py` (one config run at 1 and at N workers, trees compared).
`generated_utc` in `generation_manifest.json` and the elapsed line in
`statistics.md` are wall-clock and sit outside the guarantee.

## 4. Extension contract — one file per family

A new augmentation family is a single module in `augmentations/`:

```python
class MyParams(AugParams):
    my_length_m: float = Field(1.0, ge=0.0, le=10.0, description="... [m]")

@register
class MyAug(Augmentation):
    key, name, order_hint = "my_key", "My name", 45
    section = "physics"            # or "geometry"
    Params, card = MyParams, ScienceCard(...)
    def apply(self, img, labels, params, rng, strength) -> AugResult: ...
```

Everything else is automatic: the science card appears in the Library, the
parameter form is generated from the Pydantic schema (bounds → slider range,
`[unit]` suffix → unit label, description → tooltip), each float parameter
gets a stochastic-law selector, profiles serialize it, and the
family-contract test (`test_family_contract`) covers it by iterating the
registry.

`AugResult` carries the four ways a family may act:

* geometric change → `warp=FieldWarp(...)`; labels follow automatically;
* direct label edit → `labels_override` (F6);
* layout / nadir / heading change → `meta_override`; the pipeline rebuilds
  the `SonarImage` with the new metadata and resets the cached nadir band
  (the G-families);
* photometric → pixels only, honouring `strength` via `blend()`.

### 4.1 Sections: geometry vs physics

`Augmentation.section` is `"physics"` or `"geometry"`; the Library groups
cards under two headers. Registry, pipeline, profiles, preview and generation
treat both alike — the G-families are ordinary registered families with
`order_hint` 1–2, i.e. first in the physical order, because they represent
the *acquisition-direction choice*, logically prior to everything else.

* **G1 `mirror_across_track`** — exact column-reversal `FieldWarp`
  (involution). `single_port ↔ single_starboard` via `meta_override`; `dual`
  swaps sides with the nadir metadata mirrored (`nadir_center_frac → 1 − c`;
  centered waterfalls keep the nadir in place). Because each side's canonical
  range axis maps onto the other side's, shadows remain strictly down-range.
* **G2 `reverse_along_track`** — exact row-reversal `FieldWarp` (survey line
  replayed in the opposite direction); heading metadata rotated 180° when a
  heading was recorded.

Both are involutions, and their `strength` is intentionally binary (any value
> 0 applies the full transform); use `probability` to control frequency.

## 5. GUI architecture

* `MainWindow` owns session state (dataset, pipeline, master seed).
* Preview recomputation: 150 ms debounce → `_PreviewWorker` (QThread) holding
  a **lock-guarded per-row job map**, emitting `computed(row_id, image,
  labels)`. A **per-stage cache** keyed by the cumulative chain of
  `config_hash()`es recomputes only stages from the first change onward; keys
  start with the image key, so rows cache independently. Bounded at 128
  entries, cleared on seed change.
* **Preview (Area 4)** is a scrollable vertical stack of selectable
  `PreviewRow`s, each displaying one dataset image through 1–6 tiles (the
  tile count is shared across rows). Each row has its **own fixed height**,
  dragged via a bottom-edge grip and clamped 160–1400 px (default 340), so
  adding or removing a row never resizes the others. A newly assigned image
  fits to view once. Zoom/pan synchronization is scoped **per row** — tiles
  in a row share an image, while syncing across rows of differently-sized
  images produced misleading offsets. The pipeline order strip below the rows
  is global: one pipeline, many images.
* `ParamsForm` is generated per selection; edits mutate the shared
  `AugmentationInstance` and trigger the debounce. Each float parameter
  carries a law selector — *fixed*, *uniform*, *normal*, *loguniform* — whose
  values appear on a second line. Laws are stored on the instance and
  consumed by generation; the left-hand value stays the nominal value the
  preview renders. `config_hash()` excludes `distributions` precisely so that
  editing a law never invalidates the preview stage cache.
* `PipelineStrip` reorder = permutation of `pipeline.instances`;
  “Physical order” calls `pipeline.sort_physical()` (order_hint sort).
* The generation dialog builds a `GenerationConfig` — copying each enabled
  instance's laws into `InstanceGenSpec.param_distributions` and showing a
  read-only stochastic summary — and runs the same engine as the CLI in a
  worker thread (progress/ETA/cancel signals).
* **Profiles** store instances including their laws. There is no execution-mode
  selector: a profile is stochastic iff some parameter declares a law
  (`PipelineProfile.is_stochastic`). There are no profile-level
  `mode`/`distributions` fields, and `extra="forbid"` means a profile written
  before v0.4.0 — which still carries them — is rejected by name rather than
  loaded with its laws silently dropped.

## 6. Intensity-domain policy

Internal processing is linear `[0,1]` — the domain where multiplicative sonar
physics is native. The export mapping is **declared** by the acquisition
pipeline (`sss_aug_dataset.yaml: intensity_mapping`) and exactly inverted on
load; dB-parameterized effects (F2/F5/F7/F8 gains) convert via `10^(dB/10)`,
so each computation runs in its physically appropriate domain by
construction.

* When no mapping is declared the documented default assumption is **`log`**
  (dB waterfall export, `log_range_db` dynamic range, default 40 dB), which
  matches how SSS software normally exports waterfalls — and the GCS
  `intensity_db` export in particular. A dataset that is actually linear and
  does not say so is silently mis-inverted, which is why the field must be
  declared explicitly.
* Batch export takes mapping `auto` by default: re-apply the declared input
  mapping, so original and augmented files live in the same domain.

The inverse is exact only to the extent the declared mapping describes the
export; the residual approximation and its consequences are stated in
`docs/scientific_documentation.md`.

## 7. Known approximations

1. **Equation rendering**: encyclopedia equations are fenced code blocks, not
   pre-rendered SVG (matplotlib mathtext). Rationale: zero extra runtime
   dependency and no rendering failure modes; the `equations` extra and a
   renderer hook remain planned (see `future_work.md`).
2. **Turn geometry** (F4): integrated-heading shear approximation of the
   swath fan rather than full polar resampling — documented in
   `f4_platform_motion.md` §6.
3. **Shadow segmentation** (F6): Otsu-based in-box segmentation behind a
   confidence gate, which skips a box rather than guessing — documented in
   `f6_shadow.md` §6.
4. **Multipath** (F8): incoherent and phenomenological — a hard-negative
   generator, not calibrated echo levels — documented in `f8_multipath.md` §6.

## 8. Cross-platform text IO

**Every** text read and write in the package passes `encoding="utf-8"`
explicitly (encyclopedia loader, profiles, presets, dataset config and
sidecars, labels, generation outputs, CLI, QSS loader). Relying on the OS
default codec raises `UnicodeDecodeError` on Windows, where cp1252 cannot
decode the shipped documentation. A regression test that loads every
encyclopedia page enforces it.
