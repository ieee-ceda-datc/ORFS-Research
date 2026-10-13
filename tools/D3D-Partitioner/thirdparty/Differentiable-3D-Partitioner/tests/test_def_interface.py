"""
Unit tests for the DEF interface
"""

import unittest
import numpy as np
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from partitioner.interfaces.def_interface import DEFInterface


class TestDEFInterface(unittest.TestCase):
    """Test cases for DEF Interface."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.interface = DEFInterface(
            num_partitions_x=2,
            num_partitions_y=2,
            num_partitions_z=2
        )
        
        # Sample DEF content
        self.sample_def = """
DESIGN test_design ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;

COMPONENTS 4 ;
- comp1 NAND2 + PLACED ( 1000 1000 ) N ;
- comp2 NOR2 + PLACED ( 8000 1000 ) N ;
- comp3 INV + PLACED ( 1000 8000 ) N ;
- comp4 BUF + PLACED ( 8000 8000 ) N ;
END COMPONENTS

PINS 2 ;
- in1 + NET in1 + DIRECTION INPUT + FIXED ( 0 5000 ) N ;
- out1 + NET out1 + DIRECTION OUTPUT + FIXED ( 10000 5000 ) N ;
END PINS

END DESIGN
"""
        
    def test_initialization(self):
        """Test interface initialization."""
        self.assertIsNotNone(self.interface.partitioner)
        self.assertIsNotNone(self.interface.parser)
        
    def test_partition_from_content(self):
        """Test partitioning from DEF content."""
        assignments, results = self.interface.partition_from_content(
            self.sample_def,
            use_pins_as_terminals=True
        )
        
        self.assertEqual(len(assignments), 4)
        self.assertIn('design_name', results)
        self.assertEqual(results['design_name'], 'test_design')
        self.assertEqual(results['num_components'], 4)
        self.assertEqual(results['num_pins'], 2)
        
    def test_export_partitioned_components(self):
        """Test exporting partitioned components."""
        self.interface.partition_from_content(self.sample_def)
        
        partitioned = self.interface.export_partitioned_components()
        
        self.assertIsInstance(partitioned, dict)
        # Should have some partitions with components
        total_components = sum(len(comps) for comps in partitioned.values())
        self.assertEqual(total_components, 4)
        
    def test_get_partition_summary(self):
        """Test partition summary generation."""
        self.interface.partition_from_content(self.sample_def)
        
        summary = self.interface.get_partition_summary()
        
        self.assertIsInstance(summary, str)
        self.assertIn('test_design', summary)
        

if __name__ == '__main__':
    unittest.main()
