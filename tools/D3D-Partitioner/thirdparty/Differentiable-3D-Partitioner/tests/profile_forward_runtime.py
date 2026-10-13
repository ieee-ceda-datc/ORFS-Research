"""
Profile runtime breakdown of the four forward operators in Partitioner
for an OpenROAD ASAP7 benchmark, and generate runtime charts.
"""
import argparse
import json
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import numpy as np
import matplotlib.pyplot as plt
from partitioner import DreamplaceParser, Differentiable3DPartitionerFlow
from partitioner.core.partitioner import Partitioner


def profile_forward(model, num_warmup=50, num_runs=200, device='cuda'):
    """Profile each forward operator independently."""
    lambda_wl = 1.0
    lambda_cut = 1.0
    lambda_balance = 1.0
    lambda_density = 1e-9

    model.current_iteration = 7000
    model.alpha = 20.0

    all_net_indices = model.all_net_indices

    def build_shared_inputs():
        z = model.get_z()
        pin_pos_x = model.get_pin_pos_x()
        pin_pos_y = model.get_pin_pos_y()
        return z, pin_pos_x, pin_pos_y

    # ---- Warmup ----
    print(f"Warming up ({num_warmup} iterations)...")
    for _ in range(num_warmup):
        model(lambda_wl=lambda_wl, lambda_cut=lambda_cut,
              lambda_balance=lambda_balance, lambda_density=lambda_density)
    if device == 'cuda':
        torch.cuda.synchronize()

    timings = {}

    z, pin_pos_x, pin_pos_y = build_shared_inputs()
    if device == 'cuda':
        torch.cuda.synchronize()

    # ---- 1. HPWL (compute_hpwl_batch with shared preprocess) ----
    print("Profiling HPWL...")
    if device == 'cuda':
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(num_runs):
        hpwl_top, hpwl_bottom = model.compute_hpwl_batch(
            all_net_indices,
            layer='both',
            z=z,
            pin_pos_x=pin_pos_x,
            pin_pos_y=pin_pos_y)
        total_hpwl = (model.net_weights * (hpwl_top + hpwl_bottom)).sum()
    if device == 'cuda':
        torch.cuda.synchronize()
    t1 = time.perf_counter()
    timings['HPWL'] = (t1 - t0) / num_runs

    # ---- 2. Cutsize (compute_cutsize_loss with shared preprocess) ----
    print("Profiling Cutsize...")
    if device == 'cuda':
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(num_runs):
        cutsize_loss = model.compute_cutsize_loss(
            z=z,
            pin_pos_x=pin_pos_x,
            pin_pos_y=pin_pos_y)
    if device == 'cuda':
        torch.cuda.synchronize()
    t1 = time.perf_counter()
    timings['Cutsize'] = (t1 - t0) / num_runs

    # ---- 3. Balance (compute_balance_loss with shared z) ----
    print("Profiling Balance...")
    if device == 'cuda':
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(num_runs):
        balance_loss = model.compute_balance_loss(z=z)
    if device == 'cuda':
        torch.cuda.synchronize()
    t1 = time.perf_counter()
    timings['Balance'] = (t1 - t0) / num_runs

    # ---- 4. Density (compute_density_loss) ----
    print("Profiling Density...")
    if device == 'cuda':
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(num_runs):
        density_loss = model.compute_density_loss()
    if device == 'cuda':
        torch.cuda.synchronize()
    t1 = time.perf_counter()
    timings['Density'] = (t1 - t0) / num_runs

    # ---- 5. Full forward (for reference) ----
    print("Profiling full forward...")
    if device == 'cuda':
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(num_runs):
        model(lambda_wl=lambda_wl, lambda_cut=lambda_cut,
              lambda_balance=lambda_balance, lambda_density=lambda_density)
    if device == 'cuda':
        torch.cuda.synchronize()
    t1 = time.perf_counter()
    timings['Full Forward'] = (t1 - t0) / num_runs

    return timings


