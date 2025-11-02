#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import re
from typing import Dict, Tuple

# Capture the first line of a component: - inst master ... (+ PLACED|+ FIXED) ( x y ) orient ... ;
COMP_FIRST_RE = re.compile(r'^\s*-\s+(\S+)\s+(\S+)(.*)$')
PLACE_RE = re.compile(
    r'(\+\s*(?:PLACED|FIXED)\s*\(\s*)(-?\d+)\s+(-?\d+)(\s*\)\s*)([A-Z0-9]+)'
)

def parse_coords_map(def_path: str) -> Dict[str, Tuple[str, str, str]]:
    """
    Returns a map from inst -> (x, y, orient) (extracted from a "single-tier" DEF).
    Only parses the first line of each entry in the COMPONENTS section; ignores instances without a placement fragment.
    """
    inst2xyo: Dict[str, Tuple[str, str, str]] = {}
    with open(def_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    in_comp = False
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()

        if not in_comp and s.startswith("COMPONENTS"):
            in_comp = True; i += 1; continue
        if in_comp and s == "END COMPONENTS":
            in_comp = False; i += 1; continue

        if in_comp:
            m = COMP_FIRST_RE.match(line)
            if m:
                inst, master, rest = m.groups()
                m2 = PLACE_RE.search(rest)
                if m2:
                    x, y, orient = m2.group(2), m2.group(3), m2.group(5)
                    inst2xyo[inst] = (x, y, orient)
                # Skip to ';'
                i += 1
                while i < n and ';' not in lines[i]:
                    i += 1
                if i < n: i += 1
                continue
        i += 1
    return inst2xyo

def merge_coords_into_base(base_def: str, upper_map: Dict[str, Tuple[str,str,str]],
                           bottom_map: Dict[str, Tuple[str,str,str]], out_def: str) -> None:
    """
    Replaces (x y) ORIENT in the first line of each component in the base DEF's
    COMPONENTS section with coordinates from the upper/bottom map.
    Matching priority: upper_map > bottom_map (in theory, they should not overlap).
    """
    with open(base_def, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    out_lines = []
    in_comp = False
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()

        if not in_comp and s.startswith("COMPONENTS"):
            in_comp = True
            out_lines.append(line); i += 1; continue
        if in_comp and s == "END COMPONENTS":
            in_comp = False
            out_lines.append(line); i += 1; continue

        if in_comp:
            m = COMP_FIRST_RE.match(line)
            if m:
                inst, master, rest = m.groups()
                # Select coordinate source
                xyo = upper_map.get(inst) or bottom_map.get(inst)
                if xyo:
                    x, y, orient = xyo
                    def repl(mobj):
                        return f"{mobj.group(1)}{x} {y}{mobj.group(4)}{orient}"
                    rest2, cnt = PLACE_RE.subn(repl, rest, count=1)
                    if cnt == 0:
                        # If the component's first line has no placement fragment, write it as is.
                        out_lines.append(line)
                    else:
                        prefix = line[:m.start()]
                        out_lines.append(f"{prefix}- {inst} {master}{rest2}\n")
                else:
                    out_lines.append(line)
                # Copy until ';'
                i += 1
                while i < n:
                    out_lines.append(lines[i])
                    if ';' in lines[i]:
                        i += 1
                        break
                    i += 1
                continue

        out_lines.append(line)
        i += 1

    with open(out_def, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

def main():
    ap = argparse.ArgumentParser(description="Merge per-tier legalized DEF coords back into base CTS DEF.")
    ap.add_argument("--base", required=True, help="Base CTS DEF (e.g., 4_1_cts.def)")
    ap.add_argument("--upper", required=True, help="Upper-only legalized DEF (e.g., 4_2_upper.def)")
    ap.add_argument("--bottom", required=True, help="Bottom-only legalized DEF (e.g., 4_2_bottom.def)")
    ap.add_argument("--out", required=True, help="Merged DEF output (e.g., 4_cts.def)")
    args = ap.parse_args()

    upper_map  = parse_coords_map(args.upper)
    bottom_map = parse_coords_map(args.bottom)
    merge_coords_into_base(args.base, upper_map, bottom_map, args.out)
    print(f"[merge_def] Merged -> {args.out}. Upper insts: {len(upper_map)}; Bottom insts: {len(bottom_map)}")

if __name__ == "__main__":
    main()
