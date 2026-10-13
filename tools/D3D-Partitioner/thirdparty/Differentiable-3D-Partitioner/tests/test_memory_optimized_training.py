import os
import sys
import unittest

import torch


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from partitioner.core.partitioner import Partitioner


class TestMemoryOptimizedTraining(unittest.TestCase):

    def _build_model(self,
                     net_chunk_size=0,
                     optimize_filler_positions=False,
                     identity_map=False):
        num_nodes = 6
        pin2node = torch.tensor([0, 1, 1, 2, 3, 3, 4, 5], dtype=torch.long)
        starts = torch.tensor([0, 2, 5, 8], dtype=torch.long)
        flat_map = None if identity_map else torch.arange(8, dtype=torch.long)
        node_x = torch.tensor([0.0, 1.0, 2.0, 4.0, 6.0, 7.0])
        node_y = torch.tensor([0.0, 2.0, 1.0, 5.0, 3.0, 6.0])
        pin_pos_x = node_x[pin2node] + 0.1
        pin_pos_y = node_y[pin2node] + 0.2

        # Two tail entries model a fixed node/filler pair.
        node_pos = torch.cat((node_x, torch.tensor([2.5, 3.5]), node_y,
                              torch.tensor([2.0, 4.0])))
        config = {
            'gumbel_tau': 0.1,
            'gumbel_switch_iteration': 1000,
            'ignore_net_degree': 100,
            'net_chunk_size': net_chunk_size,
            'optimize_filler_positions': optimize_filler_positions,
            'cutsize_handle_terminal_overlap': False,
            'balance_loss': {
                'top_threshold_factor': 0.55,
                'bottom_threshold_factor': 0.55,
                'num_bins_x': 2,
                'num_bins_y': 2,
            },
        }
        model = Partitioner(
            num_nodes=num_nodes,
            flat_net2pin_map=flat_map,
            flat_net2pin_start_map=starts,
            pin2node_map=pin2node,
            pin_pos_x=pin_pos_x,
            pin_pos_y=pin_pos_y,
            node_x=node_x,
            node_y=node_y,
            node_pos=node_pos,
            node_size_x=torch.ones(num_nodes),
            node_size_y=torch.ones(num_nodes),
            dreamplace_basic=None,
            config=config,
        )
        with torch.no_grad():
            model.t.copy_(torch.tensor([-0.3, 0.2, -0.1, 0.4, -0.2, 0.1]))
        return model

    def _objective_and_flat_grad(self, model):
        flat = torch.nn.Parameter(model.pack_nesterov_parameters())
        model.set_obj_and_grad_context(lambda_wl=1.0,
                                       lambda_cut=0.25,
                                       lambda_balance=0.1,
                                       lambda_density=0.0)
        objective, gradient = model.obj_and_grad_fn(flat)
        return objective.detach(), gradient.detach().clone()

    def test_chunked_backward_matches_full_backward(self):
        full_model = self._build_model(net_chunk_size=0)
        chunked_model = self._build_model(net_chunk_size=1)
        chunked_model.load_state_dict(full_model.state_dict())

        full_objective, full_gradient = self._objective_and_flat_grad(full_model)
        chunk_objective, chunk_gradient = self._objective_and_flat_grad(
            chunked_model)

        torch.testing.assert_close(chunk_objective, full_objective)
        torch.testing.assert_close(chunk_gradient,
                                   full_gradient,
                                   rtol=2e-5,
                                   atol=2e-5)

    def test_chunked_public_backward_matches_standard_backward(self):
        full_model = self._build_model(net_chunk_size=0)
        chunked_model = self._build_model(net_chunk_size=1)
        chunked_model.load_state_dict(full_model.state_dict())

        full_loss = full_model(lambda_wl=1.0,
                               lambda_cut=0.25,
                               lambda_balance=0.1)
        full_loss.backward()
        full_grads = {
            name: parameter.grad.detach().clone()
            for name, parameter in full_model._nesterov_param_specs
        }

        chunked_loss = chunked_model.backward_objective_in_net_chunks(
            lambda_wl=1.0, lambda_cut=0.25, lambda_balance=0.1)
        torch.testing.assert_close(chunked_loss, full_loss.detach())
        for name, parameter in chunked_model._nesterov_param_specs:
            torch.testing.assert_close(parameter.grad,
                                       full_grads[name],
                                       rtol=2e-5,
                                       atol=2e-5)

    def test_frozen_tail_is_not_in_optimizer_vector(self):
        frozen_model = self._build_model(optimize_filler_positions=False)
        trainable_tail_model = self._build_model(
            optimize_filler_positions=True)

        frozen_names = [name for name, _ in frozen_model._nesterov_param_specs]
        trainable_names = [
            name for name, _ in trainable_tail_model._nesterov_param_specs
        ]
        self.assertNotIn('x_tail', frozen_names)
        self.assertNotIn('y_tail', frozen_names)
        self.assertIn('x_tail', trainable_names)
        self.assertIn('y_tail', trainable_names)
        self.assertEqual(trainable_tail_model._nesterov_numel -
                         frozen_model._nesterov_numel, 4)

    def test_identity_flat_map_matches_explicit_map(self):
        explicit_model = self._build_model(identity_map=False)
        identity_model = self._build_model(identity_map=True)
        identity_model.load_state_dict(explicit_model.state_dict(),
                                       strict=False)
        z = explicit_model.get_z().detach()
        explicit = explicit_model.compute_hpwl_batch(
            explicit_model.all_net_indices, z=z)
        identity = identity_model.compute_hpwl_batch(
            identity_model.all_net_indices, z=z)
        torch.testing.assert_close(identity[0], explicit[0])
        torch.testing.assert_close(identity[1], explicit[1])


if __name__ == '__main__':
    unittest.main()
