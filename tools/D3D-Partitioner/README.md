# D3D Partitioner

D3D Partitioner performs differentiable two-tier partitioning using the
D2D-Placer data model, DREAMPlace placement operators, and the
Differentiable-3D-Partitioner algorithm. It is installed and run as a
standalone tool; it is not linked into OpenROAD.

The TaiWei release exposes the existing CPU execution path only. Upstream
CUDA implementation files remain in the source tree for provenance, while the
release environment, build wrapper, and flow driver select CPU operators
deterministically.

## Source layout

```text
placer/                                  D2D flow and D3D adapter
thirdparty/DREAMPlace/                   placement engine and operators
thirdparty/Differentiable-3D-Partitioner D3D optimization algorithm
thirdparty/3d-placer/                    D2D parser/placement dependency
d3d-partition-driver/                    CPU setup, install, check, and driver
```

The source revisions used for this vendored snapshot are recorded in
`.taiwei-vendored-source.json`. Algorithm-specific runtime YAML files used by
TaiWei are maintained under
`TaiWei-Pin-3D/scripts_d3d_partition/config`; the original upstream configs are
retained here as source reference.

## Build and install

Run the independent setup from the adjacent `ORFS-Research` directory:

```bash
make -C tools/D3D-Partitioner/d3d-partition-driver setup
```

This creates a CPU-only dependency environment and uses separate generated
directories:

```text
tools/build/d3d-partitioner
tools/install/d3d-partitioner
```

The D3D setup is intentionally separate from `build_openroad`. See
`d3d-partition-driver/README.md` for individual preflight, install, and check
commands.

## TaiWei entry

The public flow entry is:

```text
make ord-tier-partition-d3d
```

The driver consumes the current TaiWei floorplan handoff and emits a
name-bearing assignment. TaiWei validates the assignment before publishing
the standard downstream `partition.txt`. The existing
`make ord-tier-partition` path remains the TritonPart implementation.
