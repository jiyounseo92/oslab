# kimlab-cdk2-enrichment-v2 — curated outputs

These are the curated per-block outputs from the CDK2 enrichment benchmark
run referenced in the manuscript. Input dataset: DUD-E CDK2 (631 actives,
23,918 decoys, receptor 1KE5).

Full per-ligand files (every docked pose, every MD frame, every FEP
transformation) are too large to ship in the repo; they are attached as a
release asset (`kimlab-cdk2-enrichment-v2-completed-results.zip`, ~940 MB).
What is here is everything you need to inspect the ranked results without
downloading the full bundle.

## File map

### Block 1 — Docking (`docking/`)

| File | Description |
| --- | --- |
| `docking_report.md` | Per-block markdown report with ranked top hits, enrichment metrics, and figures |
| `vina_results.csv.gz` | Full Vina ranking for all 24,549 ligands (gzipped) |
| `small_screen_summary.json.gz` | Machine-readable summary used by the dashboard's Reports tab |

### Block 2 — Hit refinement (`hit-refinement/`)

| File | Description |
| --- | --- |
| `hit_refinement_report.md` | Per-block report with re-ranked top hits |
| `vina_results.csv` | Re-docked Vina scores for the refined subset |
| `per_ligand_seed_summary.csv` | Per-ligand statistics across multiple Vina seeds |
| `hit_refinement_summary.json` | Machine-readable summary |

### Block 3 — MD pass/fail gate (`md-optimization/`)

| File | Description |
| --- | --- |
| `md_optimization_report.md` | Per-pose pass/fail calls from the short OpenMM MD gate |

### Block 4 — Free-energy perturbation (`fep/`)

| File | Description |
| --- | --- |
| `fep_report.md` | OpenFE ΔΔG results for the surviving pair(s) |
| `fep_results.json` | Machine-readable ΔΔG, error bars, network topology |

## Reading the reports

The markdown reports in this directory are the same ones the dashboard
displays under the "Reports" tab. They are self-contained — open them in
any markdown viewer. Tables of figures referenced inside use absolute paths
from the original run on the production server; those paths point into the
full release bundle.

## Reproducing the run

```bash
# 1. Fetch the DUD-E CDK2 input data
oslab fetch-benchmark cdk2-dude --to <your_workspace>

# 2. Start the dashboard
oslab dashboard serve --host 127.0.0.1 --port 8770 --root <your_workspace>

# 3. In the browser, click Quick start: CDK2 full pipeline and confirm
#    the form references files under <your_workspace>/benchmarks/cdk2-dude/

# 4. Copy the generated AI prompt and paste it into Codex / Claude Code /
#    another coding agent. The agent will execute the four-block pipeline
#    on your GPU host and stream progress back into the dashboard.
```
