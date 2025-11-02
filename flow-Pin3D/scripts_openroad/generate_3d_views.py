#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
from typing import Dict, List

# --------------------------
# Name Normalization: DEF / Verilog
# --------------------------

def normalize_from_def(inst_name: str) -> str:
    """Normalizes an instance name from DEF format (which may contain escaped brackets like \\[ \\]) to a canonical form, e.g., dpath[6]."""
    return inst_name.replace('\\[', '[').replace('\\]', ']')

def normalize_from_verilog(inst_name: str) -> str:
    """Normalizes a Verilog instance name (which may be an escaped identifier starting with a backslash) to a canonical form."""
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
    Reads partition.txt, format: <inst_name> <die(0 or 1)>.
    Ignores empty lines and comments starting with #.
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
            # Store keys in both styles for easier lookup and override.
            part[normalize_from_def(inst)] = die
            part[normalize_from_verilog(inst)] = die
    return part

# --------------------------
# Infer inst->die from DEF
# --------------------------

COMP_BEGIN_RE = re.compile(r'^\s*COMPONENTS\b', re.I)
COMP_END_RE   = re.compile(r'^\s*END\s+COMPONENTS\b', re.I)
# Capture leading whitespace | instance name | master | the rest of the line
COMP_FIRST_RE = re.compile(r'^(\s*)-\s+(\S+)\s+(\S+)(.*)$')

# ---------- Read DEF -> part_map ----------
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
            m = COMP_FIRST_RE.match(line)  # ^(\s*)-\s+(\S+)\s+(\S+)(.*)$
            if m:
                _, inst_raw, master, _ = m.groups()
                inst_norm = normalize_from_def(inst_raw)
                if master.endswith('_upper'):
                    part[inst_norm] = 0
                elif master.endswith('_bottom'):
                    part[inst_norm] = 1

                # If the line itself contains a semicolon, advance one line; otherwise, find the next ';'.
                if ';' in line:
                    i += 1
                else:
                    i += 1
                    while i < n and ';' not in lines[i]:
                        i += 1
                    if i < n:  # consume the ';' line
                        i += 1
                continue
        i += 1
    return part

# ---------- Rewrite DEF ----------
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
            m = COMP_FIRST_RE.match(line)  # ^(\s*)-\s+(\S+)\s+(\S+)(.*)$
            if m:
                indent, inst_raw, master, rest = m.groups()
                key = normalize_from_def(inst_raw)
                die = part_map.get(key, None)

                if (die is None) or master.endswith('_upper') or master.endswith('_bottom'):
                    out.append(line)
                else:
                    new_master = master + ('_upper' if die == 0 else '_bottom')
                    out.append(f"{indent}- {inst_raw} {new_master}{rest}\n")

                # If the line already has a semicolon, don't consume subsequent lines.
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
                out.append(line); i += 1; continue
        else:
            out.append(line); i += 1

    with open(def_out, 'w') as f:
        f.writelines(out)

# --------------------------
# Rewrite Verilog: Append suffix to module names
# --------------------------
# Format: <module> [#(...)] <inst> (
# - <module>: identifier starting with a letter
# - Optional parameterization: #(...) (non-greedy)
# - <inst>: regular identifier or escaped instance name (\... ending with whitespace)
# - Ensure at least one space between <inst> and '('

VERILOG_INST_RE = re.compile(
    r'''^(\s*)                              # 1: leading whitespace
         ([A-Za-z_]\w*)                     # 2: module name (without suffix)
         (\s*)                              # 3: space between module name and optional #(...)
         (?: ( \#\s*\( .*? \) ) (\s*) )?    # 4: optional parameters; 5: space after parameters
         ( (?:\\\S+)|(?:[A-Za-z_]\w*) )     # 6: instance name (escaped or regular)
         \s* (\()                           # 7: up to '('
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

        # Normalize instance name for lookup
        key = normalize_from_verilog(inst_tok)
        die = part_map.get(key, None)

        # Don't add suffix again if module already has one (e.g., INV_X1_upper)
        if die is None or module.endswith('_upper') or module.endswith('_bottom'):
            out.append(line); i += 1; continue

        new_module = module + ('_upper' if die == 0 else '_bottom')

        # Restore optional parameter block if it exists
        if param_blk is not None:
            param_part = f"{sp_mod_to_hash}{param_blk}{sp_hash_to_inst or ''}"
        else:
            param_part = sp_mod_to_hash or ''

        # Construct the new first line: ensure at least one space between instance name and '('
        rest_after_paren = line[m.end():]  # remainder after '(', contains first port or whitespace
        new_first = f"{indent}{new_module}{param_part}{inst_tok} {paren}{rest_after_paren}"
        out.append(new_first)

        # If the line already contains ';', the instance definition ends on this line.
        # Otherwise, copy lines as-is until ';'.
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
    ap.add_argument('--partition', default=None, help='Optional: partition.txt (<inst> <die>), takes precedence over DEF-derived partitioning')
    args = ap.parse_args()

    # 1) Infer inst->die from DEF
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
