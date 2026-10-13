#!/usr/bin/env python3
"""Run D2D/D3D and emit a name-bearing, tool-neutral assignment JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Sequence

import yaml


CASE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
DEFAULTS_FILE = Path(__file__).resolve().parent / "config" / "d2d_cpu_defaults.json"
D3D_PARTITIONER_NAMES = frozenset(
    {
        "d3d",
        "d3d-partitioner",
        "d3d_partitioner",
        "differentiable-3d-partitioner",
        "differentiable_3d_partitioner",
        "differentiable3d",
        "differentiable3dpartitioner",
    }
)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def expand_environment(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [expand_environment(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_environment(item) for key, item in value.items()}
    return value


def decode_node_name(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    return str(value)


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} is not a readable file: {path}")


def validate_d3d_partitioner(params: dict[str, Any]) -> None:
    partitioner = str(params.get("partitioner", "")).strip().lower()
    if partitioner not in D3D_PARTITIONER_NAMES:
        raise ValueError(
            "D3D partition driver requires template field "
            f"'partitioner' to select Differentiable-3D-Partitioner; got "
            f"{params.get('partitioner')!r}"
        )


def apply_d2d_bin_config(
    params: dict[str, Any], d3d_config: dict[str, Any]
) -> None:
    """Apply the design-specific DREAMPlace bin grid from the TaiWei YAML."""
    d2d_config = d3d_config.get("d2d")
    if d2d_config is None:
        return
    if not isinstance(d2d_config, dict):
        raise ValueError("D3D config field 'd2d' must be a YAML mapping")

    allowed_keys = {"num_bins_x", "num_bins_y", "global_place_stages"}
    unknown_keys = sorted(set(d2d_config) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"unsupported D3D config d2d field(s): {unknown_keys}")

    missing_keys = sorted({"num_bins_x", "num_bins_y"} - set(d2d_config))
    if missing_keys:
        raise ValueError(f"D3D config d2d is missing field(s): {missing_keys}")

    stages = d2d_config.get("global_place_stages")
    if (
        not isinstance(stages, list)
        or len(stages) != 1
        or not isinstance(stages[0], dict)
    ):
        raise ValueError(
            "D3D config d2d.global_place_stages must contain exactly one mapping"
        )
    missing_stage_keys = sorted({"num_bins_x", "num_bins_y"} - set(stages[0]))
    if missing_stage_keys:
        raise ValueError(
            "D3D config d2d.global_place_stages[0] is missing field(s): "
            f"{missing_stage_keys}"
        )

    bin_values = (
        d2d_config["num_bins_x"],
        d2d_config["num_bins_y"],
        stages[0]["num_bins_x"],
        stages[0]["num_bins_y"],
    )
    if any(type(value) is not int or value <= 0 for value in bin_values):
        raise ValueError(
            "all four D3D config d2d bin values must be positive integers"
        )
    if len(set(bin_values)) != 1:
        raise ValueError("all four D3D config d2d bin values must be identical")

    params["num_bins_x"] = bin_values[0]
    params["num_bins_y"] = bin_values[1]
    default_stages = params.get("global_place_stages")
    if (
        not isinstance(default_stages, list)
        or not default_stages
        or not isinstance(default_stages[0], dict)
    ):
        raise ValueError("internal D2D defaults have no global placement stage")
    default_stages[0]["num_bins_x"] = bin_values[2]
    default_stages[0]["num_bins_y"] = bin_values[3]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--case-name", required=True)
    parser.add_argument("--def", dest="def_path", required=True, type=Path)
    parser.add_argument("--verilog", required=True, type=Path)
    parser.add_argument("--sdc", required=True, type=Path)
    parser.add_argument("--lef", action="append", required=True, type=Path)
    parser.add_argument("--num-threads", type=int, default=8)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    for path, label in (
        (DEFAULTS_FILE, "internal D2D defaults"),
        (args.config, "D3D YAML config"),
        (args.def_path, "DEF"),
        (args.verilog, "Verilog"),
        (args.sdc, "SDC"),
    ):
        require_file(path, label)
    for lef_path in args.lef:
        require_file(lef_path, "LEF")
    if args.num_threads <= 0:
        raise ValueError(f"num-threads must be positive: {args.num_threads}")
    if not CASE_NAME.fullmatch(args.case_name):
        raise ValueError(
            "case name may contain only letters, digits, underscore, dot, and dash: "
            f"{args.case_name!r}"
        )

    runtime_root = args.runtime_root.resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    os.environ["D2D_RUNTIME_ROOT"] = str(runtime_root)

    d3d_config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if not isinstance(d3d_config, dict):
        raise ValueError(f"D3D config must contain a YAML mapping: {args.config}")
    runtime_config_root = runtime_root / "d3d_config"
    runtime_d3d_config = runtime_config_root / f"{args.case_name}.yaml"
    algorithm_config = dict(d3d_config)
    algorithm_config.pop("d2d", None)
    atomic_write(
        runtime_d3d_config,
        yaml.safe_dump(algorithm_config, sort_keys=False),
    )

    params = json.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
    if not isinstance(params, dict):
        raise ValueError(f"internal defaults must contain a JSON object: {DEFAULTS_FILE}")
    params = expand_environment(params)
    validate_d3d_partitioner(params)
    apply_d2d_bin_config(params, d3d_config)
    params.update(
        {
            "partitioner": "d3d",
            "gpu": 0,
            "differentiable_partitioner_config_root": str(
                runtime_config_root.resolve()
            ),
            "input_format": "lefdef",
            "lef_input": [str(path.resolve()) for path in args.lef],
            "def_input": str(args.def_path.resolve()),
            "verilog_input": str(args.verilog.resolve()),
            # The current D2D implementation records this path for handoff
            # provenance; it does not parse SDC timing constraints.
            "sdc_input": str(args.sdc.resolve()),
            "num_threads": args.num_threads,
        }
    )
    runtime_config = runtime_root / f"{args.case_name}.json"
    atomic_write(runtime_config, json.dumps(params, indent=2, sort_keys=True) + "\n")

    try:
        from placer.d2d_placer import D2Dplacer, init_log
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "installed D2D package is unavailable; put its install prefix and "
            "<prefix>/placer on PYTHONPATH"
        ) from error

    flow = D2Dplacer(str(runtime_config))
    logger = init_log(flow.params.result_dir_root)
    logger.info("D2D/D3D partition: init_spec -> flatten_2d_place -> partition")
    flow.init_spec()
    flow.flatten_2d_place()
    flow.partition(logger)

    placedb = flow.dreamplace.dp_2d.placedb
    movable_count = int(placedb.num_movable_nodes)
    node_names = [
        decode_node_name(name) for name in placedb.node_names[:movable_count]
    ]
    tier_values = [
        int(value) for value in flow.tier.detach().cpu().reshape(-1).tolist()
    ]
    if movable_count != len(node_names) or movable_count != len(tier_values):
        raise ValueError(
            "D2D movable/name/assignment length mismatch: "
            f"{movable_count}/{len(node_names)}/{len(tier_values)}"
        )
    if len(node_names) != len(set(node_names)):
        raise ValueError("D2D assignment contains duplicate node names")
    invalid_tiers = sorted(set(tier_values) - {0, 1})
    if invalid_tiers:
        raise ValueError(f"D2D assignment contains invalid tier values: {invalid_tiers}")

    result = {
        "schema": "orfs.d3d-partition.assignment",
        "schema_version": 1,
        "case_name": args.case_name,
        "movable_count": movable_count,
        "runtime_config": str(runtime_config),
        "d3d_config": str(runtime_d3d_config),
        "device_mode": "cpu",
        "assignments": [
            {"node": name, "tier": tier}
            for name, tier in zip(node_names, tier_values)
        ],
    }
    atomic_write(args.output, json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        "D3D_PARTITION_DRIVER_COMPLETE "
        f"movable_nodes={movable_count} tier0={tier_values.count(0)} "
        f"tier1={tier_values.count(1)} output={args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"error: {error}")
