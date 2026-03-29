#!/usr/bin/env python3
"""Compute tree similarities (top-down, bottom-up, combined) on AST CSV outputs.

Usage:
  python3 measure_similarity.py /path/to/tests_dir

"""
import os
import sys
import csv
import html
import re
from collections import defaultdict
from typing import List, Tuple, Dict
import xml.etree.ElementTree as ET


# ─────────────────────────────────────────────────────────────────────────────
# XML 标签名清洗
# ─────────────────────────────────────────────────────────────────────────────
def sanitize_xml_tags(xml_str: str) -> str:
    """
    将 XML 标签名中不合法的字符替换为下划线。
    合法 XML 名称字符：字母、数字、_ . - :（且不能以数字或 - 开头）
    AST 生成器产生的非法示例：<ASSIGNMENT-=>  <OP-+=>  <IF-ELSE>
    """
    def fix_match(m):
        prefix    = m.group(1)   # '' or '/'  (closing slash)
        tag       = m.group(2)   # raw tag name
        suffix    = m.group(3)   # '' or '/'  (self-closing slash)
        tag_clean = re.sub(r'[^A-Za-z0-9_.\-:]', '_', tag)
        if tag_clean and tag_clean[0] in '0123456789-':
            tag_clean = '_' + tag_clean
        return f'<{prefix}{tag_clean}{suffix}>'
    return re.sub(r'<(/?)([^>/\s][^>]*?)(/?)>', fix_match, xml_str)


# ─────────────────────────────────────────────────────────────────────────────
# Node / tree
# ─────────────────────────────────────────────────────────────────────────────
class Node:
    _id_counter = 0

    def __init__(self, label):
        self.label = label
        self.children = []
        self.parent = None
        self.id = Node._id_counter
        Node._id_counter += 1
        self.subtree_nodes = None
        self.subtree_size = None
        self.signature = None


def build_tree_from_element(elem) -> Node:
    node = Node(elem.tag)
    for child in list(elem):
        child_node = build_tree_from_element(child)
        child_node.parent = node
        node.children.append(child_node)
    return node


def compute_subtree_info(root: Node):
    nodes = []

    def dfs(n):
        for c in n.children:
            dfs(c)
        nodes.append(n)

    dfs(root)
    for n in nodes:
        s = {n.id}
        for c in n.children:
            s |= c.subtree_nodes
        n.subtree_nodes = s
        n.subtree_size = len(s)
        child_sigs = [c.signature for c in n.children]
        n.signature = n.label + '(' + ','.join(child_sigs) + ')'


# ─────────────────────────────────────────────────────────────────────────────
# Top-down similarity
# ─────────────────────────────────────────────────────────────────────────────
def topdown_size(a: Node, b: Node, memo: Dict[Tuple[int, int], int]) -> int:
    key = (a.id, b.id)
    if key in memo:
        return memo[key]
    if a.label != b.label:
        memo[key] = 0
        return 0
    m, n = len(a.children), len(b.children)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            v1 = dp[i + 1][j]
            v2 = dp[i][j + 1]
            match = topdown_size(a.children[i], b.children[j], memo)
            v3 = dp[i + 1][j + 1] + match if match > 0 else dp[i + 1][j + 1]
            dp[i][j] = max(v1, v2, v3)
    res = 1 + dp[0][0]
    memo[key] = res
    return res


def topdown_match(a: Node, b: Node, memo: Dict[Tuple[int, int], int]) -> Tuple[set, set]:
    matched_a, matched_b = set(), set()
    if a.label != b.label:
        return matched_a, matched_b
    matched_a.add(a.id)
    matched_b.add(b.id)
    m, n = len(a.children), len(b.children)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            v1 = dp[i + 1][j]
            v2 = dp[i][j + 1]
            match = topdown_size(a.children[i], b.children[j], memo)
            v3 = dp[i + 1][j + 1] + match if match > 0 else dp[i + 1][j + 1]
            dp[i][j] = max(v1, v2, v3)
    i = j = 0
    while i < m and j < n:
        if dp[i][j] == dp[i + 1][j]:
            i += 1
        elif dp[i][j] == dp[i][j + 1]:
            j += 1
        else:
            if topdown_size(a.children[i], b.children[j], memo) > 0:
                sub_a, sub_b = topdown_match(a.children[i], b.children[j], memo)
                matched_a |= sub_a
                matched_b |= sub_b
                i += 1
                j += 1
            else:
                i += 1
    return matched_a, matched_b


