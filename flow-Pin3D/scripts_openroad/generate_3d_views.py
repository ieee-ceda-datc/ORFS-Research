#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import re
import json
from typing import Dict, List, Tuple

# ==========================================================
# 统一名字归一化：DEF / Verilog / partition 共用
# ==========================================================

def normalize_name(inst_name: str) -> str:
    """
    统一归一规则：
      - 去掉两端空白
      - 去掉开头的转义反斜杠（Verilog/DEF 对奇怪标识符的转义）
      - 把 '\\[' '\\]' 这样的 DEF / partition 转义去掉
    """
    s = inst_name.strip()
    if s.startswith('\\'):
        s = s[1:]
    s = s.replace('\\[', '[').replace('\\]', ']')
    return s

def normalize_from_def(inst_name: str) -> str:
    """保留接口名，但内部用统一归一逻辑。"""
    return normalize_name(inst_name)

def normalize_from_verilog(inst_name: str) -> str:
    """保留接口名，但内部用统一归一逻辑。"""
    return normalize_name(inst_name)

# ==========================================================
#  Parse partition.txt
# ==========================================================

def parse_partition_file(partition_path: str) -> Dict[str, int]:
    """
    Read partition.txt, format: <inst_name> <die(0 or 1)>.
    Ignore empty lines and comments starting with #.
    die = 0 -> upper, die = 1 -> bottom
    """
    part: Dict[str, int] = {}
    if not partition_path:
        return part
    try:
        with open(partition_path, 'r') as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                toks = line.split()
                if len(toks) != 2:
                    continue
                inst, die_s = toks
                try:
                    die = int(die_s)
                except ValueError:
                    continue
                if die not in (0, 1):
                    continue
                key = normalize_name(inst)
                part[key] = die
    except FileNotFoundError:
        print(f"[WARN] partition file '{partition_path}' not found, ignore.")
    return part

# ==========================================================
#  Parse cell map JSON (map.json)
# ==========================================================

def parse_cell_map_json(
    cell_map_path: str
) -> Tuple[
    Dict[str, str],                 # base_to_bottom_macro
    Dict[str, str],                 # base_to_upper_macro
    Dict[str, Dict[str, str]],      # base_to_pin_map (bottom_pin -> upper_pin)
    Dict[str, List[str]]            # base_to_upper_extra_pins (upper pins w/o mapping)
]:
    """
    Read map.json, structure:

    {
      "bottom_file": "...",
      "upper_file":  "...",
      "cells": {
        "AND2_X1": {
          "base": "AND2_X1",
          "bottom": { "macro": "AND2_X1_bottom", ... },
          "upper": { "macro": "AND2x2_ASAP7_75t_R_upper",
                     "pins": ["A","B","VDD","VSS","Y"], ... },
          "pin_map": { "A1": "A", "A2": "B", "ZN": "Y", "VDD": "VDD", "VSS": "VSS" }
        },
        ...
      }
    }
    """
    base_to_bottom: Dict[str, str] = {}
    base_to_upper: Dict[str, str] = {}
    base_to_pin_map: Dict[str, Dict[str, str]] = {}
    base_to_upper_extra_pins: Dict[str, List[str]] = {}

    if not cell_map_path:
        return base_to_bottom, base_to_upper, base_to_pin_map, base_to_upper_extra_pins

    if not os.path.exists(cell_map_path):
        print(f"[WARN] cell map JSON '{cell_map_path}' not found, skip mapping.")
        return base_to_bottom, base_to_upper, base_to_pin_map, base_to_upper_extra_pins

    with open(cell_map_path, 'r') as f:
        data = json.load(f)

    cells = data.get("cells", {})
    if not isinstance(cells, dict):
        print("[WARN] cell map JSON format error: 'cells' is not a dict.")
        return base_to_bottom, base_to_upper, base_to_pin_map, base_to_upper_extra_pins

    for key, cell in cells.items():
        if not isinstance(cell, dict):
            continue
        base = cell.get("base", key)
        bottom = cell.get("bottom", {})
        upper = cell.get("upper", {})

        bottom_macro = bottom.get("macro")
        upper_macro = upper.get("macro")
        if bottom_macro:
            base_to_bottom[base] = bottom_macro
        if upper_macro:
            base_to_upper[base] = upper_macro

        pin_map = cell.get("pin_map", {})
        if isinstance(pin_map, dict):
            base_to_pin_map[base] = pin_map

        # 计算 upper 里“多出来”的 pin（例如 CLKGATE 的 SE）
        upper_pins = upper.get("pins", [])
        if isinstance(upper_pins, list):
            mapped_upper = set(pin_map.values()) if isinstance(pin_map, dict) else set()
            extra = [p for p in upper_pins if p not in mapped_upper]
            if extra:
                base_to_upper_extra_pins[base] = extra

    return base_to_bottom, base_to_upper, base_to_pin_map, base_to_upper_extra_pins

