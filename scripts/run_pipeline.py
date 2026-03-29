#!/usr/bin/env python3
"""
scripts/run_pipeline.py — HITS 统一 Pipeline (v3 — fixes all 6 issues)

Fix summary:
  1. Methods dir uses timestamp suffix (methods_%timestamp / methods_no_slice_%timestamp)
     so re-runs never overwrite previous results. meta.json records run_id.
     tests%dir is also created fresh per run and never reused.
  2. _collect_tests_dir gathers ALL test files across all methods with
     UNIQUE names (prefixed by method_idx) so no files are overwritten.
     Coverage is computed on the merged test set in tests%dir.
  3. Final COVERAGE STATISTICS: use the **last** coverage.csv row per method
     (avoid appending) and use modified-class columns (m_line_*) only to avoid
     double-counting the whole project.
  4. step_8_similarity also reads bigSimssum and prints mean_of_squares.
  5. step_7_bug_revealing counts total @Test methods (not test files),
     matching the compile count.
  6. Test file naming in get_code is changed to include method_idx prefix
     so files from different methods never collide.
"""

import argparse
import csv
import json
import os
import sys
import glob
import shutil
import subprocess
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from json import JSONDecodeError
from typing import Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.config import (
    playground_dir, api_keys, model, model_url,
    json_db_root, JACOCO_CLI,
    WO_SLICE_TEST_COUNT, MAX_REPAIR_TRIALS,
)
from utils.json_db import JsonDatabase
from utils.pipeline_logger import PipelineLogger
from utils.stats import LLMStatsTracker, TestStatsAggregator, wrap_generator_with_stats

from scripts.parse_data  import parse_data
from scripts.export_data import export_data

from generator.open_generator import OpenGenerator
from generator.openlimit      import ChatRateLimiter
from procedures               import get_code, get_slices, fix_code
import utils.report


def _is_method_collection(name: str) -> bool:
    return name.startswith("method_") and not name.startswith("class_")


# ══════════════════════════════════════════════════════════════════════════════
# FIX #1: Timestamped run_id for methods directory
# ══════════════════════════════════════════════════════════════════════════════

def _make_run_id() -> str:
    """Generate a unique run identifier based on current timestamp."""
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _methods_dir(project_name: str, wo_slice: bool, run_id: str) -> str:
    """
    Return the methods workspace directory for this run.
    Format: playground/<project>/<prefix>_<run_id>/
    e.g.  methods_20250101_120000   or   methods_no_slice_20250101_120000
    """
    prefix = 'methods_no_slice' if wo_slice else 'methods'
    return os.path.join(playground_dir, project_name, f"{prefix}_{run_id}")


