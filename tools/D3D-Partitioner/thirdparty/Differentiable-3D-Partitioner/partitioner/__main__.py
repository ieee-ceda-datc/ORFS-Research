'''
Author: JeanneWillis hi@jeannewillis.cn
Date: 2026-02-05 16:56:01
LastEditors: JeanneWillis hi@jeannewillis.cn
LastEditTime: 2026-02-07 00:59:03
FilePath: /Differentiable-3D-Partitioner/partitioner/__main__.py
Description: Command-line entry point for the partitioner package
'''
import sys
import argparse

from partitioner import __version__


def print_version():
    """Print package version information."""
    print(f"Differentiable 3D Partitioner v{__version__}")
    print("A flexible 3D partitioner for VLSI placement")
    print("Author: JeanneWillis hi@jeannewillis.cn")


def print_help():
    """Print help information."""
    print_version()
    print("\n" + "=" * 70)
    print("Usage:")
    print("  python -m partitioner [options]")
    print("\nOptions:")
    print("  -h, --help     Show this help message")
    print("  -v, --version  Show version information")
    print("\n" + "=" * 70)
    print(
        "\nThis package provides multiple interfaces for 3D placement partitioning:"
    )
    print("  - DEF Interface: Partition designs from DEF files")
    print("  - Tensor Interface: Partition designs using tensor inputs")
    print("\nFor examples, see:")
    print("  - examples/run_partitioner.py")
    print("\n" + "=" * 70)


def main():
    """Main entry point for command-line interface."""
    parser = argparse.ArgumentParser(
        description=
        "Differentiable 3D Partitioner - VLSI placement partitioning tool",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument(
        '-v',
        '--version',
        action='version',
        version=f'Differentiable 3D Partitioner v{__version__}')

    # Parse arguments
    args = parser.parse_args()

    # If no arguments provided, show help
    if len(sys.argv) == 1:
        print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