# ─────────────────────────────────────────────────────────────────────────────
# Bottom-up similarity
# ─────────────────────────────────────────────────────────────────────────────
def bottomup_match(root1: Node, root2: Node) -> Tuple[set, set, int]:
    sig_map1, sig_map2 = defaultdict(list), defaultdict(list)

    def collect(n, sigmap):
        sigmap[n.signature].append(n)
        for c in n.children:
            collect(c, sigmap)

    collect(root1, sig_map1)
    collect(root2, sig_map2)

    used1, used2 = set(), set()
    matched_count = 0
    ids1, ids2 = set(), set()

    for sig in sig_map1:
        if sig not in sig_map2:
            continue
        l1 = sorted(sig_map1[sig], key=lambda x: x.subtree_size, reverse=True)
        l2 = sorted(sig_map2[sig], key=lambda x: x.subtree_size, reverse=True)
        i = j = 0
        while i < len(l1) and j < len(l2):
            n1, n2 = l1[i], l2[j]
            if n1.subtree_nodes & used1:
                i += 1
                continue
            if n2.subtree_nodes & used2:
                j += 1
                continue
            matched_count += n1.subtree_size
            ids1 |= n1.subtree_nodes
            ids2 |= n2.subtree_nodes
            used1 |= n1.subtree_nodes
            used2 |= n2.subtree_nodes
            i += 1
            j += 1
    return ids1, ids2, matched_count


# ─────────────────────────────────────────────────────────────────────────────
# I/O helpers
# ─────────────────────────────────────────────────────────────────────────────
def read_ast_csv(ast_csv_path: str) -> Dict[str, list]:
    res = defaultdict(list)
    if not os.path.exists(ast_csv_path):
        return res
    try:
        # 以二进制读取，剔除 NUL 字节后再 decode
        raw = open(ast_csv_path, 'rb').read()
        if b'\x00' in raw:
            print(f'  [WARN] NUL bytes found in {os.path.basename(ast_csv_path)}, stripping...')
            raw = raw.replace(b'\x00', b'')
        text = raw.decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  [ERROR] Cannot read AST CSV {ast_csv_path}: {e}')
        return res
 
    import io
    reader = csv.reader(io.StringIO(text))
    next(reader, None)   # skip header
    for row in reader:
        try:
            if len(row) < 2:
                continue
            name = row[0].strip().strip('"')
            if not name:
                continue
            filepart = name.split('.', 1)[0] if '.' in name else name
            res[filepart].append(html.unescape(row[1]).strip())
        except Exception:
            continue
    return res


def xml_to_tree(xml_str: str) -> 'Node | None':
    """解析 XML 字符串为 Node 树；先清洗标签名（Bug C 修复）再解析。"""
    sanitized = sanitize_xml_tags(xml_str)
    try:
        root_elem = ET.fromstring(sanitized)
    except Exception:
        try:
            root_elem = ET.fromstring('<ROOT>' + sanitized + '</ROOT>')
        except Exception:
            return None
    return build_tree_from_element(root_elem)


def group_by_method(test_names: List[str]) -> Dict[str, List[str]]:
    """
    支持两种命名格式：
      旧: CSVParser_1_2Test       → key = "1"（method_id）
      新: Csv_CSVParser_parse_1Test → key = "parse"（method名）
    """
    groups = defaultdict(list)
    for tn in test_names:
        # 新命名格式: {Project}_{ClassName}_{MethodName}_{seq}Test
        # 特征：末尾是 _{纯数字}Test，倒数第二段是方法名（非纯数字）
        m_new = re.match(r'^[A-Za-z][^_]*_[A-Za-z][^_]*_([A-Za-z][^_]*)_\d+Test$', tn)
        if m_new:
            key = m_new.group(1)   # 方法名作为 key，如 "parse"
        else:
            # 旧命名: ClassName_methodId_seqTest
            m_old = re.search(r'_(\d+)_', tn)
            if m_old:
                key = m_old.group(1)
            else:
                m2 = re.search(r'(\d+)', tn)
                key = m2.group(1) if m2 else 'default'
        groups[key].append(tn)
    return groups


def extract_target_class_from_test_names(test_names: List[str]) -> str:
    """
    支持两种命名格式：
      旧: CSVParser_1_2Test       → "CSVParser"
      新: Csv_CSVParser_parse_1Test → "CSVParser"
    """
    if not test_names:
        return ''
    first = test_names[0]
    if first.endswith('Test'):
        first = first[:-4]
    parts = first.split('_')
    
    # 新命名检测：第一段是 Project 前缀（Csv/Lang 等短名），第二段才是 ClassName
    # 启发式：若 parts[0] 长度 ≤ 4 且全字母，且 parts 有 4 段以上，认为是新格式
    if (len(parts) >= 4 and
            len(parts[0]) <= 6 and parts[0].isalpha() and
            not parts[1].isdigit()):
        return parts[1]   # 直接取第二段作为 ClassName
    
    # 旧命名：走原逻辑
    target = ''
    for p in parts:
        if p.isdigit():
            break
        target = (target + '_' + p) if target else p
    return target

