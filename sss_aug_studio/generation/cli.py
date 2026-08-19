"""Headless generation CLI.

Usage::

    sss-aug-generate config.yaml [--seed 42] [--workers 4]

The YAML file is a serialized :class:`GenerationConfig` (the GUI's
Generation dialog can export one), enabling scripted, CI-reproducible
dataset builds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .engine import GenerationConfig, GenerationEngine


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Physics-informed SSS dataset generation (headless).")
    ap.add_argument("config", help="Generation config YAML (see docs/user_manual.md).")
    ap.add_argument("--seed", type=int, default=None, help="Override master seed.")
    ap.add_argument("--workers", type=int, default=None, help="Override worker count.")
    args = ap.parse_args(argv)

    doc = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.seed is not None:
        doc["master_seed"] = args.seed
    if args.workers is not None:
        doc["workers"] = args.workers
    cfg = GenerationConfig(**doc)

    def progress(done: int, total: int, elapsed: float) -> None:
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else float("inf")
        sys.stdout.write(f"\r[{done}/{total}] {100*done/max(total,1):5.1f}%  ETA {eta:6.1f}s ")
        sys.stdout.flush()

    stats = GenerationEngine(cfg).run(progress=progress)
    print(
        f"\nDone: {stats.augmented} augmented copies from {stats.images_in} images "
        f"({stats.boxes_dropped} boxes dropped) in {stats.elapsed_s:.1f}s -> {cfg.output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
