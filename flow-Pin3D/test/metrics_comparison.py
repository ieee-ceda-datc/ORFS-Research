#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

import pandas as pd


EXIT_PASS = 0
EXIT_REGRESSION = 1
EXIT_INPUT_ERR = 2


DEFAULT_KEY_CANDIDATES = ["Tech", "Design", "Tool", "Cell Name", "Cell", "Case"]
DEFAULT_TOL_REL = 0.01
DEFAULT_TOL_ABS = {
    "WNS (ns)": 1e-3,
    "TNS (ns)": 1e-3,
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compare Pin3D CI metrics summary against golden baseline."
    )

    # Support both: --summary/--golden AND positional args
    p.add_argument(
        "positional",
        nargs="*",
        help="Optional positional args: <summary_csv> <golden_csv>",
    )
    p.add_argument(
        "--summary",
        default=None,
        help="Metrics summary CSV path (default: ci_metrics_summary.csv)",
    )
    p.add_argument(
        "--golden",
        default=None,
        help="Golden CSV path (default: ci_metrics_golden.csv or test/ci_metrics_golden.csv if exists)",
    )

    p.add_argument(
        "--keys",
        default=",".join(DEFAULT_KEY_CANDIDATES),
        help=f"Comma-separated key candidates (default: {','.join(DEFAULT_KEY_CANDIDATES)})",
    )
    p.add_argument(
        "--tol-rel",
        type=float,
        default=DEFAULT_TOL_REL,
        help=f"Relative tolerance (default: {DEFAULT_TOL_REL})",
    )
    p.add_argument(
        "--tol-abs-json",
        default=None,
        help="Absolute tolerances as JSON dict, e.g. '{\"WNS (ns)\": 0.001}'. "
             "If not set, uses built-in defaults.",
    )
    p.add_argument(
        "--report",
        default="ci_metrics_compare_report.csv",
        help="Write a CSV report of differences (default: ci_metrics_compare_report.csv)",
    )
    p.add_argument(
        "--max-print",
        type=int,
        default=50,
        help="Max regression entries to print (default: 50)",
    )

    args = p.parse_args()

    # Resolve summary/golden from positional if provided
    if args.summary is None and len(args.positional) >= 1:
        args.summary = args.positional[0]
    if args.golden is None and len(args.positional) >= 2:
        args.golden = args.positional[1]

    if args.summary is None:
        args.summary = "ci_metrics_summary.csv"

    # Golden default: prefer test/ci_metrics_golden.csv if exists, else ci_metrics_golden.csv
    if args.golden is None:
        if os.path.exists("test/ci_metrics_golden.csv"):
            args.golden = "test/ci_metrics_golden.csv"
        else:
            args.golden = "ci_metrics_golden.csv"

    return args


def _load_tol_abs(args: argparse.Namespace) -> Dict[str, float]:
    if args.tol_abs_json:
        try:
            d = json.loads(args.tol_abs_json)
            if not isinstance(d, dict):
                raise ValueError("tol-abs-json must be a JSON object")
            # ensure float
            return {str(k): float(v) for k, v in d.items()}
        except Exception as e:
            print(f"[ERROR] Failed to parse --tol-abs-json: {e}", file=sys.stderr)
            sys.exit(EXIT_INPUT_ERR)
    return dict(DEFAULT_TOL_ABS)


def _read_csv_or_die(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        print(f"[ERROR] File not found: {path}", file=sys.stderr)
        sys.exit(EXIT_INPUT_ERR)
    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"[ERROR] Failed to read CSV '{path}': {e}", file=sys.stderr)
        sys.exit(EXIT_INPUT_ERR)


def _pick_keys(cur: pd.DataFrame, gold: pd.DataFrame, key_candidates: List[str]) -> List[str]:
    ccols = set(cur.columns)
    gcols = set(gold.columns)
    keys = [k for k in key_candidates if k in ccols and k in gcols]
    return keys


