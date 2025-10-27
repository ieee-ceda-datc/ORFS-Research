#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import re
from typing import Dict, Tuple

# 捕获组件首行：- inst master ... (+ PLACED|+ FIXED) ( x y ) orient ... ;
COMP_FIRST_RE = re.compile(r'^\s*-\s+(\S+)\s+(\S+)(.*)$')
PLACE_RE = re.compile(
    r'(\+\s*(?:PLACED|FIXED)\s*\(\s*)(-?\d+)\s+(-?\d+)(\s*\)\s*)([A-Z0-9]+)'
)

def parse_coords_map(def_path: str) -> Dict[str, Tuple[str, str, str]]:
    """
    返回 inst -> (x, y, orient) 的映射（从一个“单层”DEF中抓取）。
    仅解析 COMPONENTS 段首行；若没找到放置片段则忽略该实例。
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
                # 跳过到 ';'
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
    在 base DEF 的 COMPONENTS 段首行中，用 upper/bottom map 的坐标替换 (x y) ORIENT。
    匹配优先：upper_map > bottom_map（理论上两者不会重叠）。
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
                # 选择坐标源
                xyo = upper_map.get(inst) or bottom_map.get(inst)
                if xyo:
                    x, y, orient = xyo
                    def repl(mobj):
                        return f"{mobj.group(1)}{x} {y}{mobj.group(4)}{orient}"
                    rest2, cnt = PLACE_RE.subn(repl, rest, count=1)
                    if cnt == 0:
                        # 若该组件首行没有放置片段，则直接原样写入
                        out_lines.append(line)
                    else:
                        prefix = line[:m.start()]
                        out_lines.append(f"{prefix}- {inst} {master}{rest2}\n")
                else:
                    out_lines.append(line)
                # 抄到 ';'
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
    ap.add_argument("--base", required=True, help="Base CTS DEF (4_1_cts.def)")
    ap.add_argument("--upper", required=True, help="Upper-only legalized DEF (4_2_upper.def)")
    ap.add_argument("--bottom", required=True, help="Bottom-only legalized DEF (4_2_bottom.def)")
    ap.add_argument("--out", required=True, help="Merged DEF output (4_cts.def)")
    args = ap.parse_args()

    upper_map  = parse_coords_map(args.upper)
    bottom_map = parse_coords_map(args.bottom)
    merge_coords_into_base(args.base, upper_map, bottom_map, args.out)
    print(f"[merge_def] Merged -> {args.out}. Upper insts: {len(upper_map)}; Bottom insts: {len(bottom_map)}")

if __name__ == "__main__":
    main()
