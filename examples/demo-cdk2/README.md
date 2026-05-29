# demo-cdk2 — minimal self-contained demo

A tiny, self-contained Block 1 (docking) demo so you can confirm an OSLab
install works end-to-end in a few minutes, without any download or receptor
preparation.

## Contents

| File | What it is |
| --- | --- |
| `receptor.pdbqt` | Prepared DUD-E CDK2 receptor (PDB 1HCK), Vina-ready |
| `site.json` | Docking box: 14 Å cube centered on the 1HCK crystal-ligand centroid |
| `demo_ligands.smi` | 5 known CDK2 actives (DUD-E) as SMILES |

## Run it

From the repository root, with the `oslab` environment active:

```bash
oslab screen small \
  --ligands      examples/demo-cdk2/demo_ligands.smi \
  --receptor     examples/demo-cdk2/receptor.pdbqt \
  --binding-site examples/demo-cdk2/site.json \
  --max-ligands 5 --exhaustiveness 8 --no-plip \
  --out ./demo-out
```

## Expected output

A `./demo-out/` directory containing:

- `report/vina_results.csv` — ranked docking scores (one row per ligand)
- `report/docking_report.md` — human-readable report
- `report/docking_results_summary.json` — machine-readable summary
- `docking/<ligand>/<ligand>_docked.pdbqt` — docked poses
- `ligand-vina-prep/` — prepared ligand intermediates

All 5 ligands dock. A correct run produces a ranked `vina_results.csv` with
the top binders around **−9 kcal/mol** and the weakest around **−7**. Exact
AutoDock Vina scores vary slightly with platform and package build, so the
table below is a reference run, not values to match exactly — the check is
that all five dock and the strongest binders sort to the top (kcal/mol):

| Ligand | Vina score (reference) |
| --- | --- |
| active_00001 | ≈ −9.2 to −9.4 |
| active_00007 | ≈ −8.8 to −9.4 |
| active_00006 | ≈ −8.6 |
| active_00008 | ≈ −7.1 |
| active_00009 | ≈ −7.1 |

## Expected run time

~5 minutes on a single CPU core (Intel Xeon Platinum 8358, 2.6 GHz),
exhaustiveness 8, one ligand at a time. Pass `--docking-workers N` to dock
in parallel and cut this proportionally.