# ==========================================================
#  Infer inst->die mapping from DEF (fallback)
# ==========================================================

COMP_BEGIN_RE = re.compile(r'^\s*COMPONENTS\b', re.I)
COMP_END_RE   = re.compile(r'^\s*END\s+COMPONENTS\b', re.I)
# Capture leading whitespace | instance name | master | rest
COMP_FIRST_RE = re.compile(r'^(\s*)-\s+(\S+)\s+(\S+)(.*)$')

def derive_partition_from_def(def_path: str) -> Dict[str, int]:
    """
    Scan DEF COMPONENTS; if a master already ends with _upper/_bottom,
    infer inst->die (0: upper, 1: bottom).
    """
    part: Dict[str, int] = {}
    try:
        lines = open(def_path, 'r').readlines()
    except FileNotFoundError:
        print(f"[ERROR] DEF file '{def_path}' not found.")
        return part

    in_comp = False
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        if not in_comp and COMP_BEGIN_RE.match(line):
            in_comp = True
            i += 1
            continue
        if in_comp and COMP_END_RE.match(line):
            in_comp = False
            i += 1
            continue

        if in_comp:
            m = COMP_FIRST_RE.match(line)
            if m:
                _, inst_raw, master, _ = m.groups()
                inst_norm = normalize_name(inst_raw)

                if master.endswith('_upper'):
                    part[inst_norm] = 0
                elif master.endswith('_bottom'):
                    part[inst_norm] = 1

                # skip to end of this component (after ';')
                if ';' in line:
                    i += 1
                else:
                    i += 1
                    while i < n and ';' not in lines[i]:
                        i += 1
                    if i < n:
                        i += 1
                continue
        i += 1

    return part

def collect_inst_base_from_def(def_path: str) -> Dict[str, str]:
    """
    从原始 DEF 的 COMPONENTS 段里收集 inst -> base master 名，
    用于后面在 NETS 里做 pin 映射。
    """
    inst2base: Dict[str, str] = {}
    try:
        lines = open(def_path, 'r').readlines()
    except FileNotFoundError:
        print(f"[ERROR] DEF file '{def_path}' not found for collect_inst_base_from_def.")
        return inst2base

    in_comp = False
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not in_comp and COMP_BEGIN_RE.match(line):
            in_comp = True
            i += 1
            continue
        if in_comp and COMP_END_RE.match(line):
            in_comp = False
            i += 1
            continue

        if in_comp:
            m = COMP_FIRST_RE.match(line)
            if m:
                _, inst_raw, master, _ = m.groups()
                inst_norm = normalize_name(inst_raw)
                inst2base[inst_norm] = master
                # 跳到该 component 的 ';'
                if ';' in line:
                    i += 1
                else:
                    i += 1
                    while i < n and ';' not in lines[i]:
                        i += 1
                    if i < n:
                        i += 1
                continue
        i += 1

    return inst2base

# ==========================================================
#  Rewrite DEF (COMPONENTS + NETS)
# ==========================================================

NETS_BEGIN_RE = re.compile(r'^\s*NETS\b', re.I)
NETS_END_RE   = re.compile(r'^\s*END\s+NETS\b', re.I)
# ( inst pin )  or  ( 100 200 ) 之类
DEF_CONN_RE   = re.compile(r'\(\s*(\S+)\s+(\S+)\s*\)')

