#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluate-only runner:
- Discover FLOW_ROOT by searching parent dirs for env.sh
- Run "evaluate"/final stage only (no implementation flow)
- Run multiple designs in parallel
"""

import os
import sys
import shlex
import signal
import subprocess
import argparse
from pathlib import Path

NUM_CORES = 20


def find_flow_root(script_dir: Path) -> Path:
  p = script_dir
  while True:
    if (p / "env.sh").is_file():
      return p
    if p.parent == p:
      break
    p = p.parent
  raise FileNotFoundError(f"env.sh not found for {script_dir}")


def bash_source_env_and_run(flow_root: Path, design_config: str, target: str) -> subprocess.Popen:
  env_sh = flow_root / "env.sh"
  if not env_sh.is_file():
    raise FileNotFoundError(f"Missing {env_sh}")

  cmd = (
    "set -euo pipefail; "
    f"source {shlex.quote(str(env_sh))}; "
    f"export NUM_CORES={NUM_CORES}; "
    "export DESIGN_DIMENSION=2D; "
    "export FLOW_VARIANT=cadence; "
    "export USE_FLOW=cadence; "
    f"make DESIGN_CONFIG={shlex.quote(design_config)} {shlex.quote(target)}"
  )

  return subprocess.Popen(
    ["bash", "-lc", cmd],
    cwd=str(flow_root),
    preexec_fn=os.setsid,
    stdout=sys.stdout,
    stderr=sys.stderr,
  )


def terminate_all(procs):
  for p in procs:
    if p.poll() is None:
      try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
      except ProcessLookupError:
        pass


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument(
    "--target",
    default="cds-final",
    help="make target to run for evaluation only (default: cds-final)",
  )
  args = ap.parse_args()

  script_dir = Path(__file__).resolve().parent
  try:
    flow_root = find_flow_root(script_dir)
  except FileNotFoundError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 1

  design_configs = [
    # nangate45
    "designs/nangate45_3D/aes/config2d.mk",
    "designs/nangate45_3D/ibex/config2d.mk",
    "designs/nangate45_3D/jpeg/config2d.mk",
    # asap7
    "designs/asap7_3D/jpeg/config2d.mk",
    "designs/asap7_3D/aes/config2d.mk",
    "designs/asap7_3D/ibex/config2d.mk",
  ]

  procs = []
  try:
    for cfg in design_configs:
      p = bash_source_env_and_run(flow_root, cfg, args.target)
      procs.append((cfg, p))
      print(f"[START] {cfg} target={args.target} (pid={p.pid})")

    while True:
      alive = [(cfg, p) for (cfg, p) in procs if p.poll() is None]
      if not alive:
        break
      print("[STATUS] running=" + ", ".join([f"{cfg}(pid={p.pid})" for cfg, p in alive]))
      import time
      time.sleep(10)

    rc = 0
    for cfg, p in procs:
      code = p.wait()
      print(f"[DONE] {cfg} exit={code}")
      if code != 0:
        rc = 1
    return rc

  except KeyboardInterrupt:
    print("\n[INTERRUPT] terminating all jobs ...", file=sys.stderr)
    terminate_all([p for _, p in procs])
    return 130


if __name__ == "__main__":
  raise SystemExit(main())
