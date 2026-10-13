"""
Unit tests for the 3D partitioner core
"""

import unittest
import numpy as np
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from partitioner.core.partitioner import Partitioner


class TestPartitioner(unittest.TestCase):
    """Test cases for Partitioner class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.partitioner = Partitioner(
            num_partitions_x=2,
            num_partitions_y=2,
            num_partitions_z=2
        )
        
    def test_initialization(self):
        """Test partitioner initialization."""
        self.assertEqual(self.partitioner.num_partitions_x, 2)
        self.assertEqual(self.partitioner.num_partitions_y, 2)
        self.assertEqual(self.partitioner.num_partitions_z, 2)
        self.assertTrue(self.partitioner.use_terminal_awareness)
        
    def test_set_cells(self):
        """Test setting cell information."""
        positions = np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]])
        
        self.partitioner.set_cells(positions)
        
        self.assertIsNotNone(self.partitioner.cell_positions)
        self.assertEqual(len(self.partitioner.cell_positions), 3)
        np.testing.assert_array_equal(self.partitioner.cell_positions, positions)
        
    def test_compute_partition_boundaries(self):
        """Test partition boundary computation."""
        positions = np.array([[0, 0, 0], [10, 10, 10]])
        self.partitioner.set_cells(positions)
        
        boundaries = self.partitioner.compute_partition_boundaries()
        
        self.assertIn('x', boundaries)
        self.assertIn('y', boundaries)
        self.assertIn('z', boundaries)
        self.assertEqual(len(boundaries['x']), 3)  # num_partitions + 1
        
    def test_assign_partitions(self):
        """Test partition assignment."""
        positions = np.array([
            [0, 0, 0],
            [1, 1, 1],
            [10, 10, 10],
            [11, 11, 11]
        ])
        self.partitioner.set_cells(positions)
        
        assignments = self.partitioner.assign_partitions()
        
        self.assertEqual(len(assignments), 4)
        self.assertEqual(assignments.shape[1], 3)  # 3D assignments
        
    def test_get_partition_cells(self):
        """Test getting cells in a partition."""
        positions = np.array([
            [0, 0, 0],
            [1, 1, 1],
            [10, 10, 10],
            [11, 11, 11]
        ])
        self.partitioner.set_cells(positions)
        self.partitioner.assign_partitions()
        
        cells = self.partitioner.get_partition_cells((0, 0, 0))
        
        self.assertIsInstance(cells, list)
        
    def test_compute_partition_statistics(self):
        """Test partition statistics computation."""
        positions = np.array([[i, i, i] for i in range(20)])
        self.partitioner.set_cells(positions)
        self.partitioner.assign_partitions()
        
        stats = self.partitioner.compute_partition_statistics()
        
        self.assertIn('total_partitions', stats)
        self.assertIn('cells_per_partition', stats)
        self.assertEqual(stats['total_partitions'], 8)
        
    def test_partition_main_interface(self):
        """Test main partition interface."""
        positions = np.array([[i, i, i] for i in range(10)])
        
        assignments, stats = self.partitioner.partition(positions)
        
        self.assertEqual(len(assignments), 10)
        self.assertIsInstance(stats, dict)
        

if __name__ == '__main__':
    unittest.main()
