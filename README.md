# SSS Dataset Augmentation Studio

A desktop tool that augments **YOLO datasets of side-scan sonar (SSS) images**.
Each new image is a physically plausible variant of the same scene (other sea state,
altitude, gain, seabed, multipath, survey direction). Labels move with the pixels.
The input dataset is never modified, and a seed reproduces the output byte for byte.

It is an **optional** offline module of the BlueBoat project: nothing else depends on it.
It has no ROS dependency.

## Requirements

- Python 3.10 or newer
- Core: numpy, scipy, opencv-python-headless, pydantic, PyYAML (installed automatically)
- GUI only: PySide6 (the `gui` extra)

## Install

From this directory:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[gui]"        # core + GUI
pip install -e ".[dev]"        # + pytest, ruff (for development)
```

## Run

| Task | Command |
|---|---|
| Open the GUI | `sss-aug-studio` |
| Open the GUI on a dataset | `sss-aug-studio path/to/dataset` |
| Try it on the bundled demo | `sss-aug-studio demo_dataset` |
| Generate without the GUI | `sss-aug-generate config.yaml` |
| Same, other seed / worker count | `sss-aug-generate config.yaml --seed 7 --workers 4` |

Typical workflow:

1. Open a dataset in the GUI.
2. Load a preset (`Profiles ▸ Load preset`) or add augmentations from the library.
3. Tune parameters with the live preview.
4. `Generate ▸ Generate augmented dataset…`: choose output folder, seed, copies per image.
5. Optional: `Export config YAML` in that dialog, then rerun it with `sss-aug-generate`.

## Augmentations

**Geometry (exact symmetries)**

| ID | Key | Effect |
|---|---|---|
| G1 | `mirror_across_track` | Mirror port and starboard (layout-aware) |
| G2 | `reverse_along_track` | Reverse the ping order |

**Physics families**

| ID | Key | Effect |
|---|---|---|
| F1 | `speckle` | Speckle and reverberation statistics (Rayleigh / K) |
| F2 | `radiometric` | TVG residual, absorption, beam pattern |
| F3 | `slant_geometry` | Slant range and altitude geometry |
| F4 | `platform_motion` | Boat roll, heave, yaw, speed |
| F5 | `ping_artifacts` | Ping loss and sensor artefacts |
| F6 | `shadow` | Shadow and highlight modulation |
| F7 | `seabed` | Seabed reflectivity and texture |
| F8 | `multipath` | Shallow-water multipath (wall echoes, hard negatives) |

Left out on purpose: arbitrary rotation, additive Gaussian noise, colour jitter,
elastic warps, mixup / cutmix. They produce images a sonar cannot record.

**Presets:** calm sea, moderate waves, harbour inspection, river, turbid basin, fast survey.
Every float parameter is either fixed or drawn from a law (uniform, normal, log-uniform).

## Input dataset

Standard YOLO layout, flat or with `train` / `val` / `test` splits:

```
dataset/
  data.yaml                 # class names (or dataset.yaml / data.yml)
  sss_aug_dataset.yaml      # optional: acquisition metadata
  images/                   # .png .jpg .jpeg .bmp .tif .tiff
    img_001.png
    img_001.json            # optional: per-image metadata
  labels/
    img_001.txt             # YOLO boxes
```

Optional `sss_aug_dataset.yaml` (each key may sit at the top level or under `meta:`):

```yaml
layout: dual               # dual | single_port | single_starboard
intensity_mapping: log     # linear | log | gamma (log if absent)
shadow_included: true      # boxes cover highlight + shadow
meta:
  altitude_m: 2.0
  slant_range_m: 20.0
  frequency_khz: 450
```

- A per-image `{stem}.json` (or `{stem}.meta.json`) overrides these values for that image.
- Without metadata the tool runs in a normalised fallback mode.
- An unknown key is ignored with a warning.

## Output dataset

Written to a **new** folder:

| File | Content |
|---|---|
| originals | copied unchanged |
| `{stem}__aug{N}.{ext}` + `.txt` | augmented images and their labels |
| `generation_manifest.json` | full config, applied augmentations and sampled values per image |
| `statistics.md` | application counts, parameter ranges, boxes kept / dropped |
| `data.yaml`, `sss_aug_dataset.yaml` | copied from the input |

Boxes that leave the image or fall below 60 % retention (`min_box_retention`) are dropped and logged.

## Generation config (for `sss-aug-generate`)

Usually exported from the GUI. Minimal hand-written example:

```yaml
dataset_path: demo_dataset
output_path: out/demo_aug
master_seed: 42
copies_per_image: 3          # 1 to 20
workers: 0                   # 0 = CPU count - 1
specs:
  - instance: {family: mirror_across_track}
  - instance: {family: speckle, probability: 0.8}
    param_distributions:
      looks: {dist: uniform, low: 1.5, high: 6.0}
```

Other fields: `allow_combination`, `min_box_retention`, `export_mapping`
(`auto` | `linear` | `gamma` | `log`), `include_splits`.

## Tests and checks

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest   # the variable is needed in a ROS-sourced shell
pytest -m "not gui"                        # skip the Qt tests
ruff check .
python tools/repro_gate.py                 # same output at 1 and N workers
```

## Layout

```
sss_aug_studio/
  core/  physics/        data model, seeded RNG, acoustics (no Qt)
  augmentations/         one file per family
  datasets/              YOLO reader, metadata resolution
  generation/            batch engine, sss-aug-generate CLI
  profiles/presets/      the six presets
  gui/  app/             PySide6 application
  documentation/         in-app encyclopedia, bibliography
tests/                   pytest suite
tools/                   repro_gate.py, docs_sync_check.py, demo builders
demo_dataset/            four-image test fixture (see its README)
docs/                    user manual, design, history
```

## More documentation

- `docs/user_manual.md`: step-by-step use, metadata format, GUI tour
- `AUGMENTATION_STRATEGIES.md`: physics, equations and limits of each family
- `docs/DESIGN.md`: architecture, adding a family, scientific limits, equations, bibliography
- `docs/HISTORY.md`: release history
- In the app: `Help ▸ Scientific encyclopedia`