def rewrite_def_net_block(
    net_lines: List[str],
    part_map: Dict[str, int],
    inst2base: Dict[str, str],
    base_to_pin_map: Dict[str, Dict[str, str]]
) -> List[str]:
    """
    对一个 NET 语句块做 pin 映射：
      - 只处理 ( inst pin ) 形式；
      - inst == 'PIN' 时跳过；
      - die==0 (upper) 时，用 cell_map.pin_map: bottom_pin -> upper_pin;
      - die==1 (bottom) 或无映射，则保持不变。
    """
    text = ''.join(net_lines)

    def repl(m) -> str:
        inst = m.group(1)
        pin = m.group(2)
        # IO pin
        if inst == 'PIN':
            return m.group(0)

        inst_norm = normalize_name(inst)
        die = part_map.get(inst_norm, None)
        base = inst2base.get(inst_norm, None)

        # geometry (100 200) 或无 partition / 无 cell map 都保持不变
        if die is None or base is None or base not in base_to_pin_map:
            return m.group(0)

        pin_map = base_to_pin_map[base]

        if die == 0:
            # upper die: bottom_pin -> upper_pin
            new_pin = pin_map.get(pin, pin)
        else:
            # bottom die: 保持原 pin 名
            new_pin = pin

        return f"( {inst} {new_pin} )"

    new_text = DEF_CONN_RE.sub(repl, text)
    return new_text.splitlines(keepends=True)

def rewrite_def(
    def_in: str,
    def_out: str,
    part_map: Dict[str, int],
    base_to_bottom: Dict[str, str],
    base_to_upper: Dict[str, str],
    base_to_pin_map: Dict[str, Dict[str, str]],
) -> None:
    """
    Rewrite DEF:
      - COMPONENTS 段：根据 inst->die 和 cell map 改 master 名；
      - NETS 段：根据 inst->die 和 pin_map 做 pin 重命名；
      - 其他段原样拷贝。
    """
    try:
        lines = open(def_in, 'r').readlines()
    except FileNotFoundError:
        print(f"[ERROR] DEF file '{def_in}' not found.")
        return

    # 先从原始 DEF 收集 inst -> base master
    inst2base = collect_inst_base_from_def(def_in)

    out: List[str] = []
    in_comp = False
    in_nets = False
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        # --------- COMPONENTS 段 ----------
        if not in_comp and COMP_BEGIN_RE.match(line):
            in_comp = True
            out.append(line)
            i += 1
            continue
        if in_comp and COMP_END_RE.match(line):
            in_comp = False
            out.append(line)
            i += 1
            continue

        if in_comp:
            m = COMP_FIRST_RE.match(line)
            if m:
                indent, inst_raw, master, rest = m.groups()
                key = normalize_name(inst_raw)
                die = part_map.get(key, None)

                new_master = master
                if die is not None:
                    # 优先使用 map.json 的 bottom/upper macro
                    if die == 0 and master in base_to_upper:
                        new_master = base_to_upper[master]
                    elif die == 1 and master in base_to_bottom:
                        new_master = base_to_bottom[master]
                    else:
                        # 没在 cell map 里的，退回简单后缀逻辑
                        if not (master.endswith('_upper') or master.endswith('_bottom')):
                            new_master = master + ('_upper' if die == 0 else '_bottom')

                out.append(f"{indent}- {inst_raw} {new_master}{rest}\n")

                # 拷贝该 component 剩余行
                if ';' in line:
                    i += 1
                else:
                    i += 1
                    while i < n:
                        out.append(lines[i])
                        if ';' in lines[i]:
                            i += 1
                            break
                        i += 1
                continue
            else:
                out.append(line)
                i += 1
                continue

        # --------- NETS 段 ----------
        if not in_nets and NETS_BEGIN_RE.match(line):
            in_nets = True
            out.append(line)
            i += 1
            continue
        if in_nets and NETS_END_RE.match(line):
            in_nets = False
            out.append(line)
            i += 1
            continue

        if in_nets:
            stripped = line.lstrip()
            if stripped.startswith('-'):
                # 新的 net 语句块
                buf = [line]
                i += 1
                while i < n:
                    buf.append(lines[i])
                    if ';' in lines[i]:
                        i += 1
                        break
                    i += 1
                new_block = rewrite_def_net_block(buf, part_map, inst2base, base_to_pin_map)
                out.extend(new_block)
                continue
            else:
                out.append(line)
                i += 1
                continue

        # --------- 其他 ----------
        out.append(line)
        i += 1

    with open(def_out, 'w') as f:
        f.writelines(out)

