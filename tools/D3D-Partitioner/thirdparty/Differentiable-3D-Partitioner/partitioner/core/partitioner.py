'''
Author: JeanneWillis hi@jeannewillis.cn
Date: 2026-02-05 16:56:01
LastEditors: JeanneWillis hi@jeannewillis.cn
LastEditTime: 2026-02-28 18:29:24
FilePath: /Differentiable-3D-Partitioner/partitioner/core/partitioner.py
Description: 3D Partitioner Core Implementation
Implements differentiable partitioning with placement and terminal awareness
for optimized pseudo-3D placement.
'''
import logging
import os

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn

COORD_EPSILON = 1e-2
DEFAULT_IGNORE_NET_DEGREE = 100

logger = logging.getLogger(__name__)


class Partitioner(nn.Module):
    """
    Differentiable 3D Partitioner based on LogSumExp soft bounding box

    Features:
    1. Mapping trainable pre-activation variable t_i to soft assignment z_i = sigmoid(t_i)
    2. Using LSE soft bounding box to compute HPWL of top and bottom layers
    3. Computing gradient of total HPWL with respect to t, supporting end-to-end training
    4. Support differentiable cutsize loss based on Snake-3D, used to reduce cross-layer connections
    """

    def __init__(self,
                 num_nodes,
                 flat_net2pin_map,
                 flat_net2pin_start_map,
                 pin2node_map,
                 pin_pos_x,
                 pin_pos_y,
                 node_x,
                 node_y,
                 node_pos,
                 node_size_x,
                 node_size_y,
                 alpha=1.0,
                 net_weights=None,
                 gumbel_tau=0.1,
                 dreamplace_basic=None,
                 config=None,
                 die_xl=None,
                 die_xh=None,
                 die_yl=None,
                 die_yh=None):
        """
        initialize LSE partitioner

        Args:
            num_nodes: number of cells (nodes)
            flat_net2pin_map: flat net to pin mapping, shape [num_pins] tensor
            flat_net2pin_start_map: start index of each net in flat_net2pin_map, shape [num_nets+1] tensor
            pin2node_map: pin to node mapping, shape [num_pins] tensor
            pin_pos_x: x coordinates of pins, shape [num_pins] tensor
            pin_pos_y: y coordinates of pins, shape [num_pins] tensor
            alpha: LSE smoothing parameter, larger means harder to be 0 or 1
            net_weights: optional net weights, shape [num_nets] tensor
            gumbel_tau: Gumbel Softmax temperature parameter, controlling the smoothness of softmax (default 0.1)
                        smaller tau means results closer to discrete distribution; larger tau means smoother distribution
                        if config is provided, this will be overridden by config['partitioner'].get('gumbel_tau', 0.1)
            config: optional configuration dictionary or path to YAML config file
                    if provided, will override alpha and gumbel_tau from config
        """
        super(Partitioner, self).__init__()

        # Load configuration if provided
        if config is None:
            raise ValueError("config is required")

        self.config = config

        self.num_nodes = num_nodes
        self.num_nets = flat_net2pin_start_map.numel() - 1

        # Register fixed data structures without cloning an already compatible
        # tensor.  The flow owns these immutable tensors for the lifetime of
        # the model, so cloning every 10M-entry pin map only wastes memory.
        self.flat_net2pin_is_identity = flat_net2pin_map is None
        self.register_buffer(
            'flat_net2pin_map',
            None if flat_net2pin_map is None else
            flat_net2pin_map.detach().to(dtype=torch.long))
        self.register_buffer(
            'flat_net2pin_start_map',
            flat_net2pin_start_map.detach().to(dtype=torch.long))
        self.register_buffer('pin2node_map',
                             pin2node_map.detach().to(dtype=torch.long))
        # Pin position = node position + pin_offset; store offset for x,y,z co-optimization
        node_x_clone = node_x.detach().clone()
        node_y_clone = node_y.detach().clone()
        pin_offset_x = (pin_pos_x.detach().clone() -
                        node_x_clone[self.pin2node_map])
        pin_offset_y = (pin_pos_y.detach().clone() -
                        node_y_clone[self.pin2node_map])
        self.register_buffer('pin_offset_x', pin_offset_x)
        self.register_buffer('pin_offset_y', pin_offset_y)
        # node_x, node_y as optimization variables (no sigmoid), co-optimized with z
        self.node_x = nn.Parameter(node_x_clone)
        self.node_y = nn.Parameter(node_y_clone)
        self.register_buffer('node_size_x', node_size_x.detach())
        self.register_buffer('node_size_y', node_size_y.detach())

        self.dreamplace_basic = dreamplace_basic

        x_tail_clone = node_pos[num_nodes:node_pos.numel() // 2].detach().clone()
        y_tail_clone = node_pos[node_pos.numel() // 2 + num_nodes:].detach().clone()
        # DREAMPlace tails are fixed nodes followed by fillers.  Keeping all
        # of them in the Nesterov vector multiplies their storage by optimizer
        # state and gradient copies.  They still participate in density when
        # frozen; only their coordinates stop being optimized.
        self.optimize_filler_positions = bool(
            config.get('optimize_filler_positions', False))
        if self.optimize_filler_positions:
            self.x_tail = nn.Parameter(x_tail_clone)
            self.y_tail = nn.Parameter(y_tail_clone)
        else:
            self.register_buffer('x_tail', x_tail_clone)
            self.register_buffer('y_tail', y_tail_clone)

        # trainable pre-activation variable t_i (one for each cell)
        # use small random initialization to avoid all z being 0.5 (symmetric point)
        t = torch.randn(num_nodes) * 0.01
        # t = torch.ones(num_nodes) * 10
        self.t = nn.Parameter(t)
        self.t_min = -10.0
        self.t_max = 10.0
        self.clamp_t_()

        nesterov_param_specs = [('node_x', self.node_x)]
        if self.optimize_filler_positions:
            nesterov_param_specs.append(('x_tail', self.x_tail))
        nesterov_param_specs.append(('node_y', self.node_y))
        if self.optimize_filler_positions:
            nesterov_param_specs.append(('y_tail', self.y_tail))
        nesterov_param_specs.append(('t', self.t))
        self._nesterov_param_specs = tuple(nesterov_param_specs)
        self._nesterov_param_slices = {}
        offset = 0
        for name, param in self._nesterov_param_specs:
            next_offset = offset + param.numel()
            self._nesterov_param_slices[name] = slice(offset, next_offset)
            offset = next_offset
        self._nesterov_numel = offset
        self._obj_and_grad_kwargs = {
            'lambda_wl': 1.0,
            'lambda_cut': 0.0,
            'lambda_balance': 0.0,
            'lambda_density': 0.0,
            'selected_nets': None,
            'cutsize_net_weights': None,
        }
        self.net_chunk_size = int(config.get('net_chunk_size', 0) or 0)
        if self.net_chunk_size < 0:
            raise ValueError("net_chunk_size must be non-negative")
        self.cutsize_handle_terminal_overlap = bool(
            config.get('cutsize_handle_terminal_overlap', True))
        self._last_loss_components = None

        # initial_values
        # LSE smoothing parameter
        self.alpha = alpha

        # Gumbel-Softmax temperature schedule.
        # By default, keep backward compatibility with existing configs by
        # treating gumbel_tau as the final temperature and annealing from a
        # smoother starting point.
        self.gumbel_tau = float(config['gumbel_tau'])
        self.gumbel_tau_start = float(
            config.get('gumbel_tau_start', max(1.0, self.gumbel_tau)))
        self.gumbel_tau_min = float(
            config.get('gumbel_tau_min', self.gumbel_tau))
        self.gumbel_switch_iteration = int(config['gumbel_switch_iteration'])
        self.gumbel_total_iterations = int(
            config.get('gumbel_total_iterations',
                       self.gumbel_switch_iteration + 1))
        self.gumbel_anneal_iterations = int(
            config.get(
                'gumbel_anneal_iterations',
                max(1, self.gumbel_total_iterations -
                    self.gumbel_switch_iteration)))
        self.gumbel_anneal_mode = config.get('gumbel_anneal_mode',
                                             'exponential')
        if self.gumbel_tau_start <= 0 or self.gumbel_tau_min <= 0:
            raise ValueError("Gumbel temperatures must be positive")
        if self.gumbel_tau_start < self.gumbel_tau_min:
            raise ValueError(
                "gumbel_tau_start must be greater than or equal to "
                "gumbel_tau_min")
        if self.gumbel_anneal_mode not in ('exponential', 'linear'):
            raise ValueError("gumbel_anneal_mode must be 'exponential' or 'linear'")

        # Current iteration counter (used to switch between sigmoid and gumbel_softmax)
        self.current_iteration = 0
        self.cutsize_overlap_update_interval = int(
            config.get('cutsize_overlap_update_interval', 10))
        if self.cutsize_overlap_update_interval <= 0:
            raise ValueError("cutsize_overlap_update_interval must be positive")
        self._cached_overlap_mask = None
        self._cached_overlap_iteration = None
        self._cached_overlap_threshold = None

        # Slow down z optimization early so x/y can stabilize macro placement
        # before the layer assignment becomes too decisive.
        self.t_grad_scale_start = float(config.get('t_grad_scale_start', 0.000002))
        self.t_grad_scale_end = float(config.get('t_grad_scale_end', 1.0))
        self.t_grad_warmup_end = int(config.get('t_grad_warmup_end', 500))
        self.t_grad_ramp_end = int(config.get('t_grad_ramp_end', 2000))
        if self.t_grad_scale_start <= 0.0:
            raise ValueError("t_grad_scale_start must be positive")
        if self.t_grad_scale_end <= 0.0:
            raise ValueError("t_grad_scale_end must be positive")
        if self.t_grad_warmup_end < 0:
            raise ValueError("t_grad_warmup_end must be non-negative")
        if self.t_grad_ramp_end < self.t_grad_warmup_end:
            raise ValueError(
                "t_grad_ramp_end must be greater than or equal to "
                "t_grad_warmup_end")

        # net weights (if not provided, default to all 1)
        if net_weights is None:
            self.register_buffer('net_weights', torch.ones(self.num_nets))
        else:
            self.register_buffer('net_weights', net_weights.detach().clone())

        # Die dimensions for fixed HPWL normalization constants
        if die_xl is not None and die_xh is not None:
            self.die_xl_val = float(die_xl)
            self.die_x_length = float(die_xh) - float(die_xl)
        else:
            self.die_xl_val = None
            self.die_x_length = None
        if die_yl is not None and die_yh is not None:
            self.die_yl_val = float(die_yl)
            self.die_y_length = float(die_yh) - float(die_yl)
        else:
            self.die_yl_val = None
            self.die_y_length = None

        self._build_net_cache()

    def _build_net_cache(self):
        """Precompute a compact cache for nets used by the loss functions.

        The cache intentionally uses a CSR-like one-dimensional layout.  A
        padded ``[num_nets, max_degree]`` tensor is unsafe here: one clock or
        power net can make ``max_degree`` enormous even though almost every
        other net is small.
        """
        self.register_buffer(
            'all_net_indices',
            torch.arange(self.num_nets,
                         device=self.flat_net2pin_start_map.device,
                         dtype=torch.long))
        start_indices = self.flat_net2pin_start_map[:-1]
        end_indices = self.flat_net2pin_start_map[1:]
        pin_counts = end_indices - start_indices
        valid_net_mask = pin_counts >= 2

        # Match DREAMPlace's default: only nets with degree strictly below the
        # threshold participate in wirelength-related calculations.  Keep a
        # local fallback because a D2D movable-only graph has a different net
        # count from DREAMPlace's original graph and its cached mask therefore
        # cannot be applied by position.
        ignore_net_degree = self.config.get('ignore_net_degree',
                                            DEFAULT_IGNORE_NET_DEGREE)
        if ignore_net_degree is None:
            ignore_net_degree = DEFAULT_IGNORE_NET_DEGREE
        try:
            ignore_net_degree = int(ignore_net_degree)
        except (TypeError, ValueError) as exc:
            raise ValueError("ignore_net_degree must be an integer") from exc
        if ignore_net_degree < 2:
            raise ValueError("ignore_net_degree must be at least 2")
        self.ignore_net_degree = ignore_net_degree
        valid_net_mask = valid_net_mask & (pin_counts < ignore_net_degree)

        # Reuse DREAMPlace's mask only when it describes this exact net list.
        # Even in that case, retain the local degree check above as a safety
        # invariant and to preserve the >=2-pin condition.
        data_collections = getattr(self.dreamplace_basic, 'data_collections',
                                   None)
        cached_net_mask = getattr(data_collections,
                                  'net_mask_ignore_large_degrees', None)
        if cached_net_mask is not None:
            cached_net_mask = cached_net_mask.reshape(-1)
            if cached_net_mask.numel() == self.num_nets:
                valid_net_mask = valid_net_mask & cached_net_mask.to(
                    device=pin_counts.device, dtype=torch.bool)
            else:
                logger.warning(
                    "Ignoring DREAMPlace large-net mask with %d entries for "
                    "a local graph with %d nets; applying local "
                    "ignore_net_degree=%d filtering instead",
                    cached_net_mask.numel(), self.num_nets,
                    ignore_net_degree)
        valid_net_positions = torch.nonzero(valid_net_mask, as_tuple=True)[0]
        max_cache_index = max(
            self.num_nets,
            int(self.flat_net2pin_start_map[-1].item()), self.num_nodes)
        cache_index_dtype = (torch.int32 if max_cache_index < 2**31 else
                             torch.int64)

        self.register_buffer('pin_counts', pin_counts.to(cache_index_dtype))
        self.register_buffer('valid_net_mask', valid_net_mask)
        self.register_buffer('valid_net_positions',
                             valid_net_positions.to(cache_index_dtype))

        net_to_valid_row = torch.full((self.num_nets, ),
                                      -1,
                                      device=pin_counts.device,
                                      dtype=cache_index_dtype)

        if valid_net_positions.numel() == 0:
            self.register_buffer('net_to_valid_row', net_to_valid_row)
            self.register_buffer(
                'valid_net_pin_counts',
                torch.empty(0,
                            device=pin_counts.device,
                            dtype=cache_index_dtype))
            self.register_buffer(
                'valid_net_pin_start_map',
                torch.zeros(1,
                            device=pin_counts.device,
                            dtype=cache_index_dtype))
            self.register_buffer(
                'valid_net_pin_indices',
                torch.empty(0,
                            device=pin_counts.device,
                            dtype=cache_index_dtype))
            return

        valid_pin_counts = pin_counts[valid_net_mask]
        valid_start_indices = start_indices[valid_net_mask]
        valid_net_pin_start_map = torch.cat((
            torch.zeros(1, device=pin_counts.device, dtype=torch.long),
            torch.cumsum(valid_pin_counts, dim=0),
        ))
        total_valid_pins = int(valid_net_pin_start_map[-1].item())
        valid_net_segment_ids = torch.repeat_interleave(
            torch.arange(valid_net_positions.numel(),
                         device=pin_counts.device,
                         dtype=torch.long), valid_pin_counts)

        # Map compact cache offsets back into the original flat net-to-pin map.
        # Every temporary below is O(total valid pins), never
        # O(num_valid_nets * maximum_net_degree).
        flat_pin_indices = torch.arange(
            total_valid_pins, device=pin_counts.device, dtype=torch.long)
        flat_pin_indices = flat_pin_indices + (
            valid_start_indices - valid_net_pin_start_map[:-1]
        )[valid_net_segment_ids]
        if self.flat_net2pin_is_identity:
            valid_net_pin_indices = flat_pin_indices
        else:
            valid_net_pin_indices = self.flat_net2pin_map[flat_pin_indices]

        net_to_valid_row[valid_net_positions] = torch.arange(
            valid_net_positions.numel(),
            device=pin_counts.device,
            dtype=cache_index_dtype)

        self.register_buffer('net_to_valid_row', net_to_valid_row)
        self.register_buffer('valid_net_pin_counts',
                             valid_pin_counts.to(cache_index_dtype))
        self.register_buffer('valid_net_pin_start_map',
                             valid_net_pin_start_map.to(cache_index_dtype))
        self.register_buffer('valid_net_pin_indices',
                             valid_net_pin_indices.to(cache_index_dtype))

    def get_trainable_parameters(self):
        return [param for _, param in self._nesterov_param_specs]

    def _split_nesterov_tensor(self, flat_tensor):
        if flat_tensor.numel() != self._nesterov_numel:
            raise ValueError(
                f"Expected flat tensor with {self._nesterov_numel} elements, "
                f"but got {flat_tensor.numel()}")

        return {
            name: flat_tensor[self._nesterov_param_slices[name]].view_as(param)
            for name, param in self._nesterov_param_specs
        }

    def pack_nesterov_parameters(self):
        return torch.cat([
            param.detach().reshape(-1) for _, param in self._nesterov_param_specs
        ])

    def clamp_t_(self):
        with torch.no_grad():
            self.t.clamp_(self.t_min, self.t_max)

    def clamp_t_in_flat_tensor_(self, flat_tensor):
        with torch.no_grad():
            flat_tensor[self._nesterov_param_slices['t']].clamp_(self.t_min,
                                                                 self.t_max)

    def sync_from_nesterov_tensor(self, flat_tensor):
        self.clamp_t_in_flat_tensor_(flat_tensor)
        split_tensors = self._split_nesterov_tensor(flat_tensor)
        with torch.no_grad():
            for name, param in self._nesterov_param_specs:
                param.copy_(split_tensors[name])
        self.clamp_t_()

    def sync_to_nesterov_tensor(self, flat_tensor):
        with torch.no_grad():
            self.clamp_t_()
            flat_tensor.copy_(self.pack_nesterov_parameters().to(flat_tensor.device))
        self.clamp_t_in_flat_tensor_(flat_tensor)

    def set_obj_and_grad_context(self,
                                 lambda_wl=1.0,
                                 lambda_cut=0.0,
                                 lambda_balance=0.0,
                                 lambda_density=0.0,
                                 selected_nets=None,
                                 cutsize_net_weights=None):
        self._obj_and_grad_kwargs = {
            'lambda_wl': lambda_wl,
            'lambda_cut': lambda_cut,
            'lambda_balance': lambda_balance,
            'lambda_density': lambda_density,
            'selected_nets': selected_nets,
            'cutsize_net_weights': cutsize_net_weights,
        }

    def nesterov_constraint_fn(self, flat_tensor):
        move_boundary_op = getattr(
            getattr(self.dreamplace_basic, 'op_collections', None),
            'move_boundary_op', None)
        with torch.no_grad():
            if move_boundary_op is not None:
                split_tensors = self._split_nesterov_tensor(flat_tensor)
                node_x = split_tensors['node_x']
                node_y = split_tensors['node_y']
                x_tail = split_tensors.get('x_tail', self.x_tail)
                y_tail = split_tensors.get('y_tail', self.y_tail)
                density_pos = torch.cat([
                    node_x.reshape(-1),
                    x_tail.reshape(-1),
                    node_y.reshape(-1),
                    y_tail.reshape(-1),
                ],
                                        dim=0)
                move_boundary_op(density_pos)

                node_x_numel = self.node_x.numel()
                x_tail_numel = self.x_tail.numel()
                node_y_numel = self.node_y.numel()

                flat_tensor[self._nesterov_param_slices['node_x']].copy_(
                    density_pos[:node_x_numel])
                flat_tensor[self._nesterov_param_slices['node_y']].copy_(
                    density_pos[node_x_numel + x_tail_numel:node_x_numel +
                                x_tail_numel + node_y_numel])
                if self.optimize_filler_positions:
                    flat_tensor[self._nesterov_param_slices['x_tail']].copy_(
                        density_pos[node_x_numel:node_x_numel + x_tail_numel])
                    flat_tensor[self._nesterov_param_slices['y_tail']].copy_(
                        density_pos[node_x_numel + x_tail_numel +
                                    node_y_numel:])
            self.clamp_t_in_flat_tensor_(flat_tensor)
        return flat_tensor

    def obj_and_grad_fn(self, flat_tensor):
        if flat_tensor.grad is not None:
            flat_tensor.grad.zero_()

        self.sync_from_nesterov_tensor(flat_tensor)

        for _, param in self._nesterov_param_specs:
            if param.grad is not None:
                param.grad.zero_()

        if (self.net_chunk_size > 0 and
                self._obj_and_grad_kwargs['selected_nets'] is None):
            obj = self.backward_objective_in_net_chunks(
                lambda_wl=self._obj_and_grad_kwargs['lambda_wl'],
                lambda_cut=self._obj_and_grad_kwargs['lambda_cut'],
                lambda_balance=self._obj_and_grad_kwargs['lambda_balance'],
                lambda_density=self._obj_and_grad_kwargs['lambda_density'],
                cutsize_net_weights=self._obj_and_grad_kwargs[
                    'cutsize_net_weights'])
        else:
            obj = self(lambda_wl=self._obj_and_grad_kwargs['lambda_wl'],
                       lambda_cut=self._obj_and_grad_kwargs['lambda_cut'],
                       lambda_balance=self._obj_and_grad_kwargs[
                           'lambda_balance'],
                       lambda_density=self._obj_and_grad_kwargs[
                           'lambda_density'],
                       selected_nets=self._obj_and_grad_kwargs[
                           'selected_nets'],
                       cutsize_net_weights=self._obj_and_grad_kwargs[
                           'cutsize_net_weights'])

            if obj.requires_grad:
                obj.backward()

        self.scale_t_grad_()

        flat_grad = torch.cat([
            (param.grad if param.grad is not None else torch.zeros_like(param)).
            reshape(-1) for _, param in self._nesterov_param_specs
        ])
        if flat_tensor.grad is None:
            flat_tensor.grad = flat_grad.detach()
        else:
            flat_tensor.grad.data.copy_(flat_grad.detach())

        return obj, flat_tensor.grad

    def get_last_loss_components(self):
        """Return detached scalar metrics from the most recent objective."""
        if self._last_loss_components is None:
            return None
        return {
            name: float(value.item()) if torch.is_tensor(value) else float(value)
            for name, value in self._last_loss_components.items()
        }

    def get_current_t_grad_scale(self):
        """Return the iteration-dependent scale applied to t gradients."""
        if self.current_iteration <= self.t_grad_warmup_end:
            return self.t_grad_scale_start
        if self.current_iteration >= self.t_grad_ramp_end:
            return self.t_grad_scale_end

        ramp_span = max(1, self.t_grad_ramp_end - self.t_grad_warmup_end)
        progress = ((self.current_iteration - self.t_grad_warmup_end) /
                    ramp_span)
        return (self.t_grad_scale_start +
                (self.t_grad_scale_end - self.t_grad_scale_start) * progress)

    def scale_t_grad_(self):
        """Scale t gradients in-place according to the warm-up schedule."""
        if self.t.grad is None:
            return

        t_grad_scale = self.get_current_t_grad_scale()
        self.t.grad.mul_(t_grad_scale)

    def _select_valid_net_rows(self, net_indices):
        if net_indices.numel() == 0:
            empty = torch.empty(0, device=self.node_x.device, dtype=torch.long)
            return empty, empty

        valid_rows = self.net_to_valid_row[net_indices].long()
        selected_mask = valid_rows >= 0
        selected_positions = torch.nonzero(selected_mask, as_tuple=True)[0]
        selected_rows = valid_rows[selected_mask]
        return selected_positions, selected_rows

    def _normalize_selected_nets(self, selected_nets):
        using_all_nets = selected_nets is None
        if selected_nets is None:
            selected_nets = self.all_net_indices
        elif isinstance(selected_nets, list):
            selected_nets = torch.tensor(selected_nets,
                                         dtype=torch.long,
                                         device=self.node_x.device)
        else:
            selected_nets = selected_nets.to(device=self.node_x.device,
                                             dtype=torch.long)

        if selected_nets.numel() == 0:
            return selected_nets, using_all_nets

        if selected_nets.max() >= self.num_nets or selected_nets.min() < 0:
            raise ValueError(
                f"selected_nets index out of range [0, {self.num_nets-1}]")
        return selected_nets, using_all_nets

    def _prepare_net_batch(self,
                           net_indices,
                           z=None,
                           include_pin_indices=False):
        num_nets = net_indices.numel()
        selected_positions, selected_rows = self._select_valid_net_rows(
            net_indices)
        prepared = {
            'net_indices': net_indices,
            'num_nets': num_nets,
            'selected_positions': selected_positions,
            'selected_rows': selected_rows,
        }

        if selected_rows.numel() == 0:
            prepared['valid_pin_counts'] = torch.empty(0,
                                                       device=self.node_x.device,
                                                       dtype=torch.long)
            prepared['segment_ids'] = torch.empty(0,
                                                  device=self.node_x.device,
                                                  dtype=torch.long)
            prepared['flat_node_indices'] = torch.empty(
                0, device=self.node_x.device, dtype=torch.long)
            prepared['z_valid'] = torch.empty(0, device=self.node_x.device)
            if include_pin_indices:
                prepared['flat_pin_indices'] = torch.empty(
                    0, device=self.node_x.device, dtype=torch.long)
            return prepared

        if z is None:
            z = self.get_z()

        prepared['valid_pin_counts'] = self.valid_net_pin_counts[
            selected_rows].long()

        # Rebuild segment/node indices only for the active batch.  Persisting
        # both duplicates consumes two more full-size index arrays, while the
        # adapter's normal chunked path only needs a small fraction at a time.
        prepared['segment_ids'] = torch.repeat_interleave(
            torch.arange(selected_rows.numel(),
                         device=self.node_x.device,
                         dtype=torch.long), prepared['valid_pin_counts'])
        if net_indices is self.all_net_indices:
            flat_pin_indices = self.valid_net_pin_indices.long()
        else:
            selected_pin_starts = self.valid_net_pin_start_map[
                selected_rows].long()
            selected_compact_starts = torch.cumsum(
                prepared['valid_pin_counts'], dim=0
            ) - prepared['valid_pin_counts']
            total_selected_pins = int(prepared['valid_pin_counts'].sum().item())
            selected_cache_indices = torch.arange(
                total_selected_pins,
                device=self.node_x.device,
                dtype=torch.long)
            selected_cache_indices = selected_cache_indices + (
                selected_pin_starts - selected_compact_starts
            )[prepared['segment_ids']]
            flat_pin_indices = self.valid_net_pin_indices[
                selected_cache_indices].long()

        prepared['flat_node_indices'] = self.pin2node_map[flat_pin_indices]
        if include_pin_indices:
            prepared['flat_pin_indices'] = flat_pin_indices
        prepared['z_valid'] = z[prepared['flat_node_indices']]
        return prepared

    def _segment_reduce_channels(self, values, segment_ids, num_segments, reduce):
        num_channels = values.shape[1]
        segment_index = segment_ids.unsqueeze(1).expand(-1, num_channels)
        init_value = float('-inf') if reduce == 'amax' else float('inf')

        if hasattr(torch.Tensor, 'scatter_reduce_'):
            reduced = torch.full((num_segments, num_channels),
                                 init_value,
                                 device=values.device,
                                 dtype=values.dtype)
            reduced = reduced.scatter_reduce_(0,
                                              segment_index,
                                              values,
                                              reduce=reduce,
                                              include_self=False)
        else:
            reduced = torch.full((num_segments, num_channels),
                                 init_value,
                                 device=values.device,
                                 dtype=values.dtype)
            for seg_id in range(num_segments):
                seg_mask = segment_ids == seg_id
                if seg_mask.any():
                    if reduce == 'amax':
                        reduced[seg_id] = values[seg_mask].max(dim=0)[0]
                    else:
                        reduced[seg_id] = values[seg_mask].min(dim=0)[0]
        return reduced

    def _compute_cutsize_batch_from_prepared(self, prepared):
        result = torch.zeros(prepared['num_nets'], device=self.node_x.device)
        if prepared['selected_rows'].numel() == 0:
            return result

        z_values = prepared['z_valid'].unsqueeze(1)
        lse_max_per_net, _ = self._segment_lse_max_channels(
            z_values, prepared['segment_ids'], prepared['selected_rows'].numel())
        z_min_per_net = self._segment_reduce_channels(
            z_values, prepared['segment_ids'], prepared['selected_rows'].numel(),
            'amin')
        min_shifted = -self.alpha * (z_values - z_min_per_net[
            prepared['segment_ids']])
        min_exp = torch.exp(min_shifted)
        min_sum = torch.zeros((prepared['selected_rows'].numel(), 1),
                              device=self.node_x.device,
                              dtype=z_values.dtype)
        min_sum = min_sum.scatter_add_(
            0, prepared['segment_ids'].unsqueeze(1), min_exp)
        lse_min_per_net = z_min_per_net - torch.log(min_sum + 1e-10) / self.alpha
        result[prepared['selected_positions']] = (
            (1.0 - lse_min_per_net[:, 0]) * lse_max_per_net[:, 0])
        return result

    def _compute_terminal_positions_from_prepared(self,
                                                 prepared,
                                                 pin_pos_x=None,
                                                 pin_pos_y=None):
        terminal_positions = torch.full((prepared['num_nets'], 2),
                                        float('nan'),
                                        device=self.node_x.device)
        cut_mask = torch.zeros(prepared['num_nets'],
                               dtype=torch.bool,
                               device=self.node_x.device)

        if prepared['selected_rows'].numel() == 0:
            return terminal_positions, cut_mask

        z_values = prepared['z_valid'].unsqueeze(1)
        z_max = self._segment_reduce_channels(z_values, prepared['segment_ids'],
                                              prepared['selected_rows'].numel(),
                                              'amax')[:, 0]
        z_min = self._segment_reduce_channels(z_values, prepared['segment_ids'],
                                              prepared['selected_rows'].numel(),
                                              'amin')[:, 0]
        all_in_top = z_min >= 0.5
        all_in_bottom = z_max < 0.5
        selected_cut_mask = ~(all_in_top | all_in_bottom)
        if not selected_cut_mask.any():
            return terminal_positions, cut_mask

        cut_positions = prepared['selected_positions'][selected_cut_mask]
        cut_mask[cut_positions] = True

        if pin_pos_x is None:
            pin_pos_x = self.get_pin_pos_x()
        if pin_pos_y is None:
            pin_pos_y = self.get_pin_pos_y()

        flat_pin_pos_x = pin_pos_x[prepared['flat_pin_indices']].unsqueeze(1)
        flat_pin_pos_y = pin_pos_y[prepared['flat_pin_indices']].unsqueeze(1)
        pin_in_top = (prepared['z_valid'] >= 0.5).unsqueeze(1)
        pin_in_bottom = ~pin_in_top
        num_segments = prepared['selected_rows'].numel()
        pos_inf = torch.full_like(flat_pin_pos_x, float('inf'))
        neg_inf = torch.full_like(flat_pin_pos_x, float('-inf'))

        top_x_max = self._segment_reduce_channels(
            torch.where(pin_in_top, flat_pin_pos_x, neg_inf),
            prepared['segment_ids'],
            num_segments,
            'amax')[:, 0]
        top_x_min = self._segment_reduce_channels(
            torch.where(pin_in_top, flat_pin_pos_x, pos_inf),
            prepared['segment_ids'],
            num_segments,
            'amin')[:, 0]
        top_y_max = self._segment_reduce_channels(
            torch.where(pin_in_top, flat_pin_pos_y, neg_inf),
            prepared['segment_ids'],
            num_segments,
            'amax')[:, 0]
        top_y_min = self._segment_reduce_channels(
            torch.where(pin_in_top, flat_pin_pos_y, pos_inf),
            prepared['segment_ids'],
            num_segments,
            'amin')[:, 0]

        bottom_x_max = self._segment_reduce_channels(
            torch.where(pin_in_bottom, flat_pin_pos_x, neg_inf),
            prepared['segment_ids'],
            num_segments,
            'amax')[:, 0]
        bottom_x_min = self._segment_reduce_channels(
            torch.where(pin_in_bottom, flat_pin_pos_x, pos_inf),
            prepared['segment_ids'],
            num_segments,
            'amin')[:, 0]
        bottom_y_max = self._segment_reduce_channels(
            torch.where(pin_in_bottom, flat_pin_pos_y, neg_inf),
            prepared['segment_ids'],
            num_segments,
            'amax')[:, 0]
        bottom_y_min = self._segment_reduce_channels(
            torch.where(pin_in_bottom, flat_pin_pos_y, pos_inf),
            prepared['segment_ids'],
            num_segments,
            'amin')[:, 0]

        inner_min_x = torch.maximum(top_x_min, bottom_x_min)
        inner_max_x = torch.minimum(top_x_max, bottom_x_max)
        inner_min_y = torch.maximum(top_y_min, bottom_y_min)
        inner_max_y = torch.minimum(top_y_max, bottom_y_max)

        terminal_positions[cut_positions, 0] = (
            inner_max_x[selected_cut_mask] + inner_min_x[selected_cut_mask]) / 2.0
        terminal_positions[cut_positions, 1] = (
            inner_max_y[selected_cut_mask] + inner_min_y[selected_cut_mask]) / 2.0
        return terminal_positions, cut_mask

    def _get_cached_overlap_mask(self, using_all_nets, overlap_threshold):
        if not using_all_nets:
            return None
        if self._cached_overlap_mask is None:
            return None
        if self._cached_overlap_threshold != overlap_threshold:
            return None
        if self._cached_overlap_iteration is None:
            return None
        if (self.current_iteration - self._cached_overlap_iteration <
                self.cutsize_overlap_update_interval):
            return self._cached_overlap_mask
        return None

    def _update_cached_overlap_mask(self, using_all_nets, overlap_threshold,
                                    overlap_mask):
        if not using_all_nets:
            return
        self._cached_overlap_mask = overlap_mask
        self._cached_overlap_iteration = self.current_iteration
        self._cached_overlap_threshold = overlap_threshold


    def get_z(self):
        """
        map pre-activation variable t to soft assignment z
        Returns:
            z: shape [num_nodes] tensor, representing the probability of each cell being assigned to the top layer
        """
        # switch to gumbel_softmax_z after gumbel_switch_iteration iterations
        if self.current_iteration < self.gumbel_switch_iteration:
            return torch.sigmoid(self.t)
        else:
            tau = self.get_current_gumbel_tau()
            return self.gumbel_softmax_z(self.t, tau=tau)

    def get_current_gumbel_tau(self):
        """
        Return the annealed Gumbel-Softmax temperature at the current iteration.
        """
        if self.current_iteration < self.gumbel_switch_iteration:
            return self.gumbel_tau_start

        anneal_iteration = max(0,
                               self.current_iteration -
                               self.gumbel_switch_iteration)
        progress = min(1.0,
                       anneal_iteration / max(1, self.gumbel_anneal_iterations))

        if self.gumbel_anneal_mode == 'linear':
            tau = (self.gumbel_tau_start +
                   (self.gumbel_tau_min - self.gumbel_tau_start) * progress)
        else:
            tau_ratio = self.gumbel_tau_min / self.gumbel_tau_start
            tau = self.gumbel_tau_start * (tau_ratio**progress)

        return max(self.gumbel_tau_min, tau)

    def get_pin_pos_x(self):
        """Current pin x = node_x[pin2node] + pin_offset_x (differentiable w.r.t. node_x)."""
        return self.node_x[self.pin2node_map] + self.pin_offset_x

    def get_pin_pos_y(self):
        """Current pin y = node_y[pin2node] + pin_offset_y (differentiable w.r.t. node_y)."""
        return self.node_y[self.pin2node_map] + self.pin_offset_y

    def gumbel_softmax_z(self, pi_logits, tau=0.1):
        """
        use Gumbel Softmax to convert logits to soft assignment probabilities
        Gumbel Softmax is a differentiable sampling method for discrete variables.

        Args:
            pi_logits: shape [num_nodes] tensor, logit values for each cell
            tau: temperature parameter, controlling the smoothness of the softmax
                 smaller tau means more discrete distribution; larger tau means more smooth distribution

        Returns:
            z: shape [num_nodes] tensor, probability of each cell being assigned to the top layer
        """
        # convert single logit t to two logits: [t, 0]
        # the first logit corresponds to top layer, the second logit corresponds to bottom layer
        # use [t, 0] instead of [t, -t] to keep the semantic consistent with the original sigmoid
        # sigmoid(t) = exp(t) / (exp(t) + exp(0)) = exp(t) / (exp(t) + 1)
        logits = torch.stack(
            [pi_logits, torch.zeros_like(pi_logits)], dim=-1)  # [num_nodes, 2]

        # generate Gumbel noise: G = -log(-log(U)), where U ~ Uniform(0,1)
        # use numerically stable implementation
        uniform = torch.rand_like(logits)
        # avoid log(0) and log(1), use clamp
        uniform = torch.clamp(uniform, min=1e-8, max=1.0 - 1e-8)
        gumbel_noise = -torch.log(-torch.log(uniform))

        # add Gumbel noise and divide by temperature parameter
        gumbel_logits = (logits + gumbel_noise) / tau  # [num_nodes, 2]
        softmax_probs = torch.softmax(gumbel_logits, dim=-1)  # [num_nodes, 2]

        # return the first element (probability of top layer)
        z = softmax_probs[..., 0]  # [num_nodes]

        return z

    def lse_max(self, weighted_vals):
        """
        numerically stable LSE maximum calculation

        formula: max(x) ≈ (1/α) * log_sum_exp(α * x)

        numerically stable implementation: log_sum_exp(a_j) = m + log Σ_j exp(a_j - m)
        where m = max_j a_j

        Args:
            weighted_vals: weighted values, shape [..., ...] tensor

        Returns:
            soft maximum, shape same as weighted_vals (except the aggregated dimension)
        """
        # use torch.logsumexp to ensure numerical stability
        # logsumexp(α * x) = log(Σ exp(α * x))
        # then divide by α to get soft maximum
        if self.alpha <= 0:
            raise ValueError("alpha must be positive")

        # calculate log_sum_exp(α * weighted_vals)
        lse = torch.logsumexp(self.alpha * weighted_vals, dim=-1)

        # return (1/α) * log_sum_exp(α * weighted_vals)
        return lse / self.alpha

    def lse_min(self, weighted_vals):
        """
        numerically stable LSE minimum calculation
        formula: min(x) ≈ -(1/α) * log_sum_exp(-α * x)

        Args:
            weighted_vals: weighted values, shape [..., ...] tensor

        Returns:
            soft minimum, shape same as weighted_vals (except the aggregated dimension)
        """
        if self.alpha <= 0:
            raise ValueError("alpha must be positive")

        # calculate log_sum_exp(-α * weighted_vals)
        lse = torch.logsumexp(-self.alpha * weighted_vals, dim=-1)

        # return -(1/α) * log_sum_exp(-α * weighted_vals)
        return -lse / self.alpha

    def segment_logsumexp(self, values, segment_ids, num_segments):
        """
        numerically stable segment-based logsumexp calculation

        Args:
            values: input values, shape [total_elements] tensor
            segment_ids: segment id for each element, shape [total_elements] tensor
            num_segments: number of segments

        Returns:
            logsumexp result for each segment, shape [num_segments] tensor
        """
        # find max value in each segment for numerical stability
        # use scatter_reduce if available (PyTorch 1.12+), otherwise use fallback
        if hasattr(torch.Tensor, 'scatter_reduce_'):
            segment_max = torch.full((num_segments, ),
                                     float('-inf'),
                                     device=values.device,
                                     dtype=values.dtype)
            segment_max = segment_max.scatter_reduce_(0,
                                                      segment_ids,
                                                      values,
                                                      reduce='amax',
                                                      include_self=False)
        else:
            # fallback: compute max for each segment (segment count is usually small)
            segment_max = torch.zeros(num_segments,
                                      device=values.device,
                                      dtype=values.dtype)
            for seg_id in range(num_segments):
                mask = segment_ids == seg_id
                if mask.any():
                    segment_max[seg_id] = values[mask].max()
                else:
                    segment_max[seg_id] = float('-inf')

        # subtract max from values for numerical stability
        values_shifted = values - segment_max[segment_ids]  # [total_elements]

        # compute exp of shifted values
        exp_values = torch.exp(values_shifted)  # [total_elements]

        # sum exp values for each segment
        segment_sum = torch.zeros(num_segments,
                                  device=values.device,
                                  dtype=values.dtype)
        segment_sum = segment_sum.scatter_add_(0, segment_ids, exp_values)

        # compute logsumexp: log(sum(exp)) = max + log(sum(exp(values - max)))
        logsumexp_per_segment = segment_max + torch.log(segment_sum + 1e-10)

        return logsumexp_per_segment

    def _segment_lse_max_channels(self, values, segment_ids, num_segments):
        """
        Segment-wise LSE and max over valid pins only.

        Args:
            values: shape [num_valid_pins, num_channels]
            segment_ids: shape [num_valid_pins], maps each pin to a net row
            num_segments: number of selected net rows

        Returns:
            lse: shape [num_segments, num_channels]
            max_vals: shape [num_segments, num_channels]
        """
        num_channels = values.shape[1]
        segment_index = segment_ids.unsqueeze(1).expand(-1, num_channels)

        if hasattr(torch.Tensor, 'scatter_reduce_'):
            max_vals = torch.full((num_segments, num_channels),
                                  float('-inf'),
                                  device=values.device,
                                  dtype=values.dtype)
            max_vals = max_vals.scatter_reduce_(0,
                                                segment_index,
                                                values,
                                                reduce='amax',
                                                include_self=False)
        else:
            max_vals = torch.full((num_segments, num_channels),
                                  float('-inf'),
                                  device=values.device,
                                  dtype=values.dtype)
            for seg_id in range(num_segments):
                seg_mask = segment_ids == seg_id
                if seg_mask.any():
                    max_vals[seg_id] = values[seg_mask].max(dim=0)[0]

        shifted = self.alpha * (values - max_vals[segment_ids])
        exp_values = torch.exp(shifted)
        segment_sum = torch.zeros((num_segments, num_channels),
                                  device=values.device,
                                  dtype=values.dtype)
        segment_sum = segment_sum.scatter_add_(0, segment_index, exp_values)
        lse = max_vals + torch.log(segment_sum + 1e-10) / self.alpha
        return lse, max_vals

    def compute_cutsize(self, net_idx):
        """
        calculate differentiable cutsize of the specified net (based on Snake-3D formula)

        formula:
        - cutsize(n) = (1 - LSE-min(z_i for i∈n)) * LSE-max(z_i for i∈n)

        This formula penalizes cross-layer connections: when all nodes are in the same layer (z_i are close to 0 or 1),
        cutsize is close to 0; when nodes are distributed between two layers, cutsize increases.

        Args:
            net_idx: index of the net

        Returns:
            differentiable cutsize of the specified net, scalar tensor
        """
        # get all pin indices for this net
        start_idx = self.flat_net2pin_start_map[net_idx]
        end_idx = self.flat_net2pin_start_map[net_idx + 1]
        if self.flat_net2pin_is_identity:
            pin_indices = torch.arange(start_idx,
                                       end_idx,
                                       device=self.node_x.device,
                                       dtype=torch.long)
        else:
            pin_indices = self.flat_net2pin_map[start_idx:end_idx]

        if pin_indices.numel() < 2:
            return torch.tensor(0.0, device=self.node_x.device)

        z = self.get_z()
        node_indices = self.pin2node_map[
            pin_indices]  # shape: [num_pins_in_net]
        z_net = z[node_indices]  # shape: [num_pins_in_net]

        lse_max_z = self.lse_max(z_net)
        lse_min_z = self.lse_min(z_net)

        # cutsize(n) = (1 - LSE-min(z_i)) * LSE-max(z_i)
        cutsize = (1.0 - lse_min_z) * lse_max_z

        return cutsize

    def compute_hpwl_batch(self,
                           net_indices,
                           layer='both',
                           z=None,
                           pin_pos_x=None,
                           pin_pos_y=None,
                           include_terminal=True,
                           prepared=None,
                           coordinate_bounds=None):
        """
        batch calculation of HPWL for multiple nets (vectorized version).

        Args:
            net_indices: network indices, tensor of shape [num_nets]
            layer: 'top', 'bottom', or 'both' (default 'both')
            include_terminal: if True (default), cut nets include an HBT
                terminal pin with z=1 on both dies in the bounding-box
                computation (Dual-Max 3D HPWL without HBT).
                If False, only the actual cell pins are used.

        Returns:
            if layer == 'both': tuple of (hpwl_top, hpwl_bottom), each [num_nets]
            else: hpwl values, tensor of shape [num_nets]
        """
        if net_indices.numel() == 0:
            empty = torch.tensor([], device=self.node_x.device)
            if layer == 'both':
                return empty, empty
            return empty

        num_nets = net_indices.numel()
        if z is None:
            z = self.get_z()

        if prepared is None:
            prepared = self._prepare_net_batch(net_indices,
                                               z=z,
                                               include_pin_indices=True)
        selected_positions = prepared['selected_positions']
        selected_rows = prepared['selected_rows']

        if selected_rows.numel() == 0:
            zeros = torch.zeros(num_nets, device=self.node_x.device)
            if layer == 'both':
                return zeros, zeros
            return zeros

        if pin_pos_x is None:
            pin_pos_x = self.get_pin_pos_x()
        if pin_pos_y is None:
            pin_pos_y = self.get_pin_pos_y()
        valid_pin_indices = prepared['flat_pin_indices']
        segment_ids = prepared['segment_ids']
        z_valid = prepared['z_valid']

        # Coordinate shift — store min/max so terminal coords use the same origin
        x_orig = pin_pos_x[valid_pin_indices]
        y_orig = pin_pos_y[valid_pin_indices]
        if coordinate_bounds is None:
            x_min = x_orig.min().detach()
            y_min = y_orig.min().detach()
        else:
            x_min, y_min, x_max, y_max = coordinate_bounds
        x_valid = x_orig - x_min + COORD_EPSILON
        y_valid = y_orig - y_min + COORD_EPSILON
        if coordinate_bounds is None:
            x_max = x_valid.max().detach()
            y_max = y_valid.max().detach()
        x_valid_rev = x_max - x_valid + COORD_EPSILON
        y_valid_rev = y_max - y_valid + COORD_EPSILON

        # ------------------------------------------------------------------ #
        # Terminal augmentation for cut nets (controlled by include_terminal)
        # When enabled, reuse _compute_terminal_positions_from_prepared.
        # Terminal z is always 1 on BOTH dies (the pin is physically present
        # on each die), so it is appended with z=1 for the top LSE and z=1
        # for the bottom LSE (not 1-z=0 like a regular bottom pin).
        # ------------------------------------------------------------------ #
        if include_terminal:
            terminal_positions, cut_mask = \
                self._compute_terminal_positions_from_prepared(
                    prepared,
                    pin_pos_x=pin_pos_x,
                    pin_pos_y=pin_pos_y)

            # Map cut_mask (net-index space) back to segment space
            cut_mask_seg = cut_mask[selected_positions]      # [num_selected]
            cut_seg_ids = torch.where(cut_mask_seg)[0]       # segment indices
        else:
            cut_seg_ids = torch.empty(0, dtype=torch.long,
                                      device=self.node_x.device)

        if cut_seg_ids.numel() > 0:
            # Absolute coordinates of terminal for each cut net
            cut_net_pos = selected_positions[cut_mask_seg]
            term_x = terminal_positions[cut_net_pos, 0]
            term_y = terminal_positions[cut_net_pos, 1]

            # Apply the same shift used for regular pins
            term_x_s = term_x - x_min + COORD_EPSILON
            term_y_s = term_y - y_min + COORD_EPSILON
            term_x_rev = x_max - term_x_s + COORD_EPSILON
            term_y_rev = y_max - term_y_s + COORD_EPSILON

            # Augmented coordinate tensors (shared by top and bottom)
            x_aug = torch.cat([x_valid, term_x_s])
            y_aug = torch.cat([y_valid, term_y_s])
            x_rev_aug = torch.cat([x_valid_rev, term_x_rev])
            y_rev_aug = torch.cat([y_valid_rev, term_y_rev])
            seg_aug = torch.cat([segment_ids, cut_seg_ids])

            # z=1 for terminal on both top and bottom
            term_ones = torch.ones(cut_seg_ids.numel(),
                                   dtype=z_valid.dtype,
                                   device=self.node_x.device)
            z_top_aug = torch.cat([z_valid, term_ones])
            z_bot_aug = torch.cat([1.0 - z_valid, term_ones])
        else:
            x_aug, y_aug = x_valid, y_valid
            x_rev_aug, y_rev_aug = x_valid_rev, y_valid_rev
            seg_aug = segment_ids
            z_top_aug = z_valid
            z_bot_aug = 1.0 - z_valid

        hpwl_top_per_net = torch.zeros(selected_rows.numel(),
                                       device=self.node_x.device)
        hpwl_bottom_per_net = torch.zeros(selected_rows.numel(),
                                          device=self.node_x.device)

        if layer in ['top', 'both']:
            top_values = torch.stack((z_top_aug * x_aug,
                                      z_top_aug * y_aug,
                                      z_top_aug * x_rev_aug,
                                      z_top_aug * y_rev_aug),
                                     dim=1)
            top_lse, top_max = self._segment_lse_max_channels(
                top_values, seg_aug, selected_rows.numel())
            hpwl_top_per_net = (
                top_lse[:, 0] + top_lse[:, 1] + top_lse[:, 2] +
                top_lse[:, 3] -
                torch.maximum(top_max[:, 0], top_max[:, 2]).detach() -
                torch.maximum(top_max[:, 1], top_max[:, 3]).detach())

        if layer in ['bottom', 'both']:
            bot_values = torch.stack((z_bot_aug * x_rev_aug,
                                      z_bot_aug * y_rev_aug,
                                      z_bot_aug * x_aug,
                                      z_bot_aug * y_aug),
                                     dim=1)
            bot_lse, bot_max = self._segment_lse_max_channels(
                bot_values, seg_aug, selected_rows.numel())
            hpwl_bottom_per_net = (
                bot_lse[:, 0] + bot_lse[:, 1] + bot_lse[:, 2] +
                bot_lse[:, 3] -
                torch.maximum(bot_max[:, 0], bot_max[:, 2]).detach() -
                torch.maximum(bot_max[:, 1], bot_max[:, 3]).detach())

        # create complete result arrays (including invalid nets)
        if layer == 'both':
            result_top = torch.zeros(num_nets, device=self.node_x.device)
            result_bottom = torch.zeros(num_nets, device=self.node_x.device)
            result_top[selected_positions] = hpwl_top_per_net
            result_bottom[selected_positions] = hpwl_bottom_per_net
            return result_top, result_bottom
        elif layer == 'top':
            result = torch.zeros(num_nets, device=self.node_x.device)
            result[selected_positions] = hpwl_top_per_net
            return result
        else:  # layer == 'bottom'
            result = torch.zeros(num_nets, device=self.node_x.device)
            result[selected_positions] = hpwl_bottom_per_net
            return result

    def compute_cutsize_batch(self, net_indices, prepared=None, z=None):
        """
        batch calculation of differentiable cutsize for multiple nets (vectorized version)

        Args:
            net_indices: network indices, tensor of shape [num_nets]

        Returns:
            cutsize values, tensor of shape [num_nets]
        """
        if prepared is None:
            if net_indices.numel() == 0:
                return torch.tensor([], device=self.node_x.device)
            prepared = self._prepare_net_batch(net_indices, z=z)
        return self._compute_cutsize_batch_from_prepared(prepared)

    def compute_terminal_positions(self,
                                  net_indices,
                                  prepared=None,
                                  z=None,
                                  pin_pos_x=None,
                                  pin_pos_y=None):
        """
        compute terminal positions at the center of the top/bottom box intersection
        for cut nets (vectorized version)

        Args:
            net_indices: network indices, tensor of shape [num_nets]

        Returns:
            terminal_positions: tensor of shape [num_nets, 2] (x, y coordinates)
                               terminal positions for non-cut nets are NaN
            cut_mask: boolean tensor of shape [num_nets], True indicates this net generates a terminal
        """
        if prepared is None:
            if net_indices.numel() == 0:
                return torch.empty((0, 2), device=self.node_x.device), torch.empty(
                    0, dtype=torch.bool, device=self.node_x.device)
            prepared = self._prepare_net_batch(net_indices,
                                               z=z,
                                               include_pin_indices=True)
        return self._compute_terminal_positions_from_prepared(
            prepared, pin_pos_x=pin_pos_x, pin_pos_y=pin_pos_y)

    def _compute_terminal_overlap_mask(self,
                                       terminal_positions,
                                       cut_mask,
                                       overlap_threshold=1500,
                                       chunk_size=2048):
        """Detect overlaps with spatial hashing instead of dense pairwise distances."""
        overlap_mask = torch.zeros(terminal_positions.shape[0],
                                   dtype=torch.bool,
                                   device=terminal_positions.device)
        valid_indices = torch.where(cut_mask)[0]
        if valid_indices.numel() < 2:
            return overlap_mask

        valid_positions = terminal_positions[valid_indices]
        if overlap_threshold <= 0:
            raise ValueError("overlap_threshold must be positive")

        cell_coords = torch.floor(valid_positions / overlap_threshold).to(
            torch.long)
        min_coords = cell_coords.min(dim=0)[0]
        shifted_coords = cell_coords - min_coords
        grid_width = shifted_coords[:, 1].max() + 1
        cell_keys = shifted_coords[:, 0] * grid_width + shifted_coords[:, 1]

        sort_order = torch.argsort(cell_keys)
        sorted_keys = cell_keys[sort_order]
        _, counts = torch.unique_consecutive(sorted_keys, return_counts=True)
        starts = torch.cumsum(
            torch.cat([
                torch.zeros(1, device=counts.device, dtype=torch.long),
                counts[:-1]
            ]),
            dim=0)
        unique_cell_coords = cell_coords[sort_order[starts]]
        cell_slices = {
            tuple(coord): (int(start), int(start + count))
            for coord, start, count in zip(unique_cell_coords.tolist(),
                                           starts.tolist(), counts.tolist())
        }

        threshold_sq = float(overlap_threshold) * float(overlap_threshold)
        has_overlap = torch.zeros(valid_indices.numel(),
                                  dtype=torch.bool,
                                  device=valid_positions.device)
        for cell_coord, (start, end) in cell_slices.items():
            current_ids = sort_order[start:end]
            neighbor_ids = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor_slice = cell_slices.get((cell_coord[0] + dx,
                                                      cell_coord[1] + dy))
                    if neighbor_slice is None:
                        continue
                    neighbor_ids.append(
                        sort_order[neighbor_slice[0]:neighbor_slice[1]])

            if not neighbor_ids:
                continue

            neighbor_ids = torch.cat(neighbor_ids, dim=0)
            for current_start in range(0, current_ids.numel(), chunk_size):
                current_end = min(current_start + chunk_size, current_ids.numel())
                current_chunk_ids = current_ids[current_start:current_end]
                current_chunk_pos = valid_positions[current_chunk_ids]
                current_has_overlap = torch.zeros(current_chunk_ids.numel(),
                                                  dtype=torch.bool,
                                                  device=valid_positions.device)

                for neighbor_start in range(0, neighbor_ids.numel(), chunk_size):
                    neighbor_end = min(neighbor_start + chunk_size,
                                       neighbor_ids.numel())
                    neighbor_chunk_ids = neighbor_ids[neighbor_start:neighbor_end]
                    neighbor_chunk_pos = valid_positions[neighbor_chunk_ids]
                    diff = (current_chunk_pos.unsqueeze(1) -
                            neighbor_chunk_pos.unsqueeze(0))
                    dist_sq = (diff * diff).sum(dim=-1)
                    same_point = (current_chunk_ids.unsqueeze(1) ==
                                  neighbor_chunk_ids.unsqueeze(0))
                    current_has_overlap |= ((dist_sq < threshold_sq) &
                                            ~same_point).any(dim=1)
                    if current_has_overlap.all():
                        break

                has_overlap[current_chunk_ids] |= current_has_overlap

        overlap_mask[valid_indices] = has_overlap
        return overlap_mask

    def detect_terminal_overlaps(self,
                                 terminal_positions,
                                 cut_mask,
                                 overlap_threshold=1500,
                                 chunk_size=2048):
        """
        detect whether terminals overlap

        Args:
            terminal_positions: tensor of shape [num_nets, 2] (x, y coordinates)
            cut_mask: boolean tensor of shape [num_nets], True indicates this net generates a terminal
            overlap_threshold: overlap threshold, terminals with distance less than this value are considered overlapping

        Returns:
            overlap_groups: list of lists, each sublist contains overlapping net indices
            overlap_mask: boolean tensor of shape [num_nets], True indicates this net's terminal overlaps with other nets' terminals
        """
        num_nets = terminal_positions.shape[0]
        overlap_mask = torch.zeros(num_nets,
                                   dtype=torch.bool,
                                   device=terminal_positions.device)
        overlap_groups = []

        valid_indices = torch.where(cut_mask)[0]

        if valid_indices.numel() < 2:
            return overlap_groups, overlap_mask

        valid_positions = terminal_positions[valid_indices]
        if overlap_threshold <= 0:
            raise ValueError("overlap_threshold must be positive")

        cell_coords = torch.floor(valid_positions / overlap_threshold).to(
            torch.long)
        min_coords = cell_coords.min(dim=0)[0]
        shifted_coords = cell_coords - min_coords
        grid_width = shifted_coords[:, 1].max() + 1
        cell_keys = shifted_coords[:, 0] * grid_width + shifted_coords[:, 1]

        sort_order = torch.argsort(cell_keys)
        sorted_keys = cell_keys[sort_order]
        _, counts = torch.unique_consecutive(sorted_keys, return_counts=True)
        starts = torch.cumsum(
            torch.cat([
                torch.zeros(1, device=counts.device, dtype=torch.long),
                counts[:-1]
            ]),
            dim=0)
        unique_cell_coords = cell_coords[sort_order[starts]]
        cell_slices = {
            tuple(coord): (int(start), int(start + count))
            for coord, start, count in zip(unique_cell_coords.tolist(),
                                           starts.tolist(), counts.tolist())
        }

        threshold_sq = float(overlap_threshold) * float(overlap_threshold)
        num_valid_nets = valid_indices.numel()
        adjacency = [set() for _ in range(num_valid_nets)]
        for cell_coord, (start, end) in cell_slices.items():
            current_ids = sort_order[start:end]
            neighbor_ids = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor_slice = cell_slices.get((cell_coord[0] + dx,
                                                      cell_coord[1] + dy))
                    if neighbor_slice is None:
                        continue
                    neighbor_ids.append(
                        sort_order[neighbor_slice[0]:neighbor_slice[1]])

            if not neighbor_ids:
                continue

            neighbor_ids = torch.cat(neighbor_ids, dim=0)
            for current_start in range(0, current_ids.numel(), chunk_size):
                current_end = min(current_start + chunk_size, current_ids.numel())
                current_chunk_ids = current_ids[current_start:current_end]
                current_chunk_pos = valid_positions[current_chunk_ids]

                for neighbor_start in range(0, neighbor_ids.numel(), chunk_size):
                    neighbor_end = min(neighbor_start + chunk_size,
                                       neighbor_ids.numel())
                    neighbor_chunk_ids = neighbor_ids[neighbor_start:neighbor_end]
                    neighbor_chunk_pos = valid_positions[neighbor_chunk_ids]
                    diff = (current_chunk_pos.unsqueeze(1) -
                            neighbor_chunk_pos.unsqueeze(0))
                    dist_sq = (diff * diff).sum(dim=-1)
                    same_point = (current_chunk_ids.unsqueeze(1) ==
                                  neighbor_chunk_ids.unsqueeze(0))
                    overlap_pairs = torch.where((dist_sq < threshold_sq) &
                                                ~same_point)
                    if overlap_pairs[0].numel() == 0:
                        continue

                    left_ids = current_chunk_ids[overlap_pairs[0]].tolist()
                    right_ids = neighbor_chunk_ids[overlap_pairs[1]].tolist()
                    for left_id, right_id in zip(left_ids, right_ids):
                        adjacency[left_id].add(right_id)
                        adjacency[right_id].add(left_id)

        visited = [False] * num_valid_nets
        for i in range(num_valid_nets):
            if visited[i] or not adjacency[i]:
                continue

            stack = [i]
            component = []
            visited[i] = True
            while stack:
                node = stack.pop()
                component.append(node)
                for neighbor in adjacency[node]:
                    if not visited[neighbor]:
                        visited[neighbor] = True
                        stack.append(neighbor)

            group_indices = torch.tensor(component,
                                         dtype=torch.long,
                                         device=valid_indices.device)
            overlap_groups.append(valid_indices[group_indices].tolist())
            overlap_mask[valid_indices[group_indices]] = True

        return overlap_groups, overlap_mask

    def compute_cutsize_loss(self,
                             selected_nets=None,
                             cutsize_net_weights=None,
                             handle_terminal_overlap=True,
                             overlap_threshold=400,
                             overlap_weight_penalty=1,
                             z=None,
                             pin_pos_x=None,
                             pin_pos_y=None,
                             prepared=None):
        """
        calculate total cutsize loss (only for selected nets)

        L_cut = Σ_{n∈selected_nets} w(n) * cutsize(n)

        if handle_terminal_overlap=True, it will detect terminal overlaps and increase the weight of one of the overlapping terminals to eliminate cutsize

        Args:
            selected_nets: network indices to apply cutsize constraint, tensor or list
                           if None, calculate for all nets
            cutsize_net_weights: weights for each selected net, tensor or list
                                 if None, use self.net_weights corresponding to the selected nets
                                 if selected_nets is None, use self.net_weights
            handle_terminal_overlap: whether to handle terminal overlap, default True
            overlap_threshold: distance threshold for terminal overlap
            overlap_weight_penalty: multiplier to increase net weight when terminals overlap

        Returns:
            total_cutsize: total cutsize loss, scalar tensor
        """
        selected_nets, using_all_nets = self._normalize_selected_nets(
            selected_nets)
        if selected_nets.numel() == 0:
            return torch.tensor(0.0, device=self.node_x.device)

        # get weights
        if cutsize_net_weights is None:
            # use weights from self.net_weights corresponding to the selected nets
            weights = self.net_weights[selected_nets].clone()
        else:
            # use user-provided weights
            if isinstance(cutsize_net_weights, list):
                cutsize_net_weights = torch.tensor(cutsize_net_weights,
                                                   dtype=torch.float32,
                                                   device=self.node_x.device)
            if cutsize_net_weights.numel() != selected_nets.numel():
                raise ValueError(
                    f"cutsize_net_weights length ({cutsize_net_weights.numel()}) "
                    f"must match selected_nets length ({selected_nets.numel()})"
                )
            weights = cutsize_net_weights.clone()

        if z is None:
            z = self.get_z()
        if prepared is None:
            prepared = self._prepare_net_batch(
                selected_nets,
                z=z,
                include_pin_indices=handle_terminal_overlap)

        # handle terminal overlap
        if handle_terminal_overlap:
            overlap_mask = self._get_cached_overlap_mask(
                using_all_nets, overlap_threshold)
            if overlap_mask is None:
                terminal_positions, cut_mask = (
                    self._compute_terminal_positions_from_prepared(
                        prepared, pin_pos_x=pin_pos_x, pin_pos_y=pin_pos_y))
                overlap_mask = self._compute_terminal_overlap_mask(
                    terminal_positions,
                    cut_mask,
                    overlap_threshold=overlap_threshold)
                self._update_cached_overlap_mask(using_all_nets,
                                                 overlap_threshold,
                                                 overlap_mask)

            if overlap_mask.any():
                weights[overlap_mask] += overlap_weight_penalty

        # vectorized calculation of cutsize for all selected nets
        cutsizes = self.compute_cutsize_batch(selected_nets,
                                              prepared=prepared)  # [num_selected_nets]

        total_cutsize = (weights * cutsizes).sum()

        return total_cutsize

    def _cutsize_weights_for_all_nets(self,
                                      z,
                                      pin_pos_x,
                                      pin_pos_y,
                                      overlap_threshold=400,
                                      overlap_weight_penalty=1):
        """Build non-differentiable cutsize weights once for chunked loss."""
        weights = self.net_weights.detach().clone()
        if not self.cutsize_handle_terminal_overlap:
            return weights

        overlap_mask = self._get_cached_overlap_mask(True, overlap_threshold)
        if overlap_mask is None:
            # Overlap selection is discrete and never contributes a useful
            # gradient.  Keeping it outside autograd prevents a second large
            # terminal-position graph from being retained alongside HPWL.
            with torch.no_grad():
                prepared = self._prepare_net_batch(
                    self.all_net_indices,
                    z=z.detach(),
                    include_pin_indices=True)
                terminal_positions, cut_mask = (
                    self._compute_terminal_positions_from_prepared(
                        prepared,
                        pin_pos_x=pin_pos_x.detach(),
                        pin_pos_y=pin_pos_y.detach()))
                overlap_mask = self._compute_terminal_overlap_mask(
                    terminal_positions,
                    cut_mask,
                    overlap_threshold=overlap_threshold)
            self._update_cached_overlap_mask(True, overlap_threshold,
                                             overlap_mask)

        if overlap_mask.any():
            weights[overlap_mask] += overlap_weight_penalty
        return weights

    def compute_balance_loss(self, z=None):
        """
        calculate balance loss
        if the density of a bin exceeds half of the bin area, add relu penalty

        Returns:
            balance_loss: balance loss, scalar tensor
        """
        if z is None:
            z = self.get_z()
        top_z = z
        bottom_z = 1 - z

        top_threshold_factor = self.config['balance_loss']['top_threshold_factor']
        bottom_threshold_factor = self.config['balance_loss']['bottom_threshold_factor']
        num_bins_x = self.config['balance_loss']['num_bins_x']
        num_bins_y = self.config['balance_loss']['num_bins_y']

        def compute_density_map(partition_z, num_bin_x, num_bin_y):
            node_x = self.node_x.detach()
            node_y = self.node_y.detach()
            x_range = node_x.max() - node_x.min()
            y_range = node_y.max() - node_y.min()
            bin_size_x = x_range / num_bin_x
            bin_size_y = y_range / num_bin_y

            # calculate the area of each bin
            node_area_map = torch.zeros(num_bin_x, num_bin_y, device=z.device)
            density_map = torch.zeros(num_bin_x, num_bin_y, device=z.device)
            node_x_min = node_x.min()
            node_y_min = node_y.min()

            # compute bin indices for all nodes at once (vectorized)
            x_idx = ((node_x - node_x_min) / bin_size_x).long()
            y_idx = ((node_y - node_y_min) / bin_size_y).long()
            x_idx = torch.clamp(x_idx, 0, num_bin_x - 1)
            y_idx = torch.clamp(y_idx, 0, num_bin_y - 1)

            # compute node areas and weighted areas (vectorized)
            node_areas = self.node_size_x * self.node_size_y  # [num_nodes]
            weighted_areas = node_areas * partition_z  # [num_nodes]

            # use index_add_ to accumulate values (vectorized)
            # index_add_ requires 1D indices, so we flatten the 2D indices
            # Convert 2D indices (x_idx, y_idx) to 1D linear indices
            linear_indices = x_idx * num_bin_y + y_idx  # [num_nodes]

            # flatten density maps for index_add_
            density_map_flat = density_map.flatten()  # [num_bin_x * num_bin_y]
            node_area_map_flat = node_area_map.flatten(
            )  # [num_bin_x * num_bin_y]
            density_map_flat.index_add_(0, linear_indices, weighted_areas)
            node_area_map_flat.index_add_(0, linear_indices, node_areas)
            density_map = density_map_flat.view(num_bin_x, num_bin_y)
            node_area_map = node_area_map_flat.view(num_bin_x, num_bin_y)

            return density_map, node_area_map

        local_top_density_map, node_area_map = compute_density_map(
            top_z, num_bins_x, num_bins_y)
        local_bottom_density_map, _ = compute_density_map(bottom_z, num_bins_x,
                                                    num_bins_y)

        local_balance_loss = torch.relu(local_top_density_map - node_area_map*top_threshold_factor).sum() + \
                       torch.relu(local_bottom_density_map - node_area_map*bottom_threshold_factor).sum()

        global_top_density_map, node_area_map = compute_density_map(
            top_z, 1, 1)
        global_bottom_density_map, _ = compute_density_map(bottom_z, 1,
                                                    1)

        global_balance_loss = torch.relu(global_top_density_map - node_area_map*top_threshold_factor).sum() + \
                       torch.relu(global_bottom_density_map - node_area_map*bottom_threshold_factor).sum()


        return local_balance_loss + global_balance_loss

    def compute_density_loss(self):
        """
        Calculate density loss using DREAMPlace density op.
        Sum of density overflow on top and bottom layer (same bin grid as placement).

        Returns:
            density_loss: density loss, scalar tensor
        """

        def get_density(pos):
            return self.dreamplace_basic.op_collections.density_op(pos)

        density_pos = torch.cat(
            [self.node_x, self.x_tail, self.node_y, self.y_tail], dim=0)
        density_loss = get_density(density_pos)
        return density_loss

    def _iter_net_chunks(self, net_indices):
        chunk_size = self.net_chunk_size or net_indices.numel()
        for start in range(0, net_indices.numel(), chunk_size):
            yield net_indices[start:start + chunk_size]

    def _valid_coordinate_bounds(self, pin_pos_x, pin_pos_y):
        """Return the global detached shift/reverse constants for HPWL."""
        with torch.no_grad():
            valid_pin_indices = self.valid_net_pin_indices
            if valid_pin_indices.numel() == 0:
                zero = torch.zeros((), device=self.node_x.device,
                                   dtype=self.node_x.dtype)
                return zero, zero, zero, zero

            # Bounds are constants in the HPWL formulation.  Reduce them in
            # pin chunks so evaluating the bounds does not create another
            # all-valid-pin x/y pair alongside the training graph.
            bound_chunk_size = int(
                self.config.get('coordinate_bound_pin_chunk_size', 1000000))
            bound_chunk_size = max(1, bound_chunk_size)
            x_min = y_min = x_raw_max = y_raw_max = None
            pin_pos_x_detached = pin_pos_x.detach()
            pin_pos_y_detached = pin_pos_y.detach()
            for start in range(0, valid_pin_indices.numel(),
                               bound_chunk_size):
                indices = valid_pin_indices[
                    start:start + bound_chunk_size].long()
                x_chunk = pin_pos_x_detached[indices]
                y_chunk = pin_pos_y_detached[indices]
                chunk_x_min = x_chunk.min()
                chunk_y_min = y_chunk.min()
                chunk_x_max = x_chunk.max()
                chunk_y_max = y_chunk.max()
                x_min = (chunk_x_min if x_min is None else
                         torch.minimum(x_min, chunk_x_min))
                y_min = (chunk_y_min if y_min is None else
                         torch.minimum(y_min, chunk_y_min))
                x_raw_max = (chunk_x_max if x_raw_max is None else
                             torch.maximum(x_raw_max, chunk_x_max))
                y_raw_max = (chunk_y_max if y_raw_max is None else
                             torch.maximum(y_raw_max, chunk_y_max))
            x_max = x_raw_max - x_min + COORD_EPSILON
            y_max = y_raw_max - y_min + COORD_EPSILON
        return x_min, y_min, x_max, y_max

    def _compute_net_objective_components(self,
                                          net_indices,
                                          z,
                                          pin_pos_x,
                                          pin_pos_y,
                                          lambda_wl,
                                          lambda_cut,
                                          cutsize_net_weights=None,
                                          coordinate_bounds=None):
        """Compute scalar wirelength/cutsize terms for one net chunk."""
        prepared = self._prepare_net_batch(net_indices,
                                           z=z,
                                           include_pin_indices=True)
        zero = torch.zeros((), device=self.node_x.device,
                           dtype=self.node_x.dtype)
        hpwl_loss = zero
        if lambda_wl != 0:
            hpwl_top, hpwl_bottom = self.compute_hpwl_batch(
                net_indices,
                layer='both',
                z=z,
                pin_pos_x=pin_pos_x,
                pin_pos_y=pin_pos_y,
                prepared=prepared,
                coordinate_bounds=coordinate_bounds)
            hpwl_loss = (self.net_weights[net_indices] *
                         (hpwl_top + hpwl_bottom)).sum()

        cutsize_loss = zero
        if lambda_cut != 0:
            cutsize_loss = self.compute_cutsize_loss(
                selected_nets=net_indices,
                cutsize_net_weights=cutsize_net_weights,
                handle_terminal_overlap=False,
                z=z,
                pin_pos_x=pin_pos_x,
                pin_pos_y=pin_pos_y,
                prepared=prepared)
        return hpwl_loss, cutsize_loss

    def _record_loss_components(self, hpwl, cutsize, balance, density,
                                total):
        self._last_loss_components = {
            'L_WL': hpwl.detach(),
            'L_cut': cutsize.detach(),
            'L_balance': balance.detach(),
            'L_density': density.detach(),
            'L_total': total.detach(),
        }

    def backward_objective_in_net_chunks(self,
                                         lambda_wl=1.0,
                                         lambda_cut=0.0,
                                         lambda_balance=0.0,
                                         lambda_density=0.0,
                                         cutsize_net_weights=None):
        """Backpropagate one net chunk at a time to cap activation memory.

        ``z`` and pin positions are shared inputs.  Chunk graphs are released
        immediately after their backward call while gradients accumulate on
        model parameters.  Only the small shared input graph is retained until
        the last net/balance backward.
        """
        z = self.get_z()
        pin_pos_x = self.get_pin_pos_x()
        pin_pos_y = self.get_pin_pos_y()
        coordinate_bounds = self._valid_coordinate_bounds(
            pin_pos_x, pin_pos_y)

        if lambda_cut != 0:
            if cutsize_net_weights is None:
                all_cut_weights = self._cutsize_weights_for_all_nets(
                    z, pin_pos_x, pin_pos_y)
            else:
                all_cut_weights = cutsize_net_weights.to(
                    device=self.node_x.device, dtype=self.node_x.dtype)
                if all_cut_weights.numel() != self.num_nets:
                    raise ValueError(
                        "chunked cutsize_net_weights must contain one value "
                        "per net")
        else:
            all_cut_weights = None

        zero = torch.zeros((), device=self.node_x.device,
                           dtype=self.node_x.dtype)
        total_hpwl = zero
        total_cutsize = zero
        chunks = list(self._iter_net_chunks(self.all_net_indices))
        for chunk_index, net_chunk in enumerate(chunks):
            chunk_weights = (None if all_cut_weights is None else
                             all_cut_weights[net_chunk])
            hpwl_chunk, cutsize_chunk = self._compute_net_objective_components(
                net_chunk,
                z,
                pin_pos_x,
                pin_pos_y,
                lambda_wl,
                lambda_cut,
                cutsize_net_weights=chunk_weights,
                coordinate_bounds=coordinate_bounds)
            chunk_objective = (lambda_wl * hpwl_chunk +
                               lambda_cut * cutsize_chunk)
            is_last_chunk = chunk_index + 1 == len(chunks)
            retain_shared_graph = not is_last_chunk
            if chunk_objective.requires_grad:
                chunk_objective.backward(retain_graph=retain_shared_graph)
            total_hpwl = total_hpwl + hpwl_chunk.detach()
            total_cutsize = total_cutsize + cutsize_chunk.detach()
            del hpwl_chunk, cutsize_chunk, chunk_objective

        balance_loss = zero
        if lambda_balance > 0:
            # Recompute the inexpensive node-level assignment graph.  This
            # lets the last net chunk free its pin-position graph immediately.
            balance_loss = self.compute_balance_loss(z=self.get_z())
            (lambda_balance * balance_loss).backward()

        density_loss = zero
        if lambda_density > 0:
            density_loss = self.compute_density_loss()
            weighted_density = lambda_density * density_loss
            if weighted_density.requires_grad:
                weighted_density.backward()

        total_loss = (lambda_wl * total_hpwl +
                      lambda_cut * total_cutsize +
                      lambda_balance * balance_loss.detach() +
                      lambda_density * density_loss.detach())
        self._record_loss_components(total_hpwl, total_cutsize,
                                     balance_loss, density_loss, total_loss)
        return total_loss

    def forward(self,
                lambda_wl=1.0,
                lambda_cut=0.0,
                lambda_balance=0.0,
                lambda_density=0.0,
                selected_nets=None,
                cutsize_net_weights=None,
                return_debug_info=False):
        """
        calculate total loss (HPWL + Cutsize + Balance + Density)
        L_WL = Σ_e (HPWL_top_e + HPWL_bottom_e) * weight_e
        L_cut = Σ_{n∈selected_nets} w(n) * cutsize(n)
        L_balance = balance loss (penalizes density exceeding half bin area)
        L_density = DREAMPlace density overflow loss (top + bottom layer)
        L_total = λ_WL * L_WL + λ_cut * L_cut + λ_balance * L_balance + λ_density * L_density

        Args:
            lambda_wl: weight of HPWL loss, default 1.0
            lambda_cut: weight of cutsize loss, default 0.0
            lambda_balance: weight of balance loss, default 0.0
            lambda_density: weight of density loss, default 0.0
            selected_nets: indices of nets to apply cutsize constraint, tensor or list
                           only used when lambda_cut > 0
            cutsize_net_weights: weights of each selected net, tensor or list
                                 if None, use self.net_weights corresponding to the selected nets
            return_debug_info: whether to return debug information, default False

        Returns:
            total_loss: total loss, scalar tensor
            if return_debug_info:
                debug_info: dict containing:
                    - 'L_WL': total HPWL loss
                    - 'L_cut': total cutsize loss
                    - 'L_balance': total balance loss
                    - 'L_density': total density loss
                    - 'L_total': total loss
                return (total_loss, debug_info) tuple
            else:
                return total_loss
        """
        z = self.get_z()
        pin_pos_x = self.get_pin_pos_x()
        pin_pos_y = self.get_pin_pos_y()

        zero = torch.zeros((), device=self.node_x.device,
                           dtype=self.node_x.dtype)
        total_hpwl = zero
        cutsize_loss = zero
        use_chunks = self.net_chunk_size > 0 and selected_nets is None
        if use_chunks:
            coordinate_bounds = self._valid_coordinate_bounds(
                pin_pos_x, pin_pos_y)
            if lambda_cut != 0:
                if cutsize_net_weights is None:
                    all_cut_weights = self._cutsize_weights_for_all_nets(
                        z, pin_pos_x, pin_pos_y)
                else:
                    all_cut_weights = cutsize_net_weights.to(
                        device=self.node_x.device, dtype=self.node_x.dtype)
            else:
                all_cut_weights = None
            for net_chunk in self._iter_net_chunks(self.all_net_indices):
                chunk_weights = (None if all_cut_weights is None else
                                 all_cut_weights[net_chunk])
                hpwl_chunk, cutsize_chunk = (
                    self._compute_net_objective_components(
                        net_chunk,
                        z,
                        pin_pos_x,
                        pin_pos_y,
                        lambda_wl,
                        lambda_cut,
                        cutsize_net_weights=chunk_weights,
                        coordinate_bounds=coordinate_bounds))
                total_hpwl = total_hpwl + hpwl_chunk
                cutsize_loss = cutsize_loss + cutsize_chunk
        else:
            prepared = self._prepare_net_batch(
                self.all_net_indices, z=z, include_pin_indices=True)
            hpwl_top_all, hpwl_bottom_all = self.compute_hpwl_batch(
                self.all_net_indices,
                layer='both',
                z=z,
                pin_pos_x=pin_pos_x,
                pin_pos_y=pin_pos_y,
                prepared=prepared)
            total_hpwl = (self.net_weights *
                          (hpwl_top_all + hpwl_bottom_all)).sum()
            if lambda_cut != 0:
                cutsize_loss = self.compute_cutsize_loss(
                    selected_nets=selected_nets,
                    cutsize_net_weights=cutsize_net_weights,
                    handle_terminal_overlap=
                    self.cutsize_handle_terminal_overlap,
                    z=z,
                    pin_pos_x=pin_pos_x,
                    pin_pos_y=pin_pos_y,
                    prepared=prepared if selected_nets is None else None)

        balance_loss = zero
        if lambda_balance > 0:
            balance_loss = self.compute_balance_loss(z=z)

        density_loss = zero
        if lambda_density > 0:
            density_loss = self.compute_density_loss()

        total_loss = (lambda_wl * total_hpwl + lambda_cut * cutsize_loss +
                      lambda_balance * balance_loss +
                      lambda_density * density_loss)
        self._record_loss_components(total_hpwl, cutsize_loss, balance_loss,
                                     density_loss, total_loss)

        # if not return debug information, return total loss
        if not return_debug_info:
            return total_loss

        # return total loss and debug information
        debug_info = {
            'L_WL': total_hpwl.item(),
            'L_cut': cutsize_loss.item() if lambda_cut != 0 else 0.0,
            'L_balance': balance_loss.item() if lambda_balance > 0 else 0.0,
            'L_density': density_loss.item() if lambda_density > 0 else 0.0,
            'L_total': total_loss.item()
        }
        return total_loss, debug_info

    @torch.no_grad()
    def get_binary_assignment(self, threshold=0.5):
        """
        get binary assignment
        threshold for binary assignment, default 0.5

        Returns:
            binary_z: binary assignment, 1 for top, 0 for bottom
        """
        z = self.get_z()
        return (z > threshold).to(torch.int32)

    @torch.no_grad()
    def get_assignment_stats(self):
        """
        get assignment statistics for debugging

        Returns:
            dict: contains z statistics
        """
        z = self.get_z()
        return {
            'gumbel_tau': self.get_current_gumbel_tau(),
            't_grad_scale': self.get_current_t_grad_scale(),
            'z_mean': z.mean().item(),
            'z_std': z.std().item(),
            'z_min': z.min().item(),
            'z_max': z.max().item(),
            'top_cells': (z > 0.5).sum().item(),
            'bottom_cells': (z <= 0.5).sum().item()
        }
