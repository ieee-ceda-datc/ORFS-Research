# Quick Start Guide

This guide will help you get started with the Differentiable 3D Partitioner.

## Installation

```bash
# Clone the repository with submodules (includes third-party libraries like DREAMPlace)
git clone --recursive https://github.com/liW-J/Differentiable-3D-partitioner.git
cd Differentiable-3D-partitioner

# Or if you've already cloned the repository without --recursive
# git submodule update --init --recursive

# Install dependencies
pip install -r requirements.txt

# Optional: Install as a package
pip install -e .
```

## Basic Usage

### Method 1: DEF File Input

If you have a DEF (Design Exchange Format) file, use the DEF interface:

```python
from partitioner import DEFInterface

# Create interface with 2x2x2 partition grid
interface = DEFInterface(
    num_partitions_x=2,
    num_partitions_y=2,
    num_partitions_z=2
)

# Partition your design
assignments, results = interface.partition_from_file("your_design.def")

# View results
print(interface.get_partition_summary())

# Export partitioned components
partitioned_components = interface.export_partitioned_components()
```

### Method 2: Tensor Input

If you have position data as arrays (e.g., from ML pipelines), use the tensor interface:

```python
from partitioner import TensorInterface
import numpy as np

# Create interface
interface = TensorInterface(
    num_partitions_x=2,
    num_partitions_y=2,
    num_partitions_z=2,
    normalize_inputs=True  # Auto-normalize coordinates
)

# Your data: N cells with (x, y, z) positions
positions = np.array([
    [100, 200, 0],
    [150, 250, 0],
    # ... more cells
])

# Optional: cell sizes
sizes = np.array([
    [10, 10, 1],
    [15, 15, 1],
    # ... more sizes
])

# Partition
assignments, results = interface.partition_from_tensors(
    positions=positions,
    sizes=sizes
)

# View results
print(interface.get_partition_summary(results))
```

## Common Parameters

### Partition Configuration
- `num_partitions_x`: Number of partitions in X direction (width)
- `num_partitions_y`: Number of partitions in Y direction (height)
- `num_partitions_z`: Number of partitions in Z direction (layers/tiers)

Example: `(2, 2, 2)` creates 8 total partitions (2×2×2 grid)

### Optimization Options
- `use_terminal_awareness`: Consider I/O pins during partitioning (default: True)
- `optimization_mode`: Optimization objective
  - `"balanced"`: Balance cell count across partitions
  - `"wirelength"`: Minimize inter-partition wirelength (future)
  - `"area"`: Balance area across partitions (future)

## Working with Results

### Partition Assignments

The `assignments` array tells you which partition each cell belongs to:

```python
# assignments is an Nx3 array
# Each row is [ix, iy, iz] partition indices
print(assignments[0])  # e.g., [0, 1, 0] means partition (0, 1, 0)
```

### Statistics

The `results` dictionary contains detailed statistics:

```python
results = {
    'num_nodes': 100,
    'num_terminals': 10,
    'partition_statistics': {
        'total_partitions': 8,
        'cells_per_partition': {
            (0, 0, 0): 15,
            (0, 0, 1): 12,
            # ... etc
        }
    }
}
```

### ML/DL Integration

The tensor interface provides utilities for machine learning:

```python
# Get binary masks for each partition
masks = interface.get_partition_masks(assignments)
```

## Examples

Run the provided examples to see both interfaces in action:

```bash
# DEF interface example
python examples/example_def_interface.py

# Tensor interface example (includes batch processing)
python examples/example_tensor_interface.py
```

## Testing

Run the test suite to verify your installation:

```bash
python -m unittest discover tests/ -v
```

All 26 tests should pass.

## Tips

1. **Start with 2x2x1**: For 2D designs, use `num_partitions_z=1`
2. **Normalization**: Enable `normalize_inputs=True` for tensor interface to handle different coordinate scales
3. **Terminal awareness**: Keep `use_terminal_awareness=True` for better quality partitioning
4. **Batch processing**: Use `partition_batch()` for processing multiple designs efficiently

## Troubleshooting

### Issue: "Cannot find DEF file"
- Check the file path is correct
- Use absolute paths or paths relative to your working directory

### Issue: "Wrong shape for positions array"
- Positions must be Nx3 (x, y, z coordinates)
- Use `positions.reshape(-1, 3)` if needed

### Issue: "Memory issues with large designs"
- Process in batches using `partition_batch()`
- Increase partition count to reduce cells per partition

## Next Steps

- Check out the [API Documentation](README.md#api-documentation) for detailed method descriptions
- Explore the `partitioner/` source code for advanced customization
- Contribute improvements via pull requests!

## Support

For questions or issues:
- Open an issue on GitHub
- Check existing issues for solutions
- Review the examples for usage patterns
