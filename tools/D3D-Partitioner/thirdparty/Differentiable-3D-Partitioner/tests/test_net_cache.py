import os
import sys
import unittest

import torch


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from partitioner.core.partitioner import Partitioner


class _DataCollections:

    def __init__(self, net_mask):
        self.net_mask_ignore_large_degrees = net_mask


class _DreamplaceBasic:

    def __init__(self, net_mask):
        self.data_collections = _DataCollections(net_mask)


class TestNetCache(unittest.TestCase):

    def _build_model(self, pin_counts, ignore_net_degree=None, cached_mask=None):
        pin_counts = [int(count) for count in pin_counts]
        num_nodes = 8
        num_pins = sum(pin_counts)
        starts = [0]
        for count in pin_counts:
            starts.append(starts[-1] + count)

        flat_net2pin_map = torch.arange(num_pins, dtype=torch.long)
        flat_net2pin_start_map = torch.tensor(starts, dtype=torch.long)
        pin2node_map = torch.arange(num_pins, dtype=torch.long) % num_nodes
        node_x = torch.arange(num_nodes, dtype=torch.float32)
        node_y = node_x + 1.0
        pin_pos_x = node_x[pin2node_map]
        pin_pos_y = node_y[pin2node_map]
        node_pos = torch.cat((node_x, node_y))
        config = {
            'gumbel_tau': 0.1,
            'gumbel_switch_iteration': 1000,
        }
        if ignore_net_degree is not None:
            config['ignore_net_degree'] = ignore_net_degree

        dreamplace_basic = None
        if cached_mask is not None:
            dreamplace_basic = _DreamplaceBasic(
                torch.tensor(cached_mask, dtype=torch.uint8))

        return Partitioner(
            num_nodes=num_nodes,
            flat_net2pin_map=flat_net2pin_map,
            flat_net2pin_start_map=flat_net2pin_start_map,
            pin2node_map=pin2node_map,
            pin_pos_x=pin_pos_x,
            pin_pos_y=pin_pos_y,
            node_x=node_x,
            node_y=node_y,
            node_pos=node_pos,
            node_size_x=torch.ones(num_nodes),
            node_size_y=torch.ones(num_nodes),
            dreamplace_basic=dreamplace_basic,
            config=config,
        )

    def test_default_filters_degree_100_and_uses_compact_storage(self):
        model = self._build_model([1, 2, 99, 100, 2000])

        self.assertEqual(model.ignore_net_degree, 100)
        self.assertEqual(model.valid_net_positions.tolist(), [1, 2])
        self.assertEqual(model.valid_net_pin_counts.tolist(), [2, 99])
        self.assertEqual(model.valid_net_pin_indices.dim(), 1)
        self.assertEqual(model.valid_net_pin_indices.numel(), 101)
        self.assertEqual(model.valid_net_pin_indices.dtype, torch.int32)
        self.assertFalse(hasattr(model, 'valid_net_node_indices'))
        self.assertFalse(hasattr(model, 'valid_net_segment_ids'))

    def test_mismatched_dreamplace_mask_falls_back_to_local_degrees(self):
        with self.assertLogs('partitioner.core.partitioner', level='WARNING'):
            model = self._build_model(
                [2, 3, 100], cached_mask=[1, 1, 1, 1, 1])

        self.assertEqual(model.valid_net_positions.tolist(), [0, 1])

    def test_matching_mask_cannot_reenable_invalid_or_large_nets(self):
        model = self._build_model([1, 2, 100], cached_mask=[1, 1, 1])

        self.assertEqual(model.valid_net_positions.tolist(), [1])

    def test_configured_threshold_matches_dreamplace_strict_boundary(self):
        model = self._build_model([2, 3, 4], ignore_net_degree=4)

        self.assertEqual(model.valid_net_positions.tolist(), [0, 1])

    def test_subset_gather_preserves_requested_net_order(self):
        model = self._build_model([2, 3, 4], ignore_net_degree=10)
        requested = torch.tensor([2, 0], dtype=torch.long)
        prepared = model._prepare_net_batch(requested,
                                            z=torch.arange(8).float(),
                                            include_pin_indices=True)

        self.assertEqual(prepared['valid_pin_counts'].tolist(), [4, 2])
        self.assertEqual(prepared['segment_ids'].tolist(), [0, 0, 0, 0, 1, 1])
        self.assertEqual(prepared['flat_pin_indices'].tolist(),
                         [5, 6, 7, 8, 0, 1])
        self.assertEqual(prepared['flat_node_indices'].tolist(),
                         [5, 6, 7, 0, 0, 1])


if __name__ == '__main__':
    unittest.main()
