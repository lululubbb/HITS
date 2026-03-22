#!/usr/bin/env python3
"""Compute bug_revealing tests for Defects4J-like projects.

Definition: A generated test is "bug-revealing" if it FAILS on the buggy (b) version
and PASSES on the fixed (f) version.

Usage (examples):
  python3 bug_revealing.py --buggy /path/to/Csv_1_b --fixed /path/to/Csv_1_f --tests /path/to/tests_dir --out summary.csv

Behavior summary:
- Auto-detect tests if --tests omitted: looks for newest tests* dir under buggy project.
- For each test .java: determine full class name from package+basename.
- Optionally copy tests into both projects' src/test/java (use --copy). If not copied, script will compile and run tests from a temporary location.
- Execution uses Maven to run a single test class per run:
    mvn -Dtest=full.test.ClassName test
  This ensures project classpath and surefire behavior.
- A test is considered PASS if Maven returns 0 and surefire reports no failures; FAIL otherwise.
- Output: CSV (default) with per-test b_result/f_result and boolean bug_revealing, and an aggregate summary printed.

Note: This script favors correctness and simplicity using Maven runs per test. It is slower but robust across projects.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
import urllib.parse

here_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(here_dir, '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from test_runner import TestRunner
from config import JUNIT_JAR, MOCKITO_JAR, LOG4J_JAR


def find_newest_tests_dir(project_root):
    parent = project_root
    candidates = []
    try:
        for name in os.listdir(parent):
            if name.startswith('tests') and os.path.isdir(os.path.join(parent, name)):
                candidates.append(os.path.join(parent, name))
    except Exception:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def discover_test_files(tests_dir):
    tests = []
    for root, _, files in os.walk(tests_dir):
        for f in files:
            if f.endswith('Test.java'):
                tests.append(os.path.join(root, f))
    return sorted(tests)


def get_full_class_name(java_file):
    pkg = ''
    try:
        with open(java_file, 'r', errors='ignore') as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('package '):
                    pkg = line.replace('package', '').replace(';', '').strip()
                    break
    except Exception:
        pass
    base = os.path.splitext(os.path.basename(java_file))[0]
    if pkg:
        return f"{pkg}.{base}"
    return base


def java_run_test(project_dir, full_class_name, class_path, timeout=120):
    cmd = [
        'java',
        '-cp', class_path,
        'org.junit.platform.console.ConsoleLauncher',
        '--disable-banner',
        '--disable-ansi-colors',
        '--details=summary',
        '--select-class', full_class_name
    ]
    try:
        proc = subprocess.run(cmd, cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, text=True)
    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'returncode': None, 'stdout': '', 'stderr': ''}
    rc = proc.returncode
    if rc == 0:
        status = 'pass'
    else:
        status = 'fail'
    return {'status': status, 'returncode': rc, 'stdout': proc.stdout, 'stderr': proc.stderr}


def java_run_test_method(project_dir, full_class_name, method_name, class_path, timeout=120):
    selector = f"{full_class_name}#{method_name}"
    cmd = [
        'java',
        '-cp', class_path,
        'org.junit.platform.console.ConsoleLauncher',
        '--disable-banner',
        '--disable-ansi-colors',
        '--details=summary',
        '--select-method', selector
    ]
    try:
        proc = subprocess.run(cmd, cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, text=True)
    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'returncode': None, 'stdout': '', 'stderr': ''}
    rc = proc.returncode
    if rc == 0:
        status = 'pass'
    else:
        status = 'fail'
    return {'status': status, 'returncode': rc, 'stdout': proc.stdout, 'stderr': proc.stderr}


def discover_test_methods(java_file):
    methods = []
    try:
        with open(java_file, 'r', errors='ignore') as fh:
            lines = fh.readlines()
    except Exception:
        return methods

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if line.startswith('@Test') or line.startswith('@org.junit.Test') or line.startswith('@org.junit.jupiter.api.Test'):
            j = i + 1
            while j < n:
                decl = lines[j].strip()
                if decl.startswith('@') or decl == '':
                    j += 1
                    continue
                m = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', decl)
                if m:
                    name = m.group(1)
                    methods.append(name)
                    break
                else:
                    j += 1
            i = j
        else:
            i += 1
    return methods


def copy_test_to_project(java_file, project_root, tests_subpath='src/test/java'):
    pkg = ''
    try:
        with open(java_file, 'r', errors='ignore') as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('package '):
                    pkg = line.replace('package', '').replace(';', '').strip()
                    break
    except Exception:
        pass
    rel_dir = pkg.replace('.', os.sep) if pkg else ''
    dest_dir = os.path.join(project_root, tests_subpath, rel_dir)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(java_file))
    shutil.copy2(java_file, dest)
    return dest


# ── 推断 target_class（modified class 简单类名）──────────────────────────
# NOTE: Defined at module level so it can be called before any local scoping issues.
def resolve_target_class(project_root, tests_top=None):
    """返回 target_class 简单类名，失败返回空字符串"""
    meta = os.path.join(project_root, 'modified_classes.src')
    if os.path.exists(meta):
        try:
            with open(meta) as _f:
                _line = _f.readline().strip()
            if _line:
                return _line.split('.')[-1]
        except Exception:
            pass
    prop = os.path.join(project_root, 'defects4j.build.properties')
    if os.path.exists(prop):
        try:
            with open(prop) as _f:
                for _l in _f:
                    if 'd4j.classes.modified' in _l and '=' in _l:
                        _val = _l.split('=', 1)[1].strip()
                        _first = _val.split(',')[0].strip()
                        if _first:
                            return _first.split('.')[-1]
        except Exception:
            pass
    tc_dir = None
    if tests_top:
        _cand = os.path.join(tests_top, 'test_cases')
        tc_dir = _cand if os.path.isdir(_cand) else (tests_top if os.path.isdir(tests_top) else None)
    if tc_dir:
        try:
            for _fname in os.listdir(tc_dir):
                if _fname.endswith('Test.java'):
                    _m = re.match(r'^(.+?)_\d+_\d+Test\.java$', _fname)
                    if _m:
                        return _m.group(1)
                    return _fname.split('_')[0]
        except Exception:
            pass
    return ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--buggy', required=True, help='Path to buggy (b) project, e.g. /path/to/Csv_1_b')
    parser.add_argument('--fixed', required=True, help='Path to fixed (f) project, e.g. /path/to/Csv_1_f')
    parser.add_argument('--tests', required=False, help='Path to generated tests directory (folder containing Test.java files). If omitted tries to find newest tests* under buggy project.')
    parser.add_argument('--copy', action='store_true', help='Copy tests into both projects under src/test/java before running')
    parser.add_argument('--out', default=None, help='CSV output path (optional; auto-derived from tests dir if omitted)')
    parser.add_argument('--timeout', type=int, default=120, help='Timeout seconds per test run')
    parser.add_argument('--fail-if-no-tests', action='store_true', help='Exit non-zero if no tests found')
    parser.add_argument('--force-clean', action='store_true', help='Force clean existing target directories or copied tests (optional)')
    args = parser.parse_args()

    buggy = os.path.abspath(args.buggy)
    fixed = os.path.abspath(args.fixed)

    # ── project prefix from buggy dir name (strip trailing _b / _f) ──────────
    proj_basename = os.path.basename(buggy)
    if proj_basename.lower().endswith('_b') or proj_basename.lower().endswith('_f'):
        proj_prefix = proj_basename[:-2]
    else:
        proj_prefix = proj_basename

    # ── resolve tests_dir ─────────────────────────────────────────────────────
    tests_dir = args.tests
    if not tests_dir:
        tests_dir = find_newest_tests_dir(buggy)
        if not tests_dir:
            print('No tests dir found under buggy project and --tests not specified.')
            if args.fail_if_no_tests:
                sys.exit(2)
            tests_dir = None
        else:
            print(f'Using tests dir: {tests_dir}')
    else:
        raw = tests_dir
        if os.path.exists(raw):
            tests_dir = os.path.abspath(raw)
        else:
            un = urllib.parse.unquote(raw)
            if os.path.exists(un):
                tests_dir = os.path.abspath(un)
            else:
                tests_dir = os.path.abspath(raw)
                print(f'Warning: provided --tests path not found as given or unquoted: {raw}')

    # if tests dir contains a test_cases subdirectory, prefer that
    if tests_dir and os.path.isdir(os.path.join(tests_dir, 'test_cases')):
        tests_dir = os.path.join(tests_dir, 'test_cases')

    # determine top-level tests directory (the tests* directory)
    top_tests_dir = None
    if tests_dir:
        if os.path.basename(tests_dir) == 'test_cases':
            top_tests_dir = os.path.dirname(tests_dir)
        elif tests_dir and os.path.basename(tests_dir).startswith('tests'):
            top_tests_dir = tests_dir
        else:
            top_tests_dir = os.path.dirname(tests_dir)

    # ── resolve target class (now that top_tests_dir is set) ─────────────────
    _target_class = resolve_target_class(buggy, top_tests_dir)
    _tgt_slug = _target_class if _target_class else 'unknown'

    # ── resolve output CSV path ───────────────────────────────────────────────
    # Priority: explicit --out > auto-derived next to tests* dir
    if args.out:
        out_path = os.path.abspath(args.out)
        # ensure the filename is prefixed correctly
        out_dir  = os.path.dirname(out_path)
        out_base = os.path.basename(out_path)
        expected_prefix = f'{proj_prefix}_{_tgt_slug}_'
        if not out_base.startswith(expected_prefix):
            out_base = f'{proj_prefix}_{_tgt_slug}_{out_base}'
        out_path = os.path.join(out_dir, out_base)
    else:
        # auto-derive: place in top_tests_dir (the tests* folder)
        base_dir = top_tests_dir if top_tests_dir else (os.path.dirname(buggy) if buggy else os.getcwd())
        out_path = os.path.join(base_dir, f'{proj_prefix}_{_tgt_slug}_bugrevealing.csv')

    # make sure the output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # ── discover test files ───────────────────────────────────────────────────
    if tests_dir and os.path.isdir(tests_dir):
        test_files = discover_test_files(tests_dir)
    else:
        test_files = []

    if not test_files:
        print('No Test.java files found. Exiting.')
        if args.fail_if_no_tests:
            sys.exit(2)
        with open(out_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['project_name', 'target_class', 'test_class', 'test_method',
                             'buggy_status', 'fixed_status', 'bug_revealing',
                             'buggy_rc', 'fixed_rc', 'notes'])
        print(f'Wrote empty summary to {out_path}')
        return

    # ── prepare detail log file ───────────────────────────────────────────────
    log_path = os.path.splitext(os.path.abspath(out_path))[0] + '.details.txt'
    try:
        logfh = open(log_path, 'w', encoding='utf-8')
        logfh.write(f'bug_revealing log started: {datetime.now().isoformat()}\n')
        logfh.write(f'buggy={buggy}\nfixed={fixed}\ntests_dir={tests_dir}\n\n')
    except Exception as e:
        print(f'Warning: cannot open detail log {log_path}: {e}')
        logfh = None

    def write_log_entry(fh, project_label, full_class, method_name, res):
        if not fh:
            return
        fh.write('---\n')
        fh.write(f'[{datetime.now().isoformat()}] {project_label} {full_class}')
        if method_name:
            fh.write(f'#{method_name}')
        fh.write(f' status={res.get("status")} returncode={res.get("returncode")}\n')
        out = res.get('stdout') or ''
        err = res.get('stderr') or ''
        if out:
            fh.write('STDOUT:\n')
            fh.write(out)
            if not out.endswith('\n'):
                fh.write('\n')
        if err:
            fh.write('STDERR:\n')
            fh.write(err)
            if not err.endswith('\n'):
                fh.write('\n')
        fh.write('\n')

    def is_discovery_error(res):
        if not res:
            return False
        try:
            text = (res.get('stderr') or '') + '\n' + (res.get('stdout') or '')
        except Exception:
            return False
        if 'failed to discover tests' in text.lower():
            return True
        return False

    def write_short_log(fh, project_label, full_class, method_name, res):
        if not fh:
            return
        fh.write('---\n')
        fh.write(f'[{datetime.now().isoformat()}] {project_label} {full_class}')
        if method_name:
            fh.write(f'#{method_name}')
        fh.write(' discovery_failed\n')

    def echo_and_log(msg):
        try:
            print(msg)
        except Exception:
            pass
        if logfh:
            try:
                logfh.write(msg)
                if not msg.endswith('\n'):
                    logfh.write('\n')
                logfh.flush()
            except Exception:
                pass

    if args.copy:
        echo_and_log('Note: --copy requested but ignored. Using tests from tests*/test_cases and compiling into tests_ChatGPT.')

    print('Note: TestRunner initialization skipped; using precompiled classes in tests_ChatGPT if available.')
    if logfh:
        try:
            logfh.write('Note: TestRunner initialization skipped; using precompiled classes in tests_ChatGPT if available.\n')
        except Exception:
            pass

    # ── build classpath ───────────────────────────────────────────────────────
    def build_classpath(project_root):
        m2 = os.path.expanduser('~/.m2/repository')
        def jar(*path):
            return os.path.join(m2, *path)

        cp = [
            os.path.join(project_root, 'target', 'classes'),
            jar('junit', 'junit', '4.13.2', 'junit-4.13.2.jar'),
            jar('org', 'hamcrest', 'hamcrest-core', '1.3', 'hamcrest-core-1.3.jar'),
            jar('commons-io', 'commons-io', '2.11.0', 'commons-io-2.11.0.jar'),
            jar('org', 'junit', 'jupiter', 'junit-jupiter-api', '5.9.2', 'junit-jupiter-api-5.9.2.jar'),
            jar('org', 'junit', 'jupiter', 'junit-jupiter-engine', '5.9.2', 'junit-jupiter-engine-5.9.2.jar'),
            jar('org', 'junit', 'jupiter', 'junit-jupiter-params', '5.9.2', 'junit-jupiter-params-5.9.2.jar'),
            jar('org', 'junit', 'platform', 'junit-platform-commons', '1.9.2', 'junit-platform-commons-1.9.2.jar'),
            jar('org', 'junit', 'platform', 'junit-platform-engine', '1.9.2', 'junit-platform-engine-1.9.2.jar'),
            jar('org', 'junit', 'vintage', 'junit-vintage-engine', '5.9.2', 'junit-vintage-engine-5.9.2.jar'),
            jar('org', 'mockito', 'mockito-core', '3.12.4', 'mockito-core-3.12.4.jar'),
            jar('org', 'mockito', 'mockito-junit-jupiter', '3.12.4', 'mockito-junit-jupiter-3.12.4.jar'),
            jar('net', 'bytebuddy', 'byte-buddy', '1.14.6', 'byte-buddy-1.14.6.jar'),
            jar('net', 'bytebuddy', 'byte-buddy-agent', '1.14.6', 'byte-buddy-agent-1.14.6.jar'),
            jar('org', 'objenesis', 'objenesis', '3.3', 'objenesis-3.3.jar'),
            jar('org', 'junit', 'platform', 'junit-platform-console-standalone', '1.9.2',
                'junit-platform-console-standalone-1.9.2.jar'),
        ]
        # include compiled tests placed under the top-level tests dir (tests_ChatGPT)
        try:
            if top_tests_dir:
                alt = os.path.join(top_tests_dir, 'tests_ChatGPT')
                if os.path.isdir(alt):
                    cp.insert(1, alt)
        except Exception:
            pass

        cp = [p for p in cp if os.path.exists(p)]
        return os.pathsep.join(cp)

    buggy_cp = build_classpath(buggy)
    fixed_cp = build_classpath(fixed)

    # ── main test loop ────────────────────────────────────────────────────────
    out_rows = []
    total_methods = 0
    bug_revealing_count = 0

    for jf in test_files:
        full = get_full_class_name(jf)
        methods = discover_test_methods(jf)
        if not methods:
            # fallback: run the whole class
            echo_and_log(f'Running test class {full} on buggy...')
            res_b = java_run_test(buggy, full, buggy_cp, timeout=args.timeout)
            echo_and_log(f'  -> {res_b["status"]}')
            echo_and_log(f'Running test class {full} on fixed...')
            res_f = java_run_test(fixed, full, fixed_cp, timeout=args.timeout)
            echo_and_log(f'  -> {res_f["status"]}')

            bstat = res_b.get('status')
            fstat = res_f.get('status')
            b_rc  = res_b.get('returncode')
            f_rc  = res_f.get('returncode')
            notes = ''
            if bstat == 'timeout' or fstat == 'timeout':
                notes = 'timeout'
            is_bug_revealing = (bstat == 'fail') and (fstat == 'pass')
            if is_bug_revealing:
                bug_revealing_count += 1
            total_methods += 1
            out_rows.append([proj_prefix, _target_class, full, '', bstat, fstat,
                              'true' if is_bug_revealing else 'false',
                              str(b_rc), str(f_rc), notes])
            if bstat != 'pass':
                if is_discovery_error(res_b):
                    notes = 'discovery_failed' if not notes else notes + ';discovery_failed'
                    write_short_log(logfh, 'buggy', full, '', res_b)
                else:
                    write_log_entry(logfh, 'buggy', full, '', res_b)
            if fstat != 'pass':
                if is_discovery_error(res_f):
                    notes = 'discovery_failed' if not notes else notes + ';discovery_failed'
                    write_short_log(logfh, 'fixed', full, '', res_f)
                else:
                    write_log_entry(logfh, 'fixed', full, '', res_f)
            out_rows[-1][9] = notes
        else:
            for m in methods:
                echo_and_log(f'Running {full}#{m} on buggy...')
                res_b = java_run_test_method(buggy, full, m, buggy_cp, timeout=args.timeout)
                echo_and_log(f'  -> {res_b["status"]}')
                echo_and_log(f'Running {full}#{m} on fixed...')
                res_f = java_run_test_method(fixed, full, m, fixed_cp, timeout=args.timeout)
                echo_and_log(f'  -> {res_f["status"]}')

                bstat = res_b.get('status')
                fstat = res_f.get('status')
                b_rc  = res_b.get('returncode')
                f_rc  = res_f.get('returncode')
                notes = ''
                if bstat == 'timeout' or fstat == 'timeout':
                    notes = 'timeout'
                is_bug_revealing = (bstat == 'fail') and (fstat == 'pass')
                if is_bug_revealing:
                    bug_revealing_count += 1
                total_methods += 1
                out_rows.append([proj_prefix, _target_class, full, m, bstat, fstat,
                                  'true' if is_bug_revealing else 'false',
                                  str(b_rc), str(f_rc), notes])
                if bstat != 'pass':
                    if is_discovery_error(res_b):
                        notes = 'discovery_failed' if not notes else notes + ';discovery_failed'
                        write_short_log(logfh, 'buggy', full, m, res_b)
                    else:
                        write_log_entry(logfh, 'buggy', full, m, res_b)
                if fstat != 'pass':
                    if is_discovery_error(res_f):
                        notes = 'discovery_failed' if not notes else notes + ';discovery_failed'
                        write_short_log(logfh, 'fixed', full, m, res_f)
                    else:
                        write_log_entry(logfh, 'fixed', full, m, res_f)
                out_rows[-1][9] = notes

    # ── write per-method CSV ──────────────────────────────────────────────────
    with open(out_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['project_name', 'target_class', 'test_class', 'test_method',
                         'buggy_status', 'fixed_status', 'bug_revealing',
                         'buggy_rc', 'fixed_rc', 'notes'])
        for r in out_rows:
            writer.writerow(r)

    # ── class-level summary CSV ───────────────────────────────────────────────
    try:
        class_level_out = os.path.splitext(out_path)[0] + '_class_level.csv'
        class_stats = {}
        for _row in out_rows:
            if len(_row) < 7:
                continue
            _key = (_row[0], _row[1], _row[2])
            _br  = str(_row[6]).strip().lower() == 'true'
            if _key not in class_stats:
                class_stats[_key] = {'total': 0, 'revealing': 0}
            class_stats[_key]['total'] += 1
            if _br:
                class_stats[_key]['revealing'] += 1
        with open(class_level_out, 'w', newline='', encoding='utf-8') as _clf:
            _cl_writer = csv.writer(_clf)
            _cl_writer.writerow(['project_name', 'target_class', 'test_class',
                                  'total_methods', 'bug_revealing_methods',
                                  'bug_revealing_rate', 'has_bug_revealing', 'br_score'])
            for (_proj_n, _tgt, _ts), _s in class_stats.items():
                _tot   = _s['total']
                _rev   = _s['revealing']
                _rate  = round(_rev / _tot, 6) if _tot else 0.0
                _has   = 'true' if _rev > 0 else 'false'
                _cl_writer.writerow([_proj_n, _tgt, _ts, _tot, _rev, _rate, _has, _rate])
        echo_and_log(f'Class-level summary: {os.path.abspath(class_level_out)}')
        if logfh:
            try:
                logfh.write(f'Class-level CSV: {os.path.abspath(class_level_out)}\n')
            except Exception:
                pass
    except Exception as _cl_err:
        print(f'Warning: failed to write class-level CSV: {_cl_err}')

    # ── shared per-project counts CSV ─────────────────────────────────────────
    counts_path = None
    try:
        shared_dir = os.path.dirname(buggy)
        counts_path = os.path.join(shared_dir, 'bugrevealing_counts.csv')
        write_header = not os.path.exists(counts_path)
        with open(counts_path, 'a', newline='') as cf:
            cwriter = csv.writer(cf)
            if write_header:
                cwriter.writerow(['project', 'testcount', 'revealingcount'])
            cwriter.writerow([proj_prefix, total_methods, bug_revealing_count])
    except Exception:
        pass

    # ── final summary ─────────────────────────────────────────────────────────
    echo_and_log('\n===== SUMMARY =====')
    echo_and_log(f'Total tests evaluated: {total_methods}')
    echo_and_log(f'Bug revealing tests: {bug_revealing_count}')
    echo_and_log(f'Summary CSV: {os.path.abspath(out_path)}')

    if logfh:
        try:
            logfh.write('\n===== SUMMARY =====\n')
            logfh.write(f'Total tests evaluated: {total_methods}\n')
            logfh.write(f'Bug revealing tests: {bug_revealing_count}\n')
            logfh.write(f'Summary CSV: {os.path.abspath(out_path)}\n')
            if counts_path:
                logfh.write(f'Per-project counts CSV: {os.path.abspath(counts_path)}\n')
            logfh.write(f'\nlog finished: {datetime.now().isoformat()}\n')
            logfh.close()
            print(f'Detailed log: {os.path.abspath(log_path)}')
        except Exception:
            pass


if __name__ == '__main__':
    main()