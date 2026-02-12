#!/usr/bin/env python3
import argparse
import os
import signal
import socket
import subprocess
import sys
import re
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

# ==============================================================================
# Safety: signals + process-group kill
# ==============================================================================

def _install_signal_handlers():
    def _handler(signum, frame):
        raise KeyboardInterrupt()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass

def _run_command_with_log(
    cmd: Sequence[str],
    log_path: Path,
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    preexec = getattr(os, "setsid", None)
    with open(log_path, "w") as log_file:
        proc = subprocess.Popen(
            list(cmd),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(cwd) if cwd else None,
            preexec_fn=preexec,
            env=env,
        )
        try:
            ret = proc.wait()
            if ret != 0:
                raise subprocess.CalledProcessError(ret, list(cmd))
        except KeyboardInterrupt:
            try:
                if preexec and hasattr(os, "killpg"):
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    proc.terminate()
            except Exception:
                pass
            raise
        except Exception:
            try:
                if preexec and hasattr(os, "killpg"):
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    proc.terminate()
            except Exception:
                pass
            raise

# ==============================================================================
# Metrics Extraction
# ==============================================================================

def extract_metrics(cfg: 'RunConfig') -> Optional[dict]:
    """解析 OpenROAD 报告以提取关键 CI 指标"""
    report_base = cfg.repo_root / "reports" / cfg.tech / cfg.case / "openroad"
    finish_rpt = report_base / "6_finish.rpt"
    drc_rpt = report_base / "5_route_drc.rpt"

    metrics = {
        "tech": cfg.tech,
        "case": cfg.case,
        "wns": "N/A",
        "tns": "N/A",
        "power_watts": "N/A",
        "drc_count": "0"
    }

    if finish_rpt.exists():
        try:
            content = finish_rpt.read_text()
            # 提取 Timing
            tns_m = re.search(r"tns\s+max\s+([-+]?\d*\.\d+|\d+)", content)
            wns_m = re.search(r"wns\s+max\s+([-+]?\d*\.\d+|\d+)", content)
            if tns_m: metrics["tns"] = tns_m.group(1)
            if wns_m: metrics["wns"] = wns_m.group(1)

            # 提取 Power (匹配 Total 行 100.0% 前的数值)
            power_p = r"Total\s+[\d\.e+-]+\s+[\d\.e+-]+\s+[\d\.e+-]+\s+([\d\.e+-]+)\s+100\.0%"
            power_m = re.search(power_p, content)
            if power_m: metrics["power_watts"] = power_m.group(1)
        except Exception as e:
            print(f"Error parsing {finish_rpt}: {e}")

    if drc_rpt.exists():
        try:
            metrics["drc_count"] = str(drc_rpt.read_text().count("violation type:"))
        except Exception as e:
            print(f"Error parsing {drc_rpt}: {e}")

    return metrics

def save_summary_csv(all_results: List[dict], repo_root: Path):
    output_path = repo_root / "ci_metrics_summary.csv"
    if not all_results:
        return
    keys = all_results[0].keys()
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(all_results)
    print(f"\n[CI] Summary metrics saved to: {output_path}")

# ==============================================================================
# Execution Logic
# ==============================================================================

@dataclass(frozen=True)
class RunConfig:
    flow: str
    tech: str
    case: str
    repo_root: Path
    do_run: bool
    do_eval: bool
    run_ci: bool

def run_one(cfg: RunConfig) -> Tuple[str, Optional[dict]]:
    """执行单个任务，返回状态消息和提取的指标（如果是 CI 模式）"""
    _install_signal_handlers()
    _load_env_from_script(cfg.repo_root / "env.sh")

    pid = os.getpid()
    run_log, eval_log = _log_paths(cfg.flow, cfg.tech, cfg.case)
    run_script, eval_script = _script_paths(cfg.repo_root, cfg.flow, cfg.tech, cfg.case)

    # --- Run Stage ---
    if cfg.do_run:
        if not run_script.exists():
            return f"[{pid}] ERROR: run.sh not found: {run_script}", None
        try:
            _run_command_with_log(["bash", str(run_script)], run_log, cwd=cfg.repo_root, env=os.environ.copy())
        except subprocess.CalledProcessError:
            return f"[{pid}] ERROR: run.sh failed: {cfg.case}", None

    # --- Eval Stage ---
    if cfg.do_eval:
        if not eval_script.exists():
            return f"[{pid}] ERROR: eval.sh not found: {eval_script}", None
        try:
            _run_command_with_log(["bash", str(eval_script)], eval_log, cwd=cfg.repo_root, env=os.environ.copy())
        except subprocess.CalledProcessError:
            return f"[{pid}] ERROR: eval.sh failed: {cfg.case}", None

    # --- Metrics Extraction ---
    metrics = extract_metrics(cfg) if cfg.run_ci else None
    
    return f"[{pid}] OK: {cfg.flow}/{cfg.tech}/{cfg.case}", metrics

# ==============================================================================
# Helper functions (Log paths, Env, etc.)
# ==============================================================================

def _log_paths(flow: str, tech: str, case: str) -> Tuple[Path, Path]:
    base = Path(f"run_logs/{tech}/{flow}")
    return base / "run" / f"{case}_run.log", base / "eval" / f"{case}_eval.log"

def _script_paths(repo_root: Path, flow: str, tech: str, case: str) -> Tuple[Path, Path]:
    base = repo_root / "test" / tech / case / flow
    return base / "run.sh", base / "eval.sh"

def _load_env_from_script(env_script: Path) -> None:
    if not env_script.exists(): return
    cmd = ["bash", "-lc", f'export FLOW_ENV_QUIET=1; source "{env_script}"; env -0']
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, check=True)
    for entry in proc.stdout.split(b"\0"):
        if not entry: continue
        key, _, value = entry.partition(b"=")
        os.environ[key.decode(errors="ignore")] = value.decode(errors="ignore")