def plot_pie_chart(timings, save_path, design, num_runs):
    """Generate a publication-quality pie chart of operator runtime breakdown."""
    operator_names = ['HPWL', 'Cutsize', 'Balance', 'Density']
    times = [timings[name] for name in operator_names]
    total_op_time = sum(times)
    other_time = max(0, timings['Full Forward'] - total_op_time)
    
    if other_time > 0.001 * total_op_time:
        labels = operator_names + ['Other']
        sizes = times + [other_time]
    else:
        labels = operator_names
        sizes = times

    total = sum(sizes)
    percentages = [s / total * 100 for s in sizes]

    colors = ['#FF9999', '#66B2FF', '#99FF99', '#FFCC99', '#FF99CC',
              '#99CCFF']
    colors = colors[:len(labels)]
    explode = [0.03] * len(labels)

    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': ['Times New Roman', 'DejaVu Serif'],
        'font.size': 12,
    })

    fig, ax = plt.subplots(figsize=(8, 6))

    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct='%1.1f%%',
        colors=colors,
        explode=explode,
        startangle=140,
        pctdistance=0.75,
        shadow=False,
        wedgeprops={'edgecolor': 'white', 'linewidth': 1.5},
    )

    for autotext in autotexts:
        autotext.set_fontsize(11)
        autotext.set_fontweight('bold')

    legend_labels = [
        f'{name}  ({t*1000:.2f} ms, {p:.1f}%)'
        for name, t, p in zip(labels, sizes, percentages)
    ]
    legend = ax.legend(wedges, legend_labels, title="Operators",
                       loc="center left", bbox_to_anchor=(1.0, 0, 0.5, 1),
                       prop={'size': 13, 'weight': 'bold'},
                       title_fontsize=14)
    legend.get_title().set_fontweight('bold')

    ax.set_title(f'Runtime Breakdown of Forward Operators\n({design})',
                 fontsize=14, fontweight='bold', pad=20)

    total_ms = timings['Full Forward'] * 1000
    info_text = (
        f'Total forward: {total_ms:.2f} ms\n'
        f'Measured over {num_runs} runs'
    )
    fig.text(0.02, 0.02, info_text, fontsize=9, fontstyle='italic',
             verticalalignment='bottom',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow',
                       alpha=0.8))

    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches='tight')
    print(f"Pie chart saved to: {save_path}")
    plt.close()


def plot_bar_chart(timings, save_path, design):
    """Generate a bar chart for detailed time comparison."""
    operator_names = ['HPWL', 'Cutsize', 'Balance', 'Density']
    times_ms = [timings[name] * 1000 for name in operator_names]

    colors = ['#FF9999', '#66B2FF', '#99FF99', '#FFCC99']

    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': ['Times New Roman', 'DejaVu Serif'],
        'font.size': 12,
    })

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(operator_names, times_ms, color=colors,
                  edgecolor='gray', linewidth=0.8)

    for bar, t in zip(bars, times_ms):
        ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.1,
                f'{t:.2f} ms', ha='center', va='bottom', fontsize=11,
                fontweight='bold')

    ax.set_ylabel('Time (ms)', fontsize=13)
    ax.set_title(f'Per-Operator Forward Runtime ({design})',
                 fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)

    full_fwd = timings['Full Forward'] * 1000
    ax.axhline(y=full_fwd, color='red', linestyle='--', alpha=0.7,
               label=f'Full Forward: {full_fwd:.2f} ms')
    legend = ax.legend(prop={'size': 13, 'weight': 'bold'})
    for text in legend.get_texts():
        text.set_fontweight('bold')

    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches='tight')
    print(f"Bar chart saved to: {save_path}")
    plt.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description='Profile forward-operator runtime breakdown.')
    parser.add_argument('--design', default='swerv_wrapper',
                        help='ASAP7 benchmark design name.')
    parser.add_argument('--num-warmup', type=int, default=50,
                        help='Warmup iterations before profiling.')
    parser.add_argument('--num-runs', type=int, default=200,
                        help='Measured runs per operator.')
    return parser.parse_args()


