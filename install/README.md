# install/

Everything you need to install OSLab and launch the dashboard.

## File map

| File | Purpose |
| --- | --- |
| [`install.sh`](install.sh) | One-shot installer for desktop and HPC. Reads `environment.yml`, sets up a micromamba environment, installs the package, and prints the launcher command. |
| [`INSTALL.md`](INSTALL.md) | Install instructions — desktop mode, HPC mode, optional OpenFE/RBFE environment for Block 4 (FEP). |
| [`HARDENED_INSTALL.md`](HARDENED_INSTALL.md) | Locked / reproducible install using `environment.lock.yml`. Recommended for production deployments. |
| [`environment.yml`](environment.yml) | Cross-platform micromamba/conda dependency spec used by `install.sh`. |
| [`environment.lock.yml`](environment.lock.yml) | Exact lock file captured from the build machine. Use this for byte-for-byte reproducible installs. |
| [`environment.openfe-rbfe.yml`](environment.openfe-rbfe.yml) | Optional companion environment for Block 4 (FEP) — some sites keep this separate from the base docking environment. |
| [`start-oslab-v2.sh.template`](start-oslab-v2.sh.template) | Per-user dashboard launcher for shared HPC servers. Copy to `~/start-oslab-v2.sh`, edit the PORT and ROOT variables, then run. |

## TL;DR

```bash
# from the repo root
./install/install.sh
```

For anything beyond the desktop default — HPC mode, custom install prefix,
optional FEP environment, locked builds — see
[`INSTALL.md`](INSTALL.md) and [`HARDENED_INSTALL.md`](HARDENED_INSTALL.md).
