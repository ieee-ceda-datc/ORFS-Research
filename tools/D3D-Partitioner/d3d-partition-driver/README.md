# D3D Partitioner CPU driver

This directory is the build and runtime boundary for the standalone TaiWei
D3D Partitioner. It builds the vendored D2D, DREAMPlace, and Differentiable
3D Partitioner sources without linking them into OpenROAD.

The released path is CPU-only. The build keeps the upstream CUDA source code
but selects existing CPU operators, uses CPU-only PyTorch, and validates that
installed extensions do not link CUDA libraries.

## Setup

From `ORFS-Research`:

```bash
make -C tools/D3D-Partitioner/d3d-partition-driver setup
```

The command creates the default environment below
`.conda/taiwei-d3d-cpu`, then builds and installs into:

```text
tools/build/d3d-partitioner
tools/install/d3d-partitioner
```

Conda, Mamba, or Micromamba must already be available. Use
`CONDA_EXE=/path/to/executable`
when it is not on `PATH`, `SETUP_ENV_PREFIX=/path/to/env` to select another
environment, and `UPDATE_ENV=1` to synchronize an existing environment with
`environment-cpu.yml`.

The setup script is independent of `build_openroad`; OpenROAD does not need
to be rebuilt to install this tool.

## Separate build steps

The same process can be run stage by stage:

```bash
make -C tools/D3D-Partitioner/d3d-partition-driver preflight \
  ENV_PREFIX=/path/to/cpu/env

make -C tools/D3D-Partitioner/d3d-partition-driver install \
  ENV_PREFIX=/path/to/cpu/env \
  JOBS="$(nproc)"

make -C tools/D3D-Partitioner/d3d-partition-driver check \
  ENV_PREFIX=/path/to/cpu/env
```

`SOURCE_DIR`, `BUILD_DIR`, `INSTALL_PREFIX`, compiler paths, Bison, Flex, and
CMake may be overridden. Defaults are derived from the driver location; no
developer-machine path is embedded in the scripts.

## Runtime contract

`run_partition.py` accepts the TaiWei D3D YAML, LEF files, and the current
DEF/Verilog/SDC handoff. It combines these with the internal D2D CPU defaults,
applies the YAML's optional design-specific `d2d` bin-grid override, fixes
`partitioner=d3d` and `gpu=0`, then writes the temporary D2D JSON only
inside the stage runtime directory. The output is an atomic, name-bearing
assignment JSON. TaiWei's `scripts_d3d_partition` layer validates that
assignment and publishes the final `partition.txt`.