def _numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def main() -> int:
    args = _parse_args()
    tol_abs = _load_tol_abs(args)

    summary_path = args.summary
    golden_path = args.golden
    report_path = args.report

    cur = _read_csv_or_die(summary_path)
    gold = _read_csv_or_die(golden_path)

    key_candidates = [x.strip() for x in args.keys.split(",") if x.strip()]
    keys = _pick_keys(cur, gold, key_candidates)

    if not keys:
        print("[ERROR] No common key columns; cannot compare.", file=sys.stderr)
        print(f"  Candidates: {key_candidates}", file=sys.stderr)
        print(f"  Summary columns: {list(cur.columns)}", file=sys.stderr)
        print(f"  Golden  columns: {list(gold.columns)}", file=sys.stderr)
        return EXIT_INPUT_ERR

    # Only compare columns present in both and not in keys
    common_cols = [c for c in gold.columns if (c in cur.columns and c not in keys)]
    if not common_cols:
        print("[ERROR] No common metric columns to compare.", file=sys.stderr)
        return EXIT_INPUT_ERR

    # Robust join: merge on keys; allow duplicates
    cur_m = cur[keys + common_cols].copy()
    gold_m = gold[keys + common_cols].copy()

    joined = gold_m.merge(
        cur_m,
        on=keys,
        how="inner",
        suffixes=("_gold", "_cur"),
        validate="m:m",
    )

    if joined.empty:
        print("[ERROR] No overlapping rows to compare (inner join is empty).", file=sys.stderr)
        return EXIT_INPUT_ERR

    bad_rows: List[Tuple[Tuple, str, float, float]] = []
    report_records = []

    tol_rel = float(args.tol_rel)

    for m in common_cols:
        gcol = f"{m}_gold"
        ccol = f"{m}_cur"

        g = _numeric_series(joined, gcol)
        c = _numeric_series(joined, ccol)
        diff = (c - g).abs()

        if m in tol_abs:
            thr = float(tol_abs[m])
            mask = diff > thr
            basis = "abs"
            thr_used = thr
            rel = None
        else:
            # Relative tolerance; protect divide-by-zero
            rel_diff = diff / (g.abs() + 1e-12)
            mask = rel_diff > tol_rel
            basis = "rel"
            thr_used = tol_rel
            rel = rel_diff

        mask = mask.fillna(False)
        if mask.any():
            # collect regression entries
            for i in joined.index[mask]:
                key_tuple = tuple(joined.loc[i, keys].tolist())
                gv = g.loc[i]
                cv = c.loc[i]
                # handle NaN -> skip or treat as regression? here: treat as regression if one side numeric, else skip
                if pd.isna(gv) and pd.isna(cv):
                    continue
                gv_f = float(gv) if not pd.isna(gv) else float("nan")
                cv_f = float(cv) if not pd.isna(cv) else float("nan")
                bad_rows.append((key_tuple, m, gv_f, cv_f))

                rec = {k: joined.loc[i, k] for k in keys}
                rec.update({
                    "metric": m,
                    "gold": gv_f,
                    "cur": cv_f,
                    "abs_diff": float(abs(cv_f - gv_f)) if (not pd.isna(gv) and not pd.isna(cv)) else float("nan"),
                    "tol_basis": basis,
                    "threshold": thr_used,
                })
                if rel is not None:
                    rec["rel_diff"] = float(rel.loc[i]) if not pd.isna(rel.loc[i]) else float("nan")
                report_records.append(rec)

    # Always write report (even pass -> empty report with headers is fine)
    if report_path:
        try:
            if report_records:
                pd.DataFrame(report_records).to_csv(report_path, index=False)
            else:
                # write an empty report with a minimal schema
                pd.DataFrame(columns=keys + ["metric", "gold", "cur", "abs_diff", "rel_diff", "tol_basis", "threshold"])\
                  .to_csv(report_path, index=False)
            print(f"[INFO] Wrote report: {report_path}")
        except Exception as e:
            print(f"[WARN] Failed to write report '{report_path}': {e}", file=sys.stderr)

    if bad_rows:
        print(f"METRICS REGRESSION DETECTED (showing up to {args.max_print}):")
        for idx, (key_tuple, m, gv, cv) in enumerate(bad_rows[: args.max_print]):
            # Pretty print keys
            key_str = ", ".join([f"{keys[i]}={key_tuple[i]}" for i in range(len(keys))])
            print(f"- [{idx+1}] {key_str} | {m}: gold={gv} cur={cv}")
        print(f"[INFO] Total regressions: {len(bad_rows)}")
        return EXIT_REGRESSION

    print("Metrics comparison passed.")
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())