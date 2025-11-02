#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
from typing import Dict, List

# --------------------------
# Name Normalization: DEF / Verilog
# --------------------------

def normalize_from_def(inst_name: str) -> str:
    """Normalize instance names from DEF (which may contain escaped brackets) to a standard format, e.g., dpath[6]."""
    return inst_name.replace('\\[', '[').replace('\\]', ']')

def normalize_from_verilog(inst_name: str) -> str:
    """Normalize Verilog instance names (which may be escaped identifiers starting with a backslash) to a standard format."""
    s = inst_name.strip()
    if s.startswith('\\'):
        s = s[1:]
        m = re.search(r'\s', s)
        if m:
            s = s[:m.start()]
    return s

# --------------------------
# Parse partition.txt
# --------------------------

def parse_partition_file(partition_path: str) -> Dict[str, int]:
    """
    Read partition.txt, format: <inst_name> <die(0 or 1)>.
    Ignore empty lines and comments starting with #.
    """
    part = {}
    if not partition_path:
        return part
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
            # Store keys in both DEF and Verilog normalized styles for easier lookup.
            part[normalize_from_def(inst)] = die
            part[normalize_from_verilog(inst)] = die
    return part

# --------------------------
# Infer inst->die mapping from DEF
# --------------------------

COMP_BEGIN_RE = re.compile(r'^\s*COMPONENTS\b', re.I)
COMP_END_RE   = re.compile(r'^\s*END\s+COMPONENTS\b', re.I)
COMP_FIRST_RE = re.compile(r'^\s*-\s+(\S+)\s+(\S+)(.*)$')  # - <inst> <master> ...

def derive_partition_from_def(def_path: str) -> Dict[str, int]:
    part = {}
    lines = open(def_path, 'r').readlines()
    in_comp = False
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        if not in_comp and COMP_BEGIN_RE.match(line):
            in_comp = True; i += 1; continue
        if in_comp and COMP_END_RE.match(line):
            in_comp = False; i += 1; continue

        if in_comp:
            m = COMP_FIRST_RE.match(line)
            if m:
                inst_raw, master, rest = m.groups()
                inst_norm = normalize_from_def(inst_raw)
                if master.endswith('_upper'):
                    part[inst_norm] = 0
                elif master.endswith('_bottom'):
                    part[inst_norm] = 1
                # Skip to the end of the component block (after ';')
                i += 1
                while i < n and ';' not in lines[i]:
                    i += 1
                if i < n: i += 1
                continue
        i += 1
    return part

# --------------------------
# Rewrite DEF: only change the master in the first line of a component
# --------------------------

def rewrite_def(def_in: str, def_out: str, part_map: Dict[str, int]) -> None:
    lines = open(def_in, 'r').readlines()
    out: List[str] = []
    in_comp = False
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        if not in_comp and COMP_BEGIN_RE.match(line):
            in_comp = True; out.append(line); i += 1; continue
        if in_comp and COMP_END_RE.match(line):
            in_comp = False; out.append(line); i += 1; continue

        if in_comp:
            m = COMP_FIRST_RE.match(line)
            if m:
                inst_raw, master, rest = m.groups()
                key = normalize_from_def(inst_raw)
                die = part_map.get(key, None)

                new_master = master
                if die is not None and not (master.endswith('_upper') or master.endswith('_bottom')):
                    new_master = master + ('_upper' if die == 0 else '_bottom')

                # Preserve original prefix/whitespace, keep the rest unchanged
                prefix = line[:m.start()]
                out.append(f"{prefix}- {inst_raw} {new_master}{rest}\n")

                # Copy lines until a ';' is found
                i += 1
                while i < n:
                    out.append(lines[i])
                    if ';' in lines[i]:
                        i += 1
                        break
                    i += 1
                continue
            else:
                out.append(line); i += 1; continue
        else:
            out.append(line); i += 1

    with open(def_out, 'w') as f:
        f.writelines(out)

# --------------------------
# Rewrite Verilog: append suffix to module names
# --------------------------
# Format: <module> [#(...)] <inst> (
# - <module>: identifier starting with a letter
# - Optional parameters: #(...) (non-greedy)
# - <inst>: regular identifier or escaped identifier (\... terminated by whitespace)
# - Ensure at least one space between <inst> and '('

VERILOG_INST_RE = re.compile(
    r'''^(\s*)                              # 1: Leading whitespace
         ([A-Za-z_]\w*)                     # 2: Module name (without suffix)
         (\s*)                              # 3: Whitespace between module name and optional #(...)
         (?: ( \#\s*\( .*? \) ) (\s*) )?    # 4: Optional parameters; 5: Whitespace after parameters
         ( (?:\\\S+)|(?:[A-Za-z_]\w*) )     # 6: Instance name (escaped or regular)
         \s* (\()                           # 7: Up to '('
     ''',
    re.VERBOSE
)

def rewrite_verilog(v_in: str, v_out: str, part_map: Dict[str, int]) -> None:
    lines = open(v_in, 'r').readlines()
    out: List[str] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        m = VERILOG_INST_RE.match(line)
        if not m:
            out.append(line); i += 1; continue

        indent, module, sp_mod_to_hash, param_blk, sp_hash_to_inst, inst_tok, paren = m.groups()

        # Normalize instance name and look up in the partition map
        key = normalize_from_verilog(inst_tok)
        die = part_map.get(key, None)

        # Don't add suffix if module already has one (e.g., INV_X1_upper)
        new_module = module
        if die is not None and not (module.endswith('_upper') or module.endswith('_bottom')):
            new_module = module + ('_upper' if die == 0 else '_bottom')

        # Restore optional parameter block if it exists
        param_part = ''
        if param_blk is not None:
            # param_blk includes "#(...)", restore surrounding whitespace with captured sp_*
            param_part = f"{sp_mod_to_hash}{param_blk}{sp_hash_to_inst or ''}"
        else:
            param_part = sp_mod_to_hash or ''

        # Construct the new first line, ensuring at least one space before '('
        rest_after_paren = line[m.end():]  # Remainder after '(', contains first port or whitespace
        new_first = f"{indent}{new_module}{param_part}{inst_tok} {paren}{rest_after_paren}"
        out.append(new_first)

        # If the line already contains ';', the instance ends on this line; otherwise, copy until ';'
        if ';' in rest_after_paren:
            i += 1
        else:
            i += 1
            while i < n:
                out.append(lines[i])
                if ';' in lines[i]:
                    i += 1
                    break
                i += 1

    with open(v_out, 'w') as f:
        f.writelines(out)

# --------------------------
# Main flow
# --------------------------

def main():
    ap = argparse.ArgumentParser(description='Append _upper/_bottom to masters in DEF/Verilog based on partition.')
    ap.add_argument('--def-in',    required=True)
    ap.add_argument('--def-out',   required=True)
    ap.add_argument('--v-in',      required=True)
    ap.add_argument('--v-out',     required=True)
    ap.add_argument('--partition', default=None, help='Optional: partition.txt (<inst> <die>), overrides inference from DEF')
    args = ap.parse_args()

    # 1) Infer inst->die mapping from DEF
    part_from_def = derive_partition_from_def(args.def_in)
    # 2) Optionally override with partition.txt
    part_from_user = parse_partition_file(args.partition)
    part = dict(part_from_def)
    part.update(part_from_user)

    # 3) Rewrite DEF + Verilog
    rewrite_def(args.def_in, args.def_out, part)
    rewrite_verilog(args.v_in, args.v_out, part)

if __name__ == '__main__':
    main()
