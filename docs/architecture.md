# Architecture — Physics-Informed SSS Augmentation Studio

Version 0.1.0 · companion to the validated design review
(`DESIGN_REVIEW_sss_augmentation_studio.md`).

## 1. Layering

```
┌─────────────────────────────────────────────────────────────┐
│ gui/            PySide6: main window, docks, preview, forms │  GUI layer
├─────────────────────────────────────────────────────────────┤
│ generation/     batch engine, distributions, headless CLI   │
│ profiles/       named pipeline configurations + presets     │  application
│ datasets/       YOLO indexing, modular metadata readers     │  services
├─────────────────────────────────────────────────────────────┤
│ augmentations/  8 physics-informed families (1 file each)   │
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
| `AcquisitionMeta` (Pydantic) | physical acquisition context: layout (`dual`/`single_port`/`single_starboard`), altitude, slant range, resolutions, speed, depth, frequency. `resolved_*()` accessors return documented fallbacks when a field is absent (normalized mode); `is_physical` flags which mode is active. |
| `SonarImage` | float32 `[0,1]` array in the (approximately) linear intensity domain; rows = pings. `sides()` yields per-side canonical **range-increasing views** so augmentation code is written once regardless of layout; `nadir_band()` auto-detects the dark nadir strip in dual layouts (declared value takes precedence). |
| `FieldWarp` | bidirectional geometric transform: inverse maps (`cv2.remap` for pixels) + analytic forward displacement (for labels). Supports composition and strength scaling. |
| `LabelSet` / `YoloBox` | YOLO labels as first-class citizens; `warped()` pushes an 8-point box hull through the forward map, re-hulls, drops boxes below the retention threshold and records `BoxProvenance`. |
| `AugmentationInstance` | family key + label + enabled + probability + strength + params dict; `config_hash()` is the cache/repro key. |
| `AugmentationPipeline` | ordered instance list; `apply()` produces `PipelineResult` (image, labels, per-stage records, manifest). Preview mode applies every enabled instance; generation mode draws per-instance Bernoulli gates. |

## 3. Determinism

All randomness flows from one **SeedSequence tree**:

```
derive_rng(master_seed, image_key, instance_id, copy_index, purpose…)
```

Keys are hashed (SHA-256) into `SeedSequence(entropy, spawn_key)`. Properties:

* same master seed ⇒ byte-identical datasets (verified in tests);
* independence across images/instances/copies ⇒ **worker-count independent**
  parallel generation (verified: tree-hash equality between 1 and 3 workers);
* changing one instance's parameters does not perturb the noise of others.

## 4. Extension contract — one file per family

A new augmentation family is a single module in `augmentations/`:

```python
class MyParams(AugParams):
    my_length_m: float = Field(1.0, ge=0.0, le=10.0, description="... [m]")

@register
class MyAug(Augmentation):
    key, name, order_hint = "my_key", "My name", 45
    Params, card = MyParams, ScienceCard(...)
    def apply(self, img, labels, params, rng, strength) -> AugResult: ...
```

Everything else is automatic: the science card appears in the Library, the
parameter form is generated from the Pydantic schema (bounds → slider range,
`[unit]` suffix → unit label, description → tooltip), the generation dialog
offers distributions for each numeric field, profiles serialize it, and the
family-contract test (`test_family_contract`) covers it by iterating the
registry.

Geometric families return a `FieldWarp` (labels follow automatically);
label-editing families (F6) return `labels_override`; photometric families
return pixels only.

## 5. GUI architecture

* `MainWindow` owns session state (dataset, current item, pipeline, seed).
* Preview recomputation: 150 ms debounce → `_PreviewWorker` (QThread) →
  **per-stage cache** keyed by the cumulative chain of `config_hash()`es, so
  editing stage *k* of *n* recomputes only stages *k…n*. Cache is bounded
  (64 entries) and invalidated on seed change.
* `ParamsForm` is generated per selection; edits mutate the shared
  `AugmentationInstance` and trigger the debounce.
* `PipelineStrip` reorder = permutation of `pipeline.instances`;
  “Physical order” calls `pipeline.sort_physical()` (order_hint sort).
* The generation dialog builds a `GenerationConfig` and runs the same engine
  as the CLI in a worker thread (progress/ETA/cancel signals).

## 6. Intensity-domain policy (decision #4)

Internal processing is linear `[0,1]`. Loaders invert declared gamma/log
mappings (`sss_aug_dataset.yaml: intensity_mapping`); undeclared 8-bit input
is **treated as linear — a documented approximation**. Export re-applies the
chosen mapping. Radiometric (dB) operations are exactly correct only in true
linear data; the approximation and its consequences are stated in
`docs/scientific_documentation.md`.

## 7. Deviations from the design review (v0.1)

1. **Equation rendering**: encyclopedia equations are fenced code blocks, not
   pre-rendered SVG (matplotlib mathtext). Rationale: zero extra runtime
   dependency and no rendering failure modes; the `equations` extra and a
   renderer hook remain planned (see `future_work.md`).
2. **K-distribution texture**: smoothed-gamma field (exact mean/variance,
   approximate marginal) instead of exact gamma-copula sampling — documented
   in `f1_speckle.md` §6.
3. **Turn geometry** (F4): integrated-heading shear approximation of the
   swath fan rather than full polar resampling — documented in
   `f4_platform_motion.md` §6.

No other deviations; all validated decisions (#1 layouts, #2 modular
metadata readers, #3 highlight+shadow labels, #4 intensity policy, #5
conservative gated F6, physical-unit parameterization) are implemented.
