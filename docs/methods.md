# OSLab Dashboard — Implementation and Usage

This document describes the final form of the OSLab dashboard (the web UI shown
in the manuscript) and a complete usage guide. It is intended as source material
for the methods section and supplementary protocol.

---

## Part 1 — Implementation

### 1.1 Design goals

The dashboard wraps the OSLab structure-based virtual-screening pipeline so
that a bench scientist who does not write Python can run a four-block
campaign (docking → hit refinement → MD pass/fail → relative free-energy
perturbation) by filling in a web form and pasting the generated script into
an AI coding agent. The agent — not the user — opens an SSH session, executes
the pipeline on a GPU host, and streams per-block progress back into the
dashboard.

Three constraints shaped the final design:

1. **No mandatory command-line interaction.** The user's only required actions
   are filling a form, copying a script, and pasting it into an AI agent.
2. **Reproducibility through stored input.** Every run records the form
   inputs that produced it, so each report can be retraced to a config.
3. **Multi-user without shared writes.** Each scientist runs a personal
   dashboard pointing at their own workspace; the pipeline writes only inside
   that workspace.

### 1.2 System architecture

The dashboard is a single Python package, `oslab`, served by a Python standard-
library `ThreadingHTTPServer`. There is no external web framework, message
queue, or database; persistence is plain JSON files under the user's
workspace.

```
oslab/
├── dashboard.py          # HTTP server, routes, state aggregation
├── templates/
│   └── dashboard.html    # Single-page UI
├── static/
│   ├── dashboard.css     # Styling
│   ├── dashboard.js      # Form auto-generation, polling
│   └── dashboard_v2.js   # Tabbed nav, monitor, workflow-grouped reports
├── binding_sites.py      # fpocket wrapper + box construction
├── docking.py            # Receptor prep (Meeko-style PDBQT)
├── ligand_prep.py        # Vina-format ligand prep
├── hit_refinement.py     # Re-docking of top hits
├── md_prep.py            # OpenMM MD setup
├── fep_run.py            # FEP simulation legs (OpenMM)
├── openfe_runner.py      # OpenFE alchemical network planning + execution
├── openfe_backend.py     # OpenFE CLI integration
├── interactions.py       # PLIP protein–ligand contact analysis
├── domain_annotations.py # UniProt / PDBe SIFTS domain annotation
├── jobs.py               # Job IDs, file locks, progress JSON paths
├── hpc.py                # SLURM job-script generation
└── terminal_orchestration.py  # End-to-end orchestrator the agent calls
```

External libraries: `rdkit` (cheminformatics), `openmm` (MD), `openfe`
(alchemical free-energy planning and execution), `vina` (docking, called as
the AutoDock Vina CLI), `fpocket` (pocket detection, CLI), `plip` (protein–
ligand interaction profiler). All runtime dependencies are pinned in a
micromamba environment shipped alongside the source.

#### HTTP layer

`dashboard.py` defines a `Handler` subclass of `BaseHTTPRequestHandler` and
exposes endpoints under three groups:

- `/` returns the rendered `dashboard.html` with cache-busting query strings
  derived from each static file's mtime.
- `/static/<path>` serves CSS/JS/images with a symlink-aware path-traversal
  guard.
- `/api/<name>` returns JSON. Key endpoints: `/api/state` (current workspace
  snapshot), `/api/jobs` (active and recent jobs with per-block progress),
  `/api/runs/<label>` (single-run detail), `/api/report/<...>` (markdown
  report content), `/api/site-search`, `/api/ligand-results`, etc.

All JSON responses pass through `_json_safe` to coerce numpy scalars, and
(when demo mode is enabled) `_redact_for_demo` to scrub the operator's
workspace path before it reaches the browser.

#### Form schema and script generation

Form fields are declared in a single `BLOCKS` configuration in `dashboard.py`,
grouped by pipeline block (docking, hit refinement, MD optimization, FEP).
For each field the configuration carries the input element type
(`text`/`select`/`number`/`file`), default placeholder, an include-or-not
checkbox at the block level, and the canonical CLI flag the field maps to.

