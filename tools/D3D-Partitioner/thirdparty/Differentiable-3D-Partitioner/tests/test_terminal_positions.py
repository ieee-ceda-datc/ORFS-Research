import os
import sys
import unittest

import torch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from partitioner.core.partitioner import Partitioner


class TestTerminalPositions(unittest.TestCase):

    def _build_model(self, pin_pos_x, pin_pos_y):
        num_nodes = pin_pos_x.numel()
        flat_net2pin_map = torch.arange(num_nodes, dtype=torch.long)
        flat_net2pin_start_map = torch.tensor([0, num_nodes], dtype=torch.long)
        pin2node_map = torch.arange(num_nodes, dtype=torch.long)
        node_x = pin_pos_x.clone()
        node_y = pin_pos_y.clone()
        node_pos = torch.cat((node_x, node_y))
        node_size_x = torch.ones(num_nodes)
        node_size_y = torch.ones(num_nodes)
        config = {
            'gumbel_tau': 0.1,
            'gumbel_switch_iteration': 1000,
        }
        return Partitioner(num_nodes=num_nodes,
                           flat_net2pin_map=flat_net2pin_map,
                           flat_net2pin_start_map=flat_net2pin_start_map,
                           pin2node_map=pin2node_map,
                           pin_pos_x=pin_pos_x,
                           pin_pos_y=pin_pos_y,
                           node_x=node_x,
                           node_y=node_y,
                           node_pos=node_pos,
                           node_size_x=node_size_x,
                           node_size_y=node_size_y,
                           config=config)

    def test_terminal_uses_intersection_box_center(self):
        pin_pos_x = torch.tensor([0.0, 10.0, 8.0, 12.0])
        pin_pos_y = torch.tensor([0.0, 4.0, 2.0, 6.0])
        model = self._build_model(pin_pos_x, pin_pos_y)
        net_indices = torch.tensor([0], dtype=torch.long)
        binary_z = torch.tensor([1.0, 1.0, 0.0, 0.0])

        terminal_positions, cut_mask = model.compute_terminal_positions(
            net_indices, z=binary_z, pin_pos_x=pin_pos_x, pin_pos_y=pin_pos_y)

        self.assertTrue(cut_mask[0].item())
        self.assertAlmostEqual(terminal_positions[0, 0].item(), 9.0)
        self.assertAlmostEqual(terminal_positions[0, 1].item(), 3.0)

    def test_half_assigned_net_is_not_marked_cut(self):
        pin_pos_x = torch.tensor([1.0, 3.0])
        pin_pos_y = torch.tensor([2.0, 4.0])
        model = self._build_model(pin_pos_x, pin_pos_y)
        net_indices = torch.tensor([0], dtype=torch.long)
        ambiguous_z = torch.tensor([0.5, 0.5])

        terminal_positions, cut_mask = model.compute_terminal_positions(
            net_indices,
            z=ambiguous_z,
            pin_pos_x=pin_pos_x,
            pin_pos_y=pin_pos_y)

        self.assertFalse(cut_mask[0].item())
        self.assertTrue(torch.isnan(terminal_positions[0]).all().item())


if __name__ == '__main__':
    unittest.main()
