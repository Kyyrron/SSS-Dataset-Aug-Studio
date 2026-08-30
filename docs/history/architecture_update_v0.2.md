# Architecture update — v0.2.0

> **Historical.** Superseded by `docs/architecture.md`, which describes the
> current release. Kept as a record of what changed at this release; not
> maintained.

Delta document only; `architecture.md` describes the base system. No layer is
redesigned — this release adds two conventions, one augmentation *section*,
one profile capability, and one bug-class fix.

## 1. Dataset conventions (now fixed)

### 1.1 `shadow_included`
New boolean on `AcquisitionMeta` (default **true**), settable per dataset
(`sss_aug_dataset.yaml`) or per image (sidecar JSON). Semantics: a YOLO box
covers the object's complete acoustic signature — highlight **and** shadow.
Consumers:

* **F6** moves the down-range box edge when scaling shadow length **only if**
  `shadow_included` is true; with `false` it modifies pixels but never labels.
* Explorer metadata table displays the flag; generation manifests record it.

### 1.2 Declared intensity mapping, dB-first
The mapping is *declared* by the acquisition pipeline, never inferred. The
internal processing domain stays **linear [0,1]** (unchanged — it is the
domain where multiplicative physics is native); loaders exactly invert the
declared export mapping, and dB-parameterized effects (F2/F5/F7/F8 gains)
convert via `10^(dB/10)` — i.e. each computation happens in its physically
appropriate domain by construction. What changes:

* **Default assumption when metadata is absent flips from `linear` to
  `log`** (`log_range_db` = 40 dB), matching how SSS software normally
  exports waterfalls. The old linear-approximation caveat is replaced by a
  documented dB-default.
* Batch export gains mapping `auto` (default): re-apply the input mapping so
  original↔augmented files live in the same domain.

## 2. New section: Geometry (G-families)

`Augmentation.section: ClassVar["physics"|"geometry"] = "physics"` — the
Library groups cards under two headers; registry, pipeline, profiles,
preview and generation are untouched (G-families are ordinary registered
families with `order_hint` 1–2, i.e. first in the physical order: they
represent the *acquisition direction choice*, logically prior to everything).

* **G1 `mirror_across_track`** — exact column-reversal `FieldWarp`
  (involution). Layout handling: `single_port ↔ single_starboard` via the new
  `AugResult.meta_override`; `dual` swaps sides, nadir metadata mirrored
  (`nadir_center_frac → 1 − c`; centered waterfalls keep the nadir in place).
  Because each side's canonical range axis maps onto the other side's range
  axis, shadows remain strictly down-range — physically consistent.
* **G2 `reverse_along_track`** — exact row-reversal `FieldWarp` (survey line
  replayed in the opposite direction); heading metadata rotated by 180° when
  present. All other physical properties preserved.

Pipeline extension: `AugResult.meta_override` (optional `AcquisitionMeta`);
when present the pipeline rebuilds the `SonarImage` with the new metadata
(also resetting the cached nadir band). One field + three lines — no
behavioral change for existing families.

## 3. Profile execution modes

`PipelineProfile` gains:

```yaml
mode: deterministic | stochastic     # default: deterministic
distributions:                       # only meaningful in stochastic mode
  <instance_id>: {<param>: {dist: uniform, low: …, high: …}, …}
```

* **deterministic** — fixed parameter values (reproducible experiments);
  distributions are ignored by the engine.
* **stochastic** — the generation dialog pre-fills its distribution table
  from the profile; per-copy sampling uses the existing RNG tree, so seeds
  remain fully reproducible (unchanged engine guarantee).

Save flow: *Profiles ▸ Save current as…* now asks name/description/**mode**;
stochastic saves capture the session's current distribution table (edited in
the generation dialog, persisted back to the session on build/export/run).
Bundled presets are explicitly `mode: deterministic`.

## 4. Cross-platform text IO (bug fix)

Root cause of the reported `UnicodeDecodeError`: `read_text()` /
`write_text()` without `encoding=` use the OS-default codec (cp1252 on
Windows) while all shipped files are UTF-8. Fix: **every** text read/write in
the package now passes `encoding="utf-8"` (encyclopedia loader, profiles,
presets, dataset config/sidecars, labels, generation outputs, CLI, QSS
loader). Enforced by a regression test that loads every encyclopedia page.

## 5. Documentation delta

New root-level: `PROJECT_OVERVIEW.md`, `GETTING_STARTED.md`,
`AUGMENTATION_STRATEGIES.md` (per-family: physical origin, math, DOI-verified
references, core code excerpt, expected effect, limitations, rigor class).
Updated: user manual (§conventions, §geometry, §profile modes), scientific
documentation (intensity policy), encyclopedia `00_overview` (flips are now
implemented as G1/G2, dB default), `f6_shadow` (`shadow_included`), new
`g_geometry.md`. Version bumped to 0.2.0.