`dashboard.js` reads the same `BLOCKS` definition from `/api/state` and
auto-renders the four blocks. As the user types or selects, the right-hand
panel rebuilds the run script live: a single shell command that invokes
`oslab orchestrate --campaign <label> --block 1 --block 2 …` with all
selected options, plus a preamble of natural-language instructions for the
AI agent (where to write outputs, how to report progress, retry policy for
transient errors).

#### Job tracking

Each block writes a JSON progress file to
`<workspace>/jobs/<job_id>/progress.json` while it runs. The dashboard polls
`/api/jobs`, which scans the `jobs/` directory and merges in any in-flight
markers. Each entry exposes:

- block name, status (`queued` / `running` / `done` / `failed`)
- current step within the block (e.g. "ligand prep 12/64")
- start time, last heartbeat
- output paths produced so far (reports, viewer JSON, results CSV)

The frontend renders one card per *campaign* (a logical group of blocks that
share a run label), with one progress row per block. When a block finishes,
its "View report" button becomes active and links to the corresponding
markdown report page.

### 1.3 Pipeline blocks

Block boundaries are fixed; users include or exclude blocks but do not edit
the block sequence.

| Block | Purpose | Engine | Output |
|---|---|---|---|
| 1. Docking | Pose generation against the chosen binding site | AutoDock Vina (CLI) | Ranked ligand list + docked SDF |
| 2. Hit refinement | Re-dock top-N hits with higher exhaustiveness and multiple seeds | AutoDock Vina | Re-scored top hits, consensus poses |
| 3. MD optimization | Short OpenMM MD as a pass/fail gate on the top refined poses | OpenMM | Pass/fail call per pose + final-frame complex |
| 4. FEP | Relative free-energy perturbation between selected top pairs | OpenFE + OpenMM | ΔΔG per edge, alchemical network |

Block 2 (hit refinement) — not MMGBSA re-ranking — is the ranking step. Block
3 is a binary gate (does the bound pose remain stable under MD?), not a
re-scoring step. Block 4 quantifies relative affinity for the small set of
poses that survived block 3.

#### Binding site selection

Block 1 inputs include three site-selection modes:

1. **fpocket auto-detection.** The dashboard runs `fpocket` on the receptor
   and presents a sortable list of pockets ranked by druggability score. For
   each pocket the dropdown displays (a) the residue range covered by the
   lining residues parsed from `pockets/pocket{N}_atm.pdb`, and (b) a domain
   annotation derived from the PDBe SIFTS `mappings/uniprot/{pdb_id}` and
   UniProt KB `uniprotkb/{accession}` REST APIs (e.g. "Transmembrane |
   Protein kinase domain"). This addresses the case where multiple pockets
   are returned but the scientist only cares about the extracellular,
   transmembrane, or cytoplasmic region.
2. **Centroid of a known ligand.** Compute the centroid of a co-crystallised
   ligand or of an SDF the user supplies.
3. **Residue centroid.** Compute the centroid of a user-supplied residue
   list.

In all three cases the binding box is widened by a user-controllable padding
and serialised to a JSON site descriptor that downstream blocks consume.

### 1.4 User interface

The page is a single HTML template with three top-level views switched by
adding/removing a body class (`view-home`, `view-monitor`, `view-reports`).
No client-side router is used; deep links use `?view=…&run=…` query strings
that the dashboard reads on load.

- **Home.** Onboarding card with a four-step explainer, a "Quick start:
  CDK2" button (which fills the form with the Wang-FEP CDK2 dataset values),
  a collapsible "Build your run" section containing the four block forms,
  and a fixed right-hand panel that holds the live-updating script with a
  single "Copy as AI prompt" button.
- **Progress Monitor.** Always-visible "Your runs & results" panel listing
  every campaign with per-block progress bars, plus a collapsible "Detailed
  monitor" drawer for raw log tails and queue contents.
- **Reports.** One card per pipeline campaign, with four block rows inside.
  Each row exposes a "View report" button that opens a focused report page
  containing the report markdown, a results table (ligand-by-ligand scores,
  MD gate calls, FEP ΔΔG), and embedded 3D viewers (mol* iframe) for the
  best pose and the MD final frame. A collapsible "Compare runs" drawer at
  the bottom of the Reports tab provides a cross-campaign table.

The UI is intentionally form-driven rather than wizard-driven: every block
is visible and editable from a single page, so the scientist can scan the
whole pipeline at a glance.

### 1.5 Deployment model

The dashboard is hosted on a shared GPU server. Each lab member runs their
own dashboard instance on a personal port and with a personal workspace:

```
~/start-oslab-v2.sh        # per-user launcher (copied from a template)
   ↓
PYTHONPATH=/data/oslab/users/<owner>/oslab_v2_shared/src \
  /opt/oslab/current/.micromamba/envs/open-structure-lab/bin/python \
  -m oslab.cli dashboard serve --host 127.0.0.1 --port <user_port> \
  --root /data/oslab/users/<user>/OSLab
```

`PYTHONPATH` overrides the system-installed `oslab` package with the shared
source copy, so updates to the UI propagate to every user on their next
launcher restart. The original install at `/opt/oslab/current/` is never
modified; the runtime micromamba environment (rdkit, openmm, openfe, vina,
etc.) is reused. Users tunnel from their laptop with
`ssh -fNL <port>:localhost:<port> <server>` and open the dashboard in a
browser.

### 1.6 Demo configuration

The same source tree supports a public, read-only demo when the
`OSLAB_DEMO_MODE=1` environment variable is set:

- The dashboard prepends a banner that explains the demo scope.
- Outgoing JSON and rendered HTML pass through `_redact_for_demo`, which
  rewrites the operator's username and workspace root to a generic
  "oslab-demo" placeholder.
- Incoming API parameters pass through the inverse `_unredact_for_demo`
  before reaching the filesystem, so paths the browser echoes back still
  resolve to the real workspace.
- HTTP Basic Auth is required (credentials from `OSLAB_BASIC_AUTH=user:pass`).
- A Cloudflare quick tunnel publishes the dashboard at an https URL.

The demo workspace contains symlinked outputs from a completed CDK2
enrichment campaign, so external reviewers can browse reports without
launching any compute.

---

## Part 2 — Usage Guide

### 2.1 Three ways to access the dashboard

| Mode | For whom | What works | What does not |
|---|---|---|---|
| Public demo (Cloudflare URL + basic auth) | External readers, reviewers | Browse a finished CDK2 campaign, inspect reports, copy the script as illustration | Cannot launch new runs |
| Personal Lambda instance (PYTHONPATH launcher) | Lab members | Launch the full four-block pipeline against their own workspace | Requires a Lambda account |
| Local install (clone of the shared source) | Anyone | Run the pipeline on a local GPU workstation | Requires installing the micromamba environment |

### 2.2 Quick start — CDK2 demonstration pipeline

The fastest way to exercise the whole dashboard, including all four blocks,
is the bundled CDK2 example. It points at a small set of known active
ligands so the full four-block pipeline finishes in roughly one hour. The
manuscript-scale benchmark uses the larger DUD-E CDK2 library (§ 2.7).

1. Open the dashboard (any of the three modes above).
2. On the Home view, click **Quick start: CDK2 full pipeline (~1 hour)**.
3. The four block forms are filled with demo values:
   - Block 1 (docking): CDK2 receptor PDB, a ligand library of 16 known
     active ligands, binding site by the centroid of the co-crystallised
     ligand, exhaustiveness 8.
   - Block 2 (hit refinement): top 5 of 16, exhaustiveness 16, three seeds.
   - Block 3 (MD optimization): top 3 of 5, 2.5 ns production on each pose.
   - Block 4 (FEP): top 1 pair, 11-window relative free-energy network.
4. Inspect the right-hand panel — the script (an AI-agent prompt) updates
   live as Quick Start fills the form.
5. Click **Copy as AI prompt** (single button on the right panel).
6. Paste the copied prompt into Codex (or another AI coding agent that can
   run shell commands over SSH).
7. The agent reads the embedded instructions, connects to the server, writes
   under your workspace, runs the pipeline block-by-block, and streams
   progress to the dashboard.
8. Switch to the **Progress Monitor** tab to watch each block. Each block
   appears as its own row inside a campaign card; click "View report" once
   the row turns green.

### 2.3 Building a custom run

For real targets, build the four blocks manually. Each block has an
include-or-not checkbox at its header; unticking a block removes it from the
generated script. Required fields are highlighted in red until filled.

#### Block 1 — Docking

- **Target protein.** Provide one of: PDB ID, UniProt accession (the
  dashboard resolves it to a structure via SIFTS), a local PDB file, or an
  AlphaFold model. Toggle structure-prep options as needed (energy
  minimisation, Meeko-style PDBQT conversion, alternate-location selection,
  residue deletion).
- **Binding site.** Pick one of three modes (see § 1.3):
  - fpocket → choose a pocket from the annotated dropdown.
  - Known ligand → upload an SDF/PDB with the bound ligand.
  - Residues → enter chain + residue numbers.
  Padding (Å) widens the docking box around the chosen centre.
- **Ligand library.** Pick a source: ZINC tranche (the dashboard streams
  from ZINC22), ChEMBL by target ID, a local SDF/MOL2 file, or a custom
  SMILES list. Set a maximum number of ligands to keep the run tractable.
- **Docking parameters.** Exhaustiveness (suggested ranges given as
  placeholders: 12 fast / 16 standard / 32 thorough), number of poses,
  CPU count, random seed, pH for ionisation, charge model. Optional flags
  to run PLIP analysis and generate 3D pose images.
- **Execution.** Choose local or SLURM. For SLURM, fill the job name,
  partition, account, GPU count, wall time, and array concurrency.

#### Block 2 — Hit refinement

Reads the docking output of Block 1 (no upload needed) and re-docks the top
N hits with higher exhaustiveness and multiple seeds. Inputs: N (top hits to
refine), exhaustiveness, number of seeds.

The ranked list produced here is the ranking the pipeline uses downstream —
Block 3 (MD) is a pass/fail filter on top of this ranking, not a re-ranking
step.

#### Block 3 — MD optimization

Reads the refined hits from Block 2. Selects the top-M poses and runs short
OpenMM MD on each as a binding-stability gate. Inputs: M (poses to gate),
production length in nanoseconds, equilibration length, GPU platform (CUDA
or CPU). Each pose receives a pass/fail call based on RMSD-to-starting-pose
stability over the production trajectory.

#### Block 4 — FEP

Reads the MD-passing poses from Block 3. Selects the top pair (or top-K
pairs) for relative free-energy perturbation via OpenFE. Inputs: number of
pairs, network type (full / hybrid / radial), simulation length per
λ window.

### 2.4 Reading reports

Each block writes a markdown report to
`<workspace>/reports/<run_label>/<block_name>.md` plus structured output
files (CSV scores, JSON pose viewers, PDB final frames).

In the **Reports** tab:

- Each completed campaign appears as one card with up to four block rows.
- Click "View report" on a row to open its focused page. The page shows:
  - Top metric cards (top docking score, best ligand, ΔΔG, MD gate calls).
  - A ranked ligand table with colour-coded gate badges.
  - The raw markdown report (collapsed by default at the bottom).
  - Embedded 3D viewers (mol* iframe) for the best pose / MD final frame
    when the block produces them.
- The "Compare runs (cross-workflow table)" drawer at the bottom of the
  Reports tab lists every block result from every campaign in one table,
  useful for screening multiple targets.

### 2.5 AI-agent workflow

The "Copy as AI prompt" button does not copy a bash script — it copies a
natural-language instruction block that *contains* the bash commands. The
embedded instructions cover:

1. Where to SSH (host, user, key, ports) — these fields are user-supplied in
   the "Run environment" drawer of the Home view.
2. Where the workspace lives and which paths are writable.
3. Which blocks are included and the exact CLI flags for each.
4. Progress reporting: the agent must write to the same `progress.json`
   files the dashboard polls, so the Progress Monitor updates in real time.
5. Retry policy for transient errors (network, transient compute failures)
   and stop conditions for terminal errors.

Tested agents include Codex (CLI), Claude Code, and any agent supporting
shell access. The pipeline runs unattended; the user does not need to keep
the dashboard open.

### 2.7 Reproducing the manuscript benchmark (DUD-E CDK2)

The published CDK2 enrichment benchmark uses the DUD-E CDK2 active/decoy
library: 631 known actives and 23,918 property-matched decoys, receptor
1KE5. A fresh OSLab install downloads this library from the DUD-E project's
canonical URL set with one CLI call:

```
oslab fetch-benchmark cdk2-dude --to <your_workspace>
```

This writes the receptor, the co-crystal ligand, the gzipped active/decoy
mol2 files, and the SMILES indices into
`<your_workspace>/benchmarks/cdk2-dude/`. The downloader is idempotent and
the DUD-E URLs (`https://dude.docking.org/targets/cdk2/...`) have been live
since 2012, which is why they are preferred over project-internal mirrors.

After the fetch completes, point the dashboard's Block 1 fields at the
downloaded `receptor.pdb`, `crystal_ligand.mol2`, and `actives_final.mol2.gz`
+ `decoys_final.mol2.gz` files. The downstream blocks (Hit Refinement, MD,
FEP) consume the previous block's outputs and require no further inputs.

### 2.8 Operational notes

- **Multi-user isolation.** Every dashboard instance is scoped to a single
  workspace (`--root`). Cross-user reads are not possible from the UI; each
  user only sees their own runs.
- **Job survival.** The pipeline is launched by the AI agent inside an SSH
  session that detaches itself (`nohup`/`tmux`/`screen`, depending on the
  agent's behaviour). Closing the dashboard or the laptop does not stop a
  running pipeline; reconnecting picks up the in-progress state from the
  progress JSON files on disk.
- **Resource limits.** Vina is CPU-only; concurrency is governed by the
  "Total CPU workers" field in Block 1. OpenMM and OpenFE use the GPU; only
  one GPU job runs at a time per workspace.
- **Resetting.** The Quick Start "Reset to empty form" link clears the
  filled values. Manually deleting a campaign means deleting its
  `<workspace>/runs/<label>/` and `<workspace>/reports/<label>/` directories.
- **Cache busting.** Static assets (`dashboard.css`, `dashboard_v2.js`) are
  served with a query string derived from the file's mtime, so users never
  need to hard-refresh after a UI update.

---

## Appendix A — Repository layout

```
/data/oslab/users/jiyoun/oslab_v2_shared/   # canonical shared source
├── README.md
├── start-oslab-v2.sh.template              # per-user launcher template
├── HARDENED_INSTALL.md                     # local-install notes
├── environment.lock.yml                    # micromamba env spec
├── src/oslab/                              # the package (see § 1.2 layout)
└── _backup-YYYYMMDD-HHMMSS/                # rolling backups before each sync
```

## Appendix B — External APIs called

| Service | Endpoint | Used for |
|---|---|---|
| PDBe SIFTS | `https://www.ebi.ac.uk/pdbe/api/mappings/uniprot/{pdb_id}` | PDB → UniProt mapping for fpocket annotations |
| UniProt KB | `https://rest.uniprot.org/uniprotkb/{accession}.json` | Topological domain / transmembrane / domain / region features |
| ZINC22 | `https://files.docking.org/zinc22/…` | Streaming ligand tranches by drug-likeness goal |
| ChEMBL | `https://www.ebi.ac.uk/chembl/api/data/…` | Target-keyed ligand sets |
| AlphaFold DB | `https://alphafold.ebi.ac.uk/files/AF-{accession}-F1-model_v4.pdb` | Predicted structures when no PDB exists |

All calls are read-only; no API keys are required. Failures are tolerated
(the corresponding field degrades to "annotation unavailable") so the
pipeline does not stall when an external service is down.
