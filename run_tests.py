"""
run_tests.py  — HITS unified test evaluation runner

Executes generated tests from each tests%* directory, then chains:
  1. Task.all_test()         → compile + exec + coverage CSVs
  2. bug_revealing.py        → bugrevealing + bugrevealing_class_level + details.txt
  3. code_to_ast.py          → AST CSV under tests*/AST/
  4. measure_similarity.py   → Similarity CSVs under tests*/Similarity/

Output files (all under tests%* directory, named {project}_{class}_*):
  status.csv, coverage.csv, coveragedetail.csv, coveragemethod.csv,
  final_scores.csv, final_scores2.csv,
  bugrevealing.csv, bugrevealing_class_level.csv, bugrevealing.details.txt,
  Similarity/*_bigSims.csv, Similarity/*_bigSimssum.csv, Similarity/*_Sims.csv

Usage:
  python run_tests.py /home/chenlu/defect4j_projects
  python run_tests.py /home/chenlu/defect4j_projects/Csv_1_b
  python run_tests.py /home/chenlu/defect4j_projects/Csv_1_b /home/chenlu/defect4j_projects/Csv_2_b
"""

import os
import re
import glob
import argparse
import subprocess
import sys

# ── import config first (must succeed before any other HITS import) ──────────
try:
    from utils.config import *
    _HITS_ROOT = os.path.dirname(os.path.abspath(__file__))
except ImportError:
    _HITS_ROOT = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _HITS_ROOT)
    from utils.config import *

try:
    from utils.config import project_dir as _default_project_dir
except ImportError:
    _default_project_dir = None

# ── Task  (uses the new test_runner.py) ──────────────────────────────────────
try:
    from scripts.task import Task
except ImportError:
    # fallback: inline minimal Task shim
    class Task:
        @staticmethod
        def all_test(test_path, target_path):
            from utils.test_runner import TestRunner
            runner = TestRunner(test_path, target_path)
            return runner.start_all_test()


def _project_number(path):
    """Natural sort key: extract first integer from basename."""
    name = os.path.basename(path)
    m = re.search(r'(\d+)', name)
    return int(m.group(1)) if m else 10 ** 9


def _find_all_projects(roots):
    """Expand a list of paths into individual _b or _f project dirs."""
    projects = []
    for root in roots:
        root = os.path.abspath(root)
        if not os.path.exists(root):
            print(f"[WARN] path not found, skipping: {root}")
            continue
        # Direct project (has pom.xml or tests%* inside)
        if (os.path.isfile(os.path.join(root, 'pom.xml')) or
                glob.glob(os.path.join(root, 'tests%*'))):
            projects.append(root)
            continue
        # Directory of projects
        children = (sorted(glob.glob(os.path.join(root, 'Csv*_*_f'))) +
                    sorted(glob.glob(os.path.join(root, 'Csv*_*_b'))))
        if children:
            projects.extend(children)
            continue
        # Fallback: any subdir that has tests%*
        for entry in sorted(os.listdir(root)):
            ep = os.path.join(root, entry)
            if os.path.isdir(ep) and glob.glob(os.path.join(ep, 'tests%*')):
                projects.append(ep)
    # deduplicate while preserving order, then sort by embedded number
    seen = set()
    unique = []
    for p in projects:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return sorted(unique, key=_project_number)


def _latest_tests_dir(project_path):
    """Return the newest tests%* directory under project_path."""
    candidates = [p for p in glob.glob(os.path.join(project_path, 'tests%*'))
                  if os.path.isdir(p)]
    if not candidates:
        return None

    def _ts_key(p):
        m = re.search(r'(\d+)', os.path.basename(p))
        return int(m.group(1)) if m else 0

    return sorted(candidates, key=_ts_key)[-1]


