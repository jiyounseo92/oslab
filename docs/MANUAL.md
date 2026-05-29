---
title: "Open Structure Lab (OSLab) — User Manual"
subtitle: "Installation, dashboard guide, and a hands-on CDK2 demo"
date: "2026"
---

# Open Structure Lab (OSLab)

**User Manual — installation, dashboard guide, and a hands-on demo.**

OSLab is an open-source, AI-mediated virtual-screening pipeline. You set up
a screening campaign in a point-and-click web dashboard; the dashboard turns
your choices into a single instruction block; you hand that block to an AI
coding agent (such as Codex or Claude Code); and the agent runs the
four-block pipeline for you while the dashboard shows live progress and the
final ranked results.

The four blocks are:

1. **Docking** — pose generation and ranking with AutoDock Vina.
2. **Hit refinement** — re-docking the top hits at higher accuracy with
   multiple seeds (this produces the ranking used downstream).
3. **MD optimization** — a short OpenMM molecular-dynamics pass/fail gate
   on the top poses (does the bound pose stay stable?).
4. **FEP** — relative binding free-energy perturbation on the survivors,
   with OpenFE.

You never type pipeline commands yourself — the dashboard generates them and
the AI agent executes them.

\newpage

# 1. The dashboard at a glance

OSLab runs entirely in your web browser, served by a small local program on
your own computer or server. The interface has three tabs.

- **Home** — where you configure a run. A short "How OSLab works" guide, a
  **Quick start: CDK2** button that fills the whole form for you, the
  block-by-block configuration form, and—on the right—the live
  **Copy AI prompt** panel.
- **Progress Monitor** — live progress for every run in your workspace, one
  card per campaign, one bar per block.
- **Reports** — the finished results: one card per campaign, with a
  per-block report, a ranked ligand table, and 3-D pose viewers.

\newpage

# 2. System requirements

**Operating system**

| OS | Native install | Notes |
| --- | --- | --- |
| Linux (tested: Ubuntu 22.04.5 LTS) | Yes | Recommended. |
| macOS (Intel and Apple Silicon) | Yes | All dependencies have macOS builds. |
| Windows | No | Two docking dependencies (AutoDock Vina, fpocket) have no Windows build. Use the browser demo, or install inside WSL2 (Ubuntu on Windows) and follow the Linux steps. |

**Software** (installed automatically; key tested versions): Python 3.11.15,
RDKit 2025.09.6, OpenMM 8.5.1, OpenFF Toolkit 0.18.0, AutoDock Vina 1.2,
Open Babel 3.1, fpocket 4.2, PLIP 2, Meeko 0.7.1, ProLIF 2.1.0,
MDAnalysis 2.10, PDBFixer 1.12, OpenFE 1.11.0 (for the FEP block).

**Hardware**

- Docking and hit refinement (Blocks 1–2): **CPU only**, no special hardware.
- MD and FEP (Blocks 3–4): an **NVIDIA CUDA GPU** (tested on A10 23 GB and
  A100 40 GB).
- Disk: the installed software environment is about **2.3 GB**.

\newpage

# 3. Installation

Everything below is typed into a **terminal**.

- **macOS:** press `Cmd`+`Space`, type `Terminal`, press Enter.
- **Linux:** open your Terminal application.
- **Windows:** OSLab does not install natively. Either use the browser demo
  (no install), or install **WSL2** (run `wsl --install` in PowerShell,
  reboot, open the new "Ubuntu" app) and run everything below there.

**Step 1 — download the code:**

```bash
git clone https://github.com/jiyounseo92/oslab.git
cd oslab
```

**Step 2 — install** (builds an isolated environment with all
dependencies; runs unattended):

```bash
./install/install.sh
```

About 3 minutes on a fast server; **5–15 minutes** on a normal laptop,
almost all of it downloading the ~2.3 GB environment.

**Step 3 — make the `oslab` command available.** OSLab installs into an
isolated environment, so `oslab` is not on your PATH until you add it
(otherwise you get `command not found`). Copy-paste this — it is also
printed at the end of the install:

```bash
export PATH="$HOME/.open-structure-lab/bin:$PATH"
```

To make it permanent, append the same line to `~/.zshrc` (macOS) or
`~/.bashrc` (Linux).

**Step 4 — check it worked:**

```bash
oslab --help
oslab check-tools     # lists the docking/chemistry tools and confirms each is found
```

