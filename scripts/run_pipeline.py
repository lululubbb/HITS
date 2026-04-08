#!/usr/bin/env python3
"""
scripts/run_pipeline.py — HITS 统一 Pipeline
用法:
  # 正常模式（有分片）
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects --fixing

  # 无分片模式（跳过 Step 1，直接生成测试）
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects --wo_slice

  # 补丁修复模式（Step 5，需要先完成 Steps 0-4）
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects --fixing

  # 跳过已完成的步骤
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects --steps 3 4 5 6
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
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.config import (
    playground_dir, api_keys, model, model_url,
    json_db_root, JACOCO_CLI, JACOCO_AGENT,
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
# run_id helpers
# ══════════════════════════════════════════════════════════════════════════════

def _make_run_id() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _methods_dir(project_name: str, wo_slice: bool, run_id: str) -> str:
    prefix = 'methods_no_slice' if wo_slice else 'methods'
    return os.path.join(playground_dir, project_name, f"{prefix}_{run_id}")


def _load_or_find_meta(project_name: str, run_id: str = None) -> dict:
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
# Step 0
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

    method_name_to_idx = {n: f"method_{i}" for i, n in enumerate(mut_names)}
    idx_to_method_name = {v: k for k, v in method_name_to_idx.items()}

    playground_root = os.path.join(playground_dir, project_name)
    os.makedirs(playground_root, exist_ok=True)

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
    with open(os.path.join(playground_root, f"meta_{run_id}.json"), 'w') as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(playground_root, "meta.json"), 'w') as f:
        json.dump(meta, f, indent=2)

    log.step_done(0, f"{len(mut_names)} methods  run_id={run_id}")
    return meta

def _collect_all_exec_files(meta: dict, compiled_dir: str = None) -> List[str]:
    """
    集中收集所有 jacoco exec 文件，供 step_6 和 step_9 共享使用。
    这样两个步骤使用相同的 exec 集合，JaCoCo 报告的 total 才会一致。
    """
    methods_root = meta['methods_root']
    exec_files: List[str] = []

    # 1. phase A 产生的 per-test exec（在 compiled_dir 中）
    if compiled_dir and os.path.isdir(compiled_dir):
        for ef in glob.glob(os.path.join(compiled_dir, "jacoco_*.exec")):
            if os.path.getsize(ef) > 0:
                exec_files.append(ef)

    # 2. 各 method 的 tests_ChatGPT/ 中的 exec
    for m, method_idx in meta['method_name_to_idx'].items():
        method_ctd = os.path.join(methods_root, method_idx, "tests_ChatGPT")
        if not os.path.isdir(method_ctd):
            continue
        for ef in glob.glob(os.path.join(method_ctd, "jacoco_*.exec")):
            if os.path.getsize(ef) > 0 and ef not in exec_files:
                exec_files.append(ef)

    # 3. 各 method 的 fixing/ 中的 runtemp/jacoco.exec
    for m, method_idx in meta['method_name_to_idx'].items():
        for ef in glob.glob(os.path.join(
                methods_root, method_idx, "fixing",
                "**", "runtemp", "jacoco.exec"), recursive=True):
            if os.path.exists(ef) and os.path.getsize(ef) > 0 and ef not in exec_files:
                exec_files.append(ef)

    return exec_files

# ══════════════════════════════════════════════════════════════════════════════
# Step 1
# ══════════════════════════════════════════════════════════════════════════════
def step_1(project_name, meta, prompt_root, log: PipelineLogger, llm_tracker=None):
    methods_root = meta['methods_root']
    n = len(meta['method_name_to_idx'])
    log.step_start(1, total=n)
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(9000, 900000, 60)

    def _work(m, idx):
        t0 = time.time()
        slicer  = get_slices.SliceInfoGenerator(prompt_root, "system_gen.jinja2", "gen_slice.jinja2")
        chatter = OpenGenerator(key=api_keys, request_url=model_url, model=model, monitor=monitor)
        if llm_tracker:
            chatter.generate = wrap_generator_with_stats(chatter, llm_tracker, "slice", m, model)
        log_dir = os.path.join(methods_root, meta['method_name_to_idx'][m])
        os.makedirs(log_dir, exist_ok=True)
        result = slicer.work(log_dir, db.get_collection(m), chatter)
        n_steps = len(result.get('steps', [])) if result else 0
        log.method(m, f"{n_steps} slices ({round(time.time()-t0,1)}s)")
        return m, n_steps

    total_slices = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m, i+1): m
                   for i, m in enumerate(meta['method_name_to_idx'])}
        for fut in as_completed(futures):
            try:
                _, ns = fut.result(); total_slices += ns
            except Exception as e:
                log.warn(f"Slice failed: {e}")
    log.step_done(1, f"{total_slices} slices across {n} methods")


# ══════════════════════════════════════════════════════════════════════════════
# Step 2
# ══════════════════════════════════════════════════════════════════════════════
def step_2(project_name, meta, prompt_root, wo_slice, fixing,
           log: PipelineLogger, llm_tracker=None):
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
        if fixing and not os.path.exists(
                os.path.join(log_dir, 'slice_fixing', 'slice_result.jsonl')):
            return m, 0
        try:
            if fixing:
                code_getter.work(db.get_collection(m), chatter, log_dir, fixing=True)
            elif not wo_slice:
                code_getter.work(db.get_collection(m), chatter, log_dir, fixing=False)
            else:
                existing = glob.glob(os.path.join(log_dir, 'steps', "*.java"))
                code_getter.work(db.get_collection(m), chatter, log_dir,
                                 fix_num=max(len(existing), WO_SLICE_TEST_COUNT), fixing=False)
        except Exception as e:
            log.warn(f"Gen failed for {m}: {e}"); return m, 0
        sub = "slice_fixing" if fixing else "steps"
        nj = len(glob.glob(os.path.join(log_dir, sub, "*.java")))
        log.method(m, f"{nj} tests")
        return m, nj

    total_gen = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m): m for m in meta['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                _, nj = fut.result(); total_gen += nj
            except Exception as e:
                log.warn(f"Gen worker error: {e}")
    log.step_done(2, f"{total_gen} test files generated")


# ══════════════════════════════════════════════════════════════════════════════
# Step 3a
# ══════════════════════════════════════════════════════════════════════════════
def step_3a(project_name, meta, prompt_root, fixing, perform_cleaning,
            log: PipelineLogger, test_tracker=None) -> dict:
    methods_root = meta['methods_root']
    n = len(meta['method_name_to_idx'])
    log.step_start("3a", total=n)
    db = JsonDatabase(json_db_root, project_name)

    if perform_cleaning:
        dirs = glob.glob(os.path.join(methods_root, "**", "fixing"), recursive=True)
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)

    total_pass = total_fail = 0

    def _work(m):
        fixer = fix_code.TestFixer(prompt_root, "system_repair.jinja2", "repair.jinja2")
        log_dir = os.path.join(methods_root, meta['method_name_to_idx'][m])
        code_dir = "slice_fixing" if fixing else "steps"
        if not os.path.isdir(os.path.join(log_dir, code_dir)):
            return m, []
        result = fixer.init_test(log_dir, meta['put_path'],
                                 db.get_collection(m), fixing=fixing)
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
# Step 3b
# ══════════════════════════════════════════════════════════════════════════════
def step_3b(project_name, meta, prompt_root, fixing,
            log: PipelineLogger, llm_tracker=None, test_tracker=None):
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
        for fc in [x for x in content.split('\n')
                   if x and (not fixing or 'Fix' in x)]:
            tasks.append((m, log_dir, fc))

    if not tasks:
        log.step_skip("3b", "no failed tests"); return

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
                if fut.result(): fixed_count += 1
            except Exception:
                pass
    log.step_done("3b", f"fixed {fixed_count}/{len(tasks)}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 4
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
            log.warn(f"parse_missing failed for {m}: {e}"); skipped += 1
    if skipped > 0 and parsed == 0:
        log.step_skip(4, f"no method_graphs in info ({skipped} skipped)")
    else:
        log.step_done(4, f"parsed={parsed}  skipped={skipped}")


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
                return m.group(1) if m else (focal.split()[-1] if focal.split() else focal)
        method_doc = coll.find_one({"table_name": "method"})
        if method_doc and method_doc.get('method_name'):
            return method_doc['method_name']
    except Exception:
        pass
    return ''


# ══════════════════════════════════════════════════════════════════════════════
# Step 6: per-method coverage
# ══════════════════════════════════════════════════════════════════════════════
def step_6(project_name, meta, log: PipelineLogger, test_tracker=None):
    from utils.test_runner import TestRunner
    methods_root = meta['methods_root']
    n = len(meta['method_name_to_idx'])
    log.step_start(6, total=n)
    db = JsonDatabase(json_db_root, project_name)

    total_compile_all = total_test_run_all = 0
    syntax_total_all  = syntax_error_all   = 0
    compile_error_all = test_run_error_all = 0
    cov_result = []

    for idx, (m, method_idx) in enumerate(meta['method_name_to_idx'].items(), start=1):
        method_root = os.path.join(methods_root, method_idx)
        focal_method_name = _get_focal_method_for_collection(m, db)
        log.info(f"  ▶ Step 6 [{idx}/{n}] focal={focal_method_name}  collection={m}")

        if not os.path.isdir(method_root):
            log.warn(f"Method root not found: {method_root}"); continue

        steps_dir = os.path.join(method_root, "steps")
        if not os.path.isdir(steps_dir):
            log.warn(f"No steps dir for {m}, skipping"); continue

        n_steps = len([f for f in os.listdir(steps_dir) if f.endswith('.java')])
        if n_steps == 0:
            log.warn(f"No .java in steps/, skipping {m}"); continue

        logs_dir = os.path.join(method_root, 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        runner = TestRunner(method_root, meta['put_path'],
                            output_path=method_root, tool='jacoco', debug=False)

        try:
            logs = runner._make_logs(logs_dir)
            compiled_test_dir = os.path.join(method_root, 'tests_ChatGPT')
            compiler_output   = os.path.join(method_root, 'compiler_output', 'CompilerOutput')
            test_output       = os.path.join(method_root, 'test_output', 'TestOutput')
            report_dir        = os.path.join(method_root, 'report')
            for d in [compiled_test_dir, os.path.dirname(compiler_output),
                      os.path.dirname(test_output), report_dir]:
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
            total_compile_all  += total_compile
            total_test_run_all += total_test_run
            syntax_total_all   += runner.SYNTAX_TOTAL
            syntax_error_all   += runner.SYNTAX_ERROR
            compile_error_all  += runner.COMPILE_ERROR
            test_run_error_all += runner.TEST_RUN_ERROR

        except Exception as e:
            log.warn(f"TestRunner failed for {m}: {e}")
            import traceback; traceback.print_exc()
            continue

        project_slug = project_name.replace('.', '')
        target_class = runner._resolve_target_class(method_root)
        tc_slug = (target_class or 'unknown').replace('.', '')
        cov_csv = os.path.join(method_root, f'{project_slug}_{tc_slug}_coverage.csv')

        inst_cov = '0%'; bran_cov = '0%'
        line_rate = branch_rate = None
        if os.path.exists(cov_csv):
            try:
                with open(cov_csv, newline='', encoding='utf-8') as f:
                    last_row = None
                    for row in csv.DictReader(f):
                        last_row = row
                    if last_row:
                        for lr_key, br_key in [('m_line_rate', 'm_branch_rate'),
                                               ('line_rate', 'branch_rate')]:
                            try:
                                if last_row.get(lr_key):
                                    line_rate   = float(last_row[lr_key])
                                    branch_rate = float(last_row.get(br_key, 0) or 0)
                                    inst_cov = f"{line_rate}%"
                                    bran_cov = f"{branch_rate}%"
                                    break
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
    all_exec_files = _collect_all_exec_files(meta)        
    result_file = os.path.join(playground_dir, project_name,
                               f"result_{meta['run_id']}.json")
    with open(result_file, 'w') as f:
        json.dump(cov_result, f, indent=2)
    with open(os.path.join(playground_dir, project_name, 'result.json'), 'w') as f:
        json.dump(cov_result, f, indent=2)

    if cov_result:
        def _pct(s):
            try: return float(s.rstrip('%'))
            except: return 0.0
        inst_vals = [_pct(list(r.values())[0].get('inst_cov', '0%')) for r in cov_result if r]
        bran_vals = [_pct(list(r.values())[0].get('bran_cov', '0%')) for r in cov_result if r]
        avg_inst = round(sum(inst_vals)/len(inst_vals), 1) if inst_vals else 0
        avg_bran = round(sum(bran_vals)/len(bran_vals), 1) if bran_vals else 0
        log.step_done(6, f"avg modified-class line={avg_inst}%  branch={avg_bran}%")
    else:
        log.step_done(6, "no coverage data")

    # 打印 per-method 汇总（step 6 专属统计）
    print(f"\n[Step 6 per-method stats]")
    print(f"  SYNTAX TOTAL:  {syntax_total_all}  ERRORS: {syntax_error_all}")
    print(f"  COMPILE TOTAL: {total_compile_all}  ERRORS: {compile_error_all}")
    print(f"  TEST RUN TOTAL: {total_test_run_all}  ERRORS: {test_run_error_all}")

    return {
        'total_compile':   total_compile_all,
        'total_test_run':  total_test_run_all,
        'syntax_total':    syntax_total_all,
        'syntax_error':    syntax_error_all,
        'compile_error':   compile_error_all,
        'test_run_error':  test_run_error_all,
        'methods_root':    methods_root,
        'all_exec_files':  all_exec_files,
    }


# ══════════════════════════════════════════════════════════════════════════════
# _collect_tests_dir — method_idx__ 前缀唯一添加处
# ══════════════════════════════════════════════════════════════════════════════
def _collect_tests_dir(project_name: str, meta: dict, run_id: str) -> str:
    """
    把各 method 的 steps/*.java 复制到 tests%<run_id>/test_cases/，
    文件名加 method_idx__ 前缀保证全局唯一。
    这是唯一加前缀的地方；get_code.py 不加前缀。
    """
    tests_dir = os.path.join(playground_dir, project_name, f"tests%{run_id}")
    test_cases_dir = os.path.join(tests_dir, "test_cases")
    os.makedirs(test_cases_dir, exist_ok=True)

    methods_root = meta['methods_root']
    copied = 0

    for m, method_idx in meta['method_name_to_idx'].items():
        steps_dir = os.path.join(methods_root, method_idx, "steps")
        if not os.path.isdir(steps_dir):
            continue
        for jf in sorted(glob.glob(os.path.join(steps_dir, "*.java"))):
            base = os.path.basename(jf)
            # 防止双重前缀（兼容旧版本残留）
            unique_name = base if base.startswith(method_idx + "__") \
                          else f"{method_idx}__{base}"
            dst = os.path.join(test_cases_dir, unique_name)
            shutil.copy2(jf, dst)
            # 修改类名以匹配新文件名
            old_class = base.replace('.java', '')
            new_class = unique_name.replace('.java', '')
            if old_class != new_class:
                try:
                    with open(dst, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # 替换 class 声明
                    pattern = r'\bclass\s+' + re.escape(old_class) + r'\b'
                    content = re.sub(pattern, f'class {new_class}', content)
                    with open(dst, 'w', encoding='utf-8') as f:
                        f.write(content)
                except Exception as e:
                    print(f"[WARN] Failed to rename class in {dst}: {e}")
            copied += 1

    print(f"[INFO] Collected {copied} test files into {test_cases_dir}")
    return tests_dir


# ══════════════════════════════════════════════════════════════════════════════
# Step 9: 全局 Test 评估（完全重写）
# ══════════════════════════════════════════════════════════════════════════════
def step_9_global_test_eval(project_name: str, meta: dict,
                             tests_dir: str, log: PipelineLogger,
                             pre_collected_exec_files: List[str] = None):
    """
    对 tests%<run_id>/test_cases/ 中的所有测试进行完整评估。

    Phase A — 调用 TestRunner.run_all_tests() 生成标准 CSV 文件：
      {project}_{class}_status.csv
      {project}_{class}_coverage.csv
      {project}_{class}_coveragedetail.csv
      {project}_{class}_coveragemethod.csv
      {project}_{class}_final_scores.csv
      {project}_{class}_final_scores2.csv

      关键：TestRunner.run_all_tests() 在 tests_dir/steps/ 中找 .java 文件，
      我们把 test_cases/ 内容复制到 steps/ 供其读取，不改动原文件。

    Phase B — 收集所有 exec 文件（Phase A 产生的 + 各 method 的），
      合并成 jacoco_merged_global.exec，生成 global_report/jacoco.xml，
      解析并打印全局覆盖率。
    """
    import xml.etree.ElementTree as ET
    from utils.test_runner import TestRunner, parse_root_pom
    from utils.test_runner_focal_fix import resolve_all_target_classes

    log.step_start(9, "Global test evaluation (compile + run + merged coverage)")

    if not tests_dir or not os.path.isdir(tests_dir):
        log.step_skip(9, "tests dir not found"); return

    test_cases_dir = os.path.join(tests_dir, "test_cases")
    if not os.path.isdir(test_cases_dir):
        log.step_skip(9, "test_cases/ subdir not found"); return

    java_files = sorted(glob.glob(os.path.join(test_cases_dir, "*.java")))
    if not java_files:
        log.step_skip(9, "no .java files in test_cases/"); return

    put_path     = meta['put_path']
    methods_root = meta['methods_root']
    project_slug = project_name.replace('.', '')

    # ── 确定 target_class ─────────────────────────────────────────────────
    target_classes = resolve_all_target_classes(put_path)
    target_class   = target_classes[0] if target_classes else 'unknown'

    # ── Phase A: 准备 steps/ 目录并调用 TestRunner.run_all_tests() ─────────
    steps_dir_for_runner = os.path.join(tests_dir, "steps")
    os.makedirs(steps_dir_for_runner, exist_ok=True)

    # 把 test_cases/ 复制到 steps/（仅复制还不存在的，避免重复运行时重写）
    for jf in java_files:
        dst = os.path.join(steps_dir_for_runner, os.path.basename(jf))
        if not os.path.exists(dst):
            shutil.copy2(jf, dst)

    n_total = len([f for f in os.listdir(steps_dir_for_runner) if f.endswith('.java')])
    log.info(f"  Total test files to evaluate: {n_total}")

    # 各输出目录（放在 tests_dir 下，和 TestRunner 标准路径对齐）
    compiled_dir    = os.path.join(tests_dir, "tests_ChatGPT")
    logs_dir        = os.path.join(tests_dir, "logs")
    report_dir      = os.path.join(tests_dir, "report")
    compiler_output = os.path.join(tests_dir, "compiler_output", "CompilerOutput")
    test_output_dir = os.path.join(tests_dir, "test_output", "TestOutput")
    for d in [compiled_dir, logs_dir, report_dir,
              os.path.dirname(compiler_output),
              os.path.dirname(test_output_dir)]:
        os.makedirs(d, exist_ok=True)

    # TestRunner 的 test_path 设为 tests_dir（其内部会找 tests_dir/steps/）
    runner = TestRunner(tests_dir, put_path, output_path=tests_dir,
                        tool='jacoco', debug=False)
    runner.instrument(compiled_dir, compiled_dir)
    logs = runner._make_logs(logs_dir)

    log.info(f"  Running TestRunner.run_all_tests() ...")
    total_compile = total_test_run = 0
    try:
        total_compile, total_test_run = runner.run_all_tests(
            tests_dir,
            compiled_test_dir=compiled_dir,
            compiler_output=compiler_output,
            test_output=test_output_dir,
            report_dir=report_dir,
            logs=logs,
            focal_method='',                   # 全局模式不限 focal method
            target_class_override=target_class,
        )
    except Exception as e:
        log.warn(f"TestRunner.run_all_tests failed: {e}")
        import traceback; traceback.print_exc()

    compile_errors  = runner.COMPILE_ERROR
    test_run_errors = runner.TEST_RUN_ERROR
    exec_pass       = max(0, total_test_run - test_run_errors)
    exec_fail       = test_run_errors

    log.info(f"  [Phase A] compile={total_compile}  compile_err={compile_errors}  "
             f"exec_pass={exec_pass}  exec_fail={exec_fail}")

    # Phase B：如果外部已经收集好 exec，直接合并；否则自己收集
    if pre_collected_exec_files:
        exec_files = pre_collected_exec_files
        log.info(f"  [Phase B] Using pre-collected {len(exec_files)} exec files from step_6")
    else:
        exec_files = _collect_all_exec_files(meta, compiled_dir)
        # B1: Phase A 产生的 per-test exec（在 compiled_dir 中）
        for ef in glob.glob(os.path.join(compiled_dir, "jacoco_*.exec")):
            if os.path.getsize(ef) > 0 and ef not in exec_files:
                exec_files.append(ef)

    log.info(f"  [Phase B] Total exec files: {len(exec_files)}")

    if not exec_files:
        log.warn("No exec files found — global coverage report skipped")
        _print_global_summary(project_name, total_compile, compile_errors,
                               exec_pass, exec_fail, 0)
        log.step_done(9, f"compile={total_compile}  exec_ok={exec_pass}  "
                         f"exec_fail={exec_fail}  NO COVERAGE DATA")
        return

    # 合并
    global_report_dir = os.path.join(tests_dir, "global_report")
    os.makedirs(global_report_dir, exist_ok=True)
    merged_exec = os.path.join(global_report_dir, "jacoco_merged_global.exec")

    if not _merge_exec_files(exec_files, merged_exec, log):
        log.warn("Exec merge failed")
        _print_global_summary(project_name, total_compile, compile_errors,
                               exec_pass, exec_fail, len(exec_files))
        log.step_done(9, "MERGE FAILED"); return

    # 生成报告
    global_xml = os.path.join(global_report_dir, "jacoco.xml")
    _generate_jacoco_report(put_path, merged_exec, global_report_dir, global_xml, log)

    # 解析 XML
    (lc, lt, bc, bt, mlc, mlt, mbc, mbt) = _parse_coverage_xml(
        global_xml, target_classes, log)

    lr   = round(100.0*lc/lt,   2) if lt   else None
    br   = round(100.0*bc/bt,   2) if bt   else None
    mlr  = round(100.0*mlc/mlt, 2) if mlt  else None
    mbr  = round(100.0*mbc/mbt, 2) if mbt  else None

    # 写入 global_coverage.csv（补充信息，标准 coverage.csv 由 TestRunner 生成）
    target_class_str = ",".join(target_classes) if target_classes else "unknown"
    gcov_csv = os.path.join(tests_dir, f"{project_slug}_global_coverage.csv")
    with open(gcov_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "project", "modified_class",
            "total_compile", "compile_error", "exec_pass", "exec_fail",
            "line_cov", "line_total", "line_rate",
            "branch_cov", "branch_total", "branch_rate",
            "m_line_cov", "m_line_total", "m_line_rate",
            "m_branch_cov", "m_branch_total", "m_branch_rate",
            "n_exec_files_merged",
        ])
        w.writerow([
            project_name, target_class_str,
            total_compile, compile_errors, exec_pass, exec_fail,
            lc or "", lt or "", lr or "",
            bc or "", bt or "", br or "",
            mlc or "", mlt or "", mlr or "",
            mbc or "", mbt or "", mbr or "",
            len(exec_files),
        ])

    _print_global_summary(project_name, total_compile, compile_errors,
                           exec_pass, exec_fail, len(exec_files),
                           lc, lt, lr, bc, bt, br, mlc, mlt, mlr, mbc, mbt, mbr)

    log.step_done(9,
                  f"compile={total_compile}  compile_err={compile_errors}  "
                  f"exec_ok={exec_pass}  exec_fail={exec_fail}  "
                  f"line={lr}%  branch={br}%  "
                  f"m_line={mlr}%  m_branch={mbr}%")


# ══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════════════════

def _merge_exec_files(exec_files: List[str], merged_exec: str,
                      log: PipelineLogger) -> bool:
    valid = [f for f in exec_files
             if os.path.exists(f) and os.path.getsize(f) > 0]
    if not valid:
        return False
    if len(valid) == 1:
        shutil.copy2(valid[0], merged_exec)
        log.info(f"  Single exec → {merged_exec}")
        return True
    if JACOCO_CLI and os.path.exists(JACOCO_CLI):
        cmd = (["java", "-jar", JACOCO_CLI, "merge"]
               + valid + ["--destfile", merged_exec])
        r = subprocess.run(cmd, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True)
        if r.returncode == 0 and os.path.exists(merged_exec) \
                and os.path.getsize(merged_exec) > 0:
            log.info(f"  Merged {len(valid)} execs → {merged_exec} "
                     f"({os.path.getsize(merged_exec)} bytes)")
            return True
        log.warn(f"  jacoco merge rc={r.returncode}: {r.stderr[:200]}")
    # fallback
    shutil.copy2(valid[0], merged_exec)
    log.warn(f"  Fallback: copied first exec → {merged_exec}")
    return os.path.getsize(merged_exec) > 0


def _generate_jacoco_report(put_path: str, merged_exec: str,
                              report_dir: str, xml_out: str,
                              log: PipelineLogger):
    from utils.test_runner import parse_root_pom
    module_poms = parse_root_pom(put_path) or []
    class_dirs  = [os.path.join(os.path.dirname(p), "target", "classes")
                   for p in module_poms
                   if os.path.exists(os.path.join(os.path.dirname(p), "target", "classes"))]
    if not class_dirs:
        fb = os.path.join(put_path, "target", "classes")
        if os.path.exists(fb):
            class_dirs = [fb]
    src_dirs = []
    for p in module_poms:
        for suffix in ["src/main/java", "src/main"]:
            sd = os.path.join(os.path.dirname(p), suffix)
            if os.path.exists(sd):
                src_dirs.append(sd); break

    if JACOCO_CLI and os.path.exists(JACOCO_CLI):
        cmd = ["java", "-jar", JACOCO_CLI, "report", merged_exec]
        for d in class_dirs:
            cmd += ["--classfiles", d]
        cmd += ["--html", report_dir, "--xml", xml_out]
        for sd in src_dirs:
            cmd += ["--sourcefiles", sd]
        r = subprocess.run(cmd, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True)
        if r.returncode == 0:
            log.info(f"  Global report → {report_dir}")
        else:
            log.warn(f"  jacoco report rc={r.returncode}: {r.stderr[:300]}")
    else:
        log.warn("  JACOCO_CLI not found — trying mvn jacoco:report")
        mvn_cmd = ["mvn", "jacoco:report",
                   f"-Djacoco.dataFile={os.path.abspath(merged_exec)}",
                   "-f", os.path.join(put_path, "pom.xml")]
        subprocess.run(mvn_cmd, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, cwd=put_path)
        mvn_xml = os.path.join(put_path, "target", "site", "jacoco", "jacoco.xml")
        if os.path.exists(mvn_xml):
            shutil.copy2(mvn_xml, xml_out)


def _parse_coverage_xml(
        xml_path: str, target_classes: List[str],
        log: PipelineLogger) -> Tuple:
    """返回 (lc, lt, bc, bt, mlc, mlt, mbc, mbt)，失败返回全 None 元组。"""
    import xml.etree.ElementTree as ET
    none8 = (None,) * 8
    if not os.path.exists(xml_path):
        log.warn(f"  jacoco.xml not found: {xml_path}"); return none8
    try:
        with open(xml_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        start = raw.find("<report")
        if start < 0: return none8
        root_elem = ET.fromstring(raw[start:])
    except Exception as e:
        log.warn(f"  Failed to parse {xml_path}: {e}"); return none8

    lc = lt = bc = bt = 0
    mlc = mlt = mbc = mbt = 0

    for c in root_elem.findall("counter"):
        ct  = c.get("type", "")
        cov = int(c.get("covered", 0))
        mis = int(c.get("missed", 0))
        if ct == "LINE":   lc = cov; lt = cov + mis
        elif ct == "BRANCH": bc = cov; bt = cov + mis

    for cls_elem in root_elem.findall(".//class"):
        cname  = cls_elem.get("name", "")
        simple = cname.split("/")[-1].split("$")[0]
        if target_classes and (simple in target_classes or
                any(cname.endswith("/" + tc) for tc in target_classes)):
            for c in cls_elem.findall("counter"):
                ct  = c.get("type", "")
                cov = int(c.get("covered", 0))
                mis = int(c.get("missed", 0))
                if ct == "LINE":     mlc += cov; mlt += cov + mis
                elif ct == "BRANCH": mbc += cov; mbt += cov + mis

    return (lc or None, lt or None, bc or None, bt or None,
            mlc or None, mlt or None, mbc or None, mbt or None)


def _print_global_summary(project_name, total_compile, compile_errors,
                           exec_pass, exec_fail, n_exec_merged,
                           lc=None, lt=None, lr=None,
                           bc=None, bt=None, br=None,
                           mlc=None, mlt=None, mlr=None,
                           mbc=None, mbt=None, mbr=None):
    print(f"\n{'='*60}")
    print(f"GLOBAL TEST EVALUATION SUMMARY: {project_name}")
    print(f"{'='*60}")
    print(f"  Tests compiled:    {total_compile}")
    print(f"  Compile errors:    {compile_errors}")
    print(f"  Exec pass:         {exec_pass}")
    print(f"  Exec fail:         {exec_fail}")
    print(f"  Exec files merged: {n_exec_merged}")
    if lr  is not None: print(f"  [Project]  Line coverage:   {lc}/{lt} = {lr:.2f}%")
    if br  is not None: print(f"  [Project]  Branch coverage: {bc}/{bt} = {br:.2f}%")
    if mlr is not None: print(f"  [ModClass] Line coverage:   {mlc}/{mlt} = {mlr:.2f}%")
    if mbr is not None: print(f"  [ModClass] Branch coverage: {mbc}/{mbt} = {mbr:.2f}%")
    if lr is None and br is None:
        print(f"  ⚠ No coverage data available")
    print(f"{'='*60}\n")


# ══════════════════════════════════════════════════════════════════════════════
# Steps 7 & 8
# ══════════════════════════════════════════════════════════════════════════════
def _count_test_methods(tests_dir: str) -> int:
    tc_dir = os.path.join(tests_dir, 'test_cases')
    if not os.path.isdir(tc_dir): tc_dir = tests_dir
    total = 0
    ann = re.compile(r'@(?:org\.junit\.(?:jupiter\.api\.)?)?Test\b')
    for jf in glob.glob(os.path.join(tc_dir, '*.java')):
        try:
            with open(jf, 'r', errors='ignore') as f:
                total += len(ann.findall(f.read()))
        except Exception:
            pass
    return total


def step_7_bug_revealing(project_name, meta, tests_dir, log: PipelineLogger):
    log.step_start(7, "Bug-revealing analysis")
    put_path = meta['put_path']
    put_root = os.path.dirname(put_path)
    base = project_name
    if base.endswith('_b'):
        buggy_proj, fixed_proj = put_path, os.path.join(put_root, base[:-2]+'_f')
    elif base.endswith('_f'):
        fixed_proj, buggy_proj = put_path, os.path.join(put_root, base[:-2]+'_b')
    else:
        buggy_proj = put_path
        fixed_proj = os.path.join(put_root, base+'_f')

    for label, path in [("buggy", buggy_proj), ("fixed", fixed_proj)]:
        if not os.path.isdir(path):
            log.step_skip(7, f"{label} project not found"); return None
    if not tests_dir or not os.path.isdir(tests_dir):
        log.step_skip(7, "tests dir not found"); return None

    total_test_methods = _count_test_methods(tests_dir)
    log.info(f"  Total @Test methods: {total_test_methods}")

    script = os.path.join(PROJECT_ROOT, "scripts", "bug_revealing.py")
    result = subprocess.run(
        [sys.executable, script, '--buggy', buggy_proj,
         '--fixed', fixed_proj, '--tests', tests_dir],
        cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        log.warn(f"bug_revealing rc={result.returncode}: {result.stderr[:300]}")

    proj_prefix = base[:-2] if base.endswith('_b') or base.endswith('_f') else base
    found = (glob.glob(os.path.join(tests_dir, f'{proj_prefix}_*_bugrevealing.csv')) +
             glob.glob(os.path.join(tests_dir, f'{proj_prefix}_bugrevealing.csv')))
    br_count = br_total = 0
    if found:
        try:
            with open(found[0], newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    br_total += 1
                    if str(row.get('bug_revealing', '')).strip().lower() == 'true':
                        br_count += 1
        except Exception:
            pass
    log.step_done(7, f"bug-revealing: {br_count}/{br_total} "
                     f"(total @Test: {total_test_methods})")
    return found[0] if found else None


def step_8_similarity(project_name, tests_dir, log: PipelineLogger):
    log.step_start(8, "AST similarity analysis")
    if not tests_dir or not os.path.isdir(tests_dir):
        log.step_skip(8, "tests dir not found"); return None

    ast_script = os.path.join(PROJECT_ROOT, "scripts", "code_to_ast.py")
    sim_script = os.path.join(PROJECT_ROOT, "scripts", "measure_similarity.py")
    for script, label in [(ast_script, "code_to_ast"), (sim_script, "measure_similarity")]:
        r = subprocess.run([sys.executable, script, tests_dir],
                           cwd=PROJECT_ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if r.returncode != 0:
            log.warn(f"{label} rc={r.returncode}: {r.stderr[:200]}")

    sim_dir = os.path.join(tests_dir, 'Similarity')
    big_sims = glob.glob(os.path.join(sim_dir, '*_bigSims.csv'))
    big_sum  = glob.glob(os.path.join(sim_dir, '*_bigSimssum.csv'))
    n_pairs = avg_sim = avg_red = mean_sq = None
    if big_sims:
        sims = []
        try:
            with open(big_sims[0], newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    try: sims.append(float(row.get('combined_similarity', 0)))
                    except Exception: pass
        except Exception:
            pass
        if sims:
            n_pairs = len(sims)
            avg_sim = round(sum(sims)/n_pairs, 4)
            avg_red = round(1.0-avg_sim, 4)
    if big_sum:
        try:
            with open(big_sum[0], newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    try: mean_sq = float(row['mean_of_squares']); break
                    except Exception: pass
        except Exception: pass
    log.step_done(8, f"pairs={n_pairs}  avg_sim={avg_sim}  "
                     f"avg_redundancy={avg_red}  mean_of_squares={mean_sq}")
    if mean_sq is not None:
        print(f"[Similarity] mean_of_squares: {mean_sq}")
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
    parser.add_argument("--run_id", default=None)
    parser.add_argument("--steps", nargs='*', type=str,
                        help="Run specific steps: 0 1 2 3a 3b 4 5 6 7 8 9")
    args = parser.parse_args()

    project_name = args.project_name
    prompt_root  = os.path.join(PROJECT_ROOT, 'prompts')
    run_id       = args.run_id or _make_run_id()

    log = PipelineLogger(project_name, verbose=args.verbose)
    log.separator()
    log.info(f"HITS Pipeline  →  {project_name}  run_id={run_id}")
    log.info(f"mode: {'wo_slice' if args.wo_slice else 'slice'}  "
             f"{'+ patch-fix' if args.fixing else ''}")
    log.separator()

    pipeline_start = time.time()

    def should_run(step) -> bool:
        return str(step) in args.steps if args.steps else True

    llm_tracker  = LLMStatsTracker(project_name, playground_dir)
    test_tracker = TestStatsAggregator(project_name, playground_dir)

    if should_run(0):
        meta = step_0(project_name, args.put_root, args.wo_slice, run_id,
                      log, skip_parse=args.skip_parse)
    else:
        meta = _load_or_find_meta(project_name, run_id)
        if not meta:
            log.error("meta.json not found. Run Step 0 first."); sys.exit(1)
        if 'methods_root' not in meta:
            prefix = 'methods_no_slice' if meta.get('wo_slice') else 'methods'
            rid = meta.get('run_id', run_id)
            meta['methods_root'] = os.path.join(
                playground_dir, project_name, f"{prefix}_{rid}")

    n_methods = len(meta.get('method_name_to_idx', {}))
    if n_methods == 0:
        log.error("No methods in workspace. Run Step 0 first."); sys.exit(1)
    log.info(f"{n_methods} focal methods  methods_root={meta['methods_root']}")

    if should_run(1):
        if args.wo_slice: log.step_skip(1, "(wo_slice mode)")
        else: step_1(project_name, meta, prompt_root, log, llm_tracker)

    if should_run(2):
        step_2(project_name, meta, prompt_root,
               args.wo_slice, fixing=False, log=log, llm_tracker=llm_tracker)

    if should_run('3a') or should_run(3):
        step_3a(project_name, meta, prompt_root,
                fixing=False, perform_cleaning=args.perform_cleaning,
                log=log, test_tracker=test_tracker)

    if should_run('3b') or should_run(3):
        step_3b(project_name, meta, prompt_root,
                fixing=False, log=log, llm_tracker=llm_tracker,
                test_tracker=test_tracker)

    if should_run(4):
        step_4(project_name, meta, log)

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

    exec_stats = {}
    if should_run(6):
        exec_stats = step_6(project_name, meta, log, test_tracker)

    tests_dir = None
    if should_run(7) or should_run(8) or should_run(9):
        tests_dir = _collect_tests_dir(project_name, meta, run_id)
        log.info(f"Tests dir: {tests_dir}")

    if should_run(7):
        step_7_bug_revealing(project_name, meta, tests_dir, log)

    if should_run(8):
        step_8_similarity(project_name, tests_dir, log)

    if should_run(9):
        # 传入 step_6 收集的 exec 文件列表，保证两个步骤用相同的 exec 集合
        pre_exec = exec_stats.get('all_exec_files') if exec_stats else None
        step_9_global_test_eval(project_name, meta, tests_dir, log,
                                pre_collected_exec_files=pre_exec)

    try:
        llm_tracker.save()
        test_tracker.save()
    except Exception:
        pass

    pipeline_wall = time.time() - pipeline_start
    sm = llm_tracker.summary()
    log.separator()
    log.info(f"Pipeline complete  →  {project_name}  run_id={run_id}")
    log.info(f"Wall-clock: {round(pipeline_wall,4)}s")
    total_calls    = sm.get('total_calls', 0)
    total_tokens   = sm.get('total_tokens', 0)
    total_prompt   = sm.get('total_prompt_tokens', 0)
    total_compl    = sm.get('total_completion_tokens', 0)
    total_llm_time = sm.get('total_elapsed_sec', 0.0)
    avg_llm_time   = round(total_llm_time/total_calls, 4) if total_calls else 0.0
    log.info(f"LLM elapsed: {round(total_llm_time,4)}s  ({total_calls} calls)")
    log.info(f"Total tokens: {total_tokens}  "
             f"(prompt={total_prompt}, completion={total_compl})")
    log.info(f"Avg LLM time/task: {avg_llm_time}s")
    log.separator()


if __name__ == '__main__':
    main()