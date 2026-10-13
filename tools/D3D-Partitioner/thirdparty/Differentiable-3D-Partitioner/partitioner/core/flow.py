'''
Author: JeanneWillis hi@jeannewillis.cn
Date: 2026-02-06 22:51:59
LastEditors: JeanneWillis hi@jeannewillis.cn
LastEditTime: 2026-02-11 02:59:11
FilePath: /Differentiable-3D-Partitioner/partitioner/core/flow.py
Description: Flow for 3D Partitioner
'''
import torch
import numpy as np
import os
import random
import sys
import matplotlib.pyplot as plt

_project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_dreamplace_install_dir = os.path.join(_project_root, "thirdparty",
                                       "DREAMPlace", "install")
_dreamplace_package_dir = os.path.join(_dreamplace_install_dir, "dreamplace")
if "dreamplace" not in sys.modules:
    for _path in (_dreamplace_install_dir, _dreamplace_package_dir):
        if os.path.exists(_path) and _path not in sys.path:
            sys.path.insert(0, _path)
from partitioner.core.partitioner import Partitioner
from partitioner.utils.visualize import visualize_z_single
from partitioner.utils.tensor2txt import tensor2txt
from dreamplace.NesterovAcceleratedGradientOptimizer import \
    NesterovAcceleratedGradientOptimizer
import yaml
from pathlib import Path


