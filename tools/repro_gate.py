#!/usr/bin/env python3
"""Byte-reproducibility gate: same config + master seed, different worker counts.

Non-negotiable #2 (``CLAUDE.md``) makes byte-reproducibility a release gate:
the same :class:`GenerationConfig` and ``master_seed`` must produce an
identical dataset regardless of worker count.  This script is that gate.  It
runs the built-in known-good case (or a config given with ``--config``) twice
-- once sequentially, once across ``--workers`` processes -- and compares the
two output trees.

Run it::

    python tools/repro_gate.py                 # known-good case, 1 vs 4 workers
    python tools/repro_gate.py --workers 8
    python tools/repro_gate.py --config my_generation_config.yaml

Exit codes: ``0`` reproducible, ``1`` mismatch, ``2`` bad invocation.

What is compared, and why not everything
----------------------------------------
The guarantee covers **images, labels, and the manifest minus its wall-clock
stamp**.  Two runs always differ in ``generated_utc``
(``generation_manifest.json``) and in the elapsed line of ``statistics.md``, so
a naive whole-tree hash reports a false failure.  The manifest also echoes the
full config back, including the ``workers`` and ``output_path`` this gate
varies on purpose -- those are the comparison's independent variables, so they
are normalized away too and every other config field is still compared.
Accordingly:

* **hard** -- every image and ``.txt`` label byte-for-byte; the manifest parsed
  as JSON with ``generated_utc``, ``config.workers`` and ``config.output_path``
  removed.  A difference fails the gate.
* **warning** -- ``statistics.md`` with the elapsed line filtered out.  This is
  reported but does not fail the gate, because it is outside the stated
  guarantee and one line of it is legitimately order-sensitive:
  ``GenerationStats.param_samples`` accumulates in ``as_completed`` order, so
  the ``mean=`` figures are summed over a differently-ordered array between a
  sequential and a pooled run.  ``min``/``max``/``n`` are order-invariant and
  the values print at ``%.4g``, so a visible difference is not expected -- but
  if one appears it is a formatting artefact, not a reproducibility failure.
* **structural** -- both trees must hold the same set of relative paths.

The input dataset is opened read-only and is never written to (non-negotiable
#1); all output goes to ``--out``, which is cleaned before each run and kept on
failure so the two trees can be inspected.

The config is built **once** and only ``workers`` and ``output_path`` are
varied between the two runs.  This is load-bearing:
``AugmentationInstance.instance_id`` defaults to a random UUID and is one of
the keys of ``derive_rng``, so a config constructed twice would seed the two
runs differently and fail spuriously.  The known-good case below pins its
instance ids for the same reason.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Iterable

import yaml

from sss_aug_studio.core.pipeline import AugmentationInstance
from sss_aug_studio.generation.engine import (
    GenerationConfig,
    GenerationEngine,
    InstanceGenSpec,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

MANIFEST = "generation_manifest.json"
STATISTICS = "statistics.md"

# Wall-clock stamp: differs between any two runs.
VOLATILE_MANIFEST_KEYS = ("generated_utc",)
# The two knobs this gate deliberately varies. They are echoed into the
# manifest's embedded config, so they are inputs of the comparison rather than
# outputs of it; everything else under "config" is compared.
VARIED_CONFIG_KEYS = ("output_path", "workers")


# --------------------------------------------------------------- known-good
def known_good_config(dataset: Path, out: Path) -> GenerationConfig:
    """The case that has passed by hand at v0.1, v0.2 and v0.3.

    4 images x 3 copies, mirror + speckle + platform motion + shadow, with
    stochastic laws on ``looks`` and ``yaw_std_deg``, master seed 1234.
    """
    specs = [
        InstanceGenSpec(
            instance=AugmentationInstance(
                family="mirror_across_track", label="mirror", instance_id="gate-mirror"
            ),
        ),
        InstanceGenSpec(
            instance=AugmentationInstance(
                family="speckle", label="speckle", instance_id="gate-speckle", probability=0.8
            ),
            param_distributions={"looks": {"dist": "uniform", "low": 1.5, "high": 6.0}},
        ),
        InstanceGenSpec(
            instance=AugmentationInstance(
                family="platform_motion", label="motion", instance_id="gate-motion"
            ),
            param_distributions={"yaw_std_deg": {"dist": "uniform", "low": 0.5, "high": 5.0}},
        ),
        InstanceGenSpec(
            instance=AugmentationInstance(family="shadow", label="shadow", instance_id="gate-shadow"),
        ),
    ]
    return GenerationConfig(
        dataset_path=str(dataset),
        output_path=str(out),
        master_seed=1234,
        copies_per_image=3,
        specs=specs,
    )


def load_config(path: Path) -> GenerationConfig:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GenerationConfig(**doc)


# --------------------------------------------------------------- comparison
def _relative_files(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def _manifest_normalized(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for key in VOLATILE_MANIFEST_KEYS:
        doc.pop(key, None)
    for key in VARIED_CONFIG_KEYS:
        doc.get("config", {}).pop(key, None)
    return doc


def _statistics_without_elapsed(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("- elapsed:")]


def compare(a: Path, b: Path) -> tuple[list[str], list[str]]:
    """Compare two generated trees. Returns (hard failures, warnings)."""
    failures: list[str] = []
    warnings: list[str] = []

    files_a, files_b = _relative_files(a), _relative_files(b)
    for rel in sorted(files_a - files_b):
        failures.append(f"only in {a.name}: {rel}")
    for rel in sorted(files_b - files_a):
        failures.append(f"only in {b.name}: {rel}")

    for rel in sorted(files_a & files_b):
        pa, pb = a / rel, b / rel
        if rel == MANIFEST:
            if _manifest_normalized(pa) != _manifest_normalized(pb):
                dropped = ", ".join(VOLATILE_MANIFEST_KEYS + tuple(f"config.{k}" for k in VARIED_CONFIG_KEYS))
                failures.append(f"{rel}: differs after dropping {dropped}")
        elif rel == STATISTICS:
            la, lb = _statistics_without_elapsed(pa), _statistics_without_elapsed(pb)
            if la != lb:
                diff = [f"    - {x}" for x in la if x not in lb] + [f"    + {y}" for y in lb if y not in la]
                warnings.append(f"{rel}: differs after dropping the elapsed line\n" + "\n".join(diff))
        elif pa.read_bytes() != pb.read_bytes():
            failures.append(f"{rel}: bytes differ")

    return failures, warnings


# --------------------------------------------------------------------- run
def _run(cfg: GenerationConfig, out: Path, workers: int) -> None:
    run_cfg = cfg.model_copy(update={"output_path": str(out), "workers": workers})
    print(f"  generating into {out} with workers={workers} ...", flush=True)
    GenerationEngine(run_cfg).run()


def _clean(paths: Iterable[Path]) -> None:
    for p in paths:
        if p.exists():
            shutil.rmtree(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=None, help="Generation config YAML; default = the known-good case.")
    ap.add_argument("--dataset", type=Path, default=REPO_ROOT / "demo_dataset", help="Dataset for the known-good case.")
    ap.add_argument("--workers", type=int, default=4, help="Worker count of the parallel run (default 4).")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / ".repro_gate", help="Scratch output root.")
    ap.add_argument("--keep", action="store_true", help="Keep the output trees even on success.")
    args = ap.parse_args(argv)

    if args.workers < 2:
        ap.error("--workers must be >= 2; the gate compares a sequential run against a parallel one")

    seq_out = args.out / "w1"
    par_out = args.out / f"w{args.workers}"
    _clean([seq_out, par_out])

    if args.config is not None:
        if not args.config.is_file():
            print(f"config not found: {args.config}", file=sys.stderr)
            return 2
        cfg = load_config(args.config)
        print(f"config: {args.config}")
    else:
        if not args.dataset.is_dir():
            print(f"dataset not found: {args.dataset}", file=sys.stderr)
            return 2
        cfg = known_good_config(args.dataset, seq_out)
        print("config: built-in known-good case")

    print(f"dataset: {cfg.dataset_path}  seed: {cfg.master_seed}  copies: {cfg.copies_per_image}")
    _run(cfg, seq_out, 1)
    _run(cfg, par_out, args.workers)

    failures, warnings = compare(seq_out, par_out)

    for w in warnings:
        print(f"WARNING  {w}")

    if failures:
        print(f"\nFAIL: {len(failures)} difference(s) between 1 and {args.workers} workers:")
        for f in failures:
            print(f"  {f}")
        print(f"\nOutput trees kept for inspection:\n  {seq_out}\n  {par_out}")
        return 1

    print(f"\nOK: 1 and {args.workers} workers produced identical images, labels and manifest.")
    if not args.keep:
        _clean([seq_out, par_out])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
