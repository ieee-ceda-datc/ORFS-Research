"""
Unit tests for the DEF parser
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from partitioner.parsers.def_parser import DEFParser


class TestDEFParser(unittest.TestCase):
    """Test cases for DEF Parser."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = DEFParser()
        
        self.sample_def = """
DESIGN test_design ;
UNITS DISTANCE MICRONS 2000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;

COMPONENTS 3 ;
- comp1 NAND2 + PLACED ( 1000 1000 ) N ;
- comp2 NOR2 + PLACED ( 5000 5000 ) N ;
- comp3 INV + FIXED ( 9000 9000 ) N ;
END COMPONENTS

PINS 2 ;
- in1 + NET in1 + DIRECTION INPUT + FIXED ( 0 5000 ) N ;
- out1 + NET out1 + DIRECTION OUTPUT + FIXED ( 10000 5000 ) N ;
END PINS

END DESIGN
"""
        
    def test_parse_content(self):
        """Test parsing DEF content."""
        data = self.parser.parse_content(self.sample_def)
        
        self.assertEqual(data['design_name'], 'test_design')
        self.assertEqual(data['units'], 2000)
        self.assertEqual(len(data['components']), 3)
        self.assertEqual(len(data['pins']), 2)
        
    def test_parse_die_area(self):
        """Test parsing die area."""
        self.parser.parse_content(self.sample_def)
        
        self.assertIsNotNone(self.parser.die_area)
        self.assertEqual(self.parser.die_area['lower_left'], (0, 0))
        self.assertEqual(self.parser.die_area['upper_right'], (10000, 10000))
        
    def test_parse_components(self):
        """Test parsing components."""
        data = self.parser.parse_content(self.sample_def)
        
        components = data['components']
        self.assertEqual(len(components), 3)
        
        # Check first component
        comp1 = components[0]
        self.assertEqual(comp1['name'], 'comp1')
        self.assertEqual(comp1['cell_type'], 'NAND2')
        self.assertEqual(comp1['position'], (1000, 1000))
        self.assertEqual(comp1['status'], 'PLACED')
        
    def test_parse_pins(self):
        """Test parsing pins."""
        data = self.parser.parse_content(self.sample_def)
        
        pins = data['pins']
        self.assertEqual(len(pins), 2)
        
        # Check first pin
        pin1 = pins[0]
        self.assertEqual(pin1['name'], 'in1')
        self.assertEqual(pin1['net'], 'in1')
        self.assertEqual(pin1['direction'], 'INPUT')
        
    def test_get_component_positions(self):
        """Test extracting component positions."""
        self.parser.parse_content(self.sample_def)
        
        positions = self.parser.get_component_positions()
        
        self.assertEqual(len(positions), 3)
        self.assertEqual(positions.shape[1], 3)  # 3D positions
        
    def test_get_pin_positions(self):
        """Test extracting pin positions."""
        self.parser.parse_content(self.sample_def)
        
        positions = self.parser.get_pin_positions()
        
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions.shape[1], 3)  # 3D positions
        
    def test_estimate_component_sizes(self):
        """Test component size estimation."""
        self.parser.parse_content(self.sample_def)
        
        sizes = self.parser.estimate_component_sizes()
        
        self.assertEqual(len(sizes), 3)
        self.assertEqual(sizes.shape[1], 3)  # 3D sizes
        

if __name__ == '__main__':
    unittest.main()
