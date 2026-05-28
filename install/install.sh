#!/usr/bin/env bash

set -euo pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$bundle_dir/.." && pwd)"

default_workspace_root="$HOME/Open Structure Lab"
if [[ -d "$HOME/Documents" ]]; then
  default_workspace_root="$HOME/Documents/Open Structure Lab"
fi

install_dir="$HOME/.open-structure-lab"
workspace_root="$default_workspace_root"
env_name="open-structure-lab"
openfe_env_name="openfe-rbfe"
mode="desktop"
micromamba_root=""
force=0
dry_run=0
install_openfe_rbfe=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Installs Open Structure Lab from this bundle into a micromamba environment.

Options:
  --install-dir DIR        Directory that will hold the unpacked source and helper files.
  --workspace-root DIR     Workspace root for runs, reports, cache, and the local catalog.
  --env-name NAME          Micromamba environment name. Default: open-structure-lab
  --openfe-env-name NAME   Micromamba environment name for the optional OpenFE/RBFE stack.
                           Default: openfe-rbfe
  --micromamba-root DIR    Micromamba root prefix. Default: INSTALL_DIR/.micromamba
  --mode desktop|hpc       desktop keeps defaults under the current home directory.
                           hpc is intended for shared filesystems and custom prefixes.
  --install-openfe-rbfe    Install the optional OpenFE/RBFE environment used by the FEP workflow.
  --force                  Replace an existing source checkout in INSTALL_DIR/src.
  --dry-run                Print planned actions without changing the system.
  --help                   Show this help text.

Examples:
  ./install.sh
  ./install.sh --mode hpc --install-dir /shared/apps/open-structure-lab \
    --workspace-root /shared/work/open-structure-lab --env-name open-structure-lab
EOF
}

log() {
  printf '[oslab-install] %s\n' "$*"
}

fail() {
  printf '[oslab-install] ERROR: %s\n' "$*" >&2
  exit 1
}

run_cmd() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

install_main_pip_extras() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf '[dry-run] MAMBA_ROOT_PREFIX=%q %q run -n %q python -m pip install --upgrade meeko prolif\n' "$micromamba_root" "$micromamba_bin" "$env_name"
    return 0
  fi
  log "Installing main-environment pip extras"
  MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" run -n "$env_name" \
    python -m pip install --upgrade meeko prolif
}

env_exists() {
  local name="$1"

  if [[ "$dry_run" -eq 1 ]]; then
    return 1
  fi

  MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" env list | awk '{print $1}' | grep -Fxq "$name"
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "Missing required bundle file: $path"
}

detect_platform() {
  local os
  local arch
  os="$(uname -s)"
  arch="$(uname -m)"

  case "$os" in
    Linux) os="linux" ;;
    Darwin) os="osx" ;;
    *) fail "Unsupported operating system: $os" ;;
  esac

  case "$os:$arch" in
    linux:x86_64|linux:amd64|osx:x86_64|osx:amd64) arch="64" ;;
    linux:arm64|linux:aarch64) arch="aarch64" ;;
    osx:arm64|osx:aarch64) arch="arm64" ;;
    *) fail "Unsupported CPU architecture: $arch" ;;
  esac

  printf '%s-%s\n' "$os" "$arch"
}

download_micromamba() {
  local target="$1"
  local platform
  local temp_dir
  local archive

  command -v curl >/dev/null 2>&1 || fail "curl is required to download micromamba"
  platform="$(detect_platform)"
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/micromamba.XXXXXX")"
  archive="$temp_dir/micromamba.tar.bz2"

  trap 'rm -rf "$temp_dir"' RETURN

  log "Downloading micromamba for $platform"
  run_cmd mkdir -p "$(dirname "$target")"
  if [[ "$dry_run" -eq 1 ]]; then
    printf '[dry-run] curl -Ls %q -o %q\n' "https://micro.mamba.pm/api/micromamba/${platform}/latest" "$archive"
    printf '[dry-run] tar -xjf %q -C %q bin/micromamba\n' "$archive" "$temp_dir"
    printf '[dry-run] install -m 755 %q %q\n' "$temp_dir/bin/micromamba" "$target"
    return 0
  fi

  curl -Ls "https://micro.mamba.pm/api/micromamba/${platform}/latest" -o "$archive"
  tar -xjf "$archive" -C "$temp_dir" bin/micromamba
  install -m 755 "$temp_dir/bin/micromamba" "$target"
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --install-dir)
      [[ "$#" -ge 2 ]] || fail "--install-dir requires a value"
      install_dir="$2"
      shift 2
      ;;
    --workspace-root)
      [[ "$#" -ge 2 ]] || fail "--workspace-root requires a value"
      workspace_root="$2"
      shift 2
      ;;
    --env-name)
      [[ "$#" -ge 2 ]] || fail "--env-name requires a value"
      env_name="$2"
      shift 2
      ;;
    --openfe-env-name)
      [[ "$#" -ge 2 ]] || fail "--openfe-env-name requires a value"
      openfe_env_name="$2"
      shift 2
      ;;
    --micromamba-root)
      [[ "$#" -ge 2 ]] || fail "--micromamba-root requires a value"
      micromamba_root="$2"
      shift 2
      ;;
    --mode)
      [[ "$#" -ge 2 ]] || fail "--mode requires a value"
      mode="$2"
      shift 2
      ;;
    --force)
      force=1
      shift
      ;;
    --install-openfe-rbfe)
      install_openfe_rbfe=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

