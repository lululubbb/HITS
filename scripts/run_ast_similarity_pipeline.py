#!/usr/bin/env python3
"""Runner: for each project under a root, run CodeToAST and measure_similarity.

Usage:
  python3 run_ast_similarity_pipeline.py /path/to/defect4j_projects

Behavior:
- For each project dir under the root, find the newest tests* directory (or test_cases),
  choose its test_cases subdir if present.
- Run src/scripts/code_to_ast.py on that tests dir to produce AST CSVs under tests*/AST.
- Run src/scripts/measure_similarity.py on the same tests dir to produce Similarity CSVs
  under tests*/Similarity.
- Read the project's bigSimssum produced by measure_similarity and append a summary line
  into a common per-project file at root/<proj_short>_bigSimssum.csv (create header if missing).

This script assumes python3 is available and that the two scripts exist at
src/scripts/code_to_ast.py and src/scripts/measure_similarity.py and are executable.
"""
import os
import sys
import subprocess
import time
import csv
import argparse
import shlex
import glob
import re


def find_tests_dir(project_path):
    # look for tests* directories and pick newest by mtime
    candidates = []
    for entry in os.listdir(project_path):
        p = os.path.join(project_path, entry)
        if os.path.isdir(p) and entry.startswith('tests'):
            candidates.append(p)
    # also accept direct 'tests' or 'test_cases'
    if not candidates:
        if os.path.isdir(os.path.join(project_path, 'tests')):
            candidates = [os.path.join(project_path, 'tests')]
        elif os.path.isdir(os.path.join(project_path, 'test_cases')):
            candidates = [os.path.join(project_path, 'test_cases')]
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    top_tests = candidates[0]
    # prefer nested test_cases
    if os.path.isdir(os.path.join(top_tests, 'test_cases')):
        return os.path.join(top_tests, 'test_cases'), top_tests
    # if the top_tests is itself a test_cases dir
    if os.path.basename(top_tests) == 'test_cases':
        return top_tests, os.path.dirname(top_tests)
    return top_tests, top_tests


def run_script(script_path, arg):
    cmd = [sys.executable, script_path, arg]
    try:
        print('Running:', ' '.join(shlex.quote(x) for x in cmd))
        res = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
        return res.returncode, res.stdout, res.stderr
    except Exception as e:
        return 1, '', str(e)


