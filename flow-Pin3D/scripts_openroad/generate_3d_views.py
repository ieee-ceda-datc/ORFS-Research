#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import re
import json
from typing import Dict, List, Tuple, Optional

# ==========================================================
# Name normalization helpers (DEF / Verilog / partition shared)
# ==========================================================

def normalize_name(inst_name: str) -> str:
    """
    Normalize instance/net/pin identifiers across DEF / Verilog / partition:
      - Strip leading/trailing whitespace
      - Remove leading escape backslash (Verilog/DEF escaped identifiers)
      - Unescape DEF-style bracket escapes: '\\[' -> '[', '\\]' -> ']'
    """
    s = inst_name.strip()
    if s.startswith('\\'):
        s = s[1:]
    s = s.replace('\\[', '[').replace('\\]', ']')
    return s

def normalize_from_def(inst_name: str) -> str:
    """Keep a dedicated entry point for DEF-side normalization."""
    return normalize_name(inst_name)

def normalize_from_verilog(inst_name: str) -> str:
    """Keep a dedicated entry point for Verilog-side normalization."""
    return normalize_name(inst_name)

def strip_tier_suffix(master: str) -> str:
    """Strip tier suffix '_upper' / '_bottom' to get base master name."""
    if master.endswith('_upper'):
        return master[:-6]
    if master.endswith('_bottom'):
        return master[:-7]
    return master

# ==========================================================
# Parse partition.txt
# ==========================================================

def parse_partition_file(partition_path: Optional[str]) -> Dict[str, int]:
    """
    Read partition.txt, format: <inst_name> <die(0 or 1)>.
    Ignore empty lines and comments starting with '#'.

    Convention:
      die = 0 -> upper
      die = 1 -> bottom
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
        print(f"[WARN] partition file '{partition_path}' not found, ignored.")

    return part

# ==========================================================
# Parse cell map JSON (map.json)
# ==========================================================

def parse_cell_map_json(
    cell_map_path: Optional[str]
) -> Tuple[
    Dict[str, str],                 # base_to_bottom_macro
    Dict[str, str],                 # base_to_upper_macro
    Dict[str, Dict[str, str]],      # base_to_pin_map (bottom_pin -> upper_pin)
    Dict[str, List[str]]            # base_to_upper_extra_pins (upper pins without mapping)
]:
    """
    Read map.json, expected structure:

    {
      "bottom_file": "...",
      "upper_file":  "...",
      "cells": {
        "AND2_X1": {
          "base": "AND2_X1",
          "bottom": { "macro": "AND2_X1_bottom", ... },
          "upper":  { "macro": "AND2x2_ASAP7_75t_R_upper",
                      "pins": ["A","B","VDD","VSS","Y"], ... },
          "pin_map": { "A1": "A", "A2": "B", "ZN": "Y", "VDD": "VDD", "VSS": "VSS" }
        }
      }
    }

    Notes:
      - base_to_pin_map maps: bottom_pin_name -> upper_pin_name
      - base_to_upper_extra_pins are upper pins not covered by pin_map (e.g., CLKGATE.SE)
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

        bottom_macro = bottom.get("macro") if isinstance(bottom, dict) else None
        upper_macro = upper.get("macro") if isinstance(upper, dict) else None

        if bottom_macro:
            base_to_bottom[base] = bottom_macro
        if upper_macro:
            base_to_upper[base] = upper_macro

        pin_map = cell.get("pin_map", {})
        if isinstance(pin_map, dict):
            base_to_pin_map[base] = pin_map

        upper_pins = upper.get("pins", []) if isinstance(upper, dict) else []
        if isinstance(upper_pins, list):
            mapped_upper = set(pin_map.values()) if isinstance(pin_map, dict) else set()
            extra = [p for p in upper_pins if p not in mapped_upper]
            if extra:
                base_to_upper_extra_pins[base] = extra

    return base_to_bottom, base_to_upper, base_to_pin_map, base_to_upper_extra_pins

# ==========================================================
# Infer inst->die mapping from DEF (explicit suffix fallback)
# ==========================================================

COMP_BEGIN_RE = re.compile(r'^\s*COMPONENTS\b', re.I)
COMP_END_RE   = re.compile(r'^\s*END\s+COMPONENTS\b', re.I)
COMP_FIRST_RE = re.compile(r'^(\s*)-\s+(\S+)\s+(\S+)(.*)$')  # indent | inst | master | rest