case "$mode" in
  desktop|hpc) ;;
  *) fail "Unsupported mode: $mode" ;;
esac

# The source can come from a packaged tarball (the installer bundle) or
# directly from a git checkout (the repo root has pyproject.toml + src/oslab).
if [[ -f "$bundle_dir/open-structure-lab-source.tar.gz" ]]; then
  source_mode="bundle"
elif [[ -f "$repo_root/pyproject.toml" && -d "$repo_root/src/oslab" ]]; then
  source_mode="repo"
else
  fail "Could not find the OSLab source. Expected either $bundle_dir/open-structure-lab-source.tar.gz (installer bundle) or $repo_root/pyproject.toml (git checkout)."
fi
require_file "$bundle_dir/environment.yml"

if [[ -z "$micromamba_root" ]]; then
  micromamba_root="$install_dir/.micromamba"
fi

if [[ "$source_mode" == "repo" ]]; then
  source_dir="$repo_root"
else
  source_dir="$install_dir/src/open-structure-lab"
fi
micromamba_bin=""
environment_file="$bundle_dir/environment.yml"
platform_id="$(detect_platform)"
linux_explicit_file="$bundle_dir/environment.linux-64.explicit.txt"
openfe_linux_explicit_file="$bundle_dir/environment.openfe-rbfe.linux-64.explicit.txt"
if [[ "${OSLAB_USE_LOCK_FILE:-0}" == "1" && -f "$bundle_dir/environment.lock.yml" ]]; then
  environment_file="$bundle_dir/environment.lock.yml"
fi

if command -v micromamba >/dev/null 2>&1; then
  micromamba_bin="$(command -v micromamba)"
else
  micromamba_bin="$micromamba_root/bin/micromamba"
  if [[ ! -x "$micromamba_bin" ]]; then
    download_micromamba "$micromamba_bin"
  fi
fi

run_cmd mkdir -p "$workspace_root"

if [[ "$source_mode" == "bundle" ]]; then
  run_cmd mkdir -p "$install_dir/src"
  if [[ -e "$source_dir" ]]; then
    if [[ "$force" -eq 1 ]]; then
      run_cmd rm -rf "$source_dir"
    else
      fail "Source directory already exists: $source_dir (use --force to replace it)"
    fi
  fi
  log "Unpacking bundled source into $source_dir"
  run_cmd mkdir -p "$source_dir"
  if [[ "$dry_run" -eq 1 ]]; then
    printf '[dry-run] tar -xzf %q -C %q\n' "$bundle_dir/open-structure-lab-source.tar.gz" "$source_dir"
  else
    tar -xzf "$bundle_dir/open-structure-lab-source.tar.gz" -C "$source_dir"
  fi
else
  log "Installing OSLab from the git checkout at $source_dir"
fi

log "Creating or updating micromamba environment $env_name"
if [[ "$dry_run" -eq 1 ]]; then
  printf '[dry-run] environment file: %q\n' "$environment_file"
  printf '[dry-run] if environment %q exists: micromamba env update; otherwise: micromamba create\n' "$env_name"
  printf '[dry-run] MAMBA_ROOT_PREFIX=%q %q run -n %q python -m pip install --no-deps --upgrade %q\n' "$micromamba_root" "$micromamba_bin" "$env_name" "$source_dir"
  printf '[dry-run] MAMBA_ROOT_PREFIX=%q %q run -n %q oslab configure --root %q\n' "$micromamba_root" "$micromamba_bin" "$env_name" "$workspace_root"
  printf '[dry-run] MAMBA_ROOT_PREFIX=%q %q run -n %q oslab init-project\n' "$micromamba_root" "$micromamba_bin" "$env_name"