def build_full_name_map(test_cases_dir: str) -> Dict[str, str]:
    """
    扫描 test_cases_dir 下所有 *Test.java 文件，读取其 package 声明，
    返回 {short_name: full_qualified_name} 映射。
    例：CSVRecord_7_6Test → org.apache.commons.csv.CSVRecord_7_6Test
    """
    fmap: Dict[str, str] = {}
    if not test_cases_dir or not os.path.isdir(test_cases_dir):
        return fmap
    for fname in os.listdir(test_cases_dir):
        if not fname.endswith('.java'):
            continue
        short = fname[:-5]  # 去掉 .java
        fpath = os.path.join(test_cases_dir, fname)
        pkg = ''
        try:
            with open(fpath, 'r', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('package '):
                        pkg = line.replace('package', '').replace(';', '').strip()
                        break
        except Exception:
            pass
        fmap[short] = f'{pkg}.{short}' if pkg else short
    return fmap
# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def process_tests_dir(tests_dir: str):
    tests_dir = os.path.abspath(tests_dir)
    if os.path.basename(tests_dir) == 'test_cases':
        top_tests_dir = os.path.dirname(tests_dir)
    elif os.path.basename(tests_dir).startswith('tests'):
        top_tests_dir = tests_dir
    else:
        top_tests_dir = os.path.dirname(tests_dir)

    project_dir = os.path.dirname(top_tests_dir)
    proj_prefix = os.path.basename(project_dir)
    proj_short  = re.sub(r'(_b|_f)$', '', proj_prefix)

    ast_dir = os.path.join(top_tests_dir, 'AST')
    ast_csv_short  = os.path.join(ast_dir, f'{proj_short}_AST.csv')
    ast_csv_legacy = os.path.join(ast_dir, f'{proj_prefix}_AST.csv')
    if os.path.exists(ast_csv_short):
        ast_csv = ast_csv_short
    elif os.path.exists(ast_csv_legacy):
        ast_csv = ast_csv_legacy
    else:
        print('AST CSV not found (tried):', ast_csv_short, 'and', ast_csv_legacy)
        return

    mapping = read_ast_csv(ast_csv)
    if not mapping:
        print('No ASTs parsed from', ast_csv)
        return

    # 构建树（sanitize 后应 100% 成功）
    trees = {}
    parse_failed = []
    for fname, xml_list in mapping.items():
        combined_xml = '<ROOT>' + ''.join(xml_list) + '</ROOT>'
        node = xml_to_tree(combined_xml)
        if node is None:
            parse_failed.append(fname)
            print(f'  [WARN] xml_to_tree still failed after sanitize: {fname}')
            continue
        compute_subtree_info(node)
        trees[fname] = node

    all_test_names = list(mapping.keys())   # 全集
    target_class   = extract_target_class_from_test_names(all_test_names)
    groups         = group_by_method(all_test_names)

    print(f'  AST entries: {len(all_test_names)}, trees built: {len(trees)}, '
          f'parse_failed: {len(parse_failed)}')

    _tc_dir = (os.path.join(top_tests_dir, 'test_cases')
               if os.path.isdir(os.path.join(top_tests_dir, 'test_cases'))
               else top_tests_dir)
    full_name_map = build_full_name_map(_tc_dir)
    if full_name_map:
        print(f'  [FULL_NAME_MAP] Loaded {len(full_name_map)} entries from {_tc_dir}')
    else:
        print(f'  [FULL_NAME_MAP] No entries loaded (dir: {_tc_dir}), short names will be used')
 
    def to_full(short_name: str) -> str:
        """短名 → 全限定名；映射缺失则原样返回"""
        return full_name_map.get(short_name, short_name)

    sim_dir = os.path.join(top_tests_dir, 'Similarity')
    os.makedirs(sim_dir, exist_ok=True)
    sims_csv = os.path.join(sim_dir, f'{proj_short}_Sims.csv')
    if target_class:
        big_csv    = os.path.join(sim_dir, f'{proj_short}_{target_class}_bigSims.csv')
        bigsum_csv = os.path.join(sim_dir, f'{proj_short}_{target_class}_bigSimssum.csv')
    else:
        big_csv    = os.path.join(sim_dir, f'{proj_short}_bigSims.csv')
        bigsum_csv = os.path.join(sim_dir, f'{proj_short}_bigSimssum.csv')

    best_map = {}   # {test_name: (src, dst, nodes_per_tree, comb_sim)}

    with open(sims_csv, 'w', newline='', encoding='utf-8') as sf:
        w = csv.writer(sf)
        w.writerow(['project', 'target_class', 'test_case_1', 'test_case_2',
                    'topdown_subtree_size', 'topdown_similarity',
                    'bottomup_subtree_size', 'bottomup_similarity',
                    'combined_subtree_size', 'combined_similarity', 'redundancy_score'])

        for key, members in groups.items():
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a_name, b_name = members[i], members[j]
                    a = trees.get(a_name)
                    b = trees.get(b_name)

                    # Bug B 修复：树缺失时写 sim=0 兜底
                    if a is None or b is None:
                        for _missing in ([a_name] if a is None else []) + \
                                        ([b_name] if b is None else []):
                            if _missing not in best_map:
                                best_map[_missing] = (_missing, '', 0, 0.0)
                                print(f'  [WARN] No tree for {_missing}, sim=0.0')
                        continue

                    size1, size2 = a.subtree_size, b.subtree_size
                    memo = {}
                    td_nodes = max(0, topdown_size(a, b, memo) - 1)
                    td_sim   = (2.0 * td_nodes) / (size1 + size2) if (size1 + size2) > 0 else 0.0
                    td_ids_a, td_ids_b = topdown_match(a, b, memo)

                    bu_ids_a, bu_ids_b, bu_nodes = bottomup_match(a, b)
                    bu_sim = (2.0 * bu_nodes) / (size1 + size2) if (size1 + size2) > 0 else 0.0

                    union_a = set(td_ids_a) | set(bu_ids_a)
                    union_b = set(td_ids_b) | set(bu_ids_b)
                    nodes_per_tree = int(round((len(union_a) + len(union_b)) / 2.0))
                    comb_sim   = (2.0 * nodes_per_tree) / (size1 + size2) if (size1 + size2) > 0 else 0.0
                    redundancy = 1.0 - comb_sim

                    w.writerow([proj_short, target_class, to_full(a_name), to_full(b_name),
                                 td_nodes, f'{td_sim:.6f}',
                                 bu_nodes, f'{bu_sim:.6f}',
                                 nodes_per_tree, f'{comb_sim:.6f}', f'{redundancy:.6f}'])

                    # Bug A 修复：prev[3] 才是 comb_sim
                    for src, dst, val in [(a_name, b_name, comb_sim),
                                          (b_name, a_name, comb_sim)]:
                        prev = best_map.get(src)
                        if prev is None or val > prev[3]:
                            best_map[src] = (src, dst, nodes_per_tree, comb_sim)

    # 兜底：全集里没进入 best_map 的（孤立 / 漏网）
    for tc in all_test_names:
        if tc not in best_map:
            best_map[tc] = (tc, '', 0, 0.0)
            print(f'  [UNMATCHED] {tc}: no valid pair found, sim=0.0')

    # bigSims
    with open(big_csv, 'w', newline='', encoding='utf-8') as bf:
        w = csv.writer(bf)
        w.writerow(['project', 'target_class', 'test_case_1', 'test_case_2',
                    'combined_subtree_size', 'combined_similarity', 'redundancy_score'])
        for tc, rec in best_map.items():
            full_tc1 = to_full(rec[0])
            full_tc2 = to_full(rec[1]) if rec[1] else ''
            w.writerow([proj_short, target_class, full_tc1, full_tc2,
                        rec[2], f'{rec[3]:.6f}', f'{1.0 - rec[3]:.6f}'])

    # bigSimssum
    vals   = [rec[3] for rec in best_map.values()]
    n      = len(vals)
    sumsq  = sum(v * v for v in vals)
    meansq = sumsq / n if n > 0 else 0.0
    with open(bigsum_csv, 'w', newline='', encoding='utf-8') as bs:
        w = csv.writer(bs)
        w.writerow(['project', 'n_tests', 'sum_of_squares', 'mean_of_squares'])
        w.writerow([proj_short, n, f'{sumsq:.6f}', f'{meansq:.6f}'])
    print(f'mean_of_squares: {meansq:.6f}')

    complete = len(best_map) == len(all_test_names)
    print(f'Wrote similarity CSVs to {sim_dir}')
    print(f'  bigSims: {len(best_map)}/{len(all_test_names)} '
          f'({"✅ complete" if complete else "⚠️ INCOMPLETE"})')
    if not complete:
        print(f'  Missing: {set(all_test_names) - set(best_map.keys())}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: measure_similarity.py /path/to/tests_dir')
        sys.exit(1)
    process_tests_dir(sys.argv[1])