# Changelog

All notable changes to OSLab are documented here. Versions correspond to the
release tags described in the project state notes; the `pyproject.toml` version
string is intentionally not bumped per-tag (the git tag is the source of truth).

## v1.1.8 — DUD-E parent-molecule de-duplication (unreleased; branch `v1.1.8-dedup`)

Base: v1.1.6. (v1.1.7 was held back and is skipped to avoid conflation.)

### Fixed — benchmark libraries counted protomer/tautomer states as distinct molecules
DUD-E stores one molecule as several protonation/tautomer states (one per line of
`*_final.ism`, one per record of `*_final.sdf.gz`). Earlier OSLab counted every
state as a separate ligand, inflating library sizes and per-molecule enrichment.
The correct unit is the unique **parent molecule**.

**De-duplication method (deterministic):** RDKit MolStandardize
`FragmentParent → Uncharger.uncharge → InChIKey[:14]` (skeleton block; invariant
to protonation and to DUD-E's enumerated tautomers). Best Vina score per parent.

**Key validation:** the full CDK2 active library collapses **747 states → 475
unique parents**, matching the official DUD-E CDK2 count of **474** within one.
The full-stereo InChIKey (499) over-splits vs. the official count, so the 14-char
skeleton key is the correct choice.

### CDK2 corrected counts
| Scope | actives | decoys | total |
|---|---|---|---|
| Full downloaded library — OLD (states) | 747 | 26,770 | 27,517 |
| Full downloaded library — NEW (unique parents) | **475** | **26,436** | **26,911** |
| Docked/prepared set — OLD (states) | 631 | 23,918 | 24,549 |
| Docked/prepared set — NEW (unique parents) | **415** | **23,635** | **24,050** |

(9 full-library / 8 docked decoys are unstandardizable by InChI and excluded from the unique-parent counts.)

### CDK2 corrected enrichment (docked set, unique parents; original `analyze_dude_results`, no re-docking)
OLD reproduces the published paper values exactly, confirming pipeline fidelity.

| Metric | paper / OLD | NEW (dedup) |
|---|---|---|
| Docking ROC-AUC | 0.728 / 0.727 | **0.738** |
| EF @ 1/5/10/20/50% | 11.54 / 4.97 / 3.53 / 2.51 / 1.59 | **12.02 / 5.25 / 3.83 / 2.67 / 1.62** |
| Funnel B1 / B2 / B3 active-fraction | 2.6 / 11.2 / 60.0 | **1.7 / 10.6 / 60.0** |
| Per-block ROC-AUC B1 / B3 | 0.73 / 0.84 | **0.738 / 0.844** |
| Per-block avg-precision B1 / B3 | 0.14 / 0.87 | **0.116 / 0.866** |

Top-1 FEP anchor parent is unchanged, so Block-3 MD / Block-4 FEP were not re-run.
Net effect: de-duplication leaves the story intact and slightly *improves* CDK2
discrimination (216 redundant active states removed).

### PENDING — 3 Figure-3 fields awaiting Prof. Kim's emitter
The emitter that produced these three values (`benchmark_metrics_summary.json`) is
not present on the server, in the completed-results bundle, or on the Mac; its
manifest points to Prof. Kim's Mac. OLD does **not** reproduce with located code,
so NEW is deliberately withheld (not fabricated):
- Block-2 per-block ROC-AUC (published 0.71; located code gives 0.678–0.699)
- Block-2 avg-precision (published 0.43; located code gives 0.403–0.425)
- Top-10 handoff active-fraction (published 80; recompute gives 90)

### KIF11 and HIV-RT reconciliation (completed)
KIF11 and HIV-RT are also DUD-E and show the same state inflation. Reconciled
against Prof. Kim's canonical benchmark data
(`from_Dr.Kim/KIF11_benchmark_data/kif11_dude_benchmark_metrics_recalculated_full.json`);
KIF11 panel d/e uses that recalculated-full scored set (6,966; the 142 failed
decoys repaired), HIV-RT uses the docked set (no recalculated-full exists). OLD
reproduces the paper values, confirming fidelity. Method identical to CDK2
(FragmentParent → Uncharger → InChIKey[:14], best score per parent, no re-docking).

Fetch-line counts (full downloaded library, unique parents):

| Target | OLD states (actives/decoys) | NEW unique parents (actives/decoys) |
|---|---|---|
| KIF11 | 116 / 6,850 | **113 / 6,633** |
| HIV-RT | 338 / 18,891 | **338 / 18,210** (9 decoys unstandardizable) |

(Also corrects the prior HIV-RT fetch-line baseline, which used the docked
`18,672` decoys instead of the full-library `18,891`.)

Panel d/e (docking ROC-AUC + EF@1%, unique parents):

| Target | ROC-AUC paper / OLD / NEW | EF@1% paper / OLD / NEW | actives OLD→NEW |
|---|---|---|---|
| KIF11 (recalc-full, n=6,966) | 0.818 / 0.818 / **0.815** | 15.4 / 15.44 / **15.80** | 116 → 113 |
| HIV-RT (docked, n=19,009) | 0.678 / 0.678 / **0.675** | 2.1 / 2.07 / **2.07** | 337 → 337 |

HIV-RT actives do not collapse at all (338→338 library, 337→337 docked); KIF11
actives collapse by 3 (116→113). Both leave the discrimination story unchanged.

### Changed
- `src/oslab/benchmarks.py`: added `_parent_key`, `_ism_smiles`, and
  `unique_parent_counts()`; `fetch_benchmark()` now includes
  `report["unique_parent_counts"]`. **Reporting-only** — download and docking
  behavior are unchanged; RDKit is imported lazily and the feature degrades to
  `{"available": False}` if RDKit or the `.ism` files are absent.
- CDK2 count strings updated to the corrected values, split by context:
  fetch/download strings (`README.md`, `docs/MANUAL.md`, `docs/methods.md`,
  `benchmarks.py` description) → 475 unique actives / 26,436 unique decoys;
  docked-context strings (`static/dashboard.js`, `examples/kimlab-cdk2-enrichment-v2/README.md`)
  → 415 / 23,635 / 24,050.
- KIF11 / HIV-RT fetch-line counts updated to unique parents (`benchmarks.py`
  descriptions, `README.md`, `docs/MANUAL.md`): KIF11 → 113 / 6,633; HIV-RT →
  338 / 18,210 (also corrects the HIV-RT baseline from the docked 18,672 to the
  full-library 18,891 states).
- `examples/kimlab-cdk2-enrichment-v2/docking/docking_report.md`: added a header
  note pointing to the corrected unique-parent counts; the historical report's
  internal numbers are intentionally preserved.

### Companion (not in this repo)
Server benchmark script `run_benchmark_workflow.py` receives a matching fix at
`write_dude_sample` (skip duplicate parents at ingestion; `analyze_dude_results`
then counts unique parents automatically). Held as a reviewed copy at
`~/cdk2_dedup_v2/original_code_copy/run_benchmark_workflow.v1.1.8.py`; the live
server originals are untouched.