else
  log "Using environment file $environment_file"
  if env_exists "$env_name"; then
    if [[ "${OSLAB_USE_EXPLICIT_LINUX:-1}" == "1" && "$platform_id" == "linux-64" && -f "$linux_explicit_file" ]]; then
      log "Updating from explicit Linux package spec $linux_explicit_file"
      MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" install -y -n "$env_name" --file "$linux_explicit_file"
    else
      MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" env update -y -n "$env_name" -f "$environment_file"
    fi
  elif [[ "${OSLAB_USE_EXPLICIT_LINUX:-1}" == "1" && "$platform_id" == "linux-64" && -f "$linux_explicit_file" ]]; then
    log "Using explicit Linux package spec $linux_explicit_file"
    MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" create -y -n "$env_name" --file "$linux_explicit_file"
  else
    MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" create -y -n "$env_name" -f "$environment_file"
  fi
  install_main_pip_extras
  MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" run -n "$env_name" python -m pip install --no-deps --upgrade "$source_dir"
  MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" run -n "$env_name" oslab configure --root "$workspace_root"
  MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" run -n "$env_name" oslab init-project
fi

if [[ "$install_openfe_rbfe" -eq 1 ]]; then
  require_file "$bundle_dir/environment.openfe-rbfe.yml"
  log "Creating or updating optional OpenFE/RBFE environment $openfe_env_name"
  if [[ "$dry_run" -eq 1 ]]; then
    printf '[dry-run] if environment %q exists: micromamba env update; otherwise: micromamba create\n' "$openfe_env_name"
  else
    if env_exists "$openfe_env_name"; then
      if [[ "${OSLAB_USE_EXPLICIT_LINUX:-1}" == "1" && "$platform_id" == "linux-64" && -f "$openfe_linux_explicit_file" ]]; then
        log "Updating OpenFE from explicit Linux package spec $openfe_linux_explicit_file"
        MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" install -y -n "$openfe_env_name" --file "$openfe_linux_explicit_file"
      else
        MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" env update -y -n "$openfe_env_name" -f "$bundle_dir/environment.openfe-rbfe.yml"
      fi
    elif [[ "${OSLAB_USE_EXPLICIT_LINUX:-1}" == "1" && "$platform_id" == "linux-64" && -f "$openfe_linux_explicit_file" ]]; then
      log "Using explicit Linux OpenFE package spec $openfe_linux_explicit_file"
      MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" create -y -n "$openfe_env_name" --file "$openfe_linux_explicit_file"
    else
      MAMBA_ROOT_PREFIX="$micromamba_root" "$micromamba_bin" create -y -n "$openfe_env_name" -f "$bundle_dir/environment.openfe-rbfe.yml"
    fi
  fi
fi

# Create a small launcher so users can run `oslab` without the long
# micromamba prefix. It lives at $install_dir/bin/oslab.
launcher_dir="$install_dir/bin"
launcher="$launcher_dir/oslab"
if [[ "$dry_run" -eq 1 ]]; then
  printf '[dry-run] create launcher %q wrapping: %q run -n %q oslab\n' "$launcher" "$micromamba_bin" "$env_name"
else
  mkdir -p "$launcher_dir"
  cat > "$launcher" <<LAUNCH
#!/usr/bin/env bash
export MAMBA_ROOT_PREFIX="$micromamba_root"
exec "$micromamba_bin" run -n "$env_name" oslab "\$@"
LAUNCH
  chmod +x "$launcher"
  log "Created oslab launcher at $launcher"
fi

cat <<EOF

Open Structure Lab installation is ready.

Install directory: $install_dir
Workspace root: $workspace_root
Environment name: $env_name
Optional OpenFE/RBFE environment: $(if [[ "$install_openfe_rbfe" -eq 1 ]]; then printf '%s' "$openfe_env_name"; else printf '%s' 'not installed'; fi)
Micromamba root: $micromamba_root
Mode: $mode

IMPORTANT — the 'oslab' command lives in an isolated environment, so typing
'oslab' alone will say "command not found" until you add it to your PATH.
A launcher was created for you at:
  $launcher

Make 'oslab' available in this terminal (copy-paste this one line):
  export PATH="$launcher_dir:\$PATH"

Then these will work:
  oslab check-tools
  oslab dashboard serve --port 8766

To make it permanent, add that same 'export PATH=...' line to your shell
startup file (~/.zshrc on macOS, ~/.bashrc on most Linux). Or, without
touching PATH, run oslab by its full path each time:
  "$launcher" check-tools

For HPC deployments, point --install-dir and --workspace-root to shared storage and use the oslab hpc export-slurm-* commands from the installed environment.
EOF