def derive_partition_from_def(def_path: str) -> Dict[str, int]:
    """
    Scan DEF COMPONENTS; if a master ends with _upper/_bottom,
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
                inst_norm = normalize_from_def(inst_raw)

                if master.endswith('_upper'):
                    part[inst_norm] = 0
                elif master.endswith('_bottom'):
                    part[inst_norm] = 1

                # Skip to end of this component (after ';')
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
    Collect inst -> base master name from DEF COMPONENTS.
    Base master strips '_upper' / '_bottom' suffix if present.
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
                inst_norm = normalize_from_def(inst_raw)
                inst2base[inst_norm] = strip_tier_suffix(master)

                # Skip to end of this component (after ';')
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

def auto_partition_by_master_count(def_path: str) -> Dict[str, int]:
    """
    Auto partition by base master instance count:
      - base masters with higher instance count -> upper (0)
      - base masters with lower  instance count -> bottom (1)

    Threshold policy:
      - Use median of base counts as threshold.
      - count >= median => upper; else => bottom.
      - If only one base master exists, place all instances in upper.
    """
    inst2base = collect_inst_base_from_def(def_path)
    if not inst2base:
        return {}

    base_count: Dict[str, int] = {}
    for _, base in inst2base.items():
        base_count[base] = base_count.get(base, 0) + 1

    counts = sorted(base_count.values())
    if len(counts) == 1:
        threshold = counts[0]
    else:
        threshold = counts[len(counts) // 2]  # median

    base_to_die: Dict[str, int] = {}
    for base, c in base_count.items():
        base_to_die[base] = 0 if c >= threshold else 1

    part: Dict[str, int] = {}
    for inst, base in inst2base.items():
        part[inst] = base_to_die[base]

    return part

# ==========================================================
# Rewrite DEF (COMPONENTS + NETS)
# ==========================================================

NETS_BEGIN_RE = re.compile(r'^\s*NETS\b', re.I)
NETS_END_RE   = re.compile(r'^\s*END\s+NETS\b', re.I)
DEF_CONN_RE   = re.compile(r'\(\s*(\S+)\s+(\S+)\s*\)')  # ( inst pin ) or ( x y )

def rewrite_def_net_block(
    net_lines: List[str],
    part_map: Dict[str, int],
    inst2base: Dict[str, str],
    base_to_pin_map: Dict[str, Dict[str, str]]
) -> List[str]:
    """
    Rewrite a single NET block (from '-' line to the terminating ';'):

      - Only rewrites connections in the form: ( inst pin )
      - Skips IO pin: ( PIN xxx )
      - For upper die instances (die==0), rename pins using pin_map (bottom_pin -> upper_pin)
      - For bottom die instances or missing mapping, keep the pin name unchanged
    """
    text = ''.join(net_lines)

    def repl(m) -> str:
        inst = m.group(1)
        pin = m.group(2)

        # IO pin connection in DEF NETS uses "PIN"
        if inst == 'PIN':
            return m.group(0)

        inst_norm = normalize_name(inst)
        die = part_map.get(inst_norm)
        base = inst2base.get(inst_norm)

        # Geometry (x y) or unknown instance/base or no pin_map -> unchanged
        if die is None or base is None or base not in base_to_pin_map:
            return m.group(0)

        pin_map = base_to_pin_map[base]

        if die == 0:
            new_pin = pin_map.get(pin, pin)
        else:
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
      - COMPONENTS: update master name based on inst->die and JSON macro mapping
      - NETS:       rename pins for upper instances using JSON pin_map
      - Others:     copy verbatim
    """
    try:
        lines = open(def_in, 'r').readlines()
    except FileNotFoundError:
        print(f"[ERROR] DEF file '{def_in}' not found.")
        return

    # inst -> base master (used for NETS pin remap)
    inst2base = collect_inst_base_from_def(def_in)

    out: List[str] = []
    in_comp = False
    in_nets = False
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        # --------- COMPONENTS ----------
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
                inst_key = normalize_from_def(inst_raw)
                die = part_map.get(inst_key)

                new_master = master
                if die is not None:
                    base = strip_tier_suffix(master)

                    # Prefer JSON macro mapping by base master name
                    if die == 0 and base in base_to_upper:
                        new_master = base_to_upper[base]
                    elif die == 1 and base in base_to_bottom:
                        new_master = base_to_bottom[base]
                    else:
                        # Fallback: enforce suffix based on die (avoid double suffix)
                        new_master = base + ('_upper' if die == 0 else '_bottom')

                out.append(f"{indent}- {inst_raw} {new_master}{rest}\n")

                # Copy remaining lines of this component until ';'
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

            out.append(line)
            i += 1
            continue

        # --------- NETS ----------
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
                # Collect a whole net block until ';'
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

            out.append(line)
            i += 1
            continue

        # --------- OTHERS ----------
        out.append(line)
        i += 1

    with open(def_out, 'w') as f:
        f.writelines(out)

# ==========================================================
# Rewrite Verilog: module rename + pin remap + bind extra upper pins
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

VERILOG_PORT_RE = re.compile(r'(\.\s*)([A-Za-z_]\w*)(\s*\()')  # .PIN(

