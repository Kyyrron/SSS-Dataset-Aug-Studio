# User manual

## What this tool does

You point it at a **YOLO dataset of side-scan sonar images**; you compose a
pipeline of **physically motivated augmentations** with live preview; you
generate an **augmented dataset** in which every new image is a plausible
alternative acquisition of the same scene — different sea state, altitude,
gain, seabed, turbidity, or basin geometry — with **labels moved
consistently** and full reproducibility from a single seed.

## 1. Prepare your dataset

Standard YOLO layout (both variants supported):

```
dataset/
  data.yaml                  # names: {0: wreck, 1: tire, ...}
  images/…  labels/…         # flat, or images/train, labels/train, …
```

### Acquisition metadata (recommended)

Physical-unit mode activates when metadata is available; otherwise the tool
falls back to documented normalized defaults (you will see *"normalized
fallback"* in the Explorer).

**Dataset-level defaults** — `sss_aug_dataset.yaml` at the root:

```yaml
layout: dual                 # dual | single_port | single_starboard
intensity_mapping: log       # linear | log | gamma — DECLARED, never inferred.
                             # The project controls the image-generation pipeline,
                             # so declare what it exported. If absent, the tool
                             # assumes log/dB (the documented default).
shadow_included: true        # label convention: a YOLO box covers the complete
                             # acoustic signature = highlight + acoustic shadow
meta:
  altitude_m: 2.0
  slant_range_m: 30.0
  res_along_m: 0.08
  speed_mps: 1.5
  depth_m: 5.0
  frequency_khz: 450
```

**Per-image sidecar** — `myimage.json` next to `myimage.png` overrides the
defaults per image (e.g. produced by your acquisition/FBR pipeline):

```json
{"layout": "single_starboard", "altitude_m": 1.6, "slant_range_m": 25.0}
```

**Label convention (`shadow_included`).** With `true` (default), a box covers
the complete acoustic signature — highlight **and** shadow — and the shadow
family (F6) moves the down-range box edge whenever it rescales the shadow.
With `false`, F6 modifies pixels only and never touches labels.

**Intensity domain.** The engine works internally in linear intensity and
automatically performs each computation in its physically appropriate
domain: multiplicative effects (speckle, reflectivity) in the linear domain,
additive gains/attenuations expressed in dB and converted via `10^(dB/10)`.
Loading exactly inverts the declared mapping; export mapping `auto`
re-applies it, so originals and augmented files live in the same domain.

## 2. GUI tour

* **Dataset Explorer** (left): open dataset, filter by class, Prev/Random/
  Next, per-image metadata table showing which physical values are in effect.
* **Augmentation Library** (right): two sections — **Geometry** (G1
  across-track mirror, G2 along-track reversal: exact acquisition symmetries,
  layout-aware, label-consistent) and **Physics-informed families** (F1–F8).
  One science card per family — phenomenon, governing equation, references. `＋ instance` adds a configurable instance
  (families support multiple instances, e.g. two speckle regimes);
  `Details` opens the encyclopedia page. The `on` checkbox toggles a whole
  family.
* **Augmentation Parameters** (bottom): auto-generated form for the selected
  instance — instance name, enabled, **probability** (used during
  generation), **strength** (0–2, live), and every physical parameter with
  slider + spinbox, bounds and units. Each float parameter also carries a
  **law selector**: *fixed* (default), or *uniform / normal / log-uniform* —
  choosing a law reveals its values (low/high or mean/std) on a second line.
  During dataset generation each copy samples the parameter from its law;
  the value on the left remains the **nominal value used by the live
  preview** (previews are always deterministic). All edits update the
  preview (~150 ms); editing a law never triggers a recompute.
* **Interactive Preview** (center): one or more **preview rows**, each
  showing one dataset image through 1–6 zoom-synchronized tiles (the *Tiles*
  selector sets the column count for **all** rows). Each tile shows
  Original / Augmented / Difference / Before-After slider / Histogram /
  Intensity profile (click to pick the profile row). Green boxes = original
  labels, orange = augmented labels. By default there is a single row with
  two tiles. Press **＋ Add row** to compare the current pipeline across
  several images: the new row is selected (blue border) — click any image in
  the Dataset Explorer to place it there; click a row at any time to select
  it and re-assign its image the same way; ✕ removes a row (the last row
  cannot be removed). Each row has its **own height**: drag the grip along a
  row's bottom edge to resize it — adding or removing rows never changes the
  size of the other rows, and a newly assigned image is automatically fitted
  to its tiles. Zoom and pan stay synchronized between the tiles of the same
  row. The **Order strip** below the rows is global (one pipeline,
  many images): drag to reorder, uncheck to bypass, or press **Physical
  order** to restore the causal chain.
* **Master seed** (toolbar): previews and generation are deterministic in
  this seed.

## 3. Profiles

`Profiles ▸ Load preset`: *Calm sea, Moderate waves, Harbour inspection,
River, Highly turbid environment, Fast survey* — curated physical parameter
sets. Load one, tune it, then `Save current as…`.

A profile simply stores its augmentation instances — **including any
per-parameter stochastic laws** configured in the Parameters form. There is
no execution mode to choose: a profile is deterministic when no parameter
declares a law, stochastic otherwise (the status bar shows which when
loading). Legacy v0.2 profiles that carried a profile-level
`mode: stochastic` block are migrated automatically on load. Seeds remain
fully reproducible in both cases.

## 4. Generate a dataset

`Generate ▸ Generate augmented dataset…`:

1. output folder, master seed, copies per image;
2. **combination policy** — allow multiple augmentations per copy (each
   instance applies with its probability) or exactly one per copy;
3. export intensity mapping (`auto` = same as input / linear / gamma /
   log);
4. review the read-only **stochastic summary** — the laws configured per
   parameter in the Augmentation Parameters form (this dialog no longer
   edits them);
5. `Generate` — progress, ETA, cancel.

Output guarantees:

* originals copied **unmodified** alongside `{stem}__augN` copies;
* labels warped consistently; boxes that leave the image or fall below 60 %
  retention are dropped (logged);
* `generation_manifest.json` — full config + per-image applied instances and
  sampled parameters (the audit trail for the thesis);
* `statistics.md` — application counts, sampled parameter ranges, box budget.

Re-running with the same config file and seed reproduces the dataset
**byte-for-byte**, regardless of worker count.

## 5. Headless / scripted use

Export the config from the dialog (`Export config YAML`), then:

```bash
sss-aug-generate generation_config.yaml            # exact reproduction
sss-aug-generate generation_config.yaml --seed 7   # new variant
```

## 6. Recommended practice

* Start from the preset closest to your target deployment; keep parameters
  inside ranges you have *measured* on real acquisitions (each encyclopedia
  page §7 tells you what to measure).
* Prefer several moderate augmentations over one extreme one.
* Keep a held-out **real** test set from the target conditions; augmentation
  is judged by real-data mAP, not by visual appeal.