# ==========================================================
#  Rewrite Verilog: module 名 + pin 映射 + 额外 upper pin 绑常数
# ==========================================================

VERILOG_INST_RE = re.compile(
    r'''^(\s*)                              # 1: leading whitespace
         ([A-Za-z_]\w*)                     # 2: module name (base cell)
         (\s*)                              # 3: space between module and optional #(...)
         (?: ( \#\s*\( .*? \) ) (\s*) )?    # 4: optional parameters; 5: space after parameters
         ( (?:\\\S+)|(?:[A-Za-z_]\w*) )     # 6: instance name (escaped or regular)
         \s* (\()                           # 7: "("
     ''',
    re.VERBOSE
)

# .PIN(  的形式
VERILOG_PORT_RE = re.compile(r'(\.\s*)([A-Za-z_]\w*)(\s*\()')

def _append_extra_ports(body: str, extra_pins: List[str]) -> str:
    """
    在实例 body（从 "(" 之后开始，直到 "…);"）末尾插入
    .PIN(1'b0) 的端口连接。
    """
    if not extra_pins:
        return body

    # 找出已有端口名，避免重复插入
    existing_ports = set()
    for mm in VERILOG_PORT_RE.finditer(body):
        existing_ports.add(mm.group(2))

    missing = [p for p in extra_pins if p not in existing_ports]
    if not missing:
        return body

    # 找最后一个 ');'
    matches = list(re.finditer(r'\)\s*;', body, flags=re.S))
    if not matches:
        return body  # 不太正常，直接放弃修改

    last = matches[-1]
    insert_pos = last.start()

    # 推断缩进：取插入点之前的最后一行的前导空白
    prefix_text = body[:insert_pos]
    lines = prefix_text.splitlines()
    indent = ""
    if lines:
        last_line = lines[-1]
        m = re.match(r'(\s*)', last_line)
        if m:
            indent = m.group(1)

    extra_str = ""
    for pin in missing:
        extra_str += f",\n{indent}.{pin}(1'b0)"

    return body[:insert_pos] + extra_str + body[insert_pos:]


