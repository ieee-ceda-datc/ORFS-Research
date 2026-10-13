#!/usr/bin/env bash
set -euo pipefail

driver_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
orfs_root="$(cd "$driver_dir/../../.." && pwd)"
source_dir="${SOURCE_DIR:-$driver_dir/..}"
build_dir="${BUILD_DIR:-$orfs_root/tools/build/d3d-partitioner}"
install_prefix="${INSTALL_PREFIX:-$orfs_root/tools/install/d3d-partitioner}"
env_prefix="${ENV_PREFIX:-${CONDA_PREFIX:-}}"
jobs="${JOBS:-$(nproc 2>/dev/null || echo 4)}"
preflight_only=0

if [[ "${1:-}" == "--preflight-only" ]]; then
  preflight_only=1
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--preflight-only]" >&2
  exit 2
fi

fail() {
  echo "[ERROR][D3D-INSTALL] $*" >&2
  exit 2
}

version_at_least() {
  local actual="$1"
  local required="$2"
  [[ "$(printf '%s\n%s\n' "$required" "$actual" | sort -V | head -n1)" == "$required" ]]
}

[[ -f "$source_dir/CMakeLists.txt" ]] || fail "source checkout missing: $source_dir"
if [[ ! -f "$source_dir/.taiwei-vendored-source.json" && ! -f "$source_dir/.gitmodules" ]]; then
  fail "not a supported D2D source checkout: $source_dir"
fi

