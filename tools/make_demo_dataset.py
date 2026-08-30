#!/usr/bin/env python3
"""Rebuild ``demo_dataset/`` from the BlueBoat-SSS-Sim acoustic simulator.

The fixture ships inside this repository, so every image in it must be
redistributable and every label must be ground truth.  Both hold here by
construction: the imagery is rendered by ``blueboat_sss_sim`` from a seeded
mission bundle, and the boxes come from the renderer's own per-ping contact
record rather than from a human tracing outlines.

Run from the repository root::

    python tools/make_demo_dataset.py

Output is byte-identical on every run.  The mission bundle is generated into
a temporary directory and discarded; no bundle is ever edited in place
(superproject CM-7), and nothing under ``BlueBoat-SSS-Sim/`` is written
(superproject CM-3).

Not packaged -- a maintenance script, like ``tools/repro_gate.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SIM_ROOT = (REPO_ROOT.parent / "BlueBoat-SSS-Sim" / "blueboat_sss_sim").resolve()
DEMO = REPO_ROOT / "demo_dataset"

# ---------------------------------------------------------------- generation
MISSION_SEED = 7          # mission bundle (world + object field + trajectory)
NOISE_SEED = 20260830     # speckle / gain-drift draws
TILE_PINGS = 320          # rows per tile; dual images are 2 x num_results wide

# Tiles chosen from a full-mission survey: box-rich, and each spans a single
# straight lawnmower leg (zero heading spread), so one heading describes it.
#   name              tile  sides kept
SELECTION = [
    ("dual_basin_01",  5, "dual"),
    ("dual_basin_02", 22, "dual"),
    ("port_leg_01",   23, "port"),
    ("stbd_leg_01",   18, "starboard"),
]
LAST_TILE = max(idx for _, idx, _ in SELECTION)


def _sim_imports():
    """Import the simulator's ROS-free offline path.

    ``blueboat_sss_sim.dataset.exporter`` is deliberately not imported: it
    pulls in PIL, which is not a dependency of this repository, and its
    ``train|val`` split layout is not the flat layout this fixture uses.
    """
    if not SIM_ROOT.is_dir():
        sys.exit(f"BlueBoat-SSS-Sim not found at {SIM_ROOT}")
    sys.path.insert(0, str(SIM_ROOT))
    from blueboat_sss_sim.core.types import Pose3D, Side
    from blueboat_sss_sim.dataset.labeler import LabelConfig, TileLabeler
    from blueboat_sss_sim.dataset.waterfall import WaterfallBuilder, WaterfallTileConfig
    from blueboat_sss_sim.mission.generate import generate_mission
    from blueboat_sss_sim.mission.patterns import WaypointTrajectory
    from blueboat_sss_sim.sonar.config import SonarConfig
    from blueboat_sss_sim.sonar.encoder import PingEncoder
    from blueboat_sss_sim.sonar.noise import GainDrift, apply_ping_noise
    from blueboat_sss_sim.sonar.renderer import GeometricRenderer
    from blueboat_sss_sim.core.geometry import enu_yaw_to_compass_deg
    from blueboat_sss_sim.worldgen.scene import SceneModel
    return {
        "Pose3D": Pose3D, "Side": Side, "LabelConfig": LabelConfig,
        "TileLabeler": TileLabeler, "WaterfallBuilder": WaterfallBuilder,
        "WaterfallTileConfig": WaterfallTileConfig, "generate_mission": generate_mission,
        "WaypointTrajectory": WaypointTrajectory, "SonarConfig": SonarConfig,
        "GainDrift": GainDrift, "apply_ping_noise": apply_ping_noise,
        "GeometricRenderer": GeometricRenderer, "SceneModel": SceneModel,
        "PingEncoder": PingEncoder, "enu_yaw_to_compass_deg": enu_yaw_to_compass_deg,
    }


def render_tiles(S, bundle: Path):
    """Render the mission and cut per-side waterfall tiles with their rows."""
    scene = S["SceneModel"].load(bundle)
    cfg = S["SonarConfig"].from_yaml(bundle / "sonar.yaml")
    acq, model = cfg.acquisition, cfg.model
    traj = S["WaypointTrajectory"].load_yaml(bundle / "trajectory.yaml")
    renderer = S["GeometricRenderer"](scene, acq, model)
    rng = np.random.default_rng(NOISE_SEED)
    period = acq.ping_period_s(model.max_ping_rate_hz)

    Side = S["Side"]
    builders = {s: S["WaterfallBuilder"](
        acq.num_results,
        S["WaterfallTileConfig"](tile_pings=TILE_PINGS, overlap_pings=0)) for s in Side}
    drifts = {s: S["GainDrift"](model, rng) for s in Side}
    # The waterfall is built from encoded u16 counts, not physical power:
    # PingEncoder applies the device's calibrated gain-index scaling and
    # quantisation, which is what the real Omniscan puts on the wire.
    encoders = {s: S["PingEncoder"](s, acq, model) for s in Side}

    n_pings = min(int(traj.duration / period), (LAST_TILE + 1) * TILE_PINGS)
    bin_edges = acq.range_start_mm / 1000.0 + (np.arange(acq.num_results) + 0.5) * acq.bin_size_m
    yaws, alts = [], []
    for k in range(n_pings):
        t = k * period
        x, y, yaw = traj.pose_at(t)
        yaws.append(yaw)
        pose = S["Pose3D"](x, y, 0.0, roll=0.0, pitch=0.0, yaw=yaw)
        for side in Side:
            r = renderer.render(side, pose, t)
            alts.append(r.ping.altitude_m)
            r.ping.power = S["apply_ping_noise"](
                r.ping.power, bin_edges < r.ping.altitude_m, drifts[side].value(t),
                model, rng, specular=r.ping.specular)
            builders[side].add_ping(encoders[side].encode(r.ping).pwr_results,
                                    r.contacts)

    tiles = {s: builders[s].ready_tiles(flush=True) for s in Side}
    return tiles, acq, model, np.array(yaws), float(np.mean(alts))


def label_all(S, tiles, acq, class_names=None):
    """Label every selected tile.  One labeler across both sides, so a class
    id means the same thing in a port tile and a starboard tile."""
    cfg = S["LabelConfig"](class_names=list(class_names) if class_names else None)
    lab = S["TileLabeler"](acq.num_results, acq.bin_size_m, cfg)
    Side = S["Side"]
    out = {}
    for _, idx, keep in SELECTION:
        for side in (Side.PORT, Side.STARBOARD):
            if keep == "dual" or keep == side.value:
                out[(idx, side.value)] = lab.label_tile(tiles[side][idx][1])
    return out, lab.class_names


def _boxes_to_lines(boxes, xform):
    """YOLO lines for ``boxes`` after applying ``xform`` to (x_center, width)."""
    lines = []
    for b in boxes:
        xc, w = xform(b.x_center, b.width)
        lines.append(f"{b.class_id} {xc:.6f} {b.y_center:.6f} {w:.6f} {b.height:.6f}")
    return lines


# Port tiles are emitted range-increasing-rightward, like starboard.  Flipping
# them puts range increasing leftward from the nadir, which is how port is
# presented in a waterfall -- and is what SonarImage treats as single_port.
def FLIP(xc, w):
    """Mirror a single-side tile: near range moves to the other edge."""
    return 1.0 - xc, w


def KEEP(xc, w):
    return xc, w


def DUAL_PORT(xc, w):
    """Port box into the left half of a composed dual image (mirrored)."""
    return (1.0 - xc) / 2.0, w / 2.0


def DUAL_STBD(xc, w):
    """Starboard box into the right half of a composed dual image."""
    return xc / 2.0 + 0.5, w / 2.0


def main() -> int:
    S = _sim_imports()
    Side = S["Side"]

    with tempfile.TemporaryDirectory(prefix="sss_demo_bundle_") as tmp:
        cwd = os.getcwd()
        os.chdir(SIM_ROOT)          # mission config paths are relative to it
        try:
            bundle = S["generate_mission"](
                SIM_ROOT / "config" / "default_mission.yaml",
                Path(tmp) / "mission", seed=MISSION_SEED)
            tiles, acq, model, yaws, altitude = render_tiles(S, bundle)
        finally:
            os.chdir(cwd)

    # Two passes so the class map is the alphabetical set actually present in
    # the shipped tiles, rather than an artifact of tile visit order.
    discovered, _ = label_all(S, tiles, acq)
    present = sorted({b.object_type for bs in discovered.values() for b in bs})
    boxes, class_names = label_all(S, tiles, acq, class_names=present)
    assert class_names == present, (class_names, present)

    # Remove only what this script generates. README.md is hand-written
    # provenance and must survive a rebuild.
    for sub in ("images", "labels"):
        if (DEMO / sub).exists():
            shutil.rmtree(DEMO / sub)
        (DEMO / sub).mkdir(parents=True)
    for gen in ("data.yaml", "sss_aug_dataset.yaml"):
        (DEMO / gen).unlink(missing_ok=True)

    stretches, written = [], []
    for name, idx, keep in SELECTION:
        rows = slice(idx * TILE_PINGS, (idx + 1) * TILE_PINGS)
        heading = round(float(S["enu_yaw_to_compass_deg"](
            float(np.mean(yaws[rows])))), 1)

        port_img = tiles[Side.PORT][idx][0]
        stbd_img = tiles[Side.STARBOARD][idx][0]
        if keep == "dual":
            img = np.hstack([np.fliplr(port_img), stbd_img])
            lines = (_boxes_to_lines(boxes[(idx, "port")], DUAL_PORT)
                     + _boxes_to_lines(boxes[(idx, "starboard")], DUAL_STBD))
            layout = "dual"
        elif keep == "port":
            img = np.fliplr(port_img)
            lines = _boxes_to_lines(boxes[(idx, "port")], FLIP)
            layout = "single_port"
        else:
            img = stbd_img
            lines = _boxes_to_lines(boxes[(idx, "starboard")], KEEP)
            layout = "single_starboard"

        assert lines, f"{name} would ship an empty label file"
        cv2.imwrite(str(DEMO / "images" / f"{name}.png"), img)
        (DEMO / "labels" / f"{name}.txt").write_text("\n".join(lines) + "\n",
                                                     encoding="utf-8")
        (DEMO / "images" / f"{name}.json").write_text(
            json.dumps({"layout": layout, "heading_deg": heading,
                        "altitude_m": round(altitude, 2)}, indent=2) + "\n",
            encoding="utf-8")

        # Fit the display mapping from the *raw* power rows, reproducing what
        # WaterfallBuilder._render did to produce these pixels.
        sides_used = ((Side.PORT, Side.STARBOARD) if keep == "dual"
                      else (Side.PORT,) if keep == "port" else (Side.STARBOARD,))
        for s in sides_used:
            power = np.stack([r.power for r in tiles[s][idx][1]]).astype(np.float64)
            lo, hi = np.percentile(np.log1p(power), [1.0, 99.5])
            stretches.append((float(lo), float(hi)))
        written.append((name, layout, len(lines), heading, img.shape))

    # The tiles are log1p-compressed then percentile-stretched, so the Studio's
    # log inverse is exact only for the dynamic range the stretch spanned.
    # Fit that range: v = (ln(1+P) - lo)/(hi - lo) matches the Studio's
    # v = log10(1 + x*(10^(d/10) - 1))/(d/10) when d/10*ln(10) = hi - lo.
    spans = np.array([hi - lo for lo, hi in stretches])
    log_range_db = round(float(np.median(spans)) * 10.0 / float(np.log(10.0)), 1)
    log_range_db = min(max(log_range_db, 1.1), 120.0)
    black_point = float(np.median([lo for lo, _ in stretches]))

    write_configs(class_names, acq, model, altitude, log_range_db)

    print(f"demo_dataset rebuilt in {DEMO}")
    for name, layout, nb, heading, shape in written:
        print(f"  {name:<16} {layout:<17} {nb} boxes  heading {heading:>5.1f} deg  {shape}")
    print(f"  classes: {class_names}")
    print(f"  log_range_db: {log_range_db}  (median black point ln(1+P)={black_point:.2f}, \n           the offset the Studio's log inverse cannot represent)")
    return 0


def write_configs(class_names, acq, model, altitude, log_range_db) -> None:
    (DEMO / "data.yaml").write_text(
        yaml.safe_dump({"names": dict(enumerate(class_names))}, sort_keys=False),
        encoding="utf-8")

    # Nadir half-width as a fraction of a *dual* image: the water column is
    # altitude/bin_size bins on each side of the join, out of 2*num_results.
    nadir_half = round(float(altitude) / float(acq.bin_size_m)
                       / (2.0 * int(acq.num_results)), 4)
    header = (
        "# Acquisition context for this dataset. Every AcquisitionMeta field is honoured\n"
        "# here at the top level and inside `meta:` — the two positions are equivalent,\n"
        "# the top level wins on conflict, and an unrecognised key warns.\n"
        "#\n"
        "# Synthetic fixture; see README.md for provenance. Per-image `layout` and\n"
        "# `heading_deg` come from the sidecar JSON beside each image.\n"
    )
    doc = {
        "layout": "dual",
        # Tiles are log1p-compressed and percentile-stretched by the simulator's
        # waterfall builder, exactly as a dB waterfall export would be.
        "intensity_mapping": "log",
        "log_range_db": float(log_range_db),
        "shadow_included": True,   # labels are box_mode="highlight_shadow"
        "nadir_center_frac": 0.5,
        "nadir_halfwidth_frac": float(nadir_half),
        "meta": {
            "altitude_m": round(altitude, 2),
            "slant_range_m": float(acq.range_length_mm) / 1000.0,
            "res_along_m": round(1.0 / float(model.max_ping_rate_hz), 4),  # 1 m/s survey speed
            "speed_mps": 1.0,
            "prf_hz": float(model.max_ping_rate_hz),
            "depth_m": 4.0,
            "frequency_khz": 450.0,
        },
    }
    with open(DEMO / "sss_aug_dataset.yaml", "w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    raise SystemExit(main())