def append_common_bigsum(root_dir, proj_short, sim_dir, tests_dir):
    # sim_dir expected tests*/Similarity
    # Look for both old and new format filenames
    bigsum_local_patterns = [
        # Csv_1_CSVParser_bigSimssum.csv  (* 匹配任意 target_class 名)
        os.path.join(sim_dir, f'{proj_short}_*_bigSimssum.csv'),
    ]
    bigsims_patterns = [
        # Csv_1_CSVParser_bigSims.csv
        os.path.join(sim_dir, f'{proj_short}_*_bigSims.csv'),
    ] 
    common_path = os.path.join(root_dir, f'bigSimssum.csv')
    write_header = not os.path.exists(common_path)

    # prefer reading local bigsum if present, but compute from bigSims if not
    proj_field = proj_short
    n_tests = ''
    sumsq = ''
    meansq = ''
    
    # Find actual bigsum file
    bigsum_local = None
    for pattern in bigsum_local_patterns:
        if '*' in pattern:
            import glob
            matches = sorted(glob.glob(pattern))
            # 排除自身就是 common_path 的情况
            matches = [m for m in matches if os.path.abspath(m) != os.path.abspath(common_path)]
            if matches:
                bigsum_local = matches[0]
                break
        elif os.path.exists(pattern):
            bigsum_local = pattern
            break
    
    # Find actual bigsims file
    bigsims_csv = None
    for pattern in bigsims_patterns:
        if '*' in pattern:
            import glob
            matches = glob.glob(pattern)
            if matches:
                bigsims_csv = matches[0]
                break
        elif os.path.exists(pattern):
            bigsims_csv = pattern
            break

    if bigsum_local and os.path.exists(bigsum_local):
        try:
            with open(bigsum_local, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                if len(rows) >= 2:
                    data = rows[1]
                    proj_field = data[0] if len(data) > 0 else proj_short
                    n_tests = data[1] if len(data) > 1 else ''
                    sumsq = data[2] if len(data) > 2 else ''
                    meansq = data[3] if len(data) > 3 else ''
        except Exception:
            pass
        # remove the local bigsum file as user prefers a single shared file
        try:
            os.remove(bigsum_local)
        except Exception:
            pass
    elif bigsims_csv and os.path.exists(bigsims_csv):
        # compute from bigSims CSV: combined_similarity is 5th or second to last column (may have redundancy_score as last)
        try:
            sims = []
            with open(bigsims_csv, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if not row:
                        continue
                    # combined_similarity expected at column 5 (index 4) in new format
                    # or last column in old format
                    try:
                        # Try new format: index 5 (0-indexed: project, target_class, test_case_1, test_case_2, combined_subtree_size, combined_similarity)
                        if len(row) >= 6:
                            val = float(row[5])
                        else:
                            # Fallback to last column
                            val = float(row[-1])
                        sims.append(val)
                    except Exception:
                        continue
            n = len(sims)
            if n > 0:
                sumsq_v = sum([v * v for v in sims])
                meansq_v = sumsq_v / n
                proj_field = proj_short
                n_tests = str(n)
                sumsq = f'{sumsq_v:.6f}'
                meansq = f'{meansq_v:.6f}'
        except Exception:
            pass
    else:
        return False, 'no_bigsum_or_bigsims'

    try:
        with open(common_path, 'a', newline='', encoding='utf-8') as cf:
            writer = csv.writer(cf)
            if write_header:
                writer.writerow(['timestamp', 'project', 'n_tests', 'sum_of_squares', 'mean_of_squares', 'tests_dir'])
            writer.writerow([int(time.time()), proj_field, n_tests, sumsq, meansq, tests_dir])
        return True, common_path
    except Exception as e:
        return False, f'write_error:{e}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', help='Root projects dir (e.g., /home/chenlu/ChatUniTest/defect4j_projects)')
    parser.add_argument('--code_to_ast', default=os.path.join(os.path.dirname(__file__), 'code_to_ast.py'), help='Path to code_to_ast.py')
    parser.add_argument('--measure_similarity', default=os.path.join(os.path.dirname(__file__),  'measure_similarity.py'), help='Path to measure_similarity.py')
    parser.add_argument('--projects', nargs='*', help='Optional list of project dir names to limit processing')
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print('Root not found or not a directory:', root)
        sys.exit(1)

    def extract_project_number(project_path):
        basename = os.path.basename(project_path)
        num_part = basename.replace('Csv_', '').replace('_b', '').split('_')[0]
        try:
            return int(num_part)
        except Exception:
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
                # If the provided path is a defects4j root containing many Csv*_*_b projects, expand them
                children = sorted(glob.glob(os.path.join(ap, 'Csv*_*_b')))
                if children:
                    for c in children:
                        seen.append(os.path.abspath(c))
                    continue
                base = os.path.basename(ap)
                if base.startswith('Csv') and base.endswith('_b') and os.path.isdir(ap):
                    seen.append(ap)
                    continue
                # try to find Csv*_*_b under this path (one level deep)
                children2 = sorted(glob.glob(os.path.join(ap, '*', 'Csv*_*_b')))
                if children2:
                    for c in children2:
                        seen.append(os.path.abspath(c))
                    continue
                print(f"Warning: provided path did not resolve to projects: {p}")
            # deduplicate preserving order
            projects = []
            for s in seen:
                if s not in projects:
                    projects.append(s)
            projects = sorted(projects, key=extract_project_number)
            return projects

        # discover under root
        root_dir = os.path.abspath(root)
        if not os.path.isdir(root_dir):
            print('Root not found:', root_dir)
            return []
        candidate_projects = glob.glob(os.path.join(root_dir, 'Csv*_*_b'))
        projects = [os.path.abspath(p) for p in sorted(candidate_projects, key=extract_project_number)]
        return projects

    projects = find_projects(args.projects if args.projects else None)
    if not projects:
        print('No projects found to process under', root)
        sys.exit(0)

    for project_path in projects:
        project_path = os.path.abspath(project_path)
        project = os.path.basename(project_path)
        print('\n=== Project:', project, '===')
        found = find_tests_dir(project_path)
        if not found:
            print('No tests dir for', project)
            continue
        test_cases_dir, top_tests_dir = found
        print('Using tests dir:', top_tests_dir, 'test_cases:', test_cases_dir)
        # run code_to_ast on the tests dir (pass either test_cases dir or top_tests_dir; code_to_ast accepts both)
        ret, out, err = run_script(args.code_to_ast, top_tests_dir)
        print('code_to_ast exit', ret)
        if out:
            print('stdout:', out[:1000])
        if err:
            print('stderr:', err[:1000])
        # run measure_similarity on top_tests_dir
        ret2, out2, err2 = run_script(args.measure_similarity, top_tests_dir)
        print('measure_similarity exit', ret2)
        if out2:
            print('stdout:', out2[:1000])
        if err2:
            print('stderr:', err2[:1000])
        # determine sim_dir and proj_short
        proj_prefix = os.path.basename(project_path)
        proj_short = proj_prefix[:-2] if proj_prefix.endswith('_b') or proj_prefix.endswith('_f') else proj_prefix
        sim_dir = os.path.join(top_tests_dir, 'Similarity')
        ok, info = append_common_bigsum(root, proj_short, sim_dir, top_tests_dir)
        if ok:
            print('Appended bigSimssum to', info)
        else:
            print('Failed to append bigSimssum for', project, 'reason:', info)

if __name__ == '__main__':
    main()