source_dir="$(cd "$source_dir" && pwd)"
if [[ ! -f "$source_dir/.taiwei-vendored-source.json" ]]; then
  source_repo_root="$(git -C "$source_dir" rev-parse --show-toplevel 2>/dev/null)" || \
    fail "source is neither a vendored release nor inside a Git checkout: $source_dir"
  if [[ "$source_dir" == "$source_repo_root" ]]; then
    source_pathspec=.
  elif [[ "$source_dir" == "$source_repo_root"/* ]]; then
    source_pathspec="${source_dir#"$source_repo_root"/}"
  else
    fail "cannot locate source inside its Git checkout: $source_dir"
  fi

  missing_submodules="$(git -C "$source_repo_root" submodule status --recursive -- "$source_pathspec" | sed -n '/^-/p')"
  [[ -z "$missing_submodules" ]] || fail $'submodules are not initialized; run:\n  git submodule update --init --recursive'
  unpinned_submodules="$(git -C "$source_repo_root" submodule status --recursive -- "$source_pathspec" | sed -n '/^+/p')"
  [[ -z "$unpinned_submodules" ]] || fail "one or more nested submodules are not at their pinned revisions"
  if [[ "${ALLOW_DIRTY_SOURCE:-0}" != "1" ]]; then
    source_status="$(git -C "$source_repo_root" status --porcelain --untracked-files=normal --ignore-submodules=none -- "$source_pathspec")"
    [[ -z "$source_status" ]] || fail "source checkout is dirty; commit the source or pass ALLOW_DIRTY_SOURCE=1 for local development"
  fi
fi

python_executable="${PYTHON_EXECUTABLE:-}"
if [[ -z "$python_executable" ]]; then
  if [[ -n "$env_prefix" && -x "$env_prefix/bin/python" ]]; then
    python_executable="$env_prefix/bin/python"
  else
    python_executable="$(command -v python3 || true)"
  fi
fi
[[ -n "$python_executable" && -x "$python_executable" ]] || fail "Python executable not found"

if [[ -z "$env_prefix" ]]; then
  env_prefix="$("$python_executable" -c 'import sys; print(sys.prefix)')"
fi
[[ -d "$env_prefix" ]] || fail "environment prefix is not a directory: $env_prefix"

cmake_executable="${CMAKE:-}"
if [[ -z "$cmake_executable" ]]; then
  if [[ -x "$env_prefix/bin/cmake" ]]; then
    cmake_executable="$env_prefix/bin/cmake"
  else
    cmake_executable="$(command -v cmake3 || command -v cmake || true)"
  fi
fi
[[ -n "$cmake_executable" && -x "$cmake_executable" ]] || fail "CMake 3.x was not found"
cmake_version="$("$cmake_executable" --version | sed -n 's/^cmake version \([0-9][0-9.]*\).*/\1/p' | head -n1)"
[[ -n "$cmake_version" ]] || fail "cannot determine CMake version"
cmake_major="${cmake_version%%.*}"
[[ "$cmake_major" -lt 4 ]] || fail "CMake $cmake_version is unsupported; use CMake 3.x"

bison_executable="${BISON_EXECUTABLE:-}"
if [[ -z "$bison_executable" ]]; then
  if [[ -x "$env_prefix/bin/bison" ]]; then
    bison_executable="$env_prefix/bin/bison"
  else
    bison_executable="$(command -v bison || true)"
  fi
fi
[[ -n "$bison_executable" && -x "$bison_executable" ]] || fail "Bison 3.8 or newer was not found"
bison_version="$("$bison_executable" --version | sed -n '1s/.* \([0-9][0-9.]*\)$/\1/p')"
version_at_least "$bison_version" "3.8" || fail "Bison $bison_version is unsupported; use Bison 3.8 or newer"

flex_executable="${FLEX_EXECUTABLE:-}"
if [[ -z "$flex_executable" ]]; then
  if [[ -x "$env_prefix/bin/flex" ]]; then
    flex_executable="$env_prefix/bin/flex"
  else
    flex_executable="$(command -v flex || true)"
  fi
fi
[[ -n "$flex_executable" && -x "$flex_executable" ]] || fail "Flex was not found"

resolve_executable() {
  local candidate="$1"
  if [[ -z "$candidate" ]]; then
    return 1
  fi
  if [[ "$candidate" == */* ]]; then
    [[ -x "$candidate" ]] || return 1
    printf '%s\n' "$candidate"
  else
    command -v "$candidate" 2>/dev/null
  fi
}

find_compiler() {
  local candidate
  for candidate in "$@"; do
    if resolve_executable "$candidate"; then
      return 0
    fi
  done
  return 1
}

c_compiler="$(find_compiler \
  "${C_COMPILER:-}" \
  "${CC:-}" \
  "$env_prefix/bin/gcc" \
  "$env_prefix"/bin/*-gcc \
  "$env_prefix/bin/cc" \
  "$env_prefix"/bin/*-cc \
  gcc cc || true)"
cxx_compiler="$(find_compiler \
  "${CXX_COMPILER:-}" \
  "${CXX:-}" \
  "$env_prefix/bin/g++" \
  "$env_prefix"/bin/*-g++ \
  "$env_prefix/bin/c++" \
  "$env_prefix"/bin/*-c++ \
  g++ c++ || true)"
[[ -n "$c_compiler" && -x "$c_compiler" ]] || fail "C compiler was not found"
[[ -n "$cxx_compiler" && -x "$cxx_compiler" ]] || fail "C++ compiler was not found"
if ! printf '%s\n' \
    '#include <optional>' \
    'int main() { std::optional<int> value{1}; return *value - 1; }' \
    | "$cxx_compiler" -std=c++17 -x c++ -fsyntax-only - >/dev/null 2>&1; then
  fail "C++ compiler does not support the required C++17 dialect: $cxx_compiler"
fi

"$python_executable" - <<'PY' || fail "Python dependency check failed; create the documented Conda environment"
import importlib
import sys

required = (
    "torch",
    "torch_optimizer",
    "ncg_optimizer",
    "numpy",
    "scipy",
    "yaml",
    "matplotlib",
)
for name in required:
    importlib.import_module(name)
import numpy
import torch
if sys.version_info[:2] != (3, 10):
    raise SystemExit(f"Python 3.10 is required; found {sys.version.split()[0]}")
if int(numpy.__version__.split(".", 1)[0]) >= 2:
    raise SystemExit(f"NumPy < 2 is required; found {numpy.__version__}")
if torch.version.cuda is not None:
    raise SystemExit(
        f"CPU-only PyTorch is required; found CUDA build {torch.version.cuda}"
    )
if torch.cuda.is_available():
    raise SystemExit("CPU-only D3D environment unexpectedly exposes CUDA")
print(
    "[INFO][D3D-INSTALL] Python dependencies OK: "
    f"python={sys.version.split()[0]} torch={torch.__version__} "
    f"device=cpu numpy={numpy.__version__}"
)
PY

echo "[INFO][D3D-INSTALL] source=$source_dir"
echo "[INFO][D3D-INSTALL] build=$build_dir"
echo "[INFO][D3D-INSTALL] install=$install_prefix"
echo "[INFO][D3D-INSTALL] environment=$env_prefix"
echo "[INFO][D3D-INSTALL] cmake=$cmake_executable ($cmake_version)"
echo "[INFO][D3D-INSTALL] bison=$bison_executable ($bison_version)"
echo "[INFO][D3D-INSTALL] c_compiler=$c_compiler"
echo "[INFO][D3D-INSTALL] cxx_compiler=$cxx_compiler (C++17 supported)"
echo "[INFO][D3D-INSTALL] device=cpu"

if [[ "$preflight_only" -eq 1 ]]; then
  echo "[INFO][D3D-INSTALL] preflight passed"
  exit 0
fi

mkdir -p "$build_dir" "$install_prefix"
runtime_library_path="$env_prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

make_args=(
  -C "$source_dir"
  -j "$jobs"
  install
  "ENV_PREFIX=$env_prefix"
  "BUILD_DIR=$build_dir"
  "INSTALL_PREFIX=$install_prefix"
  "PYTHON_EXECUTABLE=$python_executable"
  "CMAKE=$cmake_executable"
  "C_COMPILER=$c_compiler"
  "CXX_COMPILER=$cxx_compiler"
  "BISON_EXECUTABLE=$bison_executable"
  "FLEX_EXECUTABLE=$flex_executable"
  "BUILD_ENV=env LD_LIBRARY_PATH=$runtime_library_path"
)

make "${make_args[@]}"

LD_LIBRARY_PATH="$runtime_library_path" \
PYTHONNOUSERSITE=1 \
"$python_executable" "$driver_dir/check_install.py" \
  --prefix "$install_prefix" \
  --write-manifest

echo "[INFO][D3D-INSTALL] installation complete"
