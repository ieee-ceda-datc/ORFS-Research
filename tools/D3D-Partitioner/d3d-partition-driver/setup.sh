#!/usr/bin/env bash
set -euo pipefail

driver_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
orfs_root="$(cd "$driver_dir/../../.." && pwd)"
environment_file="$driver_dir/environment-cpu.yml"

env_prefix="${D3D_ENV_PREFIX:-$orfs_root/.conda/taiwei-d3d-cpu}"
conda_candidate="${D3D_CONDA_EXE:-${CONDA_EXE:-}}"
jobs="${JOBS:-$(nproc 2>/dev/null || echo 4)}"
update_env="${D3D_UPDATE_ENV:-0}"

usage() {
  cat <<EOF
Usage: $0 [options]

Create or reuse the CPU-only D3D Conda environment, build the vendored
partitioner, and validate the installed Python/C++ extensions.

Options:
  --env-prefix PATH   Environment path (default: $orfs_root/.conda/taiwei-d3d-cpu)
  --conda PATH        Conda/Mamba/Micromamba executable (or set D3D_CONDA_EXE)
  --jobs N            Parallel build jobs (default: $jobs)
  --update-env        Update an existing environment from environment-cpu.yml
  -h, --help          Show this help

Compiler overrides accepted by the installer can be exported before calling
this script, for example C_COMPILER and CXX_COMPILER.
EOF
}

fail() {
  echo "[ERROR][D3D-SETUP] $*" >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --env-prefix)
      [[ $# -ge 2 ]] || fail "--env-prefix requires a path"
      env_prefix="$2"
      shift 2
      ;;
    --conda)
      [[ $# -ge 2 ]] || fail "--conda requires an executable"
      conda_candidate="$2"
      shift 2
      ;;
    --jobs)
      [[ $# -ge 2 ]] || fail "--jobs requires a positive integer"
      jobs="$2"
      shift 2
      ;;
    --update-env)
      update_env=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || fail "jobs must be a positive integer: $jobs"
case "${update_env,,}" in
  1|yes|true|on) update_env=1 ;;
  0|no|false|off) update_env=0 ;;
  *) fail "D3D_UPDATE_ENV must be 0 or 1: $update_env" ;;
esac

if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" ]]; then
  fail "run D3D setup as the normal developer user, not through sudo"
fi

mkdir -p "$(dirname "$env_prefix")"
env_prefix="$(cd "$(dirname "$env_prefix")" && pwd)/$(basename "$env_prefix")"
[[ "$env_prefix" != "/" ]] || fail "environment prefix must not be the filesystem root"

resolve_executable() {
  local candidate="$1"
  if [[ "$candidate" == */* ]]; then
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
    fi
  else
    command -v "$candidate" 2>/dev/null || true
  fi
  return 0
}

if [[ ! -x "$env_prefix/bin/python" || "$update_env" == "1" ]]; then
  conda_executable=""
  if [[ -n "$conda_candidate" ]]; then
    conda_executable="$(resolve_executable "$conda_candidate")"
  else
    conda_executable="$(resolve_executable conda)"
    [[ -n "$conda_executable" ]] || conda_executable="$(resolve_executable mamba)"
    [[ -n "$conda_executable" ]] || conda_executable="$(resolve_executable micromamba)"
  fi
  [[ -n "$conda_executable" ]] || fail \
    "Conda/Mamba/Micromamba was not found; install one or set D3D_CONDA_EXE=/path/to/executable"

  if [[ -x "$env_prefix/bin/python" ]]; then
    echo "[INFO][D3D-SETUP] updating environment: $env_prefix"
    "$conda_executable" env update \
      --prefix "$env_prefix" \
      --file "$environment_file" \
      --prune
  else
    echo "[INFO][D3D-SETUP] creating environment: $env_prefix"
    "$conda_executable" env create \
      --prefix "$env_prefix" \
      --file "$environment_file"
  fi
else
  echo "[INFO][D3D-SETUP] reusing environment: $env_prefix"
  echo "[INFO][D3D-SETUP] pass --update-env to synchronize it with environment-cpu.yml"
fi

echo "[INFO][D3D-SETUP] checking build prerequisites"
make -C "$driver_dir" preflight \
  ENV_PREFIX="$env_prefix" \
  JOBS="$jobs"

echo "[INFO][D3D-SETUP] building and installing the partitioner"
make -C "$driver_dir" install \
  ENV_PREFIX="$env_prefix" \
  JOBS="$jobs"

echo "[INFO][D3D-SETUP] validating the installation"
make -C "$driver_dir" check \
  ENV_PREFIX="$env_prefix"

echo "[INFO][D3D-SETUP] setup completed"
printf '[INFO][D3D-SETUP] activate with: conda activate %q\n' "$env_prefix"