def _dedup_keep_order(xs: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

# ==============================================================================
# CLI + Main
# ==============================================================================

def parse_args(default_repo_root: Optional[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ORFS Runner with CI mode.")
    p.add_argument("--flow", choices=["ord", "cds", "all"], default="all")
    p.add_argument("--tech", action="append", default=[])
    p.add_argument("--case", action="append", default=[])
    p.add_argument("--jobs", type=int, default=12)
    p.add_argument("--repo-root", default=default_repo_root)
    p.add_argument("--run-CI", action="store_true", help="CI mode: force flow=ord, run-only, and extract metrics.")
    p.add_argument("--test-run", action="store_true", help="Test mode: only run the 'gcd' case.")
    
    group = p.add_mutually_exclusive_group()
    group.add_argument("--eval-only", action="store_true")
    group.add_argument("--run-only", action="store_true")
    return p.parse_args()

def main() -> int:
    _install_signal_handlers()
    script_root = Path(__file__).resolve().parent
    default_repo_root = os.environ.get("FLOW_HOME", str(script_root))
    args = parse_args(default_repo_root)
    repo_root = Path(args.repo_root).resolve()

    # --- CI Mode Logic Override ---
    if args.run_CI:
        flows = ["ord"]
        do_run, do_eval = True, False
        print("[CI MODE] Forced flow=ord, run-only stage, and metrics extraction enabled.")
    else:
        flows = ["ord", "cds"] if args.flow == "all" else [args.flow]
        do_run = not args.eval_only
        do_eval = not args.run_only

    # --- Test Run Logic Override ---
    if args.test_run:
        cases = ["gcd"]
        print("[TEST RUN] Mode enabled: only the 'gcd' case will be processed.")
    else:
        default_cases = ["gcd", "aes", "jpeg", "ibex"]
        cases = _dedup_keep_order(args.case) if args.case else default_cases

    default_techs = ["asap7_3D", "nangate45_3D", "asap7_nangate45_3D"]
    techs = _dedup_keep_order(args.tech) if args.tech else default_techs

    tasks = [RunConfig(f, t, c, repo_root, do_run, do_eval, args.run_CI) 
             for f in flows for t in techs for c in cases]

    print(f"[MAIN] repo_root={repo_root} | total_tasks={len(tasks)} | jobs={args.jobs}")

    all_metrics = []
    executor: Optional[ProcessPoolExecutor] = None
    try:
        with ProcessPoolExecutor(max_workers=args.jobs) as executor:
            futures = [executor.submit(run_one, t) for t in tasks]
            for fut in as_completed(futures):
                msg, metrics = fut.result()
                print(msg)
                if metrics:
                    all_metrics.append(metrics)
    except KeyboardInterrupt:
        if executor: executor.shutdown(wait=False)
        return 130

    if args.run_CI:
        save_summary_csv(all_metrics, repo_root)

    print("[MAIN] All experiments completed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())