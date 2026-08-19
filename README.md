# Physics-Informed SSS Augmentation Studio

Professional desktop software for **physically plausible augmentation of
YOLO side-scan sonar datasets**, built for the master thesis *Adaptive
AI-Driven Side-Scan Sonar Survey on a Small USV* (BlueBoat + Cerulean
Omniscan 450 kHz, shallow enclosed-basin regime).

Every augmentation corresponds to a real physical phenomenon of SSS
acquisition — with the governing equations, verified references, physical
units and validation recipes shipped inside the application (Help ▸
Scientific encyclopedia).

## Feature map

| Area | What you get |
|---|---|
| Dataset Explorer | YOLO datasets (flat or split layouts), class search, per-image acquisition metadata (physical-unit or normalized fallback mode) |
| Augmentation Library | 8 physics families as *science cards* (phenomenon, equation, references); multiple named instances per family |
| Parameters | auto-generated forms — sliders/spinboxes with physical units and bounds, probability, strength, live ~150 ms preview |
| Interactive Preview | 1–6 zoom-synced tiles: original / augmented / difference / before-after slider / histogram / intensity profile; label overlays; drag-reorder pipeline strip with "physical order" |
| Generation | reproducible-by-seed batch generation (byte-identical across worker counts), originals never modified, per-parameter sampling distributions, progress/ETA/cancel, manifest + statistics, YAML export + headless CLI |
| Profiles | six curated presets (calm sea, moderate waves, harbour inspection, river, turbid, fast survey) + save/load your own |

**Geometry section:** G1 across-track mirror · G2 along-track reversal —
exact, layout-aware acquisition symmetries with consistent labels.

**The 8 physics families:** speckle & reverberation statistics · radiometric
transfer (TVG/absorption/beam) · slant-range & altitude geometry · platform
motion (USV roll/heave/yaw/speed) · ping loss & sensor artifacts · shadow &
highlight modulation · seabed reflectivity & texture · shallow-water
multipath (wall echoes — the thesis C4 hard-negative generator).

Labels are first-class: geometric families move YOLO boxes through the exact
forward transform; the shadow family moves the down-range box edge; boxes
falling below 60 % retention are dropped and logged.

## Install & run

```bash
pip install -e ".[gui]"
sss-aug-studio [path/to/dataset]        # GUI (demo: sss-aug-studio demo_dataset)
sss-aug-generate config.yaml            # headless, reproducible generation
pip install -e ".[dev]" && pytest       # 24 tests
```

Requires Python ≥ 3.10. Core (everything except the GUI) has no Qt
dependency.

## Documentation

- `PROJECT_OVERVIEW.md` — single entry point · `GETTING_STARTED.md` — 5-minute quick start
- `AUGMENTATION_STRATEGIES.md` — per-family physics, math, code excerpts, rigor classification
- `docs/user_manual.md` — workflow, metadata format, generation guide
- `docs/architecture.md` — layering, determinism, extension contract
- `docs/developer_guide.md` — add a family in one file
- `docs/scientific_documentation.md` — fidelity boundaries, validation protocol
- `docs/math_appendix.md` — complete equation set
- `docs/bibliography.md` / `sss_aug_studio/documentation/bibliography.bib`
- `docs/future_work.md`
- In-app: Help ▸ Scientific encyclopedia (per-family 7-section pages)

## Reproducibility guarantee

A generation config (YAML) + master seed reproduces a dataset
**byte-for-byte**, independent of the number of worker processes. Every
output dataset carries `generation_manifest.json` (full audit trail) and
`statistics.md`.
