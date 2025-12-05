#!/usr/bin/env python3
import argparse
import os
import signal
import socket
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


# ==============================================================================
# Safety: signals + process-group kill
# ==============================================================================

def _install_signal_handlers():
    """Install signal handlers so that SIGINT/SIGTERM raise KeyboardInterrupt."""
    def _handler(signum, frame):
        raise KeyboardInterrupt()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass


def _run_command_with_log(cmd: Sequence[str], log_path: Path, cwd: Optional[Path] = None):
    """
    Run a command, redirect stdout/stderr to log_path.
    Start a new process group so we can kill the whole tree via killpg on interrupt.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as log_file:
        proc = subprocess.Popen(
            list(cmd),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(cwd) if cwd else None,
            preexec_fn=os.setsid,  # POSIX only
        )

        try:
            ret = proc.wait()
            if ret != 0:
                raise subprocess.CalledProcessError(ret, list(cmd))
        except KeyboardInterrupt:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            raise
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            raise


# ==============================================================================
# Experiment definitions
# ==============================================================================

@dataclass(frozen=True)
class RunConfig:
    flow: str                 # "ord" or "cds"
    tech: str
    case: str
    remote_user: str
    remote_host: str
    remote_project_dir: str   # only for ord eval (ssh)
    repo_root: Path           # local repo root (where test/ exists)


def _log_paths(flow: str, tech: str, case: str) -> Tuple[Path, Path]:
    base = Path(f"run_logs/{tech}/{flow}")
    run_log = base / "run" / f"{case}_run.log"
    eval_log = base / "eval" / f"{case}_eval.log"
    return run_log, eval_log


def _script_paths(repo_root: Path, flow: str, tech: str, case: str) -> Tuple[Path, Path]:
    run_script = repo_root / "test" / tech / case / flow / "run.sh"
    eval_script = repo_root / "test" / tech / case / flow / "eval.sh"
    return run_script, eval_script


def run_one(cfg: RunConfig) -> str:
    """
    Execute one (flow, tech, case) task.
    - cds: run.sh + eval.sh locally
    - ord: run.sh locally; eval.sh via ssh (logs local)
    """
    _install_signal_handlers()

    pid = os.getpid()
    host = socket.gethostname()

    run_log, eval_log = _log_paths(cfg.flow, cfg.tech, cfg.case)
    run_log.unlink(missing_ok=True)
    eval_log.unlink(missing_ok=True)

    run_script, eval_script = _script_paths(cfg.repo_root, cfg.flow, cfg.tech, cfg.case)

    print(f"[{pid}] Start {cfg.flow.upper()} tech={cfg.tech} case={cfg.case} on host={host}")

    # --- run.sh (local) ---
    if not run_script.exists():
        msg = f"[{pid}] ERROR: run.sh not found: {run_script}"
        print(msg)
        return msg

    try:
        _run_command_with_log(["bash", str(run_script)], run_log, cwd=cfg.repo_root)
    except subprocess.CalledProcessError:
        msg = f"[{pid}] ERROR: run.sh failed ({cfg.flow}/{cfg.tech}/{cfg.case}). See {run_log}"
        print(msg)
        return msg

    # --- eval.sh ---
    if cfg.flow == "cds":
        if not eval_script.exists():
            msg = f"[{pid}] ERROR: eval.sh not found: {eval_script}"
            print(msg)
            return msg
        try:
            _run_command_with_log(["bash", str(eval_script)], eval_log, cwd=cfg.repo_root)
        except subprocess.CalledProcessError:
            msg = f"[{pid}] ERROR: eval.sh failed ({cfg.flow}/{cfg.tech}/{cfg.case}). See {eval_log}"
            print(msg)
            return msg

    elif cfg.flow == "ord":
        # Local path exists check (remote may differ, but at least validate naming)
        if not eval_script.exists():
            msg = f"[{pid}] ERROR: eval.sh not found locally (for naming sanity): {eval_script}"
            print(msg)
            return msg

        remote_eval_script = f"test/{cfg.tech}/{cfg.case}/ord/eval.sh"
        remote_cmd = (
            "set -euo pipefail; "
            f"cd {cfg.remote_project_dir}; "
            'echo "[remote] CWD=$PWD"; '
            f"bash {remote_eval_script}"
        )

        ssh_target = f"{cfg.remote_user}@{cfg.remote_host}"
        try:
            _run_command_with_log(
                ["ssh", "-t", ssh_target, "bash", "-lc", "--", remote_cmd],
                eval_log,
                cwd=cfg.repo_root,
            )
        except subprocess.CalledProcessError:
            msg = f"[{pid}] ERROR: remote eval.sh failed ({cfg.flow}/{cfg.tech}/{cfg.case}). See {eval_log}"
            print(msg)
            return msg
    else:
        return f"[{pid}] ERROR: unknown flow={cfg.flow}"

    ok = f"[{pid}] OK: {cfg.flow}/{cfg.tech}/{cfg.case}"
    print(ok)
    return ok


# ==============================================================================
# CLI + orchestration
# ==============================================================================

def _dedup_keep_order(xs: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def build_tasks(
    flows: List[str],
    techs: List[str],
    cases: List[str],
    remote_user: str,
    remote_host: str,
    remote_project_dir: str,
    repo_root: Path,
) -> List[RunConfig]:
    tasks: List[RunConfig] = []
    for flow in flows:
        for tech in techs:
            for case in cases:
                tasks.append(
                    RunConfig(
                        flow=flow,
                        tech=tech,
                        case=case,
                        remote_user=remote_user,
                        remote_host=remote_host,
                        remote_project_dir=remote_project_dir,
                        repo_root=repo_root,
                    )
                )
    return tasks


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run ORFS experiments (ORD/CDS) in parallel with per-task logs."
    )
    p.add_argument(
        "--flow",
        choices=["ord", "cds", "all"],
        default="all",
        help="Which flow to run (default: all).",
    )
    p.add_argument(
        "--tech",
        action="append",
        default=[],
        help="Tech name. Repeatable. Default: run all preset techs.",
    )
    p.add_argument(
        "--case",
        action="append",
        default=[],
        help="Case/design name. Repeatable. Default: run all preset cases.",
    )
    p.add_argument(
        "--jobs",
        type=int,
        default=9,
        help="Parallel workers.",
    )

    # ORD remote eval controls (kept explicit)
    p.add_argument("--remote-user", default="zhiyuzheng", help="SSH user for ORD eval (default: zhiyuzheng).")
    p.add_argument("--remote-host", default=socket.gethostname(), help="SSH host for ORD eval (default: local hostname).")
    p.add_argument(
        "--remote-project-dir",
        default="/export/home/zhiyuzheng/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D",
        help="Remote repo root for ORD eval (default: your hardcoded path).",
    )

    p.add_argument(
        "--repo-root",
        default=None,
        help="Local repo root path (default: auto-detect as this script's parent).",
    )
    return p.parse_args()


def main() -> int:
    _install_signal_handlers()
    args = parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parent

    # Default suites (match your originals)
    default_techs = ["asap7_3D", "nangate45_3D", "asap7_nangate45_3D"]
    default_cases = ["gcd", "aes", "jpeg"]

    techs = _dedup_keep_order(args.tech) if args.tech else default_techs
    cases = _dedup_keep_order(args.case) if args.case else default_cases

    if args.flow == "all":
        flows = ["ord", "cds"]
    else:
        flows = [args.flow]

    tasks = build_tasks(
        flows=flows,
        techs=techs,
        cases=cases,
        remote_user=args.remote_user,
        remote_host=args.remote_host,
        remote_project_dir=args.remote_project_dir,
        repo_root=repo_root,
    )

    print(f"[MAIN] repo_root={repo_root}")
    print(f"[MAIN] flows={flows} techs={techs} cases={cases} jobs={args.jobs}")
    print(f"[MAIN] total_tasks={len(tasks)} logs under run_logs/<tech>/<flow>/...")

    # Run
    executor: Optional[ProcessPoolExecutor] = None
    try:
        with ProcessPoolExecutor(max_workers=args.jobs) as executor:
            futures = [executor.submit(run_one, t) for t in tasks]
            for fut in as_completed(futures):
                _ = fut.result()
    except KeyboardInterrupt:
        print("[MAIN] KeyboardInterrupt received, shutting down...")
        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        return 130

    print("[MAIN] All experiments completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
