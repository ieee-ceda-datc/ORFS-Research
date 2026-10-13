# Differentiable 3D Partitioner

Differentiable Partitioning with Placement and Terminal Awareness for Optimized Pseudo-3D Placement

A flexible 3D partitioner for VLSI placement that provides multiple interfaces for different use cases:
- **DEF Interface**: Partition designs from DEF (Design Exchange Format) files
- **Tensor Interface**: Partition designs using tensor inputs (numpy arrays) for ML/DL integration

## Features

- ✨ Multiple input interfaces (DEF files and tensors)
- 📊 Configurable partition grid (X, Y, Z dimensions)
- 🎯 Terminal-aware partitioning
- 📈 Partition statistics and visualization
- 🔄 Batch processing support
- 🤖 ML-friendly tensor operations (masks, one-hot encoding)
- 📦 Easy-to-use Python API

## Installation

The TaiWei private test snapshot already includes this project and its
recursive dependencies. From the vendored directory, install the Python
dependencies and package directly:

```bash
pip install -r requirements.txt
pip install -e .
```

## Quick Start

### Using DEF Interface

```python
from partitioner import DEFInterface

# Initialize the interface
interface = DEFInterface(
    num_partitions_x=2,
    num_partitions_y=2,
    num_partitions_z=2
)

# Partition from a DEF file
assignments, results = interface.partition_from_file("design.def")

# Print summary
print(interface.get_partition_summary())
```

### Using Tensor Interface

```python
from partitioner import TensorInterface
import numpy as np

# Initialize the interface
interface = TensorInterface(
    num_partitions_x=2,
    num_partitions_y=2,
    num_partitions_z=2,
    normalize_inputs=True
)

# Create input data
positions = np.random.rand(100, 3) * 1000  # 100 cells in 3D space
sizes = np.random.rand(100, 3) * 50        # Cell sizes

# Partition the design
assignments, results = interface.partition_from_tensors(
    positions=positions,
    sizes=sizes
)

# Print summary
print(interface.get_partition_summary(results))

# Get partition masks for ML applications
masks = interface.get_partition_masks(assignments)

# Convert to one-hot encoding
one_hot = interface.to_one_hot(assignments)
```

## Examples

Run the example scripts to see both interfaces in action:

```bash
# DEF Interface example
python examples/example_def_interface.py

# Tensor Interface example
python examples/example_tensor_interface.py
```

## API Documentation

### DEF Interface

**`DEFInterface(num_partitions_x, num_partitions_y, num_partitions_z, use_terminal_awareness, optimization_mode)`**

Interface for partitioning designs from DEF files.

**Methods:**
- `load_def(filepath)`: Load and parse a DEF file
- `partition_from_file(filepath, use_pins_as_terminals)`: Partition from a DEF file
- `partition_from_content(def_content, use_pins_as_terminals)`: Partition from DEF content string
- `export_partitioned_components()`: Get components organized by partition
- `get_partition_summary()`: Get human-readable summary

### Tensor Interface

**`TensorInterface(num_partitions_x, num_partitions_y, num_partitions_z, use_terminal_awareness, optimization_mode, normalize_inputs)`**

Interface for partitioning designs using tensor inputs.

**Methods:**
- `partition_from_tensors(positions, sizes, terminal_positions, cell_names)`: Partition from tensors
- `partition_batch(batch_positions, batch_sizes, batch_terminal_positions)`: Batch partition multiple designs
- `get_partition_masks(assignments)`: Get binary masks for each partition\
- `to_one_hot(assignments)`: Convert assignments to one-hot encoding
- `get_partition_summary(results)`: Get human-readable summary

### Core Partitioner

**`Partitioner(num_partitions_x, num_partitions_y, num_partitions_z, use_terminal_awareness, optimization_mode)`**

Core 3D partitioning engine.

**Methods:**
- `set_cells(positions, sizes, terminal_positions)`: Set cell information
- `compute_partition_boundaries()`: Compute partition boundaries
- `assign_partitions()`: Assign cells to partitions
- `get_partition_cells(partition_id)`: Get cells in a specific partition
- `compute_partition_statistics()`: Compute partition statistics
- `partition(positions, sizes, terminal_positions)`: Main partitioning interface

## Configuration Options

### Partition Grid
- `num_partitions_x`: Number of partitions in X dimension
- `num_partitions_y`: Number of partitions in Y dimension  
- `num_partitions_z`: Number of partitions in Z dimension (layers)

### Optimization
- `use_terminal_awareness`: Enable terminal-aware partitioning (default: True)
- `optimization_mode`: Optimization objective - 'balanced', 'wirelength', or 'area' (default: 'balanced')

### Tensor Interface Options
- `normalize_inputs`: Automatically normalize coordinates to [0, 1] range (default: True)

## DEF File Format

The DEF interface supports standard DEF file format. Example:

```def
DESIGN sample_design ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;

COMPONENTS 4 ;
- comp1 NAND2 + PLACED ( 1000 1000 ) N ;
- comp2 NOR2 + PLACED ( 3000 1000 ) N ;
- comp3 INV + PLACED ( 1000 3000 ) N ;
- comp4 BUF + PLACED ( 3000 3000 ) N ;
END COMPONENTS

PINS 2 ;
- in1 + NET in1 + DIRECTION INPUT + FIXED ( 0 5000 ) N ;
- out1 + NET out1 + DIRECTION OUTPUT + FIXED ( 10000 5000 ) N ;
END PINS

END DESIGN
```

## Project Structure

```
Differentiable-3D-partitioner/
├── partitioner/           # Main package
│   ├── __init__.py
│   ├── core/               # Core partitioning logic
│   │   ├── __init__.py
│   │   └── partitioner.py
│   ├── parsers/            # Input file parsers
│   │   ├── __init__.py
│   │   └── def_parser.py
│   └── interfaces/         # User-facing interfaces
│       ├── __init__.py
│       ├── def_interface.py
│       └── tensor_interface.py
├── examples/               # Example scripts
│   ├── example_def_interface.py
│   ├── example_tensor_interface.py
│   └── sample_design.def
├── tests/                  # Test suite
├── thirdparty/             # Third-party libraries
│   ├── DREAMPlace/         # GPU-accelerated VLSI placement tool
│   └── README.md           # Third-party library documentation
├── requirements.txt        # Python dependencies
├── README.md              # This file
└── LICENSE

```

## Third-Party Libraries

This project integrates third-party libraries to provide extended functionality:

### DREAMPlace
[DREAMPlace](https://github.com/limbo018/DREAMPlace) is a GPU-accelerated VLSI placement tool that can be used in conjunction with this partitioner for hierarchical placement workflows:

1. **Partition** your design using the Differentiable 3D Partitioner
2. **Place** cells within each partition using DREAMPlace for optimized results

For detailed integration instructions, see [thirdparty/README.md](thirdparty/README.md).

## Use Cases

### VLSI Design Automation
- Partition large designs for parallel placement optimization
- Multi-tier 3D IC partitioning
- Hierarchical placement preprocessing
- Integration with placement tools like DREAMPlace for complete design automation

### Machine Learning Applications
- Training data preparation for ML-based placers
- Feature extraction for placement prediction
- Partition-aware neural network architectures

### Research
- Algorithm development for 3D placement
- Partitioning strategy evaluation
- Benchmark generation

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Citation

If you use this partitioner in your research, please cite:

```bibtex
@software{differentiable_3d_partitioner,
  title = {Differentiable 3D Partitioner},
  author = {Your Name},
  year = {2026},
  url = {https://github.com/liW-J/Differentiable-3D-partitioner}
}
```

## Contact

For questions or issues, please open an issue on GitHub.
