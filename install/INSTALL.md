# Installing Open Structure Lab

`install.sh` sets up Open Structure Lab in an isolated micromamba environment
and configures a workspace root for reports, runs, cache, and the local
catalog. It works directly from a git clone or an unzipped source archive —
there is no separate tarball to download.

> **Supported systems:** Linux x86_64 and macOS (Intel or Apple Silicon).
> Not supported: Windows and Linux ARM64 (AutoDock Vina / fpocket have no
> build there). See the top-level `README.md` § 1 for details and the
> browser-demo / WSL2 alternatives.

## Get the source

Either clone the repository:

```bash
git clone https://github.com/jiyounseo92/oslab.git
cd oslab
```

…or download the source archive from the repository / a release and unzip
it, then `cd` into the extracted folder (it contains `install/`, `src/`,
`pyproject.toml`, etc.).

## Desktop install

From the repository root:

```bash
./install/install.sh
```

Default desktop locations:

- install dir: `~/.open-structure-lab`
- workspace root: `~/Documents/Open Structure Lab` when `~/Documents`
  exists, otherwise `~/Open Structure Lab`
- environment name: `open-structure-lab`

### Make the `oslab` command available

The installer puts `oslab` inside the isolated environment and prints a
launcher path at the end. Add it to your PATH for the current terminal:

```bash
export PATH="$HOME/.open-structure-lab/bin:$PATH"
oslab check-tools     # confirm the toolchain installed correctly
```

To make it permanent, append that `export` line to `~/.zshrc` (macOS) or
`~/.bashrc` (Linux).

### Optional: OpenFE/RBFE environment (Block 4, FEP)

The default install does **not** include OpenFE. Add it only if you will run
Block 4 (FEP):

```bash
./install/install.sh --install-openfe-rbfe
```

This creates a separate `openfe-rbfe` environment. Blocks 1–3 (docking, hit
refinement, MD) do not need it.

## HPC / shared-filesystem install

Use a shared install prefix and workspace root so exported SLURM jobs can
read the same files from compute nodes:

```bash
./install/install.sh \
  --mode hpc \
  --install-dir /shared/apps/open-structure-lab \
  --workspace-root /shared/work/open-structure-lab \
  --env-name open-structure-lab \
  --install-openfe-rbfe
```

## Notes

- The installer uses `micromamba` from `PATH` when available; otherwise it
  downloads a standalone binary into the selected install prefix.
- Python and chemistry dependencies are resolved from conda-forge and
  bioconda during installation (~2.3 GB; typically 5–15 min on a laptop,
  mostly download time).
- The optional OpenFE/RBFE environment is kept separate because some sites
  do not need the FEP block.
- After installation, start the dashboard with the command printed by the
  installer, or `oslab dashboard serve --root <workspace> --port 8770`.
