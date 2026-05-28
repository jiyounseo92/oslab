# Open Structure Lab (OSLab)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20401297.svg)](https://doi.org/10.5281/zenodo.20401297)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

AI-mediated four-block virtual screening pipeline — **docking → hit
refinement → short MD pass/fail → relative free-energy perturbation** —
driven by a single-page web dashboard. You fill in a form, the dashboard
generates a script, you paste the script into an AI coding agent
(Codex, Claude Code, …), and the agent runs the pipeline on your GPU host
and streams progress back into the dashboard.

Companion repository for **Seo et al.** (manuscript in preparation).
Citable archive: [Zenodo DOI 10.5281/zenodo.20401297](https://doi.org/10.5281/zenodo.20401297).

> **Reviewers / editors:** sections 1–4 below follow the Nature Research
> software submission checklist (System requirements → Installation guide →
> Demo → Instructions for use). A live demo and a runnable reviewer
> instance are linked under [Try it without installing](#try-it-without-installing).

## Where to start

| I want to… | Go to |
| --- | --- |
| **Install and run it locally** | [1. System requirements](#1-system-requirements) → [2. Installation guide](#2-installation-guide) |
| **Confirm my install works (5-min demo)** | [3. Demo](#3-demo) |
| **Run it on my own target / reproduce the paper** | [4. Instructions for use](#4-instructions-for-use) |
| **Try it without installing** | [Try it without installing](#try-it-without-installing) |
| **Understand how OSLab works** | [`docs/methods.md`](docs/methods.md) |
| **Read the benchmark reports / outputs** | [`docs/reports/`](docs/reports/), [`examples/`](examples/) |

## Repository map

```
oslab/
├── src/oslab/          Python package — CLI, dashboard, pipeline modules
├── install/            Installer script, environment specs, launcher templates
├── docs/
│   ├── methods.md      Full methods + usage write-up (pipeline pseudocode)
│   └── reports/        Two benchmark reports (DOCX) referenced in the paper
├── examples/
│   ├── demo-cdk2/      Self-contained 5-ligand docking demo (section 3)
│   └── kimlab-cdk2-enrichment-v2/   Curated per-block outputs from the paper
├── benchmarks/         Placeholder; `oslab fetch-benchmark` downloads here
├── pyproject.toml      Python package metadata (entry point: `oslab`)
├── LICENSE             Apache 2.0
└── README.md           This file
```

---

## 1. System requirements

**Operating systems**

| OS | Native install | Notes |
| --- | --- | --- |
| **Linux** (tested: Ubuntu 22.04.5 LTS) | ✅ Yes | Recommended. |
| **macOS** (Intel and Apple Silicon) | ✅ Yes | All dependencies have macOS builds. |
| **Windows** | ❌ No | Two docking dependencies (AutoDock Vina, fpocket) have no Windows build. Windows users: either use the [browser demo](#try-it-without-installing) (no install, any OS), or install inside **WSL2** (Ubuntu on Windows) and follow the Linux steps. |

**Software dependencies** (resolved automatically by the installer; key
versions the pipeline has been tested on):

| Component | Version tested |
| --- | --- |
| Python | 3.11.15 |
| RDKit | 2025.09.6 |
| OpenMM | 8.5.1 |
| OpenFF Toolkit | 0.18.0 |
| AutoDock Vina | 1.2.x (conda-forge `vina`) |
| Open Babel | 3.1.x |
| fpocket | 4.x |
| PLIP | 2.x |
| Meeko | 0.7.1 |
| ProLIF | 2.1.0 |
| MDAnalysis | 2.10.0 |
| PDBFixer | 1.12.0 |
| Biopython | 1.87 |
| OpenFE (Block 4 / FEP) | 1.11.0 |
| micromamba (installer) | 2.6.0 |

Full pinned specification: [`install/environment.yml`](install/environment.yml)
and [`install/environment.lock.yml`](install/environment.lock.yml).

**Hardware**
- **Blocks 1–2 (docking, hit refinement):** CPU only. No non-standard
  hardware required.
- **Blocks 3–4 (MD pass/fail, FEP):** an NVIDIA CUDA GPU is required.
  Tested on an NVIDIA A10 (23 GB) and previously on NVIDIA A100 (40 GB).
- Disk: the installed environment is ~2.3 GB.

---

## 2. Installation guide

Everything below is typed into a **terminal**. First open one:

- **macOS:** press `Cmd`+`Space`, type `Terminal`, press Enter.
- **Linux:** open your "Terminal" application.
- **Windows:** OSLab does not install natively (see § 1). Install
  **WSL2** first (Microsoft's "Ubuntu on Windows"; run `wsl --install`
  in PowerShell, reboot, open the new "Ubuntu" app), then run everything
  below inside that Ubuntu terminal. If you only want to look at OSLab,
  skip installing and use the [browser demo](#try-it-without-installing).

**Step 1 — download the code.** Copy-paste this into the terminal and
press Enter:

```bash
git clone https://github.com/jiyounseo92/oslab.git
cd oslab
```

**Step 2 — install.** This builds an isolated environment with all
dependencies (RDKit, OpenMM, AutoDock Vina, …). It runs unattended:

```bash
./install/install.sh
```

**Step 3 — check it worked:**

```bash
oslab --help
oslab check-tools     # lists the docking / chemistry tools and confirms each is found
```

If `oslab check-tools` shows the tools as present, you are done.

**Typical install time:** ~3 minutes on the test server (30-core Xeon,
fast connection); on a normal laptop/desktop expect **5–15 minutes**,
almost all of it downloading the ~2.3 GB environment (the computer barely
works — it is just waiting on the network).

For HPC / shared-filesystem installs and the optional OpenFE/RBFE
environment used by Block 4 (FEP), see
[`install/INSTALL.md`](install/INSTALL.md) and
[`install/HARDENED_INSTALL.md`](install/HARDENED_INSTALL.md).

---

## 3. Demo

This walks through OSLab the way it is actually used: you configure a run
in the **dashboard**, click one button to copy an **AI prompt**, paste that
prompt into an **AI coding agent** (Codex, Claude Code, Cursor, …), and the
agent runs the pipeline for you while the dashboard shows live progress and
the final report. You never type pipeline commands yourself — the agent
does, following the copied prompt.

**What you need:** the OSLab install from § 2, and an AI coding agent that
can run shell commands on the same computer (e.g. Claude Code or Codex in a
terminal).

**Step 1 — start the dashboard** (in the terminal, from the `oslab` folder):

```bash
oslab dashboard serve --root ./demo-ws --port 8770
```

Leave it running and open **http://localhost:8770** in your browser.

**Step 2 — fill in a run.** On the **Home** tab, click
**"Quick start: CDK2"**. This fills the whole form with a ready-to-run CDK2
example (you don't need to know any of the settings).

**Step 3 — copy the AI prompt.** On the right-hand panel, click
**"Copy AI prompt"**. This copies a self-contained instruction block (what
to run, where to write, how to report progress) plus the run script.

**Step 4 — hand it to your AI agent.** Paste into Claude Code / Codex /
your agent of choice and let it run. The agent executes the pipeline
autonomously and writes progress back to your workspace.

**Step 5 — watch and read the result.** In the dashboard, the
**Progress Monitor** tab shows each block running; when it finishes, the
**Reports** tab shows the ranked CDK2 results (top docking scores, best
ligands, and—if you ran the later blocks—MD and FEP results).

**Expected output:** a CDK2 docking report in the **Reports** tab, with the
ligands ranked by score (the strongest binders near the top, around
−9 kcal/mol for this set).

**Expected run time:** the docking step on the small demo set is a few
minutes of compute; the full four-block CDK2 example is ~1 hour on a GPU
machine. Total wall-clock also depends on your AI agent and hardware.

> **Just want to look at the dashboard, with no install and no AI agent?**
> Open the live browser demo — it shows the same UI and a finished CDK2
> run: [Try it without installing](#try-it-without-installing).

<details>
<summary><b>For maintainers / CI: verify the docking engine without the dashboard or an agent</b></summary>

The engine the agent ultimately calls can be run directly on the bundled
[`examples/demo-cdk2/`](examples/demo-cdk2/) inputs. This is a deterministic
check, not the normal user workflow:

```bash
oslab screen small \
  --ligands examples/demo-cdk2/demo_ligands.smi \
  --receptor examples/demo-cdk2/receptor.pdbqt \
  --binding-site examples/demo-cdk2/site.json \
  --max-ligands 5 --exhaustiveness 8 --no-plip --out ./demo-out
```

All 5 ligands dock; `demo-out/report/vina_results.csv` reproduces
active_00001 −9.198, active_00007 −8.828, active_00006 −8.668,
active_00008 −7.123, active_00009 −7.114 (kcal/mol). ~5 min on one CPU
core, or ~1–2 min with `--docking-workers 5`.
</details>

---

## 4. Instructions for use

### Run the dashboard on your own target

The dashboard is a local Python process — there is no shared web server.

```bash
oslab dashboard serve --host 127.0.0.1 --port 8770 --root <your_workspace>
```

Open `http://localhost:8770`. On a remote server, tunnel the port first:

```bash
ssh -fNL 8770:localhost:8770 <server>
open http://localhost:8770
```

The dashboard has three tabs: **Home** (four-block configuration form +
live script preview), **Progress Monitor** (per-block progress bars + log
drawer), and **Reports** (one card per campaign, with per-block reports,
ranked tables, and 3D viewers). Fill the form, copy the generated AI prompt,
and paste it into an AI coding agent to execute the pipeline on your GPU
host. Step-by-step usage: [`docs/methods.md`](docs/methods.md) § 2.

### Reproduce the manuscript benchmark

The published benchmarks use DUD-E active/decoy libraries. Fetch any of them
directly from DUD-E into your workspace:

```bash
oslab fetch-benchmark cdk2-dude  --to <your_workspace>   # 631 actives, 23,918 decoys, receptor 1HCK
oslab fetch-benchmark kif11-dude --to <your_workspace>   # 116 actives, 6,850 decoys, receptor 3CJO
oslab fetch-benchmark hivrt-dude --to <your_workspace>   # 338 actives, 18,672 decoys, receptor 3LAN
oslab fetch-benchmark --list                             # list all registered benchmarks
```

Each downloads ~8–32 MB into `<your_workspace>/benchmarks/<name>/`. The
DUD-E URLs (`https://dude.docking.org/targets/...`) have been live since
2012, which is why we prefer them over project-internal mirrors for
long-term reproducibility.

Then open the dashboard, click **Quick start: CDK2 full pipeline**, and the
form references the downloaded files. The full raw outputs of the published
CDK2 run (940 MB, 77,948 files) are attached as a release asset:
[kimlab-cdk2-enrichment-v2](https://github.com/jiyounseo92/oslab/releases/tag/kimlab-cdk2-enrichment-v2);
smaller curated per-block outputs are in
[`examples/kimlab-cdk2-enrichment-v2/`](examples/kimlab-cdk2-enrichment-v2/).

---

## Try it without installing

**Read-only demo** (browse the four-tab UI and the published CDK2 reports;
run launches disabled):
<https://opening-bailey-bag-appearing.trycloudflare.com> — login `oslab` / `oslab2026demo`

**Reviewer instance** (manuscript under review — launch a real CDK2 run from
the dashboard, no local install; DUD-E CDK2/KIF11/HIV-RT inputs pre-fetched):
<https://bet-logs-shaved-city.trycloudflare.com> — login `reviewer` / `oslab-review-2026`

The reviewer instance runs on a single NVIDIA A10 GPU; concurrent reviewers
share it, so a full 24,549-ligand DUD-E CDK2 docking is slower than the
8× A100 benchmark in the manuscript — for a quick end-to-end check we
recommend the bundled Wang-FEP demo Quick Start (16 ligands, ~1 hour).
Reviewer access will be revoked once the manuscript is accepted.

Both URLs are Cloudflare quick tunnels and rotate when the tunnel restarts;
if a link 404s, please open an issue on this repository.

---

## Citation

> Seo, J. et al. *Open Structure Lab: an AI-mediated four-block virtual
> screening pipeline.* (manuscript in preparation, 2026).
> Software archive: Zenodo, https://doi.org/10.5281/zenodo.20401297.

A formal BibTeX entry will be added on acceptance.

## License

Apache License, Version 2.0 — an [OSI-approved](https://opensource.org/licenses/Apache-2.0)
license. See [`LICENSE`](LICENSE).
