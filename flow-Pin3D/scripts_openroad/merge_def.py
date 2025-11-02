#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import re
from typing import Dict, Tuple, List

# 修改正则表达式，使其更准确
HDR_RE   = re.compile(r'^\s*-\s+(\S+)\s+(\S+)')  # "- inst master"
PLACE_RE = re.compile(
    r'\+\s*(?:PLACED|FIXED)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*([A-Z0-9]+)',
    re.IGNORECASE
)

def build_map(path: str) -> Dict[str, Tuple[str,str,str]]:
    """从给定 DEF 的 COMPONENTS 段里提取 inst -> (x,y,orient)"""
    with open(path,'r',encoding='utf-8',errors='ignore') as f:
        L = f.readlines()
    # 找段
    try:
        s = next(i for i,l in enumerate(L) if l.strip().startswith('COMPONENTS'))
        e = next(i for i in range(s+1,len(L)) if L[i].strip()=='END COMPONENTS')
    except StopIteration:
        return {}
    
    m: Dict[str, Tuple[str,str,str]] = {}
    cur = None
    i = s + 1
    
    while i < e:
        line = L[i]
        # 检查是否是新组件的开始
        h = HDR_RE.match(line)
        if h:
            cur = h.group(1)
            # 继续读取直到找到分号
            full_component = line
            j = i + 1
            while j < e and ';' not in L[j-1]:
                full_component += L[j]
                j += 1
            
            # 在整个组件定义中查找PLACED信息
            p = PLACE_RE.search(full_component)
            if p:
                m[cur] = (p.group(1), p.group(2), p.group(3))
            
            i = j - 1  # 移动到分号所在行
        
        i += 1
    
    return m

def merge(base: str, upper: Dict[str,Tuple[str,str,str]], bottom: Dict[str,Tuple[str,str,str]], outp: str):
    with open(base,'r',encoding='utf-8',errors='ignore') as f:
        L = f.readlines()
    # 段定位
    try:
        s = next(i for i,l in enumerate(L) if l.strip().startswith('COMPONENTS'))
        e = next(i for i in range(s+1,len(L)) if L[i].strip()=='END COMPONENTS')
    except StopIteration:
        with open(outp,'w',encoding='utf-8') as o: o.writelines(L); return

    cur = None
    component_start = -1
    has_placement = False
    
    for i in range(s+1, e):
        line = L[i]
        h = HDR_RE.match(line)
        if h:
            cur = h.group(1)
            component_start = i
            has_placement = False

        if cur:
            # 检查是否有来自upper或bottom的坐标信息
            xyo = upper.get(cur) or bottom.get(cur)
            
            # 检查当前行是否包含PLACED信息
            p = PLACE_RE.search(line)
            if p:
                has_placement = True
                if xyo:
                    # 如果有新的坐标信息，替换它
                    x, y, o = xyo
                    # 使用更精确的替换
                    old_placed = p.group(0)
                    new_placed = f"+ PLACED ( {x} {y} ) {o}"
                    L[i] = line.replace(old_placed, new_placed)
            
            # 如果到达分号且没有placement信息，但有来自upper/bottom的信息
            if ';' in line and not has_placement and xyo:
                # 找到合适的缩进
                indent = "      "  # 默认缩进
                # 查找该组件中是否有其他 '+' 开头的行来确定缩进
                for j in range(component_start, i+1):
                    if L[j].lstrip().startswith('+'):
                        indent = L[j][:len(L[j]) - len(L[j].lstrip())]
                        break
                
                x, y, o = xyo
                # 在分号前插入PLACED信息
                semicolon_pos = line.find(';')
                if semicolon_pos != -1:
                    # 如果分号在行尾，需要在分号前插入新行
                    if line.strip() == ';':
                        # 分号独占一行的情况
                        L[i] = f"{indent}+ PLACED ( {x} {y} ) {o}\n{line}"
                    else:
                        # 分号在其他内容后面的情况
                        line_before_semicolon = line[:semicolon_pos].rstrip()
                        line_after_semicolon = line[semicolon_pos:]
                        L[i] = f"{line_before_semicolon}\n{indent}+ PLACED ( {x} {y} ) {o} {line_after_semicolon}"

        if ';' in line:
            cur = None
            component_start = -1
            has_placement = False

    with open(outp,'w',encoding='utf-8') as o:
        o.writelines(L)

def main():
    ap = argparse.ArgumentParser(description='Tier-merged DEF placer (streaming, no block split).')
    ap.add_argument('--base',   required=True)
    ap.add_argument('--upper',  required=True)
    ap.add_argument('--bottom', required=True)
    ap.add_argument('--out',    required=True)
    args = ap.parse_args()

    um = build_map(args.upper)
    bm = build_map(args.bottom)
    
    # 调试信息
    print(f"[merge_def] Upper instances found: {len(um)}")
    print(f"[merge_def] Bottom instances found: {len(bm)}")
    
    # 合并所有唯一的实例
    all_instances = set(um.keys()) | set(bm.keys())
    print(f"[merge_def] Total unique instances to merge: {len(all_instances)}")
    
    merge(args.base, um, bm, args.out)
    print(f"[merge_def] Done. Output: {args.out}")

if __name__ == '__main__':
    main()
