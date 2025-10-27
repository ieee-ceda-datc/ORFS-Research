#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
from typing import Dict, List

# --------------------------
# 名字归一化/互通：DEF / Verilog
# --------------------------

def normalize_from_def(inst_name: str) -> str:
    """把 DEF 中的实例名（可能含 \\[ \\] 转义）变成规范名：dpath[6]"""
    return inst_name.replace('\\[', '[').replace('\\]', ']')

def normalize_from_verilog(inst_name: str) -> str:
    """把 Verilog 实例名（可能以反斜杠开头的转义标识符）变成规范名"""
    s = inst_name.strip()
    if s.startswith('\\'):
        s = s[1:]
        m = re.search(r'\s', s)
        if m:
            s = s[:m.start()]
    return s

# --------------------------
# 解析 partition.txt
# --------------------------

def parse_partition_file(partition_path: str) -> Dict[str, int]:
    """
    读取 partition.txt，格式：<inst_name> <die(0或1)>
    忽略空行和以#开头的注释。
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
            # 同时记两种风格的键，便于覆盖
            part[normalize_from_def(inst)] = die
            part[normalize_from_verilog(inst)] = die
    return part

# --------------------------
# 从 DEF 推导 inst→die
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
                # 跳到该组件块的 ';' 后
                i += 1
                while i < n and ';' not in lines[i]:
                    i += 1
                if i < n: i += 1
                continue
        i += 1
    return part

# --------------------------
# 改写 DEF：只换组件首行里的 master
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

                # 用原有前缀/空白，保持其余不变
                prefix = line[:m.start()]
                out.append(f"{prefix}- {inst_raw} {new_master}{rest}\n")

                # 抄到 ';' 为止
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
# 改写 Verilog：在模块名上追加后缀
# --------------------------
# 形式：<module> [#(...)] <inst> (
# - <module>：字母开头的标识符
# - 可选参数化：#(...)（非贪婪）
# - <inst>：普通标识符或转义实例名（\...，以空白结束）
# - 确保在 <inst> 与 '(' 之间至少留一个空格

VERILOG_INST_RE = re.compile(
    r'''^(\s*)                              # 1: 前导空白
         ([A-Za-z_]\w*)                     # 2: 模块名（不带后缀）
         (\s*)                              # 3: 模块名与可选#(...)之间的空白
         (?: ( \#\s*\( .*? \) ) (\s*) )?    # 4: 可选参数; 5: 参数后的空白
         ( (?:\\\S+)|(?:[A-Za-z_]\w*) )     # 6: 实例名（可转义或普通）
         \s* (\()                           # 7: 直到 '('
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

        # 归一化实例名查表
        key = normalize_from_verilog(inst_tok)
        die = part_map.get(key, None)

        # 已经带后缀的模块（如 INV_X1_upper）不重复加
        new_module = module
        if die is not None and not (module.endswith('_upper') or module.endswith('_bottom')):
            new_module = module + ('_upper' if die == 0 else '_bottom')

        # 恢复可选参数块（若有）
        param_part = ''
        if param_blk is not None:
            # param_blk 自带 "#(...)"，两侧空白用原样捕获的 sp_* 还原
            param_part = f"{sp_mod_to_hash}{param_blk}{sp_hash_to_inst or ''}"
        else:
            param_part = sp_mod_to_hash or ''

        # 构造新的首行：保证实例名与 '(' 之间至少一个空格
        rest_after_paren = line[m.end():]  # '(' 后的 remainder（包含端口第一项或空白）
        new_first = f"{indent}{new_module}{param_part}{inst_tok} {paren}{rest_after_paren}"
        out.append(new_first)

        # 如果该行已经包含 ';'，说明实例在一行内结束；否则原样抄到 ';'
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
# 主流程
# --------------------------

def main():
    ap = argparse.ArgumentParser(description='Append _upper/_bottom to masters in DEF/Verilog based on partition.')
    ap.add_argument('--def-in',    required=True)
    ap.add_argument('--def-out',   required=True)
    ap.add_argument('--v-in',      required=True)
    ap.add_argument('--v-out',     required=True)
    ap.add_argument('--partition', default=None, help='可选：partition.txt（<inst> <die>），优先于 DEF 推导')
    args = ap.parse_args()

    # 1) 从 DEF 推导 inst→die
    part_from_def = derive_partition_from_def(args.def_in)
    # 2) 可选用 partition.txt 覆盖
    part_from_user = parse_partition_file(args.partition)
    part = dict(part_from_def)
    part.update(part_from_user)

    # 3) 改写 DEF + Verilog
    rewrite_def(args.def_in, args.def_out, part)
    rewrite_verilog(args.v_in, args.v_out, part)

if __name__ == '__main__':
    main()
