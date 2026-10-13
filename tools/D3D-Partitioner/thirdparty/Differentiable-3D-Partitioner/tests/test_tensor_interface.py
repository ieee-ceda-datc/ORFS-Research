'''
Author: JeanneWillis hi@jeannewillis.cn
Date: 2026-02-05 16:56:01
LastEditors: JeanneWillis hi@jeannewillis.cn
LastEditTime: 2026-02-06 21:07:17
FilePath: /Differentiable-3D-Partitioner/tests/test_tensor_interface.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
"""
Unit tests for the Tensor interface
"""

import unittest
import numpy as np
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from partitioner.interfaces.tensor_interface import TensorInterface


class TestTensorInterface(unittest.TestCase):
    """Test cases for Tensor Interface."""

    def setUp(self):
        """Set up test fixtures."""
        self.interface = TensorInterface(num_partitions_x=2,
                                         num_partitions_y=2,
                                         num_partitions_z=2,
                                         normalize_inputs=True)

        np.random.seed(42)

    def test_initialization(self):
        """Test interface initialization."""
        self.assertIsNotNone(self.interface.partitioner)
        self.assertTrue(self.interface.normalize_inputs)

    def test_partition_from_tensors(self):
        """Test partitioning from tensor inputs."""
        positions = np.random.rand(20, 3) * 1000
        sizes = np.random.rand(20, 3) * 50

        assignments, results = self.interface.partition_from_tensors(
            positions=positions, sizes=sizes)

        self.assertEqual(len(assignments), 20)
        self.assertIn('num_nodes', results)
        self.assertEqual(results['num_nodes'], 20)

    def test_partition_with_terminals(self):
        """Test partitioning with terminal awareness."""
        positions = np.random.rand(10, 3) * 1000
        terminal_positions = np.array([[0, 500, 0], [1000, 500, 0]])

        assignments, results = self.interface.partition_from_tensors(
            positions=positions, terminal_positions=terminal_positions)

        self.assertEqual(results['num_terminals'], 2)

    def test_normalization(self):
        """Test coordinate normalization."""
        positions = np.array([[0, 0, 0], [1000, 1000, 1000]])

        assignments, results = self.interface.partition_from_tensors(positions)

        self.assertIsNotNone(results['normalization_params'])
        self.assertIn('min', results['normalization_params'])
        self.assertIn('max', results['normalization_params'])


if __name__ == '__main__':
    unittest.main()