def _append_extra_ports(body: str, extra_pins: List[str]) -> str:
    """
    Append missing extra ports as .PIN(1'b0) before the last ');'
    for a single instance body (from after '(' to the ending '...);').
    """
    if not extra_pins:
        return body

    existing_ports = {mm.group(2) for mm in VERILOG_PORT_RE.finditer(body)}
    missing = [p for p in extra_pins if p not in existing_ports]
    if not missing:
        return body

    matches = list(re.finditer(r'\)\s*;', body, flags=re.S))
    if not matches:
        return body

    last = matches[-1]
    insert_pos = last.start()

    # Infer indentation from the last line before insertion point
    prefix_text = body[:insert_pos]
    lines = prefix_text.splitlines()
    indent = ""
    if lines:
        m = re.match(r'(\s*)', lines[-1])
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
    Rewrite Verilog instances:
      - Rename module based on inst->die and JSON macro mapping
      - For upper die instances (die==0), rename ports using JSON pin_map (bottom_pin -> upper_pin)
      - For upper die instances, bind any extra upper pins (not covered by pin_map) to 1'b0 if missing
      - Fallback for unmapped modules: module_base + '_upper'/'_bottom'
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

        # Collect the full instance until ';'
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
            out.append(inst_text)
            continue

        indent, module, sp_mod_to_hash, param_blk, sp_hash_to_inst, inst_tok, paren = m2.groups()
        inst_norm = normalize_from_verilog(inst_tok)
        die = part_map.get(inst_norm)

        # If this instance is not partitioned, keep unchanged
        if die is None:
            out.append(inst_text)
            continue

        module_base = strip_tier_suffix(module)

        # Select new module name
        if die == 0 and module_base in base_to_upper:
            new_module = base_to_upper[module_base]
        elif die == 1 and module_base in base_to_bottom:
            new_module = base_to_bottom[module_base]
        else:
            new_module = module_base + ('_upper' if die == 0 else '_bottom')

        # Rebuild parameter part
        if param_blk is not None:
            param_part = f"{sp_mod_to_hash}{param_blk}{sp_hash_to_inst or ''}"
        else:
            param_part = sp_mod_to_hash or ''

        # Body starts right after the '(' token captured by group 7
        body = inst_text[m2.end(7):]

        # Port remap for upper die (based on base cell name)
        if die == 0 and module_base in base_to_pin_map:
            pm = base_to_pin_map[module_base]

            def _port_repl(mm):
                dot, pin, lp = mm.groups()
                new_pin = pm.get(pin, pin)
                return f"{dot}{new_pin}{lp}"

            body = VERILOG_PORT_RE.sub(_port_repl, body)

        # Bind extra upper pins to 1'b0 if missing
        if die == 0 and module_base in base_to_upper_extra_pins:
            body = _append_extra_ports(body, base_to_upper_extra_pins[module_base])

        # Reassemble
        new_first = f"{indent}{new_module}{param_part}{inst_tok} {paren}"
        out.append(new_first + body)

    with open(v_out, 'w') as f:
        f.writelines(out)

def remap_partition_majority_to_upper(part_from_user: Dict[str, int]) -> Dict[str, int]:
    """
    Ensure the larger group in partition.txt is assigned to upper (die=0).

    If count(die=1) > count(die=0), flip all assignments: die := 1 - die.
    Tie-breaking: keep original mapping (die=0 stays upper by default).
    """
    if not part_from_user:
        return part_from_user

    c0 = sum(1 for d in part_from_user.values() if d == 0)
    c1 = sum(1 for d in part_from_user.values() if d == 1)

    # If die=1 has more instances, flip so that the larger group becomes die=0 (upper)
    if c1 > c0:
        flipped = {k: (1 - v) for k, v in part_from_user.items()}
        print(f"[INFO] partition.txt remap: die=1({c1}) > die=0({c0}), flip to make majority -> upper(die=0).")
        return flipped

    print(f"[INFO] partition.txt remap: die=0({c0}) >= die=1({c1}), keep as-is (majority already upper).")
    return part_from_user

# ==========================================================
# Main
# ==========================================================

def main():
    ap = argparse.ArgumentParser(
        description='Map 2D DEF/Verilog to 3D views using partition + JSON cell map (macro rename + pin remap).'
    )
    ap.add_argument('--def-in',    required=True)
    ap.add_argument('--def-out',   required=True)
    ap.add_argument('--v-in',      required=True)
    ap.add_argument('--v-out',     required=True)
    ap.add_argument('--partition', default=None,
                    help='Optional: partition.txt (<inst> <die>), overrides DEF-derived / auto partition')
    ap.add_argument('--cell-map',  default=None,
                    help='Optional: JSON map file (map.json) with base/bottom/upper and pin_map.')
    args = ap.parse_args()

    # 1) Try to infer partition from DEF suffixes (if present)
    part_from_def = derive_partition_from_def(args.def_in)

    # 2) User partition overrides everything if provided
    part_from_user = parse_partition_file(args.partition)
    part_from_user = remap_partition_majority_to_upper(part_from_user)

    if part_from_user:
        part: Dict[str, int] = dict(part_from_def)
        part.update(part_from_user)
    elif part_from_def:
        part = dict(part_from_def)
    else:
        # 3) No explicit partition info -> auto partition:
        #    masters with more instances go to upper, fewer go to bottom.
        part = auto_partition_by_master_count(args.def_in)

    # 4) Load JSON cell mapping (optional)
    base_to_bottom, base_to_upper, base_to_pin_map, base_to_upper_extra_pins = parse_cell_map_json(args.cell_map)

    # 5) Rewrite DEF + Verilog
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
