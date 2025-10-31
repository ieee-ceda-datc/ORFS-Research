#!/usr/bin/env python3
"""
Stage-level optimization driver for OpenROAD Flow Scripts.

This tool executes the OpenROAD flow one stage at a time (synth → floorplan → place → cts → route → finish),
collects the resulting metrics/logs, and queries the existing ReAct framework to recommend
stage-local parameter tuning.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from optimize import (
    OptimizationWorkflow,
    process_log_file,
)


@dataclass
class StageDefinition:
    """Metadata describing how to run and analyse a single flow stage."""

    name: str
    make_target: str
    log_prefix: str
    description: str
    parameter_keys: List[str] = field(default_factory=list)


# Mapping between parameter identifiers used in OptimizationWorkflow and their make/env names.
PARAM_TO_ENV_VAR = {
    "synth_flatten": "SYNTH_FLATTEN",
    "core_util": "CORE_UTILIZATION",
    "cell_pad_global": "CELL_PAD_IN_SITES_GLOBAL_PLACEMENT",
    "cell_pad_detail": "CELL_PAD_IN_SITES_DETAIL_PLACEMENT",
    "lb_addon": "PLACE_DENSITY_LB_ADDON",
    "enable_dpo": "ENABLE_DPO",
    "pin_layer": "PIN_LAYER_ADJUST",
    "above_layer": "ABOVE_LAYER_ADJUST",
    "tns": "TNS_END_PERCENT",
    "cts_size": "CTS_CLUSTER_SIZE",
    "cts_diameter": "CTS_CLUSTER_DIAMETER",
}


def _stage_definitions() -> List[StageDefinition]:
    """Return the default stage ordering and configuration."""
    return [
        StageDefinition(
            name="synth",
            make_target="do-synth",
            log_prefix="1_",
            description="Logic synthesis using Yosys; focus on timing slack and area metrics.",
            parameter_keys=["synth_flatten"],
        ),
        StageDefinition(
            name="floorplan",
            make_target="do-floorplan",
            log_prefix="2_",
            description="Macro and core floorplanning; adjust area utilization and pin placement.",
            parameter_keys=[
                "core_util",
                "cell_pad_global",
                "cell_pad_detail",
                "lb_addon",
            ],
        ),
        StageDefinition(
            name="place",
            make_target="do-place",
            log_prefix="3_",
            description="Global/detail placement; tune density, legalization and detail placement options.",
            parameter_keys=[
                "lb_addon",
                "enable_dpo",
                "pin_layer",
                "above_layer",
            ],
        ),
        StageDefinition(
            name="cts",
            make_target="do-cts",
            log_prefix="4_",
            description="Clock-tree synthesis (CTS); control cluster sizing and clock routing targets.",
            parameter_keys=[
                "cts_size",
                "cts_diameter",
            ],
        ),
        StageDefinition(
            name="route",
            make_target="do-route",
            log_prefix="5_",
            description="Global and detailed routing; focus on timing violations and routing congestion.",
            parameter_keys=[
                "pin_layer",
                "above_layer",
                "tns",
            ],
        ),
        StageDefinition(
            name="finish",
            make_target="do-finish",
            log_prefix="6_",
            description="Fill, reporting and final sign-off data generation.",
            parameter_keys=[],
        ),
    ]


class StageOptimizationDriver:
    """Coordinates per-stage execution, log aggregation, and ReAct-based recommendations."""

    def __init__(
        self,
        platform: str,
        design: str,
        objective: str,
        stages: Optional[Iterable[str]] = None,
        max_react_steps: int = 3,
        temperature: float = 0.1,
        workdir: Optional[Path] = None,
        dry_run: bool = False,
    ) -> None:
        self.workdir = Path(workdir or os.getcwd())
        self.platform = platform
        self.design = design
        self.objective = objective.upper()
        self.max_react_steps = max_react_steps
        self.temperature = temperature
        self.dry_run = dry_run

        # Reuse existing workflow components (embeddings, constraints, ReAct client, etc.).
        self.workflow = OptimizationWorkflow(platform, design, objective)
        self.react = self.workflow.react_framework
        self.initial_params = self.workflow.initial_params
        self.param_constraints = self.workflow.param_constraints

        # Track per-stage overrides/recommendations.
        self.stage_overrides: Dict[str, Dict[str, Any]] = {}
        self.stage_recommendations: Dict[str, Dict[str, Any]] = {}

        stage_list = _stage_definitions()
        if stages:
            stage_filter = {name.lower() for name in stages}
            stage_list = [sd for sd in stage_list if sd.name.lower() in stage_filter]
            missing = stage_filter.difference({sd.name.lower() for sd in stage_list})
            if missing:
                raise ValueError(f"Unknown stages requested: {', '.join(sorted(missing))}")

        self.stage_sequence = stage_list

    # ------------------------------------------------------------------ CLI helpers
    def run(self) -> None:
        for stage in self.stage_sequence:
            self._execute_stage(stage)

        self._print_summary()

    # ------------------------------------------------------------------ Execution
    def _execute_stage(self, stage: StageDefinition) -> None:
        print(f"\n=== Stage: {stage.name.upper()} ===")
        print(stage.description)

        overrides = self.stage_overrides.get(stage.name, {})
        if overrides:
            print("Applying overrides:", " ".join(f"{k}={v}" for k, v in overrides.items()))

        command = ["make", stage.make_target]
        for env_var, value in overrides.items():
            command.append(f"{env_var}={value}")

        if self.dry_run:
            print("(dry-run) Skipping execution:", " ".join(command))
        else:
            print("Running:", " ".join(command))
            try:
                subprocess.run(
                    command,
                    cwd=self.workdir,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                print(f"[ERROR] Stage '{stage.name}' execution failed with exit code {exc.returncode}")
                raise

        stage_data = self._collect_stage_data(stage)
        parameter_info = self._get_stage_parameter_info(stage)

        if not parameter_info:
            print("No adjustable parameters registered for this stage; skipping ReAct recommendation.")
            return

        react_prompt = self._build_stage_prompt(stage, stage_data, parameter_info)
        tools = self._build_stage_tools(stage_data, parameter_info)

        print("[INFO] Requesting ReAct recommendations...")
        react_result = self.react.run_react_cycle(
            initial_prompt=react_prompt,
            available_tools=tools,
            max_steps=self.max_react_steps,
            temperature=self.temperature,
        )

        final_answer = react_result.get("final_answer", "")
        recommendations = self._parse_stage_recommendations(stage, final_answer, parameter_info)
        if recommendations:
            self.stage_recommendations[stage.name] = recommendations
            print("[INFO] Recommended adjustments:")
            for env_var, value in recommendations.items():
                print(f"  - {env_var} := {value}")
        else:
            print("[WARN] No actionable recommendations parsed from ReAct response.")

    # ------------------------------------------------------------------ Data aggregation
    def _collect_stage_data(self, stage: StageDefinition) -> Dict[str, Any]:
        log_dir = self.workdir / "logs"
        log_files = sorted(log_dir.glob(f"{stage.log_prefix}*.log"))
        json_files = sorted(log_dir.glob(f"{stage.log_prefix}*.json"))

        log_summaries = []
        aggregated_metrics: Dict[str, List[float]] = {}
        errors: List[str] = []

        for log_file in log_files:
            summary = process_log_file(str(log_file))
            summary["path"] = str(log_file)
            log_summaries.append(summary)

            for metric_name, value in summary.get("metrics", {}).items():
                try:
                    aggregated_metrics.setdefault(metric_name, []).append(float(value))
                except (TypeError, ValueError):
                    continue

            errors.extend(summary.get("errors", []))

        aggregated = {
            metric: {
                "mean": statistics.mean(values) if values else None,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "latest": values[-1] if values else None,
                "samples": len(values),
            }
            for metric, values in aggregated_metrics.items()
        }

        json_payloads: List[Tuple[str, Any]] = []
        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                json_payloads.append((str(json_file), data))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Failed to parse {json_file}: {exc}")

        recent_log_snippet = ""
        if log_files:
            recent_log_snippet = self._tail_file(log_files[-1], max_lines=40)

        return {
            "logs": log_summaries,
            "metrics": aggregated,
            "json": json_payloads,
            "errors": errors,
            "recent_log_snippet": recent_log_snippet,
        }

    def _get_stage_parameter_info(self, stage: StageDefinition) -> List[Dict[str, Any]]:
        info: List[Dict[str, Any]] = []
        for param_key in stage.parameter_keys:
            env_var = PARAM_TO_ENV_VAR.get(param_key)
            constraint = self.param_constraints.get(param_key)
            if env_var is None or constraint is None:
                continue

            current_value = self._current_env_value(stage.name, env_var, constraint)
            info.append(
                {
                    "param_key": param_key,
                    "env_var": env_var,
                    "type": constraint.get("type"),
                    "range": constraint.get("range"),
                    "current_value": current_value,
                }
            )

        return info

    # ------------------------------------------------------------------ Prompt + tools
    def _build_stage_prompt(
        self,
        stage: StageDefinition,
        stage_data: Dict[str, Any],
        parameter_info: List[Dict[str, Any]],
    ) -> str:
        metrics_lines = []
        for name, stats in stage_data["metrics"].items():
            metrics_lines.append(
                f"- {name}: latest={stats['latest']} mean={stats['mean']} min={stats['min']} max={stats['max']} (samples={stats['samples']})"
            )
        metrics_text = "\n".join(metrics_lines) if metrics_lines else "No metrics captured for this stage."

        parameters_text = json.dumps(parameter_info, indent=2)

        errors_text = "\n".join(stage_data.get("errors", [])) or "No errors captured."
        log_tail = stage_data.get("recent_log_snippet", "").strip() or "(no log excerpt available)"

        prompt = textwrap.dedent(
            f"""
            You are assisting with stage-specific optimization of the OpenROAD flow.

            Stage: {stage.name.upper()}
            Platform: {self.platform}
            Design: {self.design}
            Objective: {self.objective}

            Stage description:
            {stage.description}

            Recent metrics:
            {metrics_text}

            Errors (if any):
            {errors_text}

            Recent log excerpt:
            ```
            {log_tail}
            ```

            Adjustable parameters for this stage (env vars with ranges and current values):
            {parameters_text}

            Requirements:
            - Suggest updated values only for the listed parameters.
            - Keep all values within the specified ranges and respect their types.
            - Focus on improving the stage metrics relevant to the {self.objective} objective.
            - Return concise recommendations ready to be passed back to `make` as VAR=value overrides.

            Final Answer format (must be JSON):
            Final Answer: {{"parameters": {{"ENV_VAR": value, ...}}, "notes": "short justification"}}
            """
        ).strip()
        return prompt

    def _build_stage_tools(
        self,
        stage_data: Dict[str, Any],
        parameter_info: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "list_parameters": lambda _: json.dumps(parameter_info, indent=2),
            "show_metrics": lambda _: json.dumps(stage_data.get("metrics", {}), indent=2),
            "show_errors": lambda _: "\n".join(stage_data.get("errors", [])) or "No errors recorded.",
            "show_log_tail": lambda _: stage_data.get("recent_log_snippet", "") or "No log excerpt.",
        }

    # ------------------------------------------------------------------ Parsing + helpers
    def _parse_stage_recommendations(
        self,
        stage: StageDefinition,
        final_answer: str,
        parameter_info: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not final_answer or "Final Answer" not in final_answer:
            return {}

        match = re.search(r"\{.*\}", final_answer, re.DOTALL)
        if not match:
            return {}

        try:
            payload = json.loads(match.group())
        except json.JSONDecodeError:
            return {}

        raw_params = payload.get("parameters", payload)
        if not isinstance(raw_params, dict):
            return {}

        valid_envs = {info["env_var"] for info in parameter_info}
        key_to_env = {info["param_key"]: info["env_var"] for info in parameter_info}
        recommendations: Dict[str, Any] = {}

        for key, value in raw_params.items():
            env_var = key if key in valid_envs else key_to_env.get(key.lower()) or key_to_env.get(key)
            if env_var not in valid_envs:
                continue

            constraint = self._constraint_for_env(env_var, parameter_info)
            coerced = self._coerce_to_constraint(value, constraint)
            if coerced is not None:
                recommendations[env_var] = coerced

        return recommendations

    def _constraint_for_env(self, env_var: str, parameter_info: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for info in parameter_info:
            if info["env_var"] == env_var:
                return {
                    "type": info.get("type"),
                    "range": info.get("range"),
                }
        return None

    def _coerce_to_constraint(self, value: Any, constraint: Optional[Dict[str, Any]]) -> Optional[Any]:
        if constraint is None:
            return value

        value_type = constraint.get("type")
        value_range = constraint.get("range")

        try:
            if value_type == "int":
                coerced: Any = int(round(float(value)))
            elif value_type == "float":
                coerced = float(value)
            else:
                coerced = value
        except (TypeError, ValueError):
            return None

        if value_range and len(value_range) == 2:
            min_val, max_val = value_range
            if isinstance(coerced, (int, float)):
                coerced = max(min_val, min(max_val, coerced))

        return coerced

    def _current_env_value(self, stage_name: str, env_var: str, constraint: Dict[str, Any]) -> Any:
        if stage_name in self.stage_overrides and env_var in self.stage_overrides[stage_name]:
            return self.stage_overrides[stage_name][env_var]

        raw_value = self.initial_params.get(env_var)
        if raw_value is None:
            raw_value = os.environ.get(env_var)

        if raw_value is None:
            return None

        return self._coerce_to_constraint(raw_value, constraint)

    @staticmethod
    def _tail_file(path: Path, max_lines: int = 40) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            return "".join(lines[-max_lines:])
        except OSError:
            return ""

    def _print_summary(self) -> None:
        if not self.stage_recommendations:
            print("\nNo stage recommendations were produced.")
            return

        print("\n=== Stage Recommendations Summary ===")
        for stage_name, params in self.stage_recommendations.items():
            print(f"{stage_name.upper()}:")
            for env_var, value in params.items():
                print(f"  - {env_var} := {value}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run stage-by-stage optimization flow with ReAct recommendations.",
    )
    parser.add_argument("platform", help="PDK/platform name (e.g. asap7, sky130hd).")
    parser.add_argument("design", help="Design name (e.g. aes, ibex).")
    parser.add_argument("objective", help="Optimization objective (ECP, DWL, COMBO).")
    parser.add_argument(
        "--stages",
        nargs="+",
        default=None,
        help="Subset of stages to run (default: all). Options: synth floorplan place cts route finish.",
    )
    parser.add_argument(
        "--max-react-steps",
        type=int,
        default=3,
        help="Maximum reasoning steps for the ReAct loop.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Sampling temperature for the LLM.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the make commands without executing them.",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    driver = StageOptimizationDriver(
        platform=args.platform,
        design=args.design,
        objective=args.objective,
        stages=args.stages,
        max_react_steps=args.max_react_steps,
        temperature=args.temperature,
        dry_run=args.dry_run,
    )
    driver.run()


if __name__ == "__main__":
    main()