def _run_bug_revealing(project_path, tests_dir):
    """Run scripts/bug_revealing.py for a project."""
    proj_name = os.path.basename(project_path)
    # Determine buggy/fixed pair
    if proj_name.endswith('_f'):
        buggy = os.path.join(os.path.dirname(project_path),
                             proj_name[:-2] + '_b')
        fixed = project_path
    elif proj_name.endswith('_b'):
        buggy = project_path
        fixed = os.path.join(os.path.dirname(project_path),
                             proj_name[:-2] + '_f')
    else:
        print(f"  [bug_revealing] Skipping (not a _b/_f project): {proj_name}")
        return

    if not os.path.isdir(fixed):
        print(f"  [bug_revealing] Fixed project not found: {fixed}")
        return
    if not os.path.isdir(buggy):
        print(f"  [bug_revealing] Buggy project not found: {buggy}")
        return

    script = os.path.join(_HITS_ROOT, 'scripts', 'bug_revealing.py')
    if not os.path.exists(script):
        print(f"  [bug_revealing] Script not found: {script}")
        return

    cmd = [sys.executable, script,
           '--buggy', buggy,
           '--fixed', fixed,
           '--tests', tests_dir]
    print(f"  [bug_revealing] Running: {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            print(f"  [bug_revealing] FAILED (rc={proc.returncode}):\n{proc.stderr[:500]}")
        else:
            # print a one-line summary from stdout
            for line in proc.stdout.splitlines():
                if 'Bug revealing' in line or 'SUMMARY' in line or 'Total' in line:
                    print(f"  [bug_revealing] {line}")
    except Exception as e:
        print(f"  [bug_revealing] Exception: {e}")


def _run_ast_and_similarity(tests_dir):
    """Run code_to_ast.py then measure_similarity.py on the tests* directory."""
    code_to_ast_script = os.path.join(_HITS_ROOT, 'scripts', 'code_to_ast.py')
    measure_sim_script = os.path.join(_HITS_ROOT, 'scripts', 'measure_similarity.py')

    if os.path.exists(code_to_ast_script):
        print(f"  [AST] Running code_to_ast on {os.path.basename(tests_dir)}")
        try:
            proc = subprocess.run(
                [sys.executable, code_to_ast_script, tests_dir],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc.returncode != 0:
                print(f"  [AST] FAILED (rc={proc.returncode}): {proc.stderr[:300]}")
            else:
                print(f"  [AST] Done")
        except Exception as e:
            print(f"  [AST] Exception: {e}")
    else:
        print(f"  [AST] Script not found: {code_to_ast_script}")

    if os.path.exists(measure_sim_script):
        print(f"  [Similarity] Running measure_similarity on {os.path.basename(tests_dir)}")
        try:
            proc = subprocess.run(
                [sys.executable, measure_sim_script, tests_dir],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc.returncode != 0:
                print(f"  [Similarity] FAILED (rc={proc.returncode}): {proc.stderr[:300]}")
            else:
                for line in proc.stdout.splitlines():
                    if 'bigSims' in line or 'Written' in line or 'Wrote' in line:
                        print(f"  [Similarity] {line}")
        except Exception as e:
            print(f"  [Similarity] Exception: {e}")
    else:
        print(f"  [Similarity] Script not found: {measure_sim_script}")


def run_tests(target_projects=None):
    """
    Main entry point.

    For each project:
      1. Find the newest tests%* directory
      2. Run Task.all_test() → generates coverage CSVs (status, coverage,
         coveragedetail, coveragemethod, final_scores, final_scores2)
      3. Run bug_revealing.py → bugrevealing CSVs + details
      4. Run code_to_ast.py + measure_similarity.py → similarity CSVs
    """
    if target_projects:
        projects = _find_all_projects(target_projects)
    elif _default_project_dir and os.path.isdir(_default_project_dir):
        projects = _find_all_projects([_default_project_dir])
    else:
        print("No projects specified and config.project_dir not set.")
        return

    if not projects:
        print("No valid project directories found.")
        return

    print(f"Found {len(projects)} project(s) to evaluate.")

    for project_path in projects:
        proj_name = os.path.basename(project_path)
        print(f"\n{'='*60}")
        print(f"Project: {proj_name}")
        print(f"{'='*60}")

        tests_dir = _latest_tests_dir(project_path)
        if not tests_dir:
            print(f"  [WARN] No tests%* directory found under {project_path}, skipping.")
            continue
        print(f"  Using tests dir: {tests_dir}")

        # ── Step 1: Compile + execute + coverage ──────────────────────
        print(f"  [Step 1] Running tests and collecting coverage...")
        try:
            result = Task.all_test(tests_dir, project_path)
            if isinstance(result, tuple):
                total_compile, total_run = result
                print(f"  [Step 1] Done — compiled={total_compile}, ran={total_run}")
            else:
                print(f"  [Step 1] Done")
        except Exception as e:
            import traceback
            print(f"  [Step 1] ERROR: {e}")
            traceback.print_exc()

        # ── Step 2: Bug-revealing ──────────────────────────────────────
        print(f"  [Step 2] Running bug_revealing...")
        _run_bug_revealing(project_path, tests_dir)

        # ── Step 3: AST + Similarity ──────────────────────────────────
        print(f"  [Step 3] Running AST + similarity analysis...")
        _run_ast_and_similarity(tests_dir)

        # ── Print produced files ──────────────────────────────────────
        produced = [f for f in glob.glob(os.path.join(tests_dir, '*.csv'))
                    if os.path.getsize(f) > 0]
        if produced:
            print(f"  [Output] CSV files in {os.path.basename(tests_dir)}:")
            for p in sorted(produced):
                print(f"    {os.path.basename(p)}")

    print(f"\n{'='*60}")
    print("All projects evaluated.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="HITS test evaluation: coverage + bug-revealing + similarity")
    parser.add_argument(
        'projects', nargs='*',
        help="Project paths (Csv*_?_b dirs, or root dir containing them). "
             "Defaults to config.project_dir if empty.")
    args = parser.parse_args()
    run_tests(target_projects=args.projects if args.projects else None)