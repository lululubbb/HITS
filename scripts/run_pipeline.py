#!/usr/bin/env python3
"""
scripts/run_pipeline.py — HITS 统一 Pipeline
用法:
  # 正常模式（有分片）
  python run_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects --fixing

  # 无分片模式（跳过 Step 1，直接生成测试）
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects --wo_slice

  # 补丁修复模式（Step 5，需要先完成 Steps 0-4）
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects --fixing

  # 跳过已完成的步骤
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects --steps 3 4 5 6
"""

import argparse
import json
import os
import sys
import glob
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from json import JSONDecodeError
from typing import Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ── 配置 ──────────────────────────────────────────────────────────────────────
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
from procedures               import report as report_module
import utils.report


def _is_method_collection(name: str) -> bool:
    return name.startswith("method_") and not name.startswith("class_")


# ══════════════════════════════════════════════════════════════════════════════
# Step 0: workspace init
# ══════════════════════════════════════════════════════════════════════════════
def step_0(project_name, put_root, method_workspaces_prefix,
           log: PipelineLogger, skip_parse=False) -> dict:
    log.step_start(0, total=None)

    if not skip_parse:
        # 0a parse
        from scripts.task import ParseTask
        project_path = os.path.join(put_root, project_name)
        focal_json = os.path.join(PROJECT_ROOT, "scripts", "focal_classes.json")
        parse_task = ParseTask()
        _, output_path = parse_task.process_d4j_revisions(project_path, focal_json)
        if output_path is None:
            _, output_path = parse_task.find_classes(project_path)

        # 0b insert
        if output_path and os.path.isdir(output_path):
            parse_data(output_path, project_name)

        # 0c export
        export_data(project_name)

    # 0d workspace
    db = JsonDatabase(json_db_root, project_name)
    mut_names = [n for n in db.list_collection_names() if _is_method_collection(n)]
    if not mut_names:
        log.error("No method collections found after Step 0a/0b. Aborting.")
        sys.exit(1)

    method_name_to_idx = {n: f"method_{i}" for i, n in enumerate(mut_names)}
    idx_to_method_name = {v: k for k, v in method_name_to_idx.items()}
    playground_root = os.path.join(playground_dir, project_name)
    os.makedirs(playground_root, exist_ok=True)
    meta = {
        "project_name": project_name,
        "put_path": os.path.abspath(os.path.join(put_root, project_name)),
        "method_name_to_idx": method_name_to_idx,
        "idx_to_method_name": idx_to_method_name,
    }
    with open(os.path.join(playground_root, "meta.json"), 'w') as f:
        json.dump(meta, f, indent=2)
    for prefix in ['methods', 'methods_no_slice']:
        for idx in idx_to_method_name:
            os.makedirs(os.path.join(playground_root, prefix, idx), exist_ok=True)

    log.step_done(0, f"{len(mut_names)} methods")
    return meta


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: slices
# ══════════════════════════════════════════════════════════════════════════════
def step_1(project_name, meta, method_workspaces_prefix, prompt_root,
           log: PipelineLogger, llm_tracker=None):
    n = len(meta['method_name_to_idx'])
    log.step_start(1, total=n)
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(9000, 900000, 60)

    def _work(m):
        slicer  = get_slices.SliceInfoGenerator(prompt_root, "system_gen.jinja2", "gen_slice.jinja2")
        chatter = OpenGenerator(key=api_keys, request_url=model_url, model=model, monitor=monitor)
        if llm_tracker:
            chatter.generate = wrap_generator_with_stats(chatter, llm_tracker, "slice", m, model)
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix, meta['method_name_to_idx'][m])
        os.makedirs(log_dir, exist_ok=True)
        result = slicer.work(log_dir, db.get_collection(m), chatter)
        n_steps = len(result.get('steps', [])) if result else 0
        log.method(m, f"{n_steps} slices")
        return m, n_steps

    total_slices = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m): m for m in meta['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                _, ns = fut.result()
                total_slices += ns
            except Exception as e:
                log.warn(f"Slice failed for {futures[fut]}: {e}")

    log.step_done(1, f"{total_slices} total slices")


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: generate tests
# ══════════════════════════════════════════════════════════════════════════════
def step_2(project_name, meta, method_workspaces_prefix, prompt_root,
           wo_slice, fixing, log: PipelineLogger, llm_tracker=None):
    n = len(meta['method_name_to_idx'])
    log.step_start(2, total=n)
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(10000, 900000, 60)

    system_tmpl = "system_repair.jinja2" if fixing else "system_gen.jinja2"
    user_tmpl   = "repair.jinja2"        if fixing else "gen_code.jinja2"

    def _work(m):
        code_getter = get_code.InitialCodeGenerator(prompt_root, system_tmpl, user_tmpl)
        chatter = OpenGenerator(key=api_keys, request_url=model_url, model=model, monitor=monitor)
        if llm_tracker:
            stage = "patch" if fixing else "gen"
            chatter.generate = wrap_generator_with_stats(chatter, llm_tracker, stage, m, model)
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix, meta['method_name_to_idx'][m])
        if fixing:
            if not os.path.exists(os.path.join(log_dir, 'slice_fixing', 'slice_result.jsonl')):
                return m, 0
        try:
            if fixing:
                code_getter.work(db.get_collection(m), chatter, log_dir, fixing=True)
            elif not wo_slice:
                code_getter.work(db.get_collection(m), chatter, log_dir, fixing=False)
            else:
                existing = glob.glob(os.path.join(playground_dir, project_name, 'methods',
                                                   meta['method_name_to_idx'][m], 'steps', "*.java"))
                fix_num = max(len(existing), WO_SLICE_TEST_COUNT)
                code_getter.work(db.get_collection(m), chatter, log_dir,
                                 fix_num=fix_num, fixing=False)
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
def step_3a(project_name, meta, method_workspaces_prefix, prompt_root,
            fixing, perform_cleaning, log: PipelineLogger,
            test_tracker=None) -> dict:
    n = len(meta['method_name_to_idx'])
    log.step_start("3a", total=n)
    db = JsonDatabase(json_db_root, project_name)

    if perform_cleaning:
        dirs = glob.glob(f"{playground_dir}/{project_name}/{method_workspaces_prefix}/**/fixing")
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)
        log.info(f"Cleaned {len(dirs)} fixing dirs")

    total_pass = total_fail = 0

    def _work(m):
        fixer = fix_code.TestFixer(prompt_root, "system_repair.jinja2", "repair.jinja2")
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix, meta['method_name_to_idx'][m])
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
                n_tests = len(glob.glob(os.path.join(
                    playground_dir, project_name, method_workspaces_prefix,
                    meta['method_name_to_idx'][mname],
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
def step_3b(project_name, meta, method_workspaces_prefix, prompt_root,
            fixing, log: PipelineLogger, llm_tracker=None, test_tracker=None):
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(9000, 900000, 60)

    tasks = []
    for m in meta['method_name_to_idx']:
        log_dir = os.path.join(playground_dir, project_name, method_workspaces_prefix,
                               meta['method_name_to_idx'][m])
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
def step_4(project_name, meta, method_workspaces_prefix, log: PipelineLogger):
    from importlib import reload
    from procedures import parse_missing
    from utils import load_code_graph
    reload(load_code_graph); reload(parse_missing)
    log.step_start(4)
    db = JsonDatabase(json_db_root, project_name)
    parsed = skipped = 0
    for m in db.list_collection_names():
        if m not in meta['method_name_to_idx']:
            continue
        log_dir = os.path.join(playground_dir, project_name, method_workspaces_prefix,
                               meta['method_name_to_idx'][m])
        fr_dir = os.path.join(log_dir, 'full_report')
        if not os.path.isdir(fr_dir) or not os.listdir(fr_dir):
            skipped += 1
            continue
        # 检查 info 表是否有 method_graphs
        info = db.get_collection(m).find_one({"table_name": "info"})
        if not info or 'method_graphs' not in info:
            skipped += 1
            continue
        try:
            parse_missing.parse_missing(log_dir, db.get_collection(m))
            parsed += 1
        except Exception as e:
            log.warn(f"parse_missing failed for {m}: {e}")
            skipped += 1
    if skipped > 0 and parsed == 0:
        log.step_skip(4, f"no method_graphs in info table ({skipped} methods skipped). "
                      f"Run Java static analysis to generate CDG data first.")
    else:
        log.step_done(4, f"parsed={parsed}  skipped={skipped}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 6: coverage report
# ══════════════════════════════════════════════════════════════════════════════
def step_6(project_name, meta, method_workspaces_prefix, log: PipelineLogger,
           test_tracker=None):
    from importlib import reload
    reload(report_module); reload(utils.report)
    n = len(meta['method_name_to_idx'])
    log.step_start(6, total=n)
    db = JsonDatabase(json_db_root, project_name)
    cov_result = []
    for m in meta['method_name_to_idx']:
        log_dir = os.path.join(playground_dir, project_name, method_workspaces_prefix,
                               meta['method_name_to_idx'][m])
        coll = db.get_collection(m)
        try:
            report_module.single_method_report(log_dir, coll, meta['put_path'],
                                               JACOCO_CLI, src_dir='src/main')
        except Exception:
            pass
        try:
            res = report_module.single_method_analyse(log_dir, coll)
            if res:
                cov_result.append(res)
                if test_tracker:
                    for key, cov in res.items():
                        try:
                            test_tracker.add_coverage(
                                m,
                                float(cov.get('inst_cov', '0%').rstrip('%')),
                                float(cov.get('bran_cov', '0%').rstrip('%')))
                        except Exception:
                            pass
        except Exception:
            pass

    result_file = os.path.join(playground_dir, project_name, 'result.json')
    with open(result_file, 'w') as f:
        json.dump(cov_result, f, indent=2)

    if cov_result:
        inst_vals = [float(list(r.values())[0].get('inst_cov', '0%').rstrip('%'))
                     for r in cov_result if r]
        bran_vals = [float(list(r.values())[0].get('bran_cov', '0%').rstrip('%'))
                     for r in cov_result if r]
        avg_inst = round(sum(inst_vals) / len(inst_vals), 1) if inst_vals else 0
        avg_bran = round(sum(bran_vals) / len(bran_vals), 1) if bran_vals else 0
        log.step_done(6, f"avg line={avg_inst}%  branch={avg_bran}%")
    else:
        log.step_done(6, "no coverage data (check jacoco.exec)")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="HITS Pipeline")
    parser.add_argument("--project_name", required=True)
    parser.add_argument("--put_root", required=True)
    parser.add_argument("--wo_slice", action="store_true")
    parser.add_argument("--fixing", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show per-method progress lines")
    parser.add_argument("--perform_cleaning", action="store_true")
    parser.add_argument("--skip_parse", action="store_true")
    parser.add_argument("--steps", nargs='*', type=str,
                        help="Run specific steps, e.g. --steps 1 2 3a 3b 6")
    args = parser.parse_args()

    project_name = args.project_name
    method_workspaces_prefix = 'methods_no_slice' if args.wo_slice else 'methods'
    prompt_root = os.path.join(PROJECT_ROOT, 'prompts')

    log = PipelineLogger(project_name, verbose=args.verbose)
    log.separator()
    log.info(f"HITS Pipeline  →  {project_name}")
    log.info(f"mode: {'wo_slice' if args.wo_slice else 'slice'}  "
             f"{'+ patch-fix' if args.fixing else ''}")
    log.separator()

    def should_run(step) -> bool:
        if args.steps:
            return str(step) in args.steps
        return True

    llm_tracker  = LLMStatsTracker(project_name, playground_dir)
    test_tracker = TestStatsAggregator(project_name, playground_dir)

    # ── Step 0 ───────────────────────────────────────────────────────────────
    if should_run(0):
        meta = step_0(project_name, args.put_root, method_workspaces_prefix,
                      log, skip_parse=args.skip_parse)
    else:
        meta_path = os.path.join(playground_dir, project_name, "meta.json")
        with open(meta_path) as f:
            meta = json.load(f)

    n_methods = len(meta.get('method_name_to_idx', {}))
    if n_methods == 0:
        log.error("No methods in workspace. Run Step 0 first.")
        sys.exit(1)
    log.info(f"{n_methods} focal methods")

    # ── Step 1 ───────────────────────────────────────────────────────────────
    if should_run(1):
        if args.wo_slice:
            log.step_skip(1, "(wo_slice mode)")
        else:
            step_1(project_name, meta, method_workspaces_prefix, prompt_root,
                   log, llm_tracker)

    # ── Step 2 ───────────────────────────────────────────────────────────────
    if should_run(2):
        step_2(project_name, meta, method_workspaces_prefix, prompt_root,
               args.wo_slice, fixing=False, log=log, llm_tracker=llm_tracker)

    # ── Step 3a ──────────────────────────────────────────────────────────────
    if should_run('3a') or should_run(3):
        step_3a(project_name, meta, method_workspaces_prefix, prompt_root,
                fixing=False, perform_cleaning=args.perform_cleaning,
                log=log, test_tracker=test_tracker)

    # ── Step 3b ──────────────────────────────────────────────────────────────
    if should_run('3b') or should_run(3):
        step_3b(project_name, meta, method_workspaces_prefix, prompt_root,
                fixing=False, log=log, llm_tracker=llm_tracker,
                test_tracker=test_tracker)

    # ── Step 4 ───────────────────────────────────────────────────────────────
    if should_run(4):
        step_4(project_name, meta, method_workspaces_prefix, log)

    # ── Step 5 (patch, requires --fixing + slice_result.jsonl) ───────────────
    if should_run(5) and args.fixing:
        has_slice = any(
            os.path.exists(os.path.join(
                playground_dir, project_name, method_workspaces_prefix,
                idx, "slice_fixing", "slice_result.jsonl"))
            for idx in meta['idx_to_method_name'])
        if has_slice:
            log.step_start(5)
            step_2(project_name, meta, method_workspaces_prefix, prompt_root,
                   wo_slice=False, fixing=True, log=log, llm_tracker=llm_tracker)
            step_3a(project_name, meta, method_workspaces_prefix, prompt_root,
                    fixing=True, perform_cleaning=False, log=log,
                    test_tracker=test_tracker)
            log.step_done(5)
        else:
            log.step_skip(5, "no slice_result.jsonl")

    # ── Step 6 ───────────────────────────────────────────────────────────────
    if should_run(6):
        step_6(project_name, meta, method_workspaces_prefix, log, test_tracker)

    # ── Save stats ────────────────────────────────────────────────────────────
    try:
        llm_tracker.save()
        test_tracker.save()
    except Exception:
        pass

    # ── Final summary ─────────────────────────────────────────────────────────
    sm = llm_tracker.summary()
    log.separator()
    log.info(f"Pipeline complete  →  {project_name}")
    if sm.get('total_calls'):
        log.info(f"LLM calls: {sm['total_calls']}  tokens: {sm['total_tokens']}  "
                 f"time: {sm['total_elapsed_sec']:.0f}s")
    log.separator()


if __name__ == '__main__':
    main()