# Open Structure Lab (OSLab)

An open-source structure-based virtual-screening pipeline with a single-page
web dashboard that turns a four-block campaign (docking → hit refinement →
short MD pass/fail → relative free-energy perturbation) into a script you
paste into an AI coding agent. The agent runs the pipeline on your GPU host
and streams progress back into the dashboard.

This repository accompanies the OSLab manuscript (Seo et al., in
preparation). It contains the source code, the installation package, the
DUD-E CDK2 enrichment benchmark data fetcher, the two benchmark reports
that are referenced in the manuscript, and curated outputs from the
benchmark run.

## Repository layout

```
.
├── README.md                # this file
├── pyproject.toml           # Python package metadata (entry point: `oslab`)
├── environment.yml          # cross-platform micromamba/conda dependencies
├── environment.lock.yml     # exact lock file captured from the build machine
├── environment.openfe-rbfe.yml  # optional OpenFE environment for Block 4 (FEP)
├── install.sh               # one-shot installer (desktop or HPC mode)
├── INSTALL.md               # installer-bundle install notes
├── HARDENED_INSTALL.md      # locked / reproducible install notes
├── start-oslab-v2.sh.template  # per-user dashboard launcher template
├── src/oslab/               # the package (CLI + dashboard + pipeline modules)
├── benchmarks/              # placeholder; `oslab fetch-benchmark` writes here
├── examples/                # curated outputs from the manuscript benchmark run
│   └── kimlab-cdk2-enrichment-v2/
│       ├── docking/         # Block 1 outputs
│       ├── hit-refinement/  # Block 2 outputs
│       ├── md-optimization/ # Block 3 outputs
│       └── fep/             # Block 4 outputs
└── docs/
    ├── methods.md           # full methods + usage write-up
    └── reports/             # the two benchmark reports referenced in the paper
        ├── CDK2_OSLab_Four_Block_Benchmark_Report.docx
        └── CDK2_OSLab_Detailed_Methods_and_FEP_Benchmark_Report.docx
```

The full raw outputs of the benchmark run (~940 MB compressed, 77,948 files
covering every per-ligand docked pose, hit-refinement seed, MD trajectory,
and FEP transformation) are attached as a release asset on this repository
under the tag matching the manuscript revision. See § "Full raw outputs"
below.

## Quick install

```bash
git clone https://github.com/<owner>/<repo>.git oslab
cd oslab

# Option A — one-shot installer (desktop):
./install.sh

# Option B — manual install into an existing micromamba environment:
micromamba create -f environment.yml -n open-structure-lab
micromamba activate open-structure-lab
pip install -e .
```

After install, the `oslab` command is on your PATH. Confirm with:

```bash
oslab --help
oslab check-tools     # reports which structure / chemistry CLIs are present
```

See [`INSTALL.md`](INSTALL.md) for desktop vs HPC install options and
[`HARDENED_INSTALL.md`](HARDENED_INSTALL.md) for the locked, reproducible
build.

## Reproducing the manuscript benchmark

The published CDK2 enrichment benchmark uses the DUD-E CDK2 active/decoy
library: 631 known actives and 23,918 property-matched decoys, receptor
1KE5. Fetch the dataset directly from DUD-E into your workspace with:

```bash
oslab fetch-benchmark cdk2-dude --to <your_workspace>
```

This downloads ~32 MB into `<your_workspace>/benchmarks/cdk2-dude/`
(`receptor.pdb`, `crystal_ligand.mol2`, `actives_final.mol2.gz`,
`decoys_final.mol2.gz`, plus SMILES indices). The downloader is idempotent
and the DUD-E URLs (`https://dude.docking.org/targets/cdk2/...`) have been
live since 2012, which is why we prefer them over project-internal mirrors
for long-term reproducibility.

Run `oslab fetch-benchmark --list` to see all known benchmarks.

Once the fetch completes, start the dashboard and click **Quick start:
CDK2 full pipeline** to fill in every form field for a four-block run
against the downloaded files. Copy the generated script and paste it into
your preferred AI coding agent (Codex, Claude Code, etc.) to execute on
your GPU host.

## Running the dashboard

Each user runs their own dashboard pointing at their own workspace. There
is no shared web server — the dashboard is a single Python process bound to
localhost.

```bash
# pick a free local port and a workspace path
oslab dashboard serve --host 127.0.0.1 --port 8770 --root <your_workspace>
```

Then in a browser:

```
http://localhost:8770
```

On a shared HPC server, tunnel the port to your laptop first:

```bash
ssh -fNL 8770:localhost:8770 <server>
open http://localhost:8770
```

See [`docs/methods.md`](docs/methods.md) for the dashboard's UI design and
a step-by-step usage guide.

## Curated benchmark outputs (`examples/`)

The `examples/kimlab-cdk2-enrichment-v2/` directory contains the markdown
reports and ranked-results CSVs from the published benchmark run, organised
one folder per block:

- `docking/` — Block 1 docking report and full Vina ranking
- `hit-refinement/` — Block 2 hit-refinement report and per-seed table
- `md-optimization/` — Block 3 MD pass/fail report
- `fep/` — Block 4 FEP report and ΔΔG results

Large per-ligand files (every individual docked pose, MD trajectory frame,
FEP transformation) are not in this repo — they live in the release asset.

## Full raw outputs (Release asset)

The complete benchmark output bundle
(`kimlab-cdk2-enrichment-v2-completed-results.zip`, ~940 MB compressed,
77,948 files) is attached as a release asset under the tag matching the
manuscript revision. Download it from the **Releases** page and unzip to
inspect every individual pose, log, and trajectory frame.

## Citation

If you use OSLab in published work, please cite:

> Seo, J. et al. *Open Structure Lab: an AI-mediated four-block virtual
> screening pipeline.* (manuscript in preparation, 2026)

A formal BibTeX entry will be added here on acceptance.

## License

This project is licensed under the Apache License, Version 2.0. See
`pyproject.toml` for the canonical declaration.
