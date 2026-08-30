#!/usr/bin/env python3
"""Docs-sync gate: an augmentation family may not change without its docs.

Non-negotiable #10 (``CLAUDE.md``) is *docs move with the code*: changing a
family means updating its encyclopedia page and its ``AUGMENTATION_STRATEGIES.md``
section **in the same commit**.  Until now that was a habit, and TODO.md
recorded that every release nearly missed one.  This script is the mechanical
enforcement, and ``.githooks/pre-commit`` runs it.

Run it::

    python tools/docs_sync_check.py                 # the staged change (hook mode)
    python tools/docs_sync_check.py --commit HEAD
    python tools/docs_sync_check.py --range main..HEAD

Exit codes: ``0`` in sync (or nothing under ``augmentations/`` changed), ``1``
out of sync, ``2`` bad invocation.

Escape hatch
------------
A genuine no-doc-change edit -- a typo in a comment, a lint fix -- bypasses
with ``git commit --no-verify``, or with ``SSS_AUG_SKIP_DOCS_SYNC=1`` in a
script.  Both are deliberate acts that leave a trace; the point of the gate is
that forgetting is not one of them.

Why the mappings are derived rather than hard-coded
---------------------------------------------------
The extension contract promises that a new family is *one file* plus its docs
-- no GUI code, no generation code, and (this script's part of the bargain) no
edit here either.  So both halves of the mapping are read out of the tree:

* **encyclopedia page** <- the ``doc_page="..."`` value in the family module's
  own ``ScienceCard``.  ``geometric.py`` declares ``g_geometry.md`` twice, once
  per G-family, which collapses to one page.
* **strategies section** <- the headings of ``AUGMENTATION_STRATEGIES.md``,
  which name their module: ``## F1 - ... (`augmentations/speckle.py`) - ...``.
  ``geometric.py`` legitimately owns two (G1 and G2); a change to either
  satisfies it.

A touched module that declares no ``doc_page``, or that no heading claims, is
itself a failure.  Silently passing an unmapped family would let the next one
slip through the gate it was built for.

Blobs are read from the index or the named commit, never from the working
tree, so the check sees exactly what is about to be committed.

The section test is line-ranged, not whole-file: an unrelated typo fix
elsewhere in ``AUGMENTATION_STRATEGIES.md`` does not count as documenting F1.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

AUG_DIR = "sss_aug_studio/augmentations"
ENCYCLOPEDIA_DIR = "sss_aug_studio/documentation/encyclopedia"
STRATEGIES = "AUGMENTATION_STRATEGIES.md"
EXEMPT = {"base.py", "__init__.py"}

_DOC_PAGE_RE = re.compile(r'doc_page\s*=\s*"([^"]+)"')
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _git(*args: str) -> str:
    """Run git and return stdout, decoded as utf-8 (non-negotiable #5)."""
    proc = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc.stdout


class Source:
    """One thing to inspect: the index, a commit, or a range."""

    def __init__(self, mode: str, ref: str = "") -> None:
        self.mode, self.ref = mode, ref

    # -- what changed -------------------------------------------------------
    def changed_files(self) -> set[str]:
        if self.mode == "staged":
            out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
        elif self.mode == "commit":
            out = _git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", self.ref)
        else:
            out = _git("diff", "--name-only", "--diff-filter=ACMR", self.ref)
        return {line for line in out.splitlines() if line}

    # -- what the file will look like afterwards -----------------------------
    def blob(self, path: str) -> str | None:
        spec = f":{path}" if self.mode == "staged" else f"{self._end_ref()}:{path}"
        try:
            return _git("show", spec)
        except RuntimeError:
            return None

    def _end_ref(self) -> str:
        return self.ref.split("..")[-1] if self.mode == "range" else self.ref

    # -- which lines of one file changed -------------------------------------
    def changed_lines(self, path: str) -> set[int]:
        if self.mode == "staged":
            diff = _git("diff", "--cached", "-U0", "--", path)
        elif self.mode == "commit":
            diff = _git("diff-tree", "-p", "-U0", "--no-commit-id", "-r", "--root", self.ref, "--", path)
        else:
            diff = _git("diff", "-U0", self.ref, "--", path)
        lines: set[int] = set()
        for row in diff.splitlines():
            m = _HUNK_RE.match(row)
            if not m:
                continue
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count == 0:
                # pure deletion: attribute it to the surviving line it sits against
                lines.add(max(1, start))
            else:
                lines.update(range(start, start + count))
        return lines


def strategies_sections(blob: str) -> dict[str, list[tuple[int, int]]]:
    """module stem -> [(first_line, last_line)] of the sections claiming it."""
    rows = blob.splitlines()
    heads: list[tuple[int, str | None]] = []
    for i, row in enumerate(rows, start=1):
        if not row.startswith("## "):
            continue
        m = re.search(r"\(`" + re.escape(AUG_DIR.rsplit("/", 1)[-1]) + r"/([A-Za-z0-9_]+)\.py`\)", row)
        heads.append((i, m.group(1) if m else None))
    out: dict[str, list[tuple[int, int]]] = {}
    for idx, (line, stem) in enumerate(heads):
        end = heads[idx + 1][0] - 1 if idx + 1 < len(heads) else len(rows)
        if stem:
            out.setdefault(stem, []).append((line, end))
    return out


def check(source: Source) -> list[str]:
    """Return a list of problems; empty means in sync."""
    changed = source.changed_files()
    touched = sorted(
        Path(p).stem
        for p in changed
        if p.startswith(AUG_DIR + "/") and p.endswith(".py") and Path(p).name not in EXEMPT
    )
    if not touched:
        return []

    strat_blob = source.blob(STRATEGIES)
    if strat_blob is None:
        return [f"{STRATEGIES} is missing from the tree being checked."]
    sections = strategies_sections(strat_blob)
    strat_changed = source.changed_lines(STRATEGIES) if STRATEGIES in changed else set()

    problems: list[str] = []
    for stem in touched:
        module = f"{AUG_DIR}/{stem}.py"
        missing: list[str] = []

        blob = source.blob(module)
        pages = sorted(set(_DOC_PAGE_RE.findall(blob))) if blob else []
        if not pages:
            missing.append(
                'declares no doc_page="..." in its ScienceCard, so its '
                "encyclopedia page cannot be determined"
            )
        for page in pages:
            if f"{ENCYCLOPEDIA_DIR}/{page}" not in changed:
                missing.append(f"{ENCYCLOPEDIA_DIR}/{page} did not change")

        ranges = sections.get(stem)
        if not ranges:
            missing.append(
                f"no {STRATEGIES} heading names `{AUG_DIR.rsplit('/', 1)[-1]}/{stem}.py`"
            )
        elif not any(lo <= n <= hi for lo, hi in ranges for n in strat_changed):
            where = ", ".join(f"lines {lo}-{hi}" for lo, hi in ranges)
            missing.append(f"{STRATEGIES} section ({where}) did not change")

        if missing:
            problems.append(f"{module} changed, but:\n" + "".join(f"    - {m}\n" for m in missing).rstrip())
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--commit", metavar="REF", help="check one commit instead of the index")
    g.add_argument("--range", metavar="A..B", dest="rng", help="check a commit range")
    args = ap.parse_args(argv)

    if os.environ.get("SSS_AUG_SKIP_DOCS_SYNC"):
        print("docs-sync: skipped (SSS_AUG_SKIP_DOCS_SYNC is set).")
        return 0

    try:
        root = _git("rev-parse", "--show-toplevel").strip()
    except RuntimeError as exc:
        print(f"docs-sync: {exc}", file=sys.stderr)
        return 2
    os.chdir(root)

    if args.commit:
        source = Source("commit", args.commit)
    elif args.rng:
        source = Source("range", args.rng)
    else:
        source = Source("staged")

    try:
        problems = check(source)
    except RuntimeError as exc:
        print(f"docs-sync: {exc}", file=sys.stderr)
        return 2

    if not problems:
        return 0

    print("docs-sync: an augmentation family changed without its documentation.", file=sys.stderr)
    print("Non-negotiable #10 (CLAUDE.md): docs move with the code.\n", file=sys.stderr)
    for p in problems:
        print(f"  {p}\n", file=sys.stderr)
    print(
        "Update the encyclopedia page and the matching AUGMENTATION_STRATEGIES.md\n"
        "section in this same change. For a genuine no-doc-change edit, bypass with\n"
        "  git commit --no-verify\n"
        "or set SSS_AUG_SKIP_DOCS_SYNC=1.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
