# Open Structure Lab Installer Bundle

This bundle installs Open Structure Lab into a micromamba environment and configures a workspace root for reports, runs, cache, and the local catalog.

## Contents

- `install.sh`: desktop and HPC installer entrypoint
- `open-structure-lab-source.tar.gz`: project source tree without generated caches, reports, runs, or local environments
- `environment.yml`: cross-platform dependency specification for micromamba/conda
- `environment.lock.yml`: lock file captured from the build machine for reference
- `environment.openfe-rbfe.yml`: optional OpenFE/RBFE environment for the FEP workflow
- `PROJECT_README.md`: upstream project overview and CLI usage

## Desktop Install

```bash
tar -xzf open-structure-lab-installer-*.tar.gz
cd open-structure-lab-installer-*
./install.sh
```

Default desktop locations:

- install dir: `~/.open-structure-lab`
- workspace root: `~/Documents/Open Structure Lab` when `~/Documents` exists, otherwise `~/Open Structure Lab`
- environment name: `open-structure-lab`

To install the optional OpenFE/RBFE environment used by the FEP workflow:

```bash
./install.sh --install-openfe-rbfe
```

## HPC / Shared Filesystem Install

Use a shared install prefix and workspace root so exported SLURM jobs can read the same files from compute nodes.

```bash
tar -xzf open-structure-lab-installer-*.tar.gz
cd open-structure-lab-installer-*
./install.sh \
  --mode hpc \
  --install-dir /shared/apps/open-structure-lab \
  --workspace-root /shared/work/open-structure-lab \
  --env-name open-structure-lab \
  --install-openfe-rbfe
```

## Notes

- The installer will use `micromamba` from `PATH` when available.
- If `micromamba` is not installed, the installer downloads a standalone binary into the selected install prefix.
- The bundle includes the application source. Python and chemistry dependencies are still resolved from conda-forge, bioconda, and pip during installation.
- The OpenFE/RBFE environment is optional because some sites keep it separate from the base docking environment.
- After installation, start the dashboard with the command printed by the installer.