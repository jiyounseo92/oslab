# Open Structure Lab Hardened Installer

This bundle starts from the original OSLAB installer and includes the fixes learned while deploying and debugging the Lambda GPU server.

## What Is Hardened

- FEP/OpenFE subprocesses run in a clean OpenFE Python environment to avoid Python 3.11/3.13 stdlib mixing.
- OpenFE runner launches with Python `-E` and the source script path, avoiding inherited `PYTHONPATH` surprises.
- OpenFE/RBFE environment is installed by default by `install_hardened.sh`.
- AmberTools is verified because OpenFE AM1-BCC charge assignment needs `antechamber` and `sqm`.
- Linux NVIDIA installs can apply the Lambda-tested CUDA/NVRTC pin: `cuda-version=13.0`, `cuda-nvrtc<13.1`.
- PLIP is installed automatically on Ubuntu when passwordless `sudo` is available; otherwise the doctor warns.
- Dashboard includes the Lambda UI fixes for FEP live selections and more frequent FEP progress updates.
- FEP/OpenFE inputs use bound-frame ligand coordinates from MD/Optimization or MCS-aligned analogs, and skip analogs that cannot be placed in the pocket.
- Lambda defaults use NAGL partial charges, single-core OpenFE network planning, CUDA mixed precision, and an 8 second MCS timeout for analog placement.
- Helper scripts are installed:
  - `~/.open-structure-lab/bin/oslab-start-dashboard`
  - `~/.open-structure-lab/bin/oslab-doctor`

## Quick Install On A New Ubuntu/Lambda/AWS Server

```bash
tar -xzf open-structure-lab-hardened-installer-20260510.tar.gz
cd open-structure-lab-hardened-installer-20260510
./install_hardened.sh --workspace-root "$HOME/OSLabLambda"
```

Start the dashboard:

```bash
~/.open-structure-lab/bin/oslab-start-dashboard --root "$HOME/OSLabLambda" --port 8766
```

From your Mac, tunnel to a remote server:

```bash
ssh -i ~/.ssh/codex-key -N -L 9877:127.0.0.1:8766 ubuntu@SERVER_IP
```

Open:

```text
http://127.0.0.1:9877
```

## Quick Install On A Mac Desktop

```bash
tar -xzf open-structure-lab-hardened-installer-20260510.tar.gz
cd open-structure-lab-hardened-installer-20260510
./install_hardened.sh --workspace-root "$HOME/Documents/Open Structure Lab"
```

Start the dashboard:

```bash
~/.open-structure-lab/bin/oslab-start-dashboard --root "$HOME/Documents/Open Structure Lab" --port 8766
```

Open:

```text
http://127.0.0.1:8766
```

On Mac, GPU/CUDA is not expected. The FEP/OpenFE environment can still install for CPU workflows if conda-forge supports the platform.

## Diagnostic Command

```bash
~/.open-structure-lab/bin/oslab-doctor
```

The doctor checks:

- main OSLAB imports
- OpenMM import
- OpenFE version
- AmberTools wrapper
- clean OpenFE runner launch
- CUDA platform when NVIDIA is present
- PLIP command

## Important Environment Variables

```bash
export OSLAB_OPENFE_BIN="$HOME/.open-structure-lab/.micromamba/envs/openfe-rbfe/bin/openfe"
export OSLAB_OPENMM_PLATFORM=CUDA   # Linux NVIDIA server
export OSLAB_OPENMM_PLATFORM=CPU    # Mac or CPU-only server
export OSLAB_CUDA_PRECISION=mixed
export OSLAB_OPENFE_CHARGE_METHOD=nagl
export OSLAB_FEP_MCS_TIMEOUT_SECONDS=8
export OSLAB_OPENFE_PLAN_CORES=1
```

## Updating An Existing Install

Use `--force` to replace the source tree while keeping the micromamba root:

```bash
./install_hardened.sh --workspace-root "$HOME/OSLabLambda" --force
```

## Notes From Lambda Debugging

- If FEP immediately fails with `SRE module mismatch`, OpenFE is importing the wrong Python stdlib. This bundle fixes that in `oslab.openfe_backend`.
- If OpenFE says AmberTools is unavailable, run the doctor and verify `antechamber` is on the OpenFE env `PATH`.
- If FEP looks stuck at `fep-run`, check the FEP tab’s OpenFE transformation progress. Individual transformations can take minutes.
- If PLIP gets stuck or is missing on Ubuntu, install it with:

```bash
sudo apt-get update
sudo apt-get install -y plip
```