def _prepare_dreamplace_config(config_path, use_gpu):
    if use_gpu:
        return config_path, None

    with open(config_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    payload['gpu'] = 0

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    with tmp:
        json.dump(payload, tmp, indent=2)
    return tmp.name, tmp.name


def main():
    args = parse_args()
    design = args.design
    dreamplace_config = f"benchmarks/lefdef/asap7/{design}/dreamplace.json"
    config_path = f"configs/openroad/asap7/{design}.yaml"

    print("=" * 60)
    print("Runtime Profiling: Forward Operator Breakdown")
    print(f"Design: {design}")
    print("=" * 60)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"   Device: {device}")
    if device == 'cuda':
        print(f"   GPU: {torch.cuda.get_device_name(0)}")

    runtime_dreamplace_config, temp_config = _prepare_dreamplace_config(
        dreamplace_config, use_gpu=(device == 'cuda'))

    print("\n1. Parsing design with DREAMPlace...")
    parser = DreamplaceParser()
    try:
        parser.parse_design(runtime_dreamplace_config)
    finally:
        if temp_config is not None:
            os.unlink(temp_config)
    print(f"   Nodes: {parser.num_nodes}, Nets: {parser.num_nets}, Pins: {parser.num_pins}")

    print("\n2. Building Partitioner model...")
    import yaml
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    partitioner_config = dict(config.get('partitioner') or {})
    partitioner_config.setdefault('gumbel_total_iterations',
                                  config['flow']['num_iterations'])

    node_pos = parser.node_pos.to(device)
    num_nodes = parser.num_nodes
    pin_pos = parser.pin_pos.to(device) if parser.pin_pos is not None else None

    node_x = node_pos[:num_nodes]
    node_y = node_pos[node_pos.numel() // 2: node_pos.numel() // 2 + num_nodes]
    pin2node_map = parser.pin2node_map.to(device).long()
    pin_pos_x = pin_pos[:pin2node_map.numel()]
    pin_pos_y = pin_pos[pin2node_map.numel():]

    model = Partitioner(
        num_nodes=num_nodes,
        flat_net2pin_map=parser.flat_net2pin_map.to(device).long(),
        flat_net2pin_start_map=parser.flat_net2pin_start_map.to(device).long(),
        pin2node_map=pin2node_map,
        pin_pos_x=pin_pos_x,
        pin_pos_y=pin_pos_y,
        node_x=node_x,
        node_y=node_y,
        node_pos=node_pos,
        node_size_x=parser.node_size_x[:num_nodes].to(device),
        node_size_y=parser.node_size_y[:num_nodes].to(device),
        alpha=5.0,
        dreamplace_basic=parser.dreamplace_basic,
        config=partitioner_config,
    ).to(device)
    print(f"   Model created with {sum(p.numel() for p in model.parameters())} parameters")

    print("\n3. Profiling operators...")
    timings = profile_forward(model,
                              num_warmup=args.num_warmup,
                              num_runs=args.num_runs,
                              device=device)

    print("\n" + "=" * 60)
    print("Results:")
    print("=" * 60)
    for name, t in timings.items():
        print(f"  {name:20s}: {t*1000:8.3f} ms")

    op_names = ['HPWL', 'Cutsize', 'Balance', 'Density']
    op_total = sum(timings[n] for n in op_names)
    print(f"\n  {'Sum of 4 ops':20s}: {op_total*1000:8.3f} ms")
    print(f"  {'Full Forward':20s}: {timings['Full Forward']*1000:8.3f} ms")

    print("\nPercentage breakdown (among 4 operators):")
    for name in op_names:
        pct = timings[name] / op_total * 100
        print(f"  {name:20s}: {pct:5.1f}%")

    output_dir = os.path.join("results", "visualizations", design)
    os.makedirs(output_dir, exist_ok=True)

    pie_path = os.path.join(output_dir, "runtime_breakdown_pie.png")
    bar_path = os.path.join(output_dir, "runtime_breakdown_bar.png")

    print("\n4. Generating plots...")
    plot_pie_chart(timings, pie_path, design, args.num_runs)
    plot_bar_chart(timings, bar_path, design)

    print("\nDone!")


if __name__ == "__main__":
    main()