\newpage

# 4. A hands-on demo: dock a few CDK2 ligands

This is the normal OSLab workflow end to end. We dock a small set of CDK2
ligands and read the ranked result — in about five minutes.

**Step 1 — start the dashboard** (from the `oslab` folder):

```bash
oslab dashboard serve --root ./demo-ws --port 8770
```

Leave it running and open **http://localhost:8770** in your browser. You
will see the Home tab (above).

**Step 2 — fill in a run.** Click **Quick start: CDK2** on the Home tab.
This fills the whole form with a ready-to-run CDK2 example — you do not need
to understand any of the settings.

**Step 3 — copy the AI prompt.** On the right-hand panel, click
**Copy AI prompt**. This copies a self-contained instruction block (what to
run, where to write files, how to report progress) together with the run
script.

**Step 4 — hand it to your AI agent.** Paste it into Codex, Claude Code, or
your agent of choice and let it run. The agent executes the pipeline
autonomously and writes progress back into your workspace.

**Step 5 — watch it run.** Switch to the **Progress Monitor** tab. Each
block appears as a card with a progress bar — one bar per block — so you can
see which block is running and click through to its report as it finishes.

**Step 6 — read the results.** Switch to the **Reports** tab. Each campaign
is one card listing its four blocks, each with a **View report** button.
Click **View report** on the docking block to open the ranked results — the
top docking score, the best ligand, the number of ligands docked, and the
full ligand table with 3-D pose viewers.

**What to expect.** For the bundled five-ligand demo set
(`examples/demo-cdk2/`), all five ligands dock and the ranked report lists
them with the strongest binder near −9 kcal/mol. The docking step takes a
few minutes of compute; the complete four-block CDK2 example (docking → hit
refinement → MD → FEP) takes about an hour on a GPU machine.

\newpage

# 5. Reproducing the published benchmark

The published benchmarks use DUD-E active/decoy libraries. Download any of
them into your workspace with one command:

```bash
oslab fetch-benchmark cdk2-dude  --to <your_workspace>   # 631 actives, 23,918 decoys, receptor 1HCK
oslab fetch-benchmark kif11-dude --to <your_workspace>   # 116 actives, 6,850 decoys, receptor 3CJO
oslab fetch-benchmark hivrt-dude --to <your_workspace>   # 338 actives, 18,672 decoys, receptor 3LAN
```

The DUD-E URLs (`https://dude.docking.org/targets/...`) have been live since
2012, so the benchmark can be re-run independently of any private storage.
The complete raw outputs of the published CDK2 run (940 MB) are attached as
a release asset on the repository; smaller curated per-block outputs are in
`examples/kimlab-cdk2-enrichment-v2/`.

# 6. Where your files go

Every run writes only inside the workspace you pass with `--root`:

- `runs/<label>/` — intermediate files and `progress.json` (what the
  Progress Monitor reads)
- `reports/<label>/` — the markdown reports and ranked result tables (what
  the Reports tab reads)
- `logs/<label>.timeline.md` — a one-line-per-block timeline

Different users point at different workspaces, so runs never mix.

# 7. Try it without installing

A read-only public demo of the dashboard (the same one shown in this
manual) is linked from the project README at
<https://github.com/jiyounseo92/oslab>. It is useful for browsing the UI and
a finished CDK2 run without installing anything.

---

*Appendix — verifying the docking engine without the dashboard.* For a
quick, fully deterministic check (e.g. on a headless server), the engine the
AI agent ultimately calls can be run directly on the bundled inputs:

```bash
oslab screen small \
  --ligands examples/demo-cdk2/demo_ligands.smi \
  --receptor examples/demo-cdk2/receptor.pdbqt \
  --binding-site examples/demo-cdk2/site.json \
  --max-ligands 5 --exhaustiveness 8 --no-plip --out ./demo-out
```

A successful check is that **all five ligands dock** and
`demo-out/report/vina_results.csv` ranks them with the top binders around
**−9 kcal/mol**. Exact AutoDock Vina scores vary slightly by platform and
package build, so treat the numbers as approximate (roughly −9.0 to −9.4 for
the top ligand, ~−7 for the weakest); the run is correct as long as all five
dock and the strongest binders sort to the top. About 5 minutes on one CPU
core, or 1–2 minutes with `--docking-workers 5`.
