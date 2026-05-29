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
Citable archive: [Zenodo DOI 10.5281/zenodo.20401297](https://doi.org/10.5281/zenodo.20401297)
(concept DOI — always resolves to the latest version, currently v1.1.0).

> ### Reviewers / first-time visitors — start here
>
> The fastest path is the hosted **reviewer instance** — no install, no
> typing of pipeline commands:
>
> 1. Open <https://resistant-peoples-gaming-stood.trycloudflare.com>
>    (login `reviewer` / `oslab-review-2026`).
> 2. Click **"Quick start: CDK2 demo (bundled, 5 ligands)"** on the Home tab.
> 3. Click **"Copy AI prompt"** (right-hand panel).
> 4. Paste into your own AI coding agent (Codex, Claude Code, Cursor, …)
>    and let it run.
>
> The agent executes the full four-block pipeline against an **isolated
> per-browser workspace** (anonymous session cookie, ~30 days), reports
> back into the dashboard's **Progress Monitor** tab, and writes results
> into the **Reports** tab. You do not type any pipeline commands.
>
> Reviewers who instead want to install locally: sections 1–4 below follow
> the Nature Research software submission checklist
> (System requirements → Installation guide → Demo → Instructions for use).

## Where to start

| I want to… | Go to |
| --- | --- |
| **Try it without installing (recommended for reviewers)** | [Try it without installing](#try-it-without-installing) |
| **Install and run it locally** | [1. System requirements](#1-system-requirements) → [2. Installation guide](#2-installation-guide) |
| **Confirm my install works (5-min demo)** | [3. Demo](#3-demo) |
| **Run it on my own target / reproduce the paper** | [4. Instructions for use](#4-instructions-for-use) |
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
| **Linux x86_64** (tested: Ubuntu 22.04.5 LTS) | ✅ Yes | Recommended. |
| **Linux ARM64 (aarch64)** | ❌ No | fpocket has no Linux-ARM64 conda build (e.g. ARM Docker images). Use an x86_64 host, macOS, or the [browser demo](#try-it-without-installing). |
| **macOS** (Intel and Apple Silicon) | ✅ Yes | All dependencies have macOS builds, including Apple Silicon (arm64). |
| **Windows** | ❌ No | Two docking dependencies (AutoDock Vina, fpocket) have no Windows build. Windows users: either use the [browser demo](#try-it-without-installing) (no install, any OS), or install inside **WSL2** (Ubuntu on Windows) and follow the Linux x86_64 steps. |

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
| OpenFE (Block 4 / FEP) | 1.11.0 — **optional, separate environment** |
| micromamba (installer) | 2.6.0 |

OpenFE is only needed for Block 4 (FEP) and is **not** installed by the
default `./install/install.sh`. Install it separately with
`./install/install.sh --install-openfe-rbfe` (it creates an `openfe-rbfe`
environment). Blocks 1–3 (docking, hit refinement, MD) do not require it.

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

**Typical install time:** ~3 minutes on the test server (30-core Xeon,
fast connection); on a normal laptop/desktop expect **5–15 minutes**,
almost all of it downloading the ~2.3 GB environment (the computer barely
works — it is just waiting on the network).

**Step 3 — make the `oslab` command available.** OSLab installs into an
isolated environment, so typing `oslab` right after the install will say
`command not found` until you add it to your PATH. Copy-paste this one line
(it is also printed at the end of the install):

```bash
export PATH="$HOME/.open-structure-lab/bin:$PATH"
```

To make it permanent so you don't repeat this in new terminals, add that
same line to your shell startup file — `~/.zshrc` on macOS, `~/.bashrc` on
most Linux:

```bash
echo 'export PATH="$HOME/.open-structure-lab/bin:$PATH"' >> ~/.zshrc
```

**Step 4 — check it worked:**

```bash
oslab --help
oslab check-tools     # lists the docking / chemistry tools and confirms each is found
```

If `oslab check-tools` shows the tools as present, you are done. (If you
prefer not to touch PATH, you can always run it by its full path instead:
`~/.open-structure-lab/bin/oslab check-tools`.)

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
**"Quick start: CDK2 demo (bundled, 5 ligands)"**. This fills the whole
form with a ready-to-run CDK2 example (you don't need to know any of the
settings); the 5 ligands and receptor are bundled inside the installed
package, so no extra downloads are needed.

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

A successful check is that **all 5 ligands dock** and `demo-out/report/vina_results.csv`
ranks them with the top binders around **−9 kcal/mol**. Exact AutoDock Vina
scores vary slightly with platform and package build, so treat the values as
approximate (expect roughly −9.0 to −9.4 for the top ligand and ~−7 for the
weakest); the run is correct as long as all five dock and the strongest
binders sort to the top. ~5 min on one CPU core, or ~1–2 min with
`--docking-workers 5`.
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

Open the dashboard, then on the **Home** tab fill the form to point at the
downloaded files (Target → Local file → `<workspace>/benchmarks/cdk2-dude/receptor.pdb`,
Ligand library → Local file → `<workspace>/benchmarks/cdk2-dude/actives.smi`,
etc.) and copy the AI prompt as in § 3. The full raw outputs of the
published CDK2 run (940 MB, 77,948 files) are attached as a release asset:
[kimlab-cdk2-enrichment-v2](https://github.com/jiyounseo92/oslab/releases/tag/kimlab-cdk2-enrichment-v2);
smaller curated per-block outputs are in
[`examples/kimlab-cdk2-enrichment-v2/`](examples/kimlab-cdk2-enrichment-v2/).

---

## Try it without installing

Two hosted instances (no install, browser only). Both are Cloudflare quick
tunnels and may rotate when the tunnel restarts; if a link 404s, open an
issue on this repository.

**Reviewer instance — recommended for reviewers.** Launches the full
four-block pipeline against an isolated per-browser workspace. No SSH, no
local install:

> <https://resistant-peoples-gaming-stood.trycloudflare.com>
> — login `reviewer` / `oslab-review-2026`

1. Log in → Home tab → **"Quick start: CDK2 demo (bundled, 5 ligands)"**.
2. Right-hand panel → **"Copy AI prompt"**.
3. Paste into your own AI coding agent (Codex, Claude Code, Cursor, …).
4. Watch **Progress Monitor** and **Reports** tabs as the agent runs.

Each browser gets its own `anon-<id>` workspace via an HttpOnly session
cookie (`Max-Age=2592000`, ~30 days). Same browser → same history;
incognito / different browser → fresh workspace. All reviewers share one
NVIDIA A10 GPU; the bundled 5-ligand Quick Start finishes in a few
minutes. Reviewer access will be revoked once the manuscript is accepted.

**Read-only demo.** Browse the three-tab UI — Home, Progress Monitor,
Reports — and the published CDK2 reports. Run launches are disabled, so
the UI is safe to click through without committing any compute:

> <https://opening-bailey-bag-appearing.trycloudflare.com>
> — login `oslab` / `oslab2026demo`

---

## Citation

> Seo, J. et al. *Open Structure Lab: an AI-mediated four-block virtual
> screening pipeline.* (manuscript in preparation, 2026).
> Software archive: Zenodo, https://doi.org/10.5281/zenodo.20401297.

Cite the **concept DOI `10.5281/zenodo.20401297`** — it always resolves to
the latest version. It currently resolves to the v1.1.0 record
(`10.5281/zenodo.20447369`); either DOI reaches the archive, but the
concept DOI is the stable citation that will keep tracking future releases.

A formal BibTeX entry will be added on acceptance.

## License

Apache License, Version 2.0 — an [OSI-approved](https://opensource.org/licenses/Apache-2.0)
license. See [`LICENSE`](LICENSE).
