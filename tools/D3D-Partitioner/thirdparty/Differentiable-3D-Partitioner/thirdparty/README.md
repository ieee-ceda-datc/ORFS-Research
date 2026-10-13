# Third-Party Libraries

This directory contains third-party libraries integrated into the Differentiable 3D Partitioner project.

## DREAMPlace

**Repository**: https://github.com/limbo018/DREAMPlace

**Description**: DREAMPlace is a deep learning toolkit-enabled VLSI placement tool. It provides GPU-accelerated placement algorithms for modern VLSI designs, offering significant speedups over traditional CPU-based placement tools.

### Key Features

- Deep learning toolkit-enabled VLSI placement
- GPU acceleration (30X+ speedup over CPU implementations)
- Supports both global placement and detailed placement
- Runs on both CPU and GPU
- Integrated detailed placer (ABCDPlace) with 16X speedup

### Integration

DREAMPlace is integrated as a Git submodule. To initialize and update the submodule:

```bash
# Clone the repository with submodules
git clone --recursive https://github.com/liW-J/Differentiable-3D-partitioner.git

# Or if you've already cloned the repository
git submodule update --init --recursive
```

### Building DREAMPlace

Please refer to the [DREAMPlace README](./DREAMPlace/README.md) for detailed installation and build instructions.

#### Quick Build Instructions

1. Install dependencies:
```bash
# Install Python dependencies
pip install torch numpy matplotlib

# Install system dependencies (Ubuntu/Debian)
sudo apt-get install bison flex libboost-all-dev
```

2. Build DREAMPlace:
```bash
cd thirdparty/DREAMPlace
mkdir build && cd build
cmake ..
make -j$(nproc)
```

### Usage with Differentiable 3D Partitioner

DREAMPlace can be used as a complementary tool to the Differentiable 3D Partitioner:

1. Use the **Differentiable 3D Partitioner** to partition your design into multiple regions
2. Use **DREAMPlace** to perform detailed placement within each partition

This hierarchical approach can help optimize large-scale VLSI designs by combining partitioning with advanced placement algorithms.

### Publications

DREAMPlace has been published in several prestigious conferences and journals:

- DAC 2019: "DREAMPlace: Deep Learning Toolkit-Enabled GPU Acceleration for Modern VLSI Placement"
- TCAD 2020: Enhanced version with detailed placement
- ICCAD 2020: DREAMPlace 3.0 with region constraints
- DATE 2022: DREAMPlace 4.0 with timing-driven placement

For more details, see the [DREAMPlace publications](./DREAMPlace/README.md#publications).

### License

DREAMPlace is licensed under its own terms. Please refer to the [DREAMPlace LICENSE](./DREAMPlace/LICENSE) for details.

---

## Adding New Third-Party Libraries

To add a new third-party library:

1. Add as a Git submodule:
```bash
git submodule add <repository-url> thirdparty/<library-name>
```

2. Update this README with:
   - Library name and repository link
   - Description and key features
   - Build instructions
   - Usage guidelines
   - License information
