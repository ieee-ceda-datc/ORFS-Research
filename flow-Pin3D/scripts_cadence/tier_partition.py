#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tiny 2-tier partitioner (upper/bottom) with hyperedge-cut minimization.
- Minimal CLI: --def, --verilog, optional --out, --balance
- Default balance tolerance = 0.03 (±3% of total cell count)
- Y-median seed (upper/bottom), 1–2 greedy passes with balance constraint
- Output: lines "instance die(0|1)"  (0=bottom, 1=upper)
"""

import argparse, re, math, random, sys
from collections import defaultdict
from typing import Dict, List, Set, Tuple

XY = Tuple[int, int]

# --------- minimal parsers ----------
def parse_def(def_text: str) -> Dict[str, XY]:
    """inst -> (x,y) from COMPONENTS with + PLACED (...)"""
    comps: Dict[str, XY] = {}
    rx = re.compile(r"^\s*-\s+(\S+)\s+\S+.*?\(\s*(\d+)\s+(\d+)\s*\)\s+\S+\s*;\s*$", re.M)
    for m in rx.finditer(def_text):
        name, x, y = m.groups()
        comps[name] = (int(x), int(y))
    return comps

def parse_verilog_edges(v_text: str) -> List[Set[str]]:
    """Build hyperedges (nets) from gate-level Verilog instance connections."""
    v = re.sub(r"//.*?$", "", v_text, flags=re.M)
    v = re.sub(r"/\*.*?\*/", "", v, flags=re.S)
    inst_re = re.compile(r"\b\w+\s+([\w\/\.\$\[\]]+)\s*\(\s*(.*?)\);\s*", re.S)
    pin_re  = re.compile(r"\.\s*\w+\s*\(\s*([^\(\)\s,]+)\s*\)")
    net2inst: Dict[str, Set[str]] = defaultdict(set)
    for m in inst_re.finditer(v):
        inst = m.group(1)
        pins = m.group(2)
        for net in pin_re.findall(pins):
            if net in ("1'b0","1'b1","1'bx","1'bz"): continue
            if net.lower().startswith(("vdd","vss","gnd","vcc")): continue
            net2inst[net].add(inst)
    return [s for s in net2inst.values() if len(s) >= 2]

# --------- hypergraph helpers ----------
def cutsize(edges: List[Set[str]], part: Dict[str,int]) -> int:
    c = 0
    for e in edges:
        if len({part[u] for u in e}) > 1:
            c += 1
    return c

def incident(edges: List[Set[str]]) -> Dict[str, List[int]]:
    inc: Dict[str, List[int]] = defaultdict(list)
    for i,e in enumerate(edges):
        for v in e: inc[v].append(i)
    return inc

def gain_if_move(u: str, edges: List[Set[str]], inc, part: Dict[str,int]) -> int:
    """Δcut if moving u to the other tier (hyperedge model)."""
    g = 0; cu = part[u]; tu = 1 - cu
    for ei in inc.get(u, []):
        e = edges[ei]
        c0 = sum(1 for v in e if part[v] == 0)
        c1 = len(e) - c0
        was = (c0>0 and c1>0)
        if cu == 0: c0p, c1p = c0-1, c1+1
        else:       c0p, c1p = c0+1, c1-1
        now = (c0p>0 and c1p>0)
        if was and not now: g += 1
        elif (not was) and now: g -= 1
    return g

# --------- seeding & balance ----------
def y_median_seed(inst_xy: Dict[str,XY]) -> Dict[str,int]:
    ys = sorted(y for _,y in inst_xy.values())
    med = ys[len(ys)//2] if ys else 0
    return {i: (1 if y>med else 0) for i,(_,y) in inst_xy.items()}  # 0=bottom, 1=upper

def within_balance(p: Dict[str,int], tol: float) -> bool:
    n0 = sum(1 for v in p.values() if v==0)
    n1 = len(p)-n0
    return abs(n0-n1) <= math.ceil(tol*len(p))

def repair_balance(p: Dict[str,int], edges: List[Set[str]], tol: float) -> None:
    """Modify p in-place: move least-damaging nodes until within tol."""
    N = len(p); limit = math.ceil(tol*N)
    n0 = sum(1 for v in p.values() if v==0); n1 = N - n0
    diff = n0 - n1
    if abs(diff) <= limit: return
    larger = 0 if diff>0 else 1
    need = abs(diff) - limit
    inc = incident(edges)
    gains = {u: gain_if_move(u, edges, inc, p) for u,v in p.items() if v==larger}
    pos = [u for u,g in gains.items() if g>=0]
    neg = [u for u,g in gains.items() if g<0]
    pos.sort(key=lambda u: gains[u], reverse=True)
    neg.sort(key=lambda u: gains[u], reverse=True)  # closest to 0 first
    moved = 0
    for u in pos + neg:
        if moved>=need: break
        p[u] = 1 - p[u]
        moved += 1

# --------- tiny FM-like refinement ----------
def refine(part: Dict[str,int], edges: List[Set[str]], tol: float, passes: int=2) -> Dict[str,int]:
    p = dict(part)
    inc = incident(edges)
    V = list(p.keys())
    rng = random.Random(0)
    for _ in range(passes):
        improved = False
        rng.shuffle(V)
        for u in V:
            old = p[u]; p[u] = 1 - old
            if within_balance(p, tol):
                g = gain_if_move(u, edges, inc, p)
                if g >= 0:
                    improved = improved or (g>0)
                    continue
            p[u] = old
        if not improved: break
    repair_balance(p, edges, tol)
    return p

# --------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Simple 2-tier partitioner (upper/bottom) with hyperedge cut")
    ap.add_argument("--def", required=True, dest="def_file", help="DEF with placed components")
    ap.add_argument("--verilog", required=True, dest="v_file", help="Gate-level Verilog")
    ap.add_argument("--out", default="partition.txt", help="Output mapping file (default: partition.txt)")
    ap.add_argument("--balance", type=float, default=0.03, help="Max fraction imbalance (default: 0.03)")
    args = ap.parse_args()

    with open(args.def_file, "r", encoding="utf-8", errors="ignore") as f: dtext = f.read()
    with open(args.v_file,  "r", encoding="utf-8", errors="ignore") as f: vtext = f.read()

    inst_xy = parse_def(dtext)
    if not inst_xy: sys.exit("ERROR: no COMPONENTS parsed from DEF")
    edges_all = parse_verilog_edges(vtext)
    if not edges_all: sys.exit("ERROR: no nets parsed from Verilog")

    placed = set(inst_xy.keys())
    edges = []
    for e in edges_all:
        ee = e & placed
        if len(ee) >= 2: edges.append(ee)
    if not edges: sys.exit("ERROR: no usable hyperedges after DEF filtering")

    p0 = y_median_seed(inst_xy)
    c0 = cutsize(edges, p0)
    p1 = refine(p0, edges, tol=args.balance, passes=2)
    c1 = cutsize(edges, p1)

    with open(args.out, "w", encoding="utf-8") as f:
        for inst in sorted(inst_xy.keys()):
            f.write(f"{inst} {p1[inst]}\n")

    n0 = sum(1 for v in p1.values() if v==0); n1 = len(p1)-n0
    print(f"wrote: {args.out}  |  cells: {len(p1)}  bottom={n0} upper={n1}  "
          f"imbalance={(abs(n0-n1)/len(p1)):.3%}  cut: {c0}->{c1}")

if __name__ == "__main__":
    main()