class Differentiable3DPartitionerFlow:

    def __init__(self,
                 num_nodes,
                 num_nets,
                 num_pins,
                 node_pos,
                 pin_pos,
                 flat_net2pin_map,
                 flat_net2pin_start_map,
                 pin2node_map,
                 node_size_x,
                 node_size_y,
                 dreamplace_basic,
                 config_path="configs/default.yaml",
                 die_xl=None,
                 die_yl=None,
                 die_xh=None,
                 die_yh=None):
        self.num_nodes = num_nodes
        self.num_nets = num_nets
        self.num_pins = num_pins

        if isinstance(node_pos, torch.Tensor):
            self.device = node_pos.device
        else:
            self.device = torch.device(
                "cuda" if torch.cuda.is_available() else "cpu")

        self.node_pos = node_pos.to(self.device)
        self.pin_pos = pin_pos.to(self.device)
        self.flat_net2pin_map = (
            None if flat_net2pin_map is None else
            flat_net2pin_map.to(self.device).long())
        self.flat_net2pin_start_map = flat_net2pin_start_map.to(
            self.device).long()
        self.pin2node_map = pin2node_map.to(self.device).long()
        self.node_size_x = node_size_x[:num_nodes].to(self.device)
        self.node_size_y = node_size_y[:num_nodes].to(self.device)

        self.node_x = self.node_pos[:num_nodes]
        self.node_y = self.node_pos[self.node_pos.numel() // 2:self.
                                    node_pos.numel() // 2 + num_nodes]
        self.pin_pos_x = self.pin_pos[:self.pin2node_map.numel()]
        self.pin_pos_y = self.pin_pos[self.pin2node_map.numel():]

        self.project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.dreamplace_basic = dreamplace_basic
        self.die_xl = die_xl
        self.die_yl = die_yl
        self.die_xh = die_xh
        self.die_yh = die_yh
        self.config = self.load_config(config_path=config_path)
        self.set_random_seed()

    def set_random_seed(self):
        """
        Set all supported random seeds for reproducible runs.
        """
        if self.random_seed is None:
            return

        seed = int(self.random_seed)
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)

        if torch.cuda.is_available():
            torch.cuda.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False

    def load_config(self, config_path=None):
        """
        Load YAML configuration file
        """
        if config_path is None:
            config_path = self.project_root / "configs" / "default.yaml"

        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Extract flow-related parameters from configuration
        flow_config = config.get('flow', {})
        # Training parameters
        self.num_iterations = flow_config.get('num_iterations', 5000)
        self.random_seed = flow_config.get('random_seed')
        # Optimizer configuration
        optimizer_config = flow_config.get('optimizer', {})
        self.optimizer_name = optimizer_config.get('name', 'adam')
        self.learning_rate = optimizer_config.get('learning_rate', 0.1)
        self.optimizer_use_bb = optimizer_config.get('use_bb', True)
        # LSE smoothing alpha scheduling
        alpha_config = flow_config.get('lse_smoothing_alpha', {})
        self.alpha_start = alpha_config.get('start', 20.0)
        self.alpha_end = alpha_config.get('end', 20.0)

        # Cutsize Loss configuration
        cutsize_config = flow_config.get('cutsize_loss', {})
        self.use_cutsize_loss = cutsize_config.get('enabled', True)
        lambda_cut_config = cutsize_config.get('lambda_cut', {})
        self.lambda_cut_start = lambda_cut_config.get('start', 10.0)
        self.lambda_cut_end = lambda_cut_config.get('end', 10000.0)
        self.lambda_cut_gamma = lambda_cut_config.get('gamma', 0.2)

        # Balance Loss configuration
        balance_config = flow_config.get('balance_loss', {})
        self.use_balance_loss = balance_config.get('enabled', True)
        lambda_balance_config = balance_config.get('lambda_balance', {})
        self.lambda_balance_start = lambda_balance_config.get('start', 0.0)
        self.lambda_balance_end = lambda_balance_config.get('end', 5.0)
        self.lambda_balance_gamma = lambda_balance_config.get('gamma', 10.0)

        # Density Loss configuration
        density_config = flow_config.get('density_loss', {})
        self.use_density_loss = density_config.get('enabled', False)
        lambda_density_config = density_config.get('lambda_density', {})
        self.lambda_density_start = lambda_density_config.get('start', 0.0)
        self.lambda_density_end = lambda_density_config.get('end', 500.0)
        self.lambda_density_gamma = lambda_density_config.get('gamma', 1.0)
        self.lambda_density_peak = lambda_density_config.get(
            'peak', self.lambda_density_end)
        self.lambda_density_peak_ratio = lambda_density_config.get(
            'peak_ratio', None)
        self.lambda_density_gamma_up = lambda_density_config.get(
            'gamma_up', self.lambda_density_gamma)
        self.lambda_density_gamma_down = lambda_density_config.get(
            'gamma_down', self.lambda_density_gamma)

        # Wirelength Loss configuration
        wirelength_config = flow_config.get('wirelength_loss', {})
        self.lambda_wl = wirelength_config.get('lambda_wl', 1.0)

        # Visualization configuration
        viz_config = config.get('visualization', {})
        self.log_interval = viz_config.get('log_interval', 10)
        self.save_interval = viz_config.get('save_interval', 200)

        # Output configuration
        output_config = config.get('output', {})
        self.result_dir = output_config.get('result_dir')

        return config

    @torch.no_grad()
    def _compute_true_binary_metrics(self, model, binary_z):
        """Compute exact cutsize count and terminal-aware D2D HPWL."""
        net_indices = torch.arange(self.num_nets,
                                   device=self.device,
                                   dtype=torch.long)
        pin_pos_x = model.get_pin_pos_x()
        pin_pos_y = model.get_pin_pos_y()
        binary_z = binary_z.to(dtype=pin_pos_x.dtype)
        terminal_positions, cut_mask = model.compute_terminal_positions(
            net_indices,
            z=binary_z,
            pin_pos_x=pin_pos_x,
            pin_pos_y=pin_pos_y,
        )

        total_d2d_hpwl = 0.0
        for net_idx in range(self.num_nets):
            start_idx = int(self.flat_net2pin_start_map[net_idx].item())
            end_idx = int(self.flat_net2pin_start_map[net_idx + 1].item())
            if end_idx - start_idx < 2:
                continue

            if self.flat_net2pin_map is None:
                pin_indices = torch.arange(start_idx,
                                           end_idx,
                                           device=self.device,
                                           dtype=torch.long)
            else:
                pin_indices = self.flat_net2pin_map[start_idx:end_idx]
            node_indices = self.pin2node_map[pin_indices]
            pin_x = pin_pos_x[pin_indices]
            pin_y = pin_pos_y[pin_indices]
            is_top = binary_z[node_indices].bool()
            is_bottom = ~is_top

            net_hpwl = 0.0
            if is_top.any():
                top_x = pin_x[is_top]
                top_y = pin_y[is_top]
                if cut_mask[net_idx]:
                    top_x = torch.cat((top_x,
                                       terminal_positions[net_idx, 0].view(1)))
                    top_y = torch.cat((top_y,
                                       terminal_positions[net_idx, 1].view(1)))
                net_hpwl += float((top_x.max() - top_x.min() + top_y.max() -
                                   top_y.min()).item())

            if is_bottom.any():
                bottom_x = pin_x[is_bottom]
                bottom_y = pin_y[is_bottom]
                if cut_mask[net_idx]:
                    bottom_x = torch.cat(
                        (bottom_x, terminal_positions[net_idx, 0].view(1)))
                    bottom_y = torch.cat(
                        (bottom_y, terminal_positions[net_idx, 1].view(1)))
                net_hpwl += float((bottom_x.max() - bottom_x.min() +
                                   bottom_y.max() - bottom_y.min()).item())

            total_d2d_hpwl += net_hpwl

        return {
            'true_d2d_hpwl': total_d2d_hpwl,
            'true_cutsize': int(cut_mask.sum().item()),
        }

    def run(self):
        """
        main function for differentiable partitioner
        """
        print("=" * 60)
        print("Differentiable 3D Partitioner")
        print("=" * 60)

        # load real circuit data
        print("\n1. Load real circuit data...")

        print(f"   - Number of cells: {self.num_nodes}")
        print(f"   - Number of nets: {self.num_nets}")
        print(f"   - Number of pins: {self.num_pins}")
        if self.random_seed is not None:
            print(f"   - Random seed: {self.random_seed}")
        print(
            f"   - Coordinate range: x=[{self.pin_pos_x.min():.2f}, {self.pin_pos_x.max():.2f}], "
            f"y=[{self.pin_pos_y.min():.2f}, {self.pin_pos_y.max():.2f}]")

        # initialize partitioner
        print("\n2. Initialize partitioner...")
        partitioner_config = dict(self.config.get('partitioner') or {})
        partitioner_config.setdefault('gumbel_total_iterations',
                                      self.num_iterations)
        model = Partitioner(
            num_nodes=self.num_nodes,
            flat_net2pin_map=self.flat_net2pin_map,
            flat_net2pin_start_map=self.flat_net2pin_start_map,
            pin2node_map=self.pin2node_map,
            pin_pos_x=self.pin_pos_x,
            pin_pos_y=self.pin_pos_y,
            node_x=self.node_x,
            node_y=self.node_y,
            node_pos=self.node_pos,
            node_size_x=self.node_size_x,
            node_size_y=self.node_size_y,
            alpha=1.0,
            dreamplace_basic=self.dreamplace_basic,
            config=partitioner_config,
            die_xl=self.die_xl,
            die_xh=self.die_xh,
            die_yl=self.die_yl,
            die_yh=self.die_yh,
        )
        model = model.to(self.device)
        # Pin offsets are now owned by the model; the original concatenated
        # pin-position tensor is no longer needed for training.
        self.pin_pos = None
        self.pin_pos_x = None
        self.pin_pos_y = None
        self.node_pos = None
        self.node_x = None
        self.node_y = None
        print(f"   - Initial alpha: {model.alpha}")
        print(
            f"   - Gumbel tau schedule: {model.gumbel_tau_start:.4f} -> "
            f"{model.gumbel_tau_min:.4f} ({model.gumbel_anneal_mode})"
        )
        print(
            f"   - Gumbel warm start ends at iteration: "
            f"{model.gumbel_switch_iteration}"
        )
        print(
            "   - T gradient warm-up: "
            f"{model.t_grad_scale_start:.4f} until iter {model.t_grad_warmup_end}, "
            f"then linear to 1.0000 by iter {model.t_grad_ramp_end}"
        )
        print(
            f"   - Number of trainable parameters: {sum(p.numel() for p in model.get_trainable_parameters())}"
        )

        # print initial state
        print("\n3. Initial state:")
        use_debug_info = (self.use_cutsize_loss or self.use_balance_loss or
                          self.use_density_loss)
        with torch.no_grad():
            if use_debug_info:
                initial_loss, debug_info = model(
                    lambda_wl=self.lambda_wl,
                    lambda_cut=self.lambda_cut_start
                    if self.use_cutsize_loss else 0.0,
                    lambda_balance=self.lambda_balance_start
                    if self.use_balance_loss else 0.0,
                    lambda_density=self.lambda_density_start
                    if self.use_density_loss else 0.0,
                    return_debug_info=True)
                print(f"   - Initial total loss: {initial_loss.item():.4f}")
                print(f"   - Initial HPWL: {debug_info['L_WL']:.4f}")
                if self.use_cutsize_loss:
                    print(f"   - Initial cutsize: {debug_info['L_cut']:.4f}")
                if self.use_balance_loss:
                    print(f"   - Initial balance: {debug_info['L_balance']:.4f}")
                if self.use_density_loss:
                    print(f"   - Initial density: {debug_info['L_density']:.4f}")
            else:
                initial_loss = model()
                print(f"   - Initial total HPWL: {initial_loss.item():.4f}")
            stats = model.get_assignment_stats()
        print(
            f"   - z statistics: mean={stats['z_mean']:.4f}, std={stats['z_std']:.4f}"
        )
        print(
            f"   - Number of top cells: {stats['top_cells']}, number of bottom cells: {stats['bottom_cells']}"
        )
        del initial_loss, stats

        # set optimizer
        print("\n4. Set optimizer...")
        optimizer_name = self.optimizer_name.lower()
        nesterov_param = None
        if optimizer_name == "adam":
            optimizer = torch.optim.Adam(model.get_trainable_parameters(),
                                         lr=self.learning_rate)
        elif optimizer_name == "nesterov":
            nesterov_param = torch.nn.Parameter(
                model.pack_nesterov_parameters().to(self.device))
            optimizer = NesterovAcceleratedGradientOptimizer(
                [nesterov_param],
                lr=self.learning_rate,
                obj_and_grad_fn=model.obj_and_grad_fn,
                constraint_fn=model.nesterov_constraint_fn,
                use_bb=self.optimizer_use_bb)
            model.sync_from_nesterov_tensor(nesterov_param)
        else:
            raise ValueError(
                f"Unsupported optimizer: {self.optimizer_name}. "
                "Currently supported: adam, nesterov")

        print(f"   - Optimizer: {self.optimizer_name}")
        print(f"   - Learning rate: {self.learning_rate}")
        if optimizer_name == "nesterov":
            print(f"   - Use Barzilai-Borwein step: {self.optimizer_use_bb}")

        # training parameters
        alpha_schedule = np.linspace(self.alpha_start, self.alpha_end,
                                     self.num_iterations)

        # lambda_cut schedule (exponentially increase cutsize loss weight)
        if self.use_cutsize_loss:
            t = np.linspace(0.0, 1.0, self.num_iterations)
            lambda_cut_schedule = self.lambda_cut_start + \
                (self.lambda_cut_end - self.lambda_cut_start) * (t ** self.lambda_cut_gamma)
        else:
            lambda_cut_schedule = None

        # lambda_balance schedule (linear schedule for balance loss weight)
        if self.use_balance_loss:
            t = np.linspace(0.0, 1.0, self.num_iterations)
            lambda_balance_schedule = self.lambda_balance_start + \
                (self.lambda_balance_end - self.lambda_balance_start) * (t ** self.lambda_balance_gamma)
        else:
            lambda_balance_schedule = None

        # lambda_density schedule for density loss weight
        if self.use_density_loss:
            t = np.linspace(0.0, 1.0, self.num_iterations)
            if self.lambda_density_peak_ratio is None:
                lambda_density_schedule = self.lambda_density_start + \
                    (self.lambda_density_end - self.lambda_density_start) * (t ** self.lambda_density_gamma)
            else:
                peak_ratio = float(np.clip(self.lambda_density_peak_ratio,
                                           1e-6, 1.0 - 1e-6))
                lambda_density_schedule = np.empty_like(t)

                up_mask = t <= peak_ratio
                up_t = t[up_mask] / peak_ratio
                lambda_density_schedule[up_mask] = (
                    self.lambda_density_start +
                    (self.lambda_density_peak - self.lambda_density_start) *
                    (up_t ** self.lambda_density_gamma_up))

                down_mask = ~up_mask
                down_t = (t[down_mask] - peak_ratio) / (1.0 - peak_ratio)
                lambda_density_schedule[down_mask] = (
                    self.lambda_density_peak +
                    (self.lambda_density_end - self.lambda_density_peak) *
                    (down_t ** self.lambda_density_gamma_down))
        else:
            lambda_density_schedule = None

        # Plot schedule trends before breakpoint
        visualization_dir = os.path.join(
            self.project_root, self.config['visualization']['output_dir'], self.config['design']['name'])
        os.makedirs(visualization_dir, exist_ok=True)

        print(f"\n5. Start training ({self.num_iterations} iterations)...")
        print(f"   - Alpha schedule: {self.alpha_start} → {self.alpha_end}")
        if self.use_cutsize_loss:
            print(
                f"   - Cutsize loss enabled: λ_cut exponential schedule {self.lambda_cut_start} → {self.lambda_cut_end}, applied to {self.num_nets} nets"
            )
        else:
            print(f"   - Cutsize loss disabled")
        if self.use_balance_loss:
            print(
                f"   - Balance loss enabled: λ_balance linear schedule {self.lambda_balance_start} → {self.lambda_balance_end}"
            )
        else:
            print(f"   - Balance loss disabled")
        if self.use_density_loss:
            if self.lambda_density_peak_ratio is None:
                print(
                    f"   - Density loss enabled: λ_density schedule {self.lambda_density_start} → {self.lambda_density_end}"
                )
            else:
                print(
                    f"   - Density loss enabled: λ_density schedule {self.lambda_density_start} → "
                    f"{self.lambda_density_peak} → {self.lambda_density_end} "
                    f"(peak at {self.lambda_density_peak_ratio:.2f})"
                )
        else:
            print(f"   - Density loss disabled")
        print("-" * 60)

        # initialize lists to store training history
        history_loss = []
        history_hpwl = []
        history_cut = []
        history_balance = []
        history_density = []
        history_iterations = []

        # save initial state (iter=0) before optimization
        save_path_init = os.path.join(visualization_dir,
                                      'z_evolution_iter_0000.png')
        with torch.no_grad():
            z_init = model.get_z()
            visualize_z_single(model.node_x,
                               model.node_y,
                               z_init,
                               0,
                               save_path_init,
                               node_size_x=self.node_size_x,
                               node_size_y=self.node_size_y,
                               die_xl=self.die_xl,
                               die_yl=self.die_yl,
                               die_xh=self.die_xh,
                               die_yh=self.die_yh)
        del z_init
        print(f"   Initial state saved to: {save_path_init}")
        if self.device.type == 'cuda':
            torch.cuda.reset_peak_memory_stats(self.device)

        # training loop
        for iteration in range(self.num_iterations):
            # update current iteration (used to switch between sigmoid and gumbel_softmax)
            model.current_iteration = iteration
            model.alpha = alpha_schedule[iteration]

            # update lambda_cut (gradually increase cutsize loss weight)
            if self.use_cutsize_loss:
                lambda_cut = lambda_cut_schedule[iteration]
            else:
                lambda_cut = 0.0

            # update lambda_balance (gradually change balance loss weight)
            if self.use_balance_loss:
                lambda_balance = lambda_balance_schedule[iteration]
            else:
                lambda_balance = 0.0

            # update lambda_density (density loss weight)
            if self.use_density_loss:
                lambda_density = lambda_density_schedule[iteration]
            else:
                lambda_density = 0.0

            if nesterov_param is not None:
                model.sync_from_nesterov_tensor(nesterov_param)
                model.set_obj_and_grad_context(lambda_wl=self.lambda_wl,
                                               lambda_cut=lambda_cut,
                                               lambda_balance=lambda_balance,
                                               lambda_density=lambda_density)

            if nesterov_param is None:
                optimizer.zero_grad()
                if model.net_chunk_size > 0:
                    loss = model.backward_objective_in_net_chunks(
                        lambda_wl=self.lambda_wl,
                        lambda_cut=lambda_cut,
                        lambda_balance=lambda_balance,
                        lambda_density=lambda_density)
                    debug_info = model.get_last_loss_components()
                else:
                    if use_debug_info:
                        loss, debug_info = model(
                            lambda_wl=self.lambda_wl,
                            lambda_cut=lambda_cut,
                            lambda_balance=lambda_balance,
                            lambda_density=lambda_density,
                            return_debug_info=True)
                    else:
                        loss = model(lambda_wl=self.lambda_wl,
                                     lambda_cut=lambda_cut,
                                     lambda_balance=lambda_balance,
                                     lambda_density=lambda_density)
                        debug_info = model.get_last_loss_components()
                    loss.backward()
                model.scale_t_grad_()

                # calculate gradient statistics (for debugging)
                if model.t.grad is not None:
                    t_grad_norm = model.t.grad.norm().item()
                    # check if there are NaN or Inf gradients
                    if torch.isnan(model.t.grad).any() or torch.isinf(
                            model.t.grad).any():
                        print(
                            f"Warning: iteration {iteration+1} detected NaN/Inf gradients"
                        )
                else:
                    t_grad_norm = 0.0

                # update parameters
                optimizer.step()
                model.clamp_t_()
            else:
                loss, flat_grad = model.obj_and_grad_fn(nesterov_param)
                debug_info = model.get_last_loss_components()
                if model.t.grad is not None:
                    t_grad_norm = model.t.grad.norm().item()
                    if torch.isnan(model.t.grad).any() or torch.isinf(
                            model.t.grad).any():
                        print(
                            f"Warning: iteration {iteration+1} detected NaN/Inf gradients"
                        )
                else:
                    t_grad_norm = 0.0

                if torch.isnan(flat_grad).any() or torch.isinf(flat_grad).any():
                    print(
                        f"Warning: iteration {iteration+1} detected NaN/Inf gradients"
                    )
                if hasattr(optimizer, 'set_precomputed_obj_and_grad'):
                    optimizer.set_precomputed_obj_and_grad(loss, flat_grad)
                optimizer.step()
                model.sync_from_nesterov_tensor(nesterov_param)
                model.sync_to_nesterov_tensor(nesterov_param)

            # Record the objective evaluated at the pre-update point.  The
            # Nesterov path gets these values from its single gradient pass;
            # it no longer builds a separate diagnostic autograd graph.
            history_iterations.append(iteration + 1)
            history_loss.append(float(loss.item()))
            history_hpwl.append(debug_info.get('L_WL', float(loss.item())))
            history_cut.append(
                debug_info.get('L_cut', 0.0)
                if self.use_cutsize_loss else 0.0)
            history_balance.append(
                debug_info.get('L_balance', 0.0)
                if self.use_balance_loss else 0.0)
            history_density.append(
                debug_info.get('L_density', 0.0)
                if self.use_density_loss else 0.0)

            # print and visualize at specified intervals
            if (iteration + 1) % self.log_interval == 0 or iteration == 0:
                with torch.no_grad():
                    z = model.get_z()
                    dz_dt_norm = (z * (1 - z)).norm().item()
                    stats = model.get_assignment_stats()
                memory_str = ""
                if self.device.type == 'cuda':
                    allocated_gb = torch.cuda.memory_allocated(
                        self.device) / (1024**3)
                    peak_gb = torch.cuda.max_memory_allocated(
                        self.device) / (1024**3)
                    memory_str = (f" | CUDA alloc/peak: {allocated_gb:.2f}/"
                                  f"{peak_gb:.2f} GiB")

                if use_debug_info:
                    log_str = f"Iter {iteration+1:4d} | Loss: {loss.item():8.2f} | HPWL: {debug_info['L_WL']:8.2f}"
                    if self.use_cutsize_loss:
                        log_str += f" | Cut: {debug_info['L_cut']:6.4f} | λ_cut: {lambda_cut:6.4f}"
                    if self.use_balance_loss:
                        log_str += f" | Balance: {debug_info['L_balance']:6.4f} | λ_balance: {lambda_balance:6.4f}"
                    if self.use_density_loss:
                        log_str += f" | Density: {debug_info['L_density']:6.4f} | λ_den: {lambda_density:6.4f}"
                    log_str += f" | Alpha: {model.alpha:5.2f} | ||dt||: {t_grad_norm:6.4f} | Top: {stats['top_cells']:3d} | Bottom: {stats['bottom_cells']:3d}"
                    log_str += memory_str
                    print(log_str)
                else:
                    print(f"Iter {iteration+1:4d} | "
                          f"Loss: {loss.item():8.2f} | "
                          f"Alpha: {model.alpha:5.2f} | "
                          f"||dt||: {t_grad_norm:6.4f} | "
                          f"||dz/dt||: {dz_dt_norm:6.4f} | "
                          f"Top: {stats['top_cells']:3d} | "
                          f"Bottom: {stats['bottom_cells']:3d}"
                          f"{memory_str}")

            if (iteration + 1) % self.save_interval == 0 or iteration == 0:
                save_path = os.path.join(
                    visualization_dir,
                    f'z_evolution_iter_{iteration+1:04d}.png')
                with torch.no_grad():
                    z = model.get_z()
                    visualize_z_single(model.node_x,
                                       model.node_y,
                                       z,
                                       iteration + 1,
                                       save_path,
                                       node_size_x=self.node_size_x,
                                       node_size_y=self.node_size_y,
                                       die_xl=self.die_xl,
                                       die_yl=self.die_yl,
                                       die_xh=self.die_xh,
                                       die_yh=self.die_yh)
                del z

                fig, axes = plt.subplots(3, 2, figsize=(14, 12))

                # Plot Loss
                axes[0, 0].plot(history_iterations,
                                history_loss,
                                'b-',
                                linewidth=2,
                                label='Total Loss')
                axes[0, 0].set_xlabel('Iteration', fontsize=12)
                axes[0, 0].set_ylabel('Loss', fontsize=12)
                axes[0, 0].set_title('Training Loss',
                                     fontsize=14,
                                     fontweight='bold')
                axes[0, 0].grid(True, alpha=0.3)
                axes[0, 0].legend(fontsize=10)

                # Plot HPWL
                axes[0, 1].plot(history_iterations,
                                history_hpwl,
                                'g-',
                                linewidth=2,
                                label='HPWL')
                axes[0, 1].set_xlabel('Iteration', fontsize=12)
                axes[0, 1].set_ylabel('HPWL', fontsize=12)
                axes[0, 1].set_title('Half-Perimeter Wire Length',
                                     fontsize=14,
                                     fontweight='bold')
                axes[0, 1].grid(True, alpha=0.3)
                axes[0, 1].legend(fontsize=10)

                # Plot Cutsize
                if self.use_cutsize_loss and any(v > 0 for v in history_cut):
                    axes[1, 0].plot(history_iterations,
                                    history_cut,
                                    'r-',
                                    linewidth=2,
                                    label='Cutsize Loss')
                    axes[1, 0].set_xlabel('Iteration', fontsize=12)
                    axes[1, 0].set_ylabel('Cutsize Loss', fontsize=12)
                    axes[1, 0].set_title('Cutsize Loss',
                                         fontsize=14,
                                         fontweight='bold')
                    axes[1, 0].grid(True, alpha=0.3)
                    axes[1, 0].legend(fontsize=10)
                else:
                    axes[1, 0].text(0.5,
                                    0.5,
                                    'Cutsize Loss\nNot Enabled',
                                    ha='center',
                                    va='center',
                                    fontsize=12,
                                    transform=axes[1, 0].transAxes)
                    axes[1, 0].set_title('Cutsize Loss',
                                         fontsize=14,
                                         fontweight='bold')

                # Plot Balance
                if self.use_balance_loss and any(v > 0
                                                 for v in history_balance):
                    axes[1, 1].plot(history_iterations,
                                    history_balance,
                                    'm-',
                                    linewidth=2,
                                    label='Balance Loss')
                    axes[1, 1].set_xlabel('Iteration', fontsize=12)
                    axes[1, 1].set_ylabel('Balance Loss', fontsize=12)
                    axes[1, 1].set_title('Balance Loss',
                                         fontsize=14,
                                         fontweight='bold')
                    axes[1, 1].grid(True, alpha=0.3)
                    axes[1, 1].legend(fontsize=10)
                else:
                    axes[1, 1].text(0.5,
                                    0.5,
                                    'Balance Loss\nNot Enabled',
                                    ha='center',
                                    va='center',
                                    fontsize=12,
                                    transform=axes[1, 1].transAxes)
                    axes[1, 1].set_title('Balance Loss',
                                         fontsize=14,
                                         fontweight='bold')

                # Plot Density
                if self.use_density_loss and any(v > 0 for v in history_density):
                    axes[2, 0].plot(history_iterations,
                                    history_density,
                                    'c-',
                                    linewidth=2,
                                    label='Density Loss')
                    axes[2, 0].set_xlabel('Iteration', fontsize=12)
                    axes[2, 0].set_ylabel('Density Loss', fontsize=12)
                    axes[2, 0].set_title('Density Loss',
                                         fontsize=14,
                                         fontweight='bold')
                    axes[2, 0].grid(True, alpha=0.3)
                    axes[2, 0].legend(fontsize=10)
                else:
                    axes[2, 0].text(0.5,
                                    0.5,
                                    'Density Loss\nNot Enabled',
                                    ha='center',
                                    va='center',
                                    fontsize=12,
                                    transform=axes[2, 0].transAxes)
                    axes[2, 0].set_title('Density Loss',
                                         fontsize=14,
                                         fontweight='bold')
                axes[2, 1].axis('off')

                plt.tight_layout()
                curve_save_path = os.path.join(visualization_dir,
                                               'training_curves.png')
                plt.savefig(curve_save_path, dpi=150, bbox_inches='tight')
                print(f"   Training curves saved to: {curve_save_path}")
                plt.close()

        print("-" * 60)

        # final results
        print("\n6. Training completed, final results:")
        with torch.no_grad():
            if use_debug_info:
                final_loss, final_debug_info = model(
                    lambda_wl=self.lambda_wl,
                    lambda_cut=self.lambda_cut_end
                    if self.use_cutsize_loss else 0.0,
                    lambda_balance=self.lambda_balance_end
                    if self.use_balance_loss else 0.0,
                    lambda_density=self.lambda_density_end
                    if self.use_density_loss else 0.0,
                    return_debug_info=True)
                print(f"   - Final total loss: {final_loss.item():.4f}")
                print(f"   - Final HPWL: {final_debug_info['L_WL']:.4f}")
                if self.use_cutsize_loss:
                    print(
                        f"   - Final cutsize: {final_debug_info['L_cut']:.4f}")
                if self.use_balance_loss:
                    print(
                        f"   - Final balance: {final_debug_info['L_balance']:.4f}")
                if self.use_density_loss:
                    print(
                        f"   - Final density: {final_debug_info['L_density']:.4f}")
            else:
                final_loss = model(
                    lambda_balance=self.lambda_balance_end
                    if self.use_balance_loss else 0.0,
                    lambda_density=self.lambda_density_end
                    if self.use_density_loss else 0.0)
                print(f"   - Final total HPWL: {final_loss.item():.4f}")

        stats = model.get_assignment_stats()
        print(
            f"   - z statistics: mean={stats['z_mean']:.4f}, std={stats['z_std']:.4f}, "
            f"min={stats['z_min']:.4f}, max={stats['z_max']:.4f}")
        print(
            f"   - Number of top cells: {stats['top_cells']}, number of bottom cells: {stats['bottom_cells']}"
        )

        # get binary assignment
        binary_z = model.get_binary_assignment()
        true_binary_metrics = self._compute_true_binary_metrics(model, binary_z)
        print(
            f"   - Final true D2D HPWL (with terminals): {true_binary_metrics['true_d2d_hpwl']:.4f}"
        )
        print(
            f"   - Final true cutsize count: {true_binary_metrics['true_cutsize']}"
        )
        print(f"\n7. Binary assignment (threshold=0.5):")
        print(f"   - Number of top cells: {binary_z.sum().item()}")
        print(f"   - Number of bottom cells: {(1 - binary_z).sum().item()}")

        with torch.no_grad():
            z = model.get_z()
        print(f"\n8. Example soft assignment values (first 10 cells):")
        for i in range(min(10, self.num_nodes)):
            print(
                f"   Cell {i:3d} (x={model.node_x[i].item():.2f}, y={model.node_y[i].item():.2f}): z={z[i].item():.4f} → {'Top' if z[i] > 0.5 else 'Bottom'}"
            )

        print("\n" + "=" * 60)
        print("Done!")
        print("=" * 60)

        # Save results
        result_path = os.path.join(self.project_root, self.result_dir,
                                   self.config['design']['name'],
                                   'binary_assignment.pt')
        os.makedirs(os.path.dirname(result_path), exist_ok=True)
        torch.save(binary_z, result_path)
        print(f"   Binary assignment saved to: {result_path}")
        tensor2txt(binary_z, os.path.join(self.project_root, self.result_dir,
                                   self.config['design']['name'],
                                   'binary_assignment.txt'))
        final_metrics = {
            'design_name': self.config['design']['name'],
            'final_total_loss': float(final_loss.item()),
            'final_hpwl': float(final_debug_info['L_WL'])
            if use_debug_info else float(final_loss.item()),
            'final_cutsize': float(final_debug_info.get('L_cut', 0.0))
            if use_debug_info else 0.0,
            'final_balance': float(final_debug_info.get('L_balance', 0.0))
            if use_debug_info else 0.0,
            'final_density': float(final_debug_info.get('L_density', 0.0))
            if use_debug_info else 0.0,
            'top_cells': int(binary_z.sum().item()),
            'bottom_cells': int((1 - binary_z).sum().item()),
        }
        final_metrics.update(true_binary_metrics)
        return final_metrics


if __name__ == "__main__":
    print("Starting 3D Partitioner Flow...")
    differentiable_3d_partitioner_flow = Differentiable3DPartitionerFlow(
        num_nodes=2735,
        num_nets=2644,
        num_pins=8110,
        node_pos=torch.load(
            "benchmarks/tensor/iccad2022/case2_hidden/placement.pt").detach(),
        pin_pos=torch.load(
            "benchmarks/tensor/iccad2022/case2_hidden/pinpos.pt").detach(),
        flat_net2pin_map=torch.load(
            "benchmarks/tensor/iccad2022/case2_hidden/flat_net2pin_map.pt").
        detach(),
        flat_net2pin_start_map=torch.load(
            "benchmarks/tensor/iccad2022/case2_hidden/flat_net2pin_start_map.pt"
        ).detach(),
        pin2node_map=torch.load(
            "benchmarks/tensor/iccad2022/case2_hidden/pin2node_map.pt").detach(
            ),
        node_size_x=torch.load(
            "benchmarks/tensor/iccad2022/case2_hidden/node_size_x.pt").detach(
            ),
        node_size_y=torch.load(
            "benchmarks/tensor/iccad2022/case2_hidden/node_size_y.pt").detach(
            ),
    )
    differentiable_3d_partitioner_flow.run()