def rewrite_verilog(
    v_in: str,
    v_out: str,
    part_map: Dict[str, int],
    base_to_bottom: Dict[str, str],
    base_to_upper: Dict[str, str],
    base_to_pin_map: Dict[str, Dict[str, str]],
    base_to_upper_extra_pins: Dict[str, List[str]],
) -> None:
    """
    对 Verilog：
      - 根据 inst->die 和 cell map，把 module 名改成 bottom.macro / upper.macro；
      - 对 upper die 的实例，按 pin_map 做端口重命名（.A1(...) -> .A(...)）；
      - 对 upper die 中没有映射的 upper 端口（如 CLKGATE 的 SE），
        如果实例中未显式连接，则自动补 .SE(1'b0)。
      - 如果 module 不在 JSON map 中，但实例有 die，则 fallback：module + '_upper' / '_bottom'
    """
    try:
        lines = open(v_in, 'r').readlines()
    except FileNotFoundError:
        print(f"[ERROR] Verilog file '{v_in}' not found.")
        return

    out: List[str] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        m = VERILOG_INST_RE.match(line)
        if not m:
            out.append(line)
            i += 1
            continue

        # 匹配到一个实例的第一行，收集整个实例直到 ';'
        inst_lines = [line]
        i += 1
        while i < n:
            inst_lines.append(lines[i])
            if ';' in lines[i]:
                i += 1
                break
            i += 1

        inst_text = ''.join(inst_lines)
        m2 = VERILOG_INST_RE.match(inst_text)
        if not m2:
            # 理论上不会发生，直接原样输出
            out.append(inst_text)
            continue

        indent, module, sp_mod_to_hash, param_blk, sp_hash_to_inst, inst_tok, paren = m2.groups()
        inst_norm = normalize_from_verilog(inst_tok)
        die = part_map.get(inst_norm, None)

        # 没在 partition 里的实例，不动
        if die is None:
            out.append(inst_text)
            continue

        # 选择新 module 名：
        #   1) 如果在 JSON map 中，优先用 base_to_upper/base_to_bottom
        #   2) 否则 fallback：简单加 _upper / _bottom 后缀（和 DEF 保持一致）
        if die == 0 and module in base_to_upper:
            new_module = base_to_upper[module]
        elif die == 1 and module in base_to_bottom:
            new_module = base_to_bottom[module]
        else:
            # fallback：module 不在 cell map
            if module.endswith('_upper') or module.endswith('_bottom'):
                new_module = module
            else:
                new_module = module + ('_upper' if die == 0 else '_bottom')

        # 组装参数部分
        if param_blk is not None:
            param_part = f"{sp_mod_to_hash}{param_blk}{sp_hash_to_inst or ''}"
        else:
            param_part = sp_mod_to_hash or ''

        # body: 从 "(" 之后的部分开始，包含所有端口连接等
        body = inst_text[m2.end(7):]

        # pin 映射（只有 upper die 且 module 在 pin_map 中才做）
        def port_repl(pm: Dict[str, str]):
            def _inner(mm):
                dot, pin, lp = mm.groups()
                new_pin = pm.get(pin, pin)
                return f"{dot}{new_pin}{lp}"
            return _inner

        if die == 0 and module in base_to_pin_map:
            pm = base_to_pin_map[module]
            body = VERILOG_PORT_RE.sub(port_repl(pm), body)

        # upper die 上，多出来的 upper pins（如 SE）自动绑 1'b0
        if die == 0 and module in base_to_upper_extra_pins:
            extra_pins = base_to_upper_extra_pins[module]
            body = _append_extra_ports(body, extra_pins)

        # 重新拼装整个实例
        new_first = f"{indent}{new_module}{param_part}{inst_tok} {paren}"
        new_text = new_first + body
        out.append(new_text)

    with open(v_out, 'w') as f:
        f.writelines(out)

# ==========================================================
#  Main
# ==========================================================

def main():
    ap = argparse.ArgumentParser(
        description='Map 2D DEF/Verilog to 3D views using partition + JSON cell map (masters + pin remap).'
    )
    ap.add_argument('--def-in',    required=True)
    ap.add_argument('--def-out',   required=True)
    ap.add_argument('--v-in',      required=True)
    ap.add_argument('--v-out',     required=True)
    ap.add_argument('--partition', default=None,
                    help='Optional: partition.txt (<inst> <die>), overrides DEF-derived partition')
    ap.add_argument('--cell-map',  default=None,
                    help='JSON map file (map.json) with base/bottom/upper and pin_map.')
    args = ap.parse_args()

    # 1) 从 DEF 中推断 inst->die（通过 *_upper / *_bottom master）
    part_from_def = derive_partition_from_def(args.def_in)

    # 2) 用户 partition.txt 覆盖
    part_from_user = parse_partition_file(args.partition)
    part: Dict[str, int] = dict(part_from_def)
    part.update(part_from_user)

    # 3) 读取 JSON cell map
    base_to_bottom, base_to_upper, base_to_pin_map, base_to_upper_extra_pins = parse_cell_map_json(args.cell_map)

    # 4) Rewrite DEF + Verilog
    rewrite_def(args.def_in, args.def_out, part, base_to_bottom, base_to_upper, base_to_pin_map)
    rewrite_verilog(
        args.v_in,
        args.v_out,
        part,
        base_to_bottom,
        base_to_upper,
        base_to_pin_map,
        base_to_upper_extra_pins
    )

if __name__ == '__main__':
    main()
