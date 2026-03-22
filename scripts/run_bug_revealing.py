#!/usr/bin/env python3
"""Run bug_revealing.py across defects4j-like projects and collect summaries.

Usage: python3 run_bug_revealing.py [project_paths...]
If no projects passed, will scan `project_dir` from `src/config.py` for Csv*_*_b directories.

For each project found (buggy _b), this script:
 - finds the newest tests%* directory under the project
 - invokes scripts/bug_revealing.py with --buggy, --fixed, --tests and lets the script
   write its CSV into the tests* directory (default behavior)
 - prints progress and errors

Outputs are placed under each tests* directory (bugrevealing.csv)
"""

import os
import sys
import glob
import argparse
import subprocess
from config import project_dir

PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
BUG_REVEALING = os.path.join(HERE, 'bug_revealing.py')


def extract_project_number(project_path):
    """提取项目路径中的数字（比如Csv_12_b → 12），用于自然排序"""
    basename = os.path.basename(project_path)
    # 拆分规则：去掉Csv_和_b，取第一个数字部分
    # 适配格式：Csv_1_b、Csv_10_b、Csv_12_xxx_b等
    num_part = basename.replace('Csv_', '').replace('_b', '').split('_')[0]
    try:
        return int(num_part)
    except ValueError:
        # 非数字命名的项目放最后
        return 9999


def find_projects(targets=None):
    projects = []
    if targets and len(targets) > 0:
        seen = []
        for p in targets:
            ap = os.path.abspath(p)
            if not os.path.exists(ap):
                print(f"Warning: provided project path does not exist: {p}")
                continue
            # If the provided path is a defects4j root containing many Csv*_*_b projects,
            # expand them.
            children = sorted(glob.glob(os.path.join(ap, 'Csv*_12_b')))
            if children:
                for c in children:
                    seen.append(os.path.abspath(c))
                continue
            # If the provided path itself looks like a single buggy project (endswith _b), accept it
            base = os.path.basename(ap)
            if base.startswith('Csv') and base.endswith('_b') and os.path.isdir(ap):
                seen.append(ap)
                continue
            # Otherwise, try to find Csv*_*_b under this path (one level deep)
            children2 = sorted(glob.glob(os.path.join(ap, '*', 'Csv*_12_b')))
            if children2:
                for c in children2:
                    seen.append(os.path.abspath(c))
                continue
            print(f"Warning: provided path did not resolve to projects: {p}")
        # deduplicate while preserving order
        projects = []
        for s in seen:
            if s not in projects:
                projects.append(s)
        # 关键修改1：对用户传入路径解析出的项目按数字序排序
        projects = sorted(projects, key=extract_project_number)
        return projects
    # discover under project_dir
    root = os.path.abspath(project_dir)
    if not os.path.isdir(root):
        print(f"project_dir from config not found: {root}")
        return []
    # 关键修改2：扫描config目录的项目时按数字序排序
    candidate_projects = glob.glob(os.path.join(root, 'Csv*_12_b'))
    for p in sorted(candidate_projects, key=extract_project_number):
        projects.append(os.path.abspath(p))
    return projects


def find_newest_tests(project_root):
    candidates = sorted(glob.glob(os.path.join(project_root, 'tests%*')))
    if not candidates:
        return None
    # prefer lexicographically last (assumes timestamp-like suffix)
    return os.path.abspath(candidates[-1])


def run_for_project(buggy_proj):
    project_name = os.path.basename(buggy_proj)
    if not project_name.endswith('_b'):
        print(f"Skipping non-buggy project: {project_name}")
        return
    fixed_proj = os.path.join(os.path.dirname(buggy_proj), project_name.replace('_b', '_f'))
    if not os.path.isdir(fixed_proj):
        print(f"Fixed project not found for {project_name}, expected: {fixed_proj}")
        return
    tests = find_newest_tests(buggy_proj)
    if not tests:
        print(f"No tests%* directory found under {buggy_proj}, skipping")
        return
    # prefer the parent tests* dir (not test_cases)
    tests_dir = tests
    # build command: use Python executable to run bug_revealing.py
    cmd = [PY, BUG_REVEALING, '--buggy', buggy_proj, '--fixed', fixed_proj, '--tests', tests_dir]
    print(f"Running bug_revealing for {project_name} using tests dir: {tests_dir}")
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(proc.stdout)
        if proc.returncode != 0:
            print(f"bug_revealing failed for {project_name}, rc={proc.returncode}")
            print(proc.stderr)
        else:
            print(f"Completed {project_name}, results in {tests_dir}")
    except Exception as e:
        print(f"Error running bug_revealing for {project_name}: {e}")


def main():
    parser = argparse.ArgumentParser(description='Run bug_revealing across projects')
    parser.add_argument('projects', nargs='*', help='Optional project paths (Csv*_?_b). If empty, uses config.project_dir discovery')
    args = parser.parse_args()

    projects = find_projects(args.projects if args.projects else None)
    if not projects:
        print('No projects found to run')
        return
    for p in projects:
        run_for_project(p)


if __name__ == '__main__':
    main()
