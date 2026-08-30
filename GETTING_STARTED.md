# Getting started

Goal: from a fresh clone to your first augmented dataset in ~5 minutes.

## 1. Install

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[gui]"          # core + PySide6 GUI
pip install -e ".[dev]"          # optional: pytest
```

Dependencies (installed automatically): numpy, scipy, opencv-python-headless,
pydantic v2, PyYAML; GUI extra adds PySide6. Python ≥ 3.10.

## 2. Project structure (what you'll touch)

```
demo_dataset/            ready-to-open 4-image YOLO demo (synthetic)
sss_aug_studio/          the package (core / physics / augmentations / gui / …)
docs/                    reference documentation
PROJECT_OVERVIEW.md      map of everything
AUGMENTATION_STRATEGIES.md   per-family science + code
```

## 3. First launch

```bash
sss-aug-studio demo_dataset
```

You should see a dual-side waterfall: a dark water column down the centre,
the seabed brightening away from it on both sides. Verify: `pytest`
(37 tests) if you installed the dev extra.

## 4. Available commands

| Command | Purpose |
|---|---|
| `sss-aug-studio [dataset]` | the GUI |
| `sss-aug-generate config.yaml [--seed N] [--workers K]` | headless, reproducible generation |
| `pytest` | test suite |

## 5. The interface in 60 seconds

Left — **Dataset Explorer**: images, class filter, per-image acquisition
metadata. Right — **Augmentation Library**: two sections, *Geometry* (G1
mirror, G2 reversal — exact symmetries) and *Physics-informed families*
(F1–F8); each card shows the phenomenon + equation; `＋ instance` adds it to
the pipeline, `Details` opens the encyclopedia. Bottom — **Parameters**:
auto-generated form for the selected instance (physical units, live
preview). Center — **Preview**: 1–6 zoom-synced tiles (original, augmented,
difference, before/after slider, histogram, profile) with label overlays,
and the drag-reorderable **Order strip** (`Physical order` restores the
causal chain). Toolbar — the **master seed**.

## 6. Your first augmentation profile

1. `Profiles ▸ Load preset ▸ Harbour inspection` (a good thesis-regime
   start), or build your own: in the Library press `＋ instance` on
   *Speckle*, *Platform motion* and *G1 — Across-track mirror*; click each
   entry in the Order strip and tune its parameters.
2. Watch the preview; use the Difference tile to see exactly what changed.
3. Want a parameter to vary between generated copies? Pick a **law** on its
   row in the Parameters form (uniform / normal / log-uniform) — the value
   on the left stays the nominal preview value.
4. `Profiles ▸ Save current as…` — the profile stores your instances, laws
   included; it is deterministic if no parameter declares a law.

## 7. Your first augmented dataset

1. `Generate ▸ Generate augmented dataset…`
2. Set output folder, seed, copies per image (start with 2), keep export
   mapping `auto`.
3. The dialog shows a read-only summary of the stochastic laws you set in
   the Parameters form (e.g. `roll_amp_deg ~ normal(mean=5, std=2)`).
4. `Generate`. Output contains untouched originals + `{name}__augN` copies,
   warped labels, `generation_manifest.json` and `statistics.md`.
5. Reproduce it anytime: `Export config YAML` →
   `sss-aug-generate config.yaml` (byte-identical, any worker count).

## 8. Where to go next

* Full workflow & metadata formats → `docs/user_manual.md`
* The science of each family → `AUGMENTATION_STRATEGIES.md` and Help ▸
  Scientific encyclopedia
* Extending the tool (one file per family) → `docs/developer_guide.md`
* What to measure on your real data before trusting parameters →
  `docs/scientific_documentation.md` §validation