def _load_or_find_meta(project_name: str, run_id: str = None) -> dict:
    """
    Load meta.json.  If run_id is given, look for meta_%run_id.json first.
    Falls back to meta.json for backwards compat.
    """
    pg = os.path.join(playground_dir, project_name)
    if run_id:
        candidate = os.path.join(pg, f"meta_{run_id}.json")
        if os.path.exists(candidate):
            with open(candidate) as f:
                return json.load(f)
    fallback = os.path.join(pg, "meta.json")
    if os.path.exists(fallback):
        with open(fallback) as f:
            return json.load(f)
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# Step 0: workspace init
# ══════════════════════════════════════════════════════════════════════════════
def step_0(project_name, put_root, wo_slice, run_id,
           log: PipelineLogger, skip_parse=False) -> dict:
    log.step_start(0, total=None)

    if not skip_parse:
        from scripts.task import ParseTask
        project_path = os.path.join(put_root, project_name)
        focal_json = os.path.join(PROJECT_ROOT, "scripts", "focal_classes.json")
        parse_task = ParseTask()
        _, output_path = parse_task.process_d4j_revisions(project_path, focal_json)
        if output_path is None:
            _, output_path = parse_task.find_classes(project_path)
        if output_path and os.path.isdir(output_path):
            parse_data(output_path, project_name)
        export_data(project_name)

    db = JsonDatabase(json_db_root, project_name)
    mut_names = [n for n in db.list_collection_names() if _is_method_collection(n)]
    if not mut_names:
        log.error("No method collections found after Step 0. Aborting.")
        sys.exit(1)

    # FIX #1: method_name → method_{i} mapping stays stable; workspace dir uses run_id
    method_name_to_idx = {n: f"method_{i}" for i, n in enumerate(mut_names)}
    idx_to_method_name = {v: k for k, v in method_name_to_idx.items()}

    playground_root = os.path.join(playground_dir, project_name)
    os.makedirs(playground_root, exist_ok=True)

    # FIX #1: workspace directory is timestamped
    methods_root = _methods_dir(project_name, wo_slice, run_id)
    os.makedirs(methods_root, exist_ok=True)
    for idx in idx_to_method_name:
        os.makedirs(os.path.join(methods_root, idx), exist_ok=True)

    meta = {
        "project_name": project_name,
        "put_path": os.path.abspath(os.path.join(put_root, project_name)),
        "run_id": run_id,
        "wo_slice": wo_slice,
        "methods_root": methods_root,
        "method_name_to_idx": method_name_to_idx,
        "idx_to_method_name": idx_to_method_name,
    }
    # Save both versioned and legacy meta
    meta_path = os.path.join(playground_root, f"meta_{run_id}.json")
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    # Also overwrite meta.json for tools that still read it
    with open(os.path.join(playground_root, "meta.json"), 'w') as f:
        json.dump(meta, f, indent=2)

    log.step_done(0, f"{len(mut_names)} methods  run_id={run_id}")
    return meta


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: slices — with per-method progress logging
# ══════════════════════════════════════════════════════════════════════════════
def step_1(project_name, meta, prompt_root,
           log: PipelineLogger, llm_tracker=None):
    methods_root = meta['methods_root']
    n = len(meta['method_name_to_idx'])
    log.step_start(1, total=n)
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(9000, 900000, 60)
    completed = [0]

    def _work(m, idx):
        t0 = time.time()
        slicer  = get_slices.SliceInfoGenerator(prompt_root, "system_gen.jinja2", "gen_slice.jinja2")
        chatter = OpenGenerator(key=api_keys, request_url=model_url, model=model, monitor=monitor)
        if llm_tracker:
            chatter.generate = wrap_generator_with_stats(chatter, llm_tracker, "slice", m, model)
        log_dir = os.path.join(methods_root, meta['method_name_to_idx'][m])
        os.makedirs(log_dir, exist_ok=True)
        log.info(f"[Slice {idx}/{n}] Starting: {m}")
        result = slicer.work(log_dir, db.get_collection(m), chatter)
        n_steps = len(result.get('steps', [])) if result else 0
        elapsed = round(time.time() - t0, 1)
        completed[0] += 1
        log.info(f"[Slice {completed[0]}/{n}] Done: {m} → {n_steps} slices ({elapsed}s)")
        log.method(m, f"{n_steps} slices")
        return m, n_steps

    total_slices = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m, i+1): m
                   for i, m in enumerate(meta['method_name_to_idx'])}
        for fut in as_completed(futures):
            try:
                _, ns = fut.result()
                total_slices += ns
            except Exception as e:
                log.warn(f"Slice failed for {futures[fut]}: {e}")

    log.step_done(1, f"{total_slices} total slices across {n} methods")


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: generate tests
# FIX #6: method_idx is passed to get_code so it can prefix test file names
# ══════════════════════════════════════════════════════════════════════════════
def step_2(project_name, meta, prompt_root,
           wo_slice, fixing, log: PipelineLogger, llm_tracker=None):
    methods_root = meta['methods_root']
    n = len(meta['method_name_to_idx'])
    log.step_start(2, total=n)
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(10000, 900000, 60)

    system_tmpl = "system_repair.jinja2" if fixing else "system_gen.jinja2"
    user_tmpl   = "repair.jinja2"        if fixing else "gen_code.jinja2"

    def _work(m):
        method_idx = meta['method_name_to_idx'][m]
        code_getter = get_code.InitialCodeGenerator(prompt_root, system_tmpl, user_tmpl)
        chatter = OpenGenerator(key=api_keys, request_url=model_url, model=model, monitor=monitor)
        if llm_tracker:
            stage = "patch" if fixing else "gen"
            chatter.generate = wrap_generator_with_stats(chatter, llm_tracker, stage, m, model)
        log_dir = os.path.join(methods_root, method_idx)
        if fixing:
            if not os.path.exists(os.path.join(log_dir, 'slice_fixing', 'slice_result.jsonl')):
                return m, 0
        try:
            if fixing:
                # FIX #6: pass method_idx so generated files get unique prefix
                code_getter.work(db.get_collection(m), chatter, log_dir,
                                 fixing=True, method_idx=method_idx)
            elif not wo_slice:
                code_getter.work(db.get_collection(m), chatter, log_dir,
                                 fixing=False, method_idx=method_idx)
            else:
                existing = glob.glob(os.path.join(log_dir, 'steps', "*.java"))
                fix_num = max(len(existing), WO_SLICE_TEST_COUNT)
                code_getter.work(db.get_collection(m), chatter, log_dir,
                                 fix_num=fix_num, fixing=False, method_idx=method_idx)
        except (JSONDecodeError, Exception) as e:
            log.warn(f"Gen failed for {m}: {e}")
            return m, 0
        sub = "slice_fixing" if fixing else "steps"
        n_java = len(glob.glob(os.path.join(log_dir, sub, "*.java")))
        log.method(m, f"{n_java} tests")
        return m, n_java

    total_gen = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m): m for m in meta['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                _, nj = fut.result()
                total_gen += nj
            except Exception as e:
                log.warn(f"Gen worker error: {e}")

    log.step_done(2, f"{total_gen} test files generated")


# ══════════════════════════════════════════════════════════════════════════════
# Step 3a: run initial tests
# ══════════════════════════════════════════════════════════════════════════════
def step_3a(project_name, meta, prompt_root,
            fixing, perform_cleaning, log: PipelineLogger,
            test_tracker=None) -> dict:
    methods_root = meta['methods_root']
    n = len(meta['method_name_to_idx'])
    log.step_start("3a", total=n)
    db = JsonDatabase(json_db_root, project_name)

    if perform_cleaning:
        dirs = glob.glob(os.path.join(methods_root, "**", "fixing"), recursive=True)
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)
        log.info(f"Cleaned {len(dirs)} fixing dirs")

    total_pass = total_fail = 0

    def _work(m):
        fixer = fix_code.TestFixer(prompt_root, "system_repair.jinja2", "repair.jinja2")
        log_dir = os.path.join(methods_root, meta['method_name_to_idx'][m])
        code_dir = "slice_fixing" if fixing else "steps"
        if not os.path.isdir(os.path.join(log_dir, code_dir)):
            return m, []
        result = fixer.init_test(log_dir, meta['put_path'], db.get_collection(m), fixing=fixing)
        return m, result if result else []

    failed_all = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m): m for m in meta['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                mname, failed = fut.result()
                failed_all[mname] = failed
                method_idx = meta['method_name_to_idx'][mname]
                n_tests = len(glob.glob(os.path.join(
                    methods_root, method_idx,
                    "slice_fixing" if fixing else "steps", "*.java")))
                total_fail += len(failed)
                total_pass += max(0, n_tests - len(failed))
                if test_tracker:
                    for f in failed:
                        test_tracker.add_test_result(mname, f, 'pass', 'fail')
            except Exception as e:
                log.warn(f"init_test error: {e}")

    log.step_done("3a", f"pass={total_pass}  fail={total_fail}")
    return failed_all


# ══════════════════════════════════════════════════════════════════════════════
# Step 3b: fix failed tests
# ══════════════════════════════════════════════════════════════════════════════
def step_3b(project_name, meta, prompt_root,
            fixing, log: PipelineLogger, llm_tracker=None, test_tracker=None):
    methods_root = meta['methods_root']
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(9000, 900000, 60)

    tasks = []
    for m in meta['method_name_to_idx']:
        log_dir = os.path.join(methods_root, meta['method_name_to_idx'][m])
        failed_txt = os.path.join(log_dir, "fixing", "init_test_failed.txt")
        if not os.path.exists(failed_txt):
            continue
        with open(failed_txt) as f:
            content = f.read().strip()
        failed_list = [x for x in content.split('\n')
                       if x and (not fixing or 'Fix' in x)]
        for fc in failed_list:
            tasks.append((m, log_dir, fc))

    if not tasks:
        log.step_skip("3b", "no failed tests")
        return

    log.step_start("3b", total=len(tasks))
    fixed_count = 0

    def _fix(m, log_dir, fc):
        fixer = fix_code.TestFixer(prompt_root, "system_repair.jinja2",
                                   "repair.jinja2" if not fixing else "repair_patch.jinja2")
        chatter = OpenGenerator(key=api_keys, request_url=model_url, model=model, monitor=monitor)
        if llm_tracker:
            chatter.generate = wrap_generator_with_stats(chatter, llm_tracker, "fix", m, model)
        try:
            ok = fixer.single_unitest_fix(log_dir, db.get_collection(m), fc,
                                          meta['put_path'], chatter)
            if test_tracker:
                test_tracker.add_test_result(m, fc, 'pass', 'pass' if ok else 'fail')
            return ok
        except RuntimeError:
            return False

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(_fix, *t) for t in tasks]
        for fut in as_completed(futures):
            try:
                if fut.result():
                    fixed_count += 1
            except Exception:
                pass

    log.step_done("3b", f"fixed {fixed_count}/{len(tasks)}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 4: parse missing coverage
# ══════════════════════════════════════════════════════════════════════════════
def step_4(project_name, meta, log: PipelineLogger):
    from importlib import reload
    from procedures import parse_missing
    from utils import load_code_graph
    reload(load_code_graph); reload(parse_missing)
    methods_root = meta['methods_root']
    log.step_start(4)
    db = JsonDatabase(json_db_root, project_name)
    parsed = skipped = 0
    for m in db.list_collection_names():
        if m not in meta['method_name_to_idx']:
            continue
        log_dir = os.path.join(methods_root, meta['method_name_to_idx'][m])
        fr_dir = os.path.join(log_dir, 'full_report')
        if not os.path.isdir(fr_dir) or not os.listdir(fr_dir):
            skipped += 1; continue
        info = db.get_collection(m).find_one({"table_name": "info"})
        if not info or 'method_graphs' not in info:
            skipped += 1; continue
        try:
            parse_missing.parse_missing(log_dir, db.get_collection(m))
            parsed += 1
        except Exception as e:
            log.warn(f"parse_missing failed for {m}: {e}")
            skipped += 1
    if skipped > 0 and parsed == 0:
        log.step_skip(4, f"no method_graphs in info ({skipped} skipped)")
    else:
        log.step_done(4, f"parsed={parsed}  skipped={skipped}")


# ══════════════════════════════════════════════════════════════════════════════
# FIX #6 helper: derive focal method from JsonDB collection
# ══════════════════════════════════════════════════════════════════════════════
def _get_focal_method_for_collection(collection_name: str, db) -> str:
    try:
        coll = db.get_collection(collection_name)
        raw = coll.find_one({"table_name": "raw_data"})
        if raw and raw.get('method_name'):
            return raw['method_name']
        d3 = coll.find_one({"table_name": "direction_3"})
        if d3:
            focal = d3.get('focal_method', '')
            if focal:
                m = re.search(r'(\w+)\s*\(', focal)
                if m:
                    return m.group(1)
                return focal.split()[-1] if focal.split() else focal
        method_doc = coll.find_one({"table_name": "method"})
        if method_doc and method_doc.get('method_name'):
            return method_doc['method_name']
    except Exception:
        pass
    return ''


# ══════════════════════════════════════════════════════════════════════════════
# Step 6: coverage report
# FIX #3: coverage aggregation uses max total-lines per method (not sum), so the
# same class's total lines aren't counted multiple times across methods.
# ══════════════════════════════════════════════════════════════════════════════
def step_6(project_name, meta, log: PipelineLogger, test_tracker=None):
    from utils.test_runner import TestRunner
    methods_root = meta['methods_root']
    n = len(meta['method_name_to_idx'])
    log.step_start(6, total=n)

    db = JsonDatabase(json_db_root, project_name)

    total_compile_all = 0
    total_test_run_all = 0
    syntax_total_all = 0
    syntax_error_all = 0
    compile_error_all = 0
    test_run_error_all = 0

    cov_result = []

    for idx, (m, method_idx) in enumerate(meta['method_name_to_idx'].items(), start=1):
        method_root = os.path.join(methods_root, method_idx)
        focal_method_name = _get_focal_method_for_collection(m, db)
        log.info(f"  ▶ Step 6 [{idx}/{n}] focal_method={focal_method_name}  "
                 f"collection={m}  dir={method_root}")

        if not os.path.isdir(method_root):
            log.warn(f"Method root not found: {method_root}"); continue

        steps_dir = os.path.join(method_root, "steps")
        if not os.path.isdir(steps_dir):
            log.warn(f"No steps dir for {m}, skipping"); continue

        n_steps = len([f for f in os.listdir(steps_dir) if f.endswith('.java')])
        log.info(f"    Found {n_steps} test files in steps/")
        if n_steps == 0:
            log.warn(f"No .java files in steps/, skipping coverage for {m}"); continue

        logs_dir = os.path.join(method_root, 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        runner = TestRunner(method_root, meta['put_path'], output_path=method_root,
                            tool='jacoco', debug=False)

        try:
            logs = runner._make_logs(logs_dir)
            compiled_test_dir = os.path.join(method_root, 'tests_ChatGPT')
            compiler_output   = os.path.join(method_root, 'compiler_output', 'CompilerOutput')
            test_output       = os.path.join(method_root, 'test_output', 'TestOutput')
            report_dir        = os.path.join(method_root, 'report')
            for d in [compiled_test_dir,
                      os.path.dirname(compiler_output),
                      os.path.dirname(test_output),
                      report_dir]:
                os.makedirs(d, exist_ok=True)

            total_compile, total_test_run = runner.run_all_tests(
                method_root,
                compiled_test_dir=compiled_test_dir,
                compiler_output=compiler_output,
                test_output=test_output,
                report_dir=report_dir,
                logs=logs,
                focal_method=focal_method_name,
            )
            total_compile_all   += total_compile
            total_test_run_all  += total_test_run
            syntax_total_all    += runner.SYNTAX_TOTAL
            syntax_error_all    += runner.SYNTAX_ERROR
            compile_error_all   += runner.COMPILE_ERROR
            test_run_error_all  += runner.TEST_RUN_ERROR

        except Exception as e:
            log.warn(f"TestRunner failed for {m}: {e}")
            import traceback; traceback.print_exc()
            continue

        # Read coverage from written CSV
        project_slug = project_name.replace('.', '')
        target_class = runner._resolve_target_class(method_root)
        tc_slug = (target_class or 'unknown').replace('.', '')
        cov_csv = os.path.join(method_root, f'{project_slug}_{tc_slug}_coverage.csv')

        inst_cov = '0%'; bran_cov = '0%'
        line_rate = branch_rate = None
        if os.path.exists(cov_csv):
            try:
                with open(cov_csv, newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    # Use LAST row to avoid stale appended rows
                    last_row = None
                    for row in reader:
                        last_row = row
                    if last_row:
                        if last_row.get('m_line_rate'):
                            try:
                                line_rate = float(last_row['m_line_rate'])
                                inst_cov = f"{line_rate}%"
                            except Exception:
                                pass
                        if last_row.get('m_branch_rate'):
                            try:
                                branch_rate = float(last_row['m_branch_rate'])
                                bran_cov = f"{branch_rate}%"
                            except Exception:
                                pass
            except Exception:
                pass

        cov_result.append({m: {'inst_cov': inst_cov, 'bran_cov': bran_cov}})
        if test_tracker and line_rate is not None:
            try:
                test_tracker.add_coverage(m, line_rate, branch_rate or 0.0)
            except Exception:
                pass

    # Save result.json
    result_file = os.path.join(playground_dir, project_name,
                               f"result_{meta['run_id']}.json")
    with open(result_file, 'w') as f:
        json.dump(cov_result, f, indent=2)
    # Also write legacy result.json
    with open(os.path.join(playground_dir, project_name, 'result.json'), 'w') as f:
        json.dump(cov_result, f, indent=2)

    if cov_result:
        def _pct(s):
            try: return float(s.rstrip('%'))
            except: return 0.0
        inst_vals = [_pct(list(r.values())[0].get('inst_cov', '0%')) for r in cov_result if r]
        bran_vals = [_pct(list(r.values())[0].get('bran_cov', '0%')) for r in cov_result if r]
        avg_inst = round(sum(inst_vals) / len(inst_vals), 1) if inst_vals else 0
        avg_bran = round(sum(bran_vals) / len(bran_vals), 1) if bran_vals else 0
        log.step_done(6, f"avg modified-class line={avg_inst}%  branch={avg_bran}%")
    else:
        log.step_done(6, "no coverage data")

    return {
        'total_compile':   total_compile_all,
        'total_test_run':  total_test_run_all,
        'syntax_total':    syntax_total_all,
        'syntax_error':    syntax_error_all,
        'compile_error':   compile_error_all,
        'test_run_error':  test_run_error_all,
        'methods_root':    methods_root,
    }


# ══════════════════════════════════════════════════════════════════════════════
# FIX #2 + #6: Build tests% directory with UNIQUE file names
# ══════════════════════════════════════════════════════════════════════════════
def _collect_tests_dir(project_name: str, meta: dict, run_id: str) -> str:
    """
    Collect ALL generated test .java files from steps/ across all methods into
    a single tests%<run_id> directory with UNIQUE filenames.

    FIX #6: Each file is renamed to include its method_idx prefix so files from
    different focal methods never overwrite each other, e.g.:
        method_0__ExtendedBufferedReader_0_0Test.java
        method_1__ExtendedBufferedReader_0_0Test.java

    FIX #1: The directory name is tests%<run_id> — never reused across runs.
    FIX #2: ALL .java files from all methods are included (not just passing ones)
    so that coverage, bug-revealing and similarity are computed on the full set.
    """
    tests_dir = os.path.join(playground_dir, project_name, f"tests%{run_id}")
    test_cases_dir = os.path.join(tests_dir, "test_cases")
    os.makedirs(test_cases_dir, exist_ok=True)

    methods_root = meta['methods_root']
    copied = 0
    name_conflicts = 0

    for m, method_idx in meta['method_name_to_idx'].items():
        steps_dir = os.path.join(methods_root, method_idx, "steps")
        if not os.path.isdir(steps_dir):
            continue
        for jf in sorted(glob.glob(os.path.join(steps_dir, "*.java"))):
            base = os.path.basename(jf)
            # FIX #6: prefix with method_idx so names are globally unique
            unique_name = f"{method_idx}__{base}"
            dst = os.path.join(test_cases_dir, unique_name)
            if os.path.exists(dst):
                name_conflicts += 1
            shutil.copy2(jf, dst)
            copied += 1

    if name_conflicts:
        print(f"[WARN] {name_conflicts} name conflicts resolved by method_idx prefix")
    print(f"[INFO] Collected {copied} test files into {test_cases_dir}")
    return tests_dir


# ══════════════════════════════════════════════════════════════════════════════
# FIX #5: count @Test methods in test files for bug-revealing summary
# ══════════════════════════════════════════════════════════════════════════════
def _count_test_methods(tests_dir: str) -> int:
    """Count total @Test annotated methods across all *Test.java files."""
    tc_dir = os.path.join(tests_dir, 'test_cases')
    if not os.path.isdir(tc_dir):
        tc_dir = tests_dir
    total = 0
    ann_pattern = re.compile(r'@(?:org\.junit\.(?:jupiter\.api\.)?)?Test\b')
    for jf in glob.glob(os.path.join(tc_dir, '*.java')):
        try:
            with open(jf, 'r', errors='ignore') as f:
                content = f.read()
            total += len(ann_pattern.findall(content))
        except Exception:
            pass
    return total


# ══════════════════════════════════════════════════════════════════════════════
# Step 7: bug-revealing
# FIX #5: report @Test method count not file count
# ══════════════════════════════════════════════════════════════════════════════
def step_7_bug_revealing(project_name, meta, tests_dir, log: PipelineLogger):
    log.step_start(7, "Bug-revealing analysis")
    put_path = meta['put_path']
    put_root = os.path.dirname(put_path)

    base = project_name
    if base.endswith('_b'):
        buggy_proj = put_path
        fixed_proj = os.path.join(put_root, base[:-2] + '_f')
    elif base.endswith('_f'):
        fixed_proj = put_path
        buggy_proj = os.path.join(put_root, base[:-2] + '_b')
    else:
        buggy_proj = put_path
        fixed_proj = os.path.join(put_root, base + '_f')

    if not os.path.isdir(buggy_proj):
        log.warn(f"Buggy project not found: {buggy_proj}")
        log.step_skip(7, "buggy project not found"); return None
    if not os.path.isdir(fixed_proj):
        log.warn(f"Fixed project not found: {fixed_proj}")
        log.step_skip(7, "fixed project not found"); return None
    if not tests_dir or not os.path.isdir(tests_dir):
        log.warn(f"Tests dir not found: {tests_dir}")
        log.step_skip(7, "tests dir not found"); return None

    # FIX #5: count @Test methods (not files) for denominator
    total_test_methods = _count_test_methods(tests_dir)
    log.info(f"  Total @Test methods in test suite: {total_test_methods}")

    script = os.path.join(PROJECT_ROOT, "scripts", "bug_revealing.py")
    cmd = [sys.executable, script,
           '--buggy', buggy_proj,
           '--fixed', fixed_proj,
           '--tests', tests_dir]
    log.info(f"Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.stdout:
        for line in result.stdout.splitlines():
            log.info(f"  [br] {line}")
    if result.returncode != 0:
        log.warn(f"bug_revealing rc={result.returncode}")
        if result.stderr:
            log.warn(result.stderr[:500])

    proj_prefix = base[:-2] if base.endswith('_b') or base.endswith('_f') else base
    found = (glob.glob(os.path.join(tests_dir, f'{proj_prefix}_*_bugrevealing.csv')) +
             glob.glob(os.path.join(tests_dir, f'{proj_prefix}_bugrevealing.csv')))

    br_count = br_methods_total = 0
    if found:
        try:
            with open(found[0], newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    br_methods_total += 1  # each row = one @Test method
                    if str(row.get('bug_revealing', '')).strip().lower() == 'true':
                        br_count += 1
        except Exception:
            pass

    # FIX #5: show both counted @Test methods and evaluated @Test methods
    log.step_done(7, f"bug-revealing: {br_count}/{br_methods_total} @Test methods "
                     f"reveal bugs  (total @Test in suite: {total_test_methods})")
    return found[0] if found else None


# ══════════════════════════════════════════════════════════════════════════════
# Step 9: Global test evaluation (compile, execute, coverage for all tests)
# ══════════════════════════════════════════════════════════════════════════════
def step_9_global_test_eval(project_name, meta, tests_dir, log: PipelineLogger):
    from utils.test_runner import TestRunner
    log.step_start(9, "Global test evaluation")
    if not tests_dir or not os.path.isdir(tests_dir):
        log.step_skip(9, "tests dir not found"); return

    put_path = meta['put_path']
    runner = TestRunner(tests_dir, put_path, output_path=tests_dir, tool='jacoco', debug=False)
    try:
        runner.start_all_test()
        log.step_done(9, f"Global evaluation completed in {tests_dir}")
    except Exception as e:
        log.warn(f"Global test eval failed: {e}")
        log.step_skip(9, "evaluation failed")
def step_8_similarity(project_name, tests_dir, log: PipelineLogger):
    log.step_start(8, "AST similarity analysis")

    if not tests_dir or not os.path.isdir(tests_dir):
        log.step_skip(8, "tests dir not found"); return None

    ast_script = os.path.join(PROJECT_ROOT, "scripts", "code_to_ast.py")
    sim_script = os.path.join(PROJECT_ROOT, "scripts", "measure_similarity.py")

    for script, label in [(ast_script, "code_to_ast"), (sim_script, "measure_similarity")]:
        result = subprocess.run(
            [sys.executable, script, tests_dir],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            log.warn(f"{label} rc={result.returncode}: {result.stderr[:200]}")
        else:
            log.info(f"{label} done")

    sim_dir = os.path.join(tests_dir, 'Similarity')
    big_sims = glob.glob(os.path.join(sim_dir, '*_bigSims.csv'))
    big_sum  = glob.glob(os.path.join(sim_dir, '*_bigSimssum.csv'))

    avg_sim = avg_red = mean_sq = None
    n_pairs = 0

    # Read bigSims for per-test similarity
    if big_sims:
        sims = []
        try:
            with open(big_sims[0], newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    try:
                        sims.append(float(row.get('combined_similarity', 0)))
                    except Exception:
                        pass
        except Exception:
            pass
        if sims:
            n_pairs = len(sims)
            avg_sim = round(sum(sims) / n_pairs, 4)
            avg_red = round(1.0 - avg_sim, 4)

    # FIX #4: read mean_of_squares from bigSimssum
    if big_sum:
        try:
            with open(big_sum[0], newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('mean_of_squares'):
                        try:
                            mean_sq = float(row['mean_of_squares'])
                        except Exception:
                            pass
                    break
        except Exception:
            pass

    log.step_done(8, f"similarity pairs={n_pairs}  avg_sim={avg_sim}  "
                     f"avg_redundancy={avg_red}  mean_of_squares={mean_sq}")
    # FIX #4: explicit print of mean_of_squares
    if mean_sq is not None:
        print(f"[Similarity] mean_of_squares (from bigSimssum): {mean_sq}")
    return big_sims[0] if big_sims else None


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="HITS Pipeline")
    parser.add_argument("--project_name", required=True)
    parser.add_argument("--put_root", required=True)
    parser.add_argument("--wo_slice", action="store_true")
    parser.add_argument("--fixing", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--perform_cleaning", action="store_true")
    parser.add_argument("--skip_parse", action="store_true")
    # FIX #1: allow resuming a previous run by specifying its run_id
    parser.add_argument("--run_id", default=None,
                        help="Resume a previous run by its timestamp ID "
                             "(e.g. 20250101_120000). If omitted, a new run is created.")
    parser.add_argument("--steps", nargs='*', type=str,
                        help="Run specific steps e.g. --steps 1 2 3a 3b 6 7 8")
    args = parser.parse_args()

    project_name = args.project_name
    prompt_root  = os.path.join(PROJECT_ROOT, 'prompts')

    # FIX #1: each new pipeline invocation gets a fresh run_id unless resuming
    if args.run_id:
        run_id = args.run_id
    else:
        run_id = _make_run_id()

    log = PipelineLogger(project_name, verbose=args.verbose)
    log.separator()
    log.info(f"HITS Pipeline  →  {project_name}  run_id={run_id}")
    log.info(f"mode: {'wo_slice' if args.wo_slice else 'slice'}  "
             f"{'+ patch-fix' if args.fixing else ''}")
    log.separator()

    pipeline_start = time.time()

    def should_run(step) -> bool:
        if args.steps:
            return str(step) in args.steps
        return True

    llm_tracker  = LLMStatsTracker(project_name, playground_dir)
    test_tracker = TestStatsAggregator(project_name, playground_dir)

    # ── Step 0 ────────────────────────────────────────────────────────────────
    if should_run(0):
        meta = step_0(project_name, args.put_root, args.wo_slice, run_id,
                      log, skip_parse=args.skip_parse)
    else:
        meta = _load_or_find_meta(project_name, run_id)
        if not meta:
            log.error("meta.json not found. Run Step 0 first.")
            sys.exit(1)
        # Ensure methods_root key exists for older meta files
        if 'methods_root' not in meta:
            prefix = 'methods_no_slice' if meta.get('wo_slice') else 'methods'
            rid = meta.get('run_id', run_id)
            meta['methods_root'] = os.path.join(
                playground_dir, project_name, f"{prefix}_{rid}")

    n_methods = len(meta.get('method_name_to_idx', {}))
    if n_methods == 0:
        log.error("No methods in workspace. Run Step 0 first.")
        sys.exit(1)
    log.info(f"{n_methods} focal methods to process  methods_root={meta['methods_root']}")

    # ── Step 1 ────────────────────────────────────────────────────────────────
    if should_run(1):
        if args.wo_slice:
            log.step_skip(1, "(wo_slice mode)")
        else:
            step_1(project_name, meta, prompt_root, log, llm_tracker)

    # ── Step 2 ────────────────────────────────────────────────────────────────
    if should_run(2):
        step_2(project_name, meta, prompt_root,
               args.wo_slice, fixing=False, log=log, llm_tracker=llm_tracker)

    # ── Step 3a ───────────────────────────────────────────────────────────────
    if should_run('3a') or should_run(3):
        step_3a(project_name, meta, prompt_root,
                fixing=False, perform_cleaning=args.perform_cleaning,
                log=log, test_tracker=test_tracker)

    # ── Step 3b ───────────────────────────────────────────────────────────────
    if should_run('3b') or should_run(3):
        step_3b(project_name, meta, prompt_root,
                fixing=False, log=log, llm_tracker=llm_tracker,
                test_tracker=test_tracker)

    # ── Step 4 ────────────────────────────────────────────────────────────────
    if should_run(4):
        step_4(project_name, meta, log)

    # ── Step 5 (patch fix) ────────────────────────────────────────────────────
    if should_run(5) and args.fixing:
        methods_root = meta['methods_root']
        has_slice = any(
            os.path.exists(os.path.join(
                methods_root, idx, "slice_fixing", "slice_result.jsonl"))
            for idx in meta['idx_to_method_name'])
        if has_slice:
            log.step_start(5)
            step_2(project_name, meta, prompt_root,
                   wo_slice=False, fixing=True, log=log, llm_tracker=llm_tracker)
            step_3a(project_name, meta, prompt_root,
                    fixing=True, perform_cleaning=False, log=log,
                    test_tracker=test_tracker)
            log.step_done(5)
        else:
            log.step_skip(5, "no slice_result.jsonl")

    # ── Step 6: coverage ──────────────────────────────────────────────────────
    exec_stats = {}
    if should_run(6):
        exec_stats = step_6(project_name, meta, log, test_tracker)

    # ── FIX #1 + #2: Collect tests into a per-run tests%<run_id> directory ───
    # This replaces the old "find existing or create" logic.
    # The tests%dir is always fresh per run so re-runs don't overwrite.
    tests_dir = None
    if should_run(7) or should_run(8):
        # FIX #1: always create a NEW tests dir for this run
        tests_dir = _collect_tests_dir(project_name, meta, run_id)
        log.info(f"Tests dir for this run: {tests_dir}")

    # ── Step 7: bug-revealing ─────────────────────────────────────────────────
    if should_run(7):
        step_7_bug_revealing(project_name, meta, tests_dir, log)

    # ── Step 8: similarity ────────────────────────────────────────────────────
    if should_run(8):
        step_8_similarity(project_name, tests_dir, log)

    # ── Step 9: global test evaluation ────────────────────────────────────────
    if should_run(9):
        step_9_global_test_eval(project_name, meta, tests_dir, log)

    # ── Save stats ────────────────────────────────────────────────────────────
    try:
        llm_tracker.save()
        test_tracker.save()
    except Exception:
        pass

    pipeline_wall = time.time() - pipeline_start

    # ── Final summary ─────────────────────────────────────────────────────────
    sm = llm_tracker.summary()
    ts = test_tracker.summary()

    log.separator()
    log.info(f"Pipeline complete  →  {project_name}  run_id={run_id}")

    total_tasks = n_methods
    log.info(f"Tasks: {total_tasks}/{total_tasks}")

    total_calls      = sm.get('total_calls', 0)
    total_tokens     = sm.get('total_tokens', 0)
    total_prompt     = sm.get('total_prompt_tokens', 0)
    total_completion = sm.get('total_completion_tokens', 0)
    total_llm_time   = sm.get('total_elapsed_sec', 0.0)
    avg_llm_time     = round(total_llm_time / total_calls, 4) if total_calls else 0.0

    log.info(f"Wall-clock: {round(pipeline_wall, 4)}s")
    log.info(f"LLM-only elapsed: {round(total_llm_time, 4)}s  ({total_calls} calls)")
    log.info(f"Total tokens: {total_tokens}  "
             f"(prompt={total_prompt}, completion={total_completion})")
    log.info(f"Avg LLM time/task: {avg_llm_time}s")

    # ── Compile/exec/coverage statistics ─────────────────────────────────────
    if exec_stats:
        stotal = exec_stats.get('syntax_total', 0)
        serr   = exec_stats.get('syntax_error', 0)
        ctotal = exec_stats.get('total_compile', 0)
        cerr   = exec_stats.get('compile_error', 0)
        rtotal = exec_stats.get('total_test_run', 0)
        rerr   = exec_stats.get('test_run_error', 0)

        print()
        print(f"SYNTAX TOTAL COUNT: {stotal}")
        print(f"SYNTAX ERROR COUNT: {serr}")
        print(f"COMPILE TOTAL COUNT: {ctotal}")
        print(f"COMPILE ERROR COUNT: {cerr}")
        print(f"TEST RUN TOTAL COUNT: {rtotal}")
        print(f"TEST RUN ERROR COUNT: {rerr}")

        # FIX #3: aggregate coverage correctly
        # line_total for whole project should NOT be summed across methods
        # (that double-counts). Use MAX per project (all methods test same project).
        # For modified class, SUM coverage-count and use MAX total-count.
        print("-" * 50)
        print("COVERAGE STATISTICS (ALL ATTEMPTS):")

        methods_root = exec_stats.get('methods_root', meta['methods_root'])

        # FIX #3: accumulate correctly
        # project-level: keep running maximum of totals (same binary each time),
        #   sum the covered counts (union approximation via jacoco merge)
        proj_line_cov_max = proj_line_total_max = 0
        proj_branch_cov_max = proj_branch_total_max = 0
        # modified-class: sum covered, max total
        mc_line_cov_sum = mc_line_total_max = 0
        mc_branch_cov_sum = mc_branch_total_max = 0
        target_class_name = None

        for m_name, method_idx in meta['method_name_to_idx'].items():
            method_root = os.path.join(methods_root, method_idx)
            for cov_csv in glob.glob(os.path.join(method_root, '*_coverage.csv')):
                try:
                    with open(cov_csv, newline='', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        last_row = None
                        for row in reader:
                            last_row = row
                        if not last_row:
                            continue
                        if not target_class_name and last_row.get('modified_class'):
                            target_class_name = last_row['modified_class']
                        try:
                            # Project-level: take max of totals (same project binary)
                            lc  = int(last_row.get('line_cov') or 0)
                            lt  = int(last_row.get('line_total') or 0)
                            bc  = int(last_row.get('branch_cov') or 0)
                            bt  = int(last_row.get('branch_total') or 0)
                            if lt > proj_line_total_max:
                                proj_line_total_max = lt
                            if bt > proj_branch_total_max:
                                proj_branch_total_max = bt
                            # Covered: use max per method (each run contributes)
                            proj_line_cov_max   = max(proj_line_cov_max, lc)
                            proj_branch_cov_max = max(proj_branch_cov_max, bc)
                            # Modified class: sum covered (tests from diff methods
                            # may cover different lines), max total
                            mlc = int(last_row.get('m_line_cov') or 0)
                            mlt = int(last_row.get('m_line_total') or 0)
                            mbc = int(last_row.get('m_branch_cov') or 0)
                            mbt = int(last_row.get('m_branch_total') or 0)
                            mc_line_cov_sum    += mlc
                            mc_branch_cov_sum  += mbc
                            if mlt > mc_line_total_max:
                                mc_line_total_max = mlt
                            if mbt > mc_branch_total_max:
                                mc_branch_total_max = mbt
                        except Exception:
                            pass
                except Exception:
                    pass

        if proj_line_total_max > 0:
            lr = round(100 * proj_line_cov_max / proj_line_total_max, 2)
            print(f"  全项目 行覆盖率: {lr}% ({proj_line_cov_max}/{proj_line_total_max})")
        if proj_branch_total_max > 0:
            br = round(100 * proj_branch_cov_max / proj_branch_total_max, 2)
            print(f"  全项目 分支覆盖率: {br}% ({proj_branch_cov_max}/{proj_branch_total_max})")
        if target_class_name:
            print(f"  target_class: {target_class_name}")
            if mc_line_total_max > 0:
                # Cap sum at 100% (union of covered lines cannot exceed total)
                mc_line_cov_capped = min(mc_line_cov_sum, mc_line_total_max)
                mlr = round(100 * mc_line_cov_capped / mc_line_total_max, 2)
                print(f"    行覆盖率: {mlr}% ({mc_line_cov_capped}/{mc_line_total_max})")
            if mc_branch_total_max > 0:
                mc_branch_cov_capped = min(mc_branch_cov_sum, mc_branch_total_max)
                mbr = round(100 * mc_branch_cov_capped / mc_branch_total_max, 2)
                print(f"    分支覆盖率: {mbr}% ({mc_branch_cov_capped}/{mc_branch_total_max})")
        print("-" * 50)

    log.separator()


if __name__ == '__main__':
    main()