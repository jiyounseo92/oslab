# Open Structure Lab (OSLab)

AI-mediated four-block virtual screening pipeline — **docking → hit
refinement → short MD pass/fail → relative free-energy perturbation** —
driven by a single-page web dashboard. You fill in a form, the dashboard
generates a script, you paste the script into an AI coding agent
(Codex, Claude Code, …), and the agent runs the pipeline on your GPU host
and streams progress back into the dashboard.

Companion repository for **Seo et al.** (manuscript in preparation).

## Where to start

| I want to… | Go to |
| --- | --- |
| **Understand how OSLab works** | [`docs/methods.md`](docs/methods.md) |
| **Install and run it locally** | [`install/INSTALL.md`](install/INSTALL.md) (or the quick install below) |
| **Reproduce the CDK2 benchmark from the paper** | [Reproducing the benchmark](#reproducing-the-manuscript-benchmark) (below) |
| **Read the two benchmark reports referenced in the paper** | [`docs/reports/`](docs/reports/) |
| **Browse the per-block outputs from the benchmark run** | [`examples/kimlab-cdk2-enrichment-v2/`](examples/kimlab-cdk2-enrichment-v2/) |
| **Download the full 940 MB raw outputs (every pose, every trajectory)** | [Releases → kimlab-cdk2-enrichment-v2](https://github.com/jiyounseo92/oslab/releases/tag/kimlab-cdk2-enrichment-v2) |

## Repository map

```
oslab/
├── src/oslab/          Python package — CLI, dashboard, pipeline modules
├── install/            Installer script, environment specs, launcher templates
├── docs/
│   ├── methods.md      Full methods + usage write-up
│   └── reports/        Two benchmark reports (DOCX) referenced in the paper
├── examples/           Curated outputs from the published CDK2 benchmark
│   └── kimlab-cdk2-enrichment-v2/   one folder per block: docking / hit-refinement / md-optimization / fep
├── benchmarks/         Placeholder; `oslab fetch-benchmark` downloads here
├── pyproject.toml      Python package metadata (entry point: `oslab`)
├── LICENSE             Apache 2.0
└── README.md           This file
```

## Quick install

```bash
git clone https://github.com/jiyounseo92/oslab.git
cd oslab

# One-shot install into a micromamba environment named open-structure-lab:
./install/install.sh
```

After install, the `oslab` command is on your PATH. Confirm:

```bash
oslab --help
oslab check-tools     # report which structure / chemistry CLIs are present
```

For HPC / shared-filesystem installs and the optional OpenFE/RBFE
environment used by Block 4 (FEP), see [`install/INSTALL.md`](install/INSTALL.md)
and [`install/HARDENED_INSTALL.md`](install/HARDENED_INSTALL.md).

## Run the dashboard

The dashboard is a Python process you run locally — there is no shared
web server.

```bash
oslab dashboard serve --host 127.0.0.1 --port 8770 --root <your_workspace>
```

Open `http://localhost:8770` in a browser. On a remote server, tunnel the
port to your laptop first:

```bash
ssh -fNL 8770:localhost:8770 <server>
open http://localhost:8770
```

The dashboard has three tabs:

- **Home** — onboarding, the four-block configuration form, and the live
  script preview.
- **Progress Monitor** — per-block progress bars for every run in this
  workspace, plus a detailed log drawer.
- **Reports** — one card per pipeline campaign, with the per-block
  markdown report, ranked ligand table, and 3D viewers.

See [`docs/methods.md`](docs/methods.md) § 2 for a full step-by-step
usage guide.

## Reproducing the manuscript benchmark

The published CDK2 enrichment benchmark uses the **DUD-E CDK2** active/decoy
library: 631 known actives and 23,918 property-matched decoys, receptor
1KE5. Fetch it directly from DUD-E into your workspace with one command:

```bash
oslab fetch-benchmark cdk2-dude --to <your_workspace>
```

This downloads ~32 MB into `<your_workspace>/benchmarks/cdk2-dude/`
(`receptor.pdb`, `crystal_ligand.mol2`, `actives_final.mol2.gz`,
`decoys_final.mol2.gz`, plus SMILES indices). The downloader is idempotent
and the DUD-E URLs (`https://dude.docking.org/targets/cdk2/...`) have been
live since 2012, which is why we prefer them over project-internal mirrors
for long-term reproducibility.

```bash
oslab fetch-benchmark --list   # list all registered benchmarks
```

Once the fetch completes, open the dashboard, click **Quick start: CDK2
full pipeline**, and the form will reference the downloaded files. Copy
the generated script and paste it into your preferred AI coding agent
(Codex, Claude Code, …) to execute on your GPU host.

The full raw outputs of the published run (940 MB compressed, 77,948 files)
are attached as a release asset:
[kimlab-cdk2-enrichment-v2](https://github.com/jiyounseo92/oslab/releases/tag/kimlab-cdk2-enrichment-v2).
Smaller curated outputs (markdown reports + ranked CSVs per block) are in
[`examples/kimlab-cdk2-enrichment-v2/`](examples/kimlab-cdk2-enrichment-v2/).

## Citation

If you use OSLab in published work, please cite:

> Seo, J. et al. *Open Structure Lab: an AI-mediated four-block virtual
> screening pipeline.* (manuscript in preparation, 2026)

A formal BibTeX entry will be added here on acceptance.

## License

Apache License, Version 2.0. See [`LICENSE`](LICENSE).
