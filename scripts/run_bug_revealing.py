#!/usr/bin/env python3
"""Run bug_revealing.py across defects4j-like projects and collect summaries.

用法:
  python3 run_bug_revealing.py [project_paths...]

示例:
  python3 run_bug_revealing.py /path/to/Csv_1_f
  python3 run_bug_revealing.py /path/to/Csv_1_f --test_dir "tests%20260328155208"
"""

import os
import sys
import glob
import argparse
import subprocess

PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
# 尝试定位核心脚本 bug_revealing.py
BUG_REVEALING = os.path.join(HERE, 'bug_revealing.py')

def extract_project_number(project_path):
    """提取项目路径中的数字，用于自然排序"""
    basename = os.path.basename(project_path)
    import re
    m = re.search(r'(\d+)', basename)
    try:
        return int(m.group(1)) if m else 9999
    except ValueError:
        return 9999


def find_projects(targets=None):
    """
    解析传入路径，返回项目列表。
    """
    projects = []
    if not targets:
        # 如果没有传入参数，不再依赖 config，而是提示用户或使用当前目录
        print("提示: 未指定项目路径。请手动传入项目目录或根目录。")
        return []

    seen = []
    for p in targets:
        ap = os.path.abspath(p)
        if not os.path.exists(ap):
            print(f"Warning: provided project path does not exist: {p}")
            continue

        base = os.path.basename(ap)

        # 情况1：传入的是单个 _f 或 _b 项目目录
        if (base.endswith('_f') or base.endswith('_b')) and os.path.isdir(ap):
            seen.append(ap)
            continue

        # 情况2：传入的是根目录，展开其下所有子目录
        # 兼容多种项目前缀，不再硬编码 Csv
        children_f = sorted(glob.glob(os.path.join(ap, '*_*_f')))
        children_b = sorted(glob.glob(os.path.join(ap, '*_*_b')))

        if children_f:
            for c in children_f:
                seen.append(os.path.abspath(c))
        elif children_b:
            for c in children_b:
                seen.append(os.path.abspath(c))
        else:
            print(f"Warning: provided path did not resolve to projects (no _f/_b folders): {p}")

    # 去重并按数字排序
    unique_projects = []
    for s in seen:
        if s not in unique_projects:
            unique_projects.append(s)
    
    return sorted(unique_projects, key=extract_project_number)


def find_newest_tests(project_root):
    """在给定项目目录下找最新的 tests%* 目录"""
    candidates = sorted(glob.glob(os.path.join(project_root, 'tests%*')))
    if not candidates:
        return None
    return os.path.abspath(candidates[-1])


def resolve_buggy_fixed(proj_path):
    """
    推导出 buggy_proj、fixed_proj 和 tests_source_proj。
    """
    proj_path = os.path.abspath(proj_path)
    project_name = os.path.basename(proj_path)
    parent_dir = os.path.dirname(proj_path)

    if project_name.endswith('_f'):
        fixed_proj = proj_path
        buggy_name = project_name[:-2] + '_b'
        buggy_proj = os.path.join(parent_dir, buggy_name)
        if not os.path.isdir(buggy_proj):
            print(f"❌ Buggy project not found for {project_name}, expected: {buggy_proj}")
            return None
        tests_source_proj = fixed_proj
        mode = "fixed-first"

    elif project_name.endswith('_b'):
        buggy_proj = proj_path
        fixed_name = project_name[:-2] + '_f'
        fixed_proj = os.path.join(parent_dir, fixed_name)
        if not os.path.isdir(fixed_proj):
            print(f"❌ Fixed project not found for {project_name}, expected: {fixed_proj}")
            return None
        tests_source_proj = buggy_proj
        mode = "buggy-first (legacy)"
    else:
        return None

    return buggy_proj, fixed_proj, tests_source_proj

def run_for_project(proj_path, specified_test_dir=None):
    """运行单个项目变体"""
    res = resolve_buggy_fixed(proj_path)
    if not res: return
    buggy_proj, fixed_proj, tests_source_proj = res

    if specified_test_dir:
        if os.path.isabs(specified_test_dir):
            tests_dir = specified_test_dir
        else:
            tests_dir = os.path.join(tests_source_proj, specified_test_dir)
    else:
        tests_dir = find_newest_tests(tests_source_proj)

    if not tests_dir or not os.path.exists(tests_dir):
        print(f"❌ Error: Test directory not found: {tests_dir}")
        return

    cmd = [
        PY, BUG_REVEALING,
        '--buggy', buggy_proj,
        '--fixed', fixed_proj,
        '--tests', tests_dir,
    ]
    
    print(f"🚀 Running: {os.path.basename(proj_path)} | Dir: {os.path.basename(tests_dir)}")
    
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            print(f"  FAILED: rc={proc.returncode}\n  Error: {proc.stderr}")
        else:
            print(f"  SUCCESS")
    except Exception as e:
        print(f"  CRASHED: {e}")


def main():
    parser = argparse.ArgumentParser(description='Batch run bug_revealing without config dependency.')
    parser.add_argument('projects', nargs='*', help='Project paths (_f or _b).')
    parser.add_argument('--test_dir', type=str, help='Manual specified test directory name')
    
    args = parser.parse_args()

    # 如果没有任何参数，强制退出提示
    if not args.projects:
        print("Usage: python3 run_bug_revealing.py [project_paths...]")
        sys.exit(1)

    projects = find_projects(args.projects)

    if not projects:
        print('No valid projects resolved.')
        return

    for p in projects:
        run_for_project(p, specified_test_dir=args.test_dir)

if __name__ == '__main__':
    main()