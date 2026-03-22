#!/usr/bin/env python3
"""
scripts/run_pipeline.py  — HITS 统一 Pipeline（重写版）

用法:
  cd /home/chenlu/HITS
  python scripts/run_pipeline.py --project_name Csv_1_b \
      --put_root /home/chenlu/HITS/defect4j_projects [--wo_slice] [--fixing]

步骤:
  0a. 解析项目源码 (task.ParseTask)
  0b. 将解析结果插入 JsonDB (parse_data.parse_data)
  0c. 从 JsonDB 导出数据集 (export_data.export_data)
  0d. 初始化工作区 (create_workspace.main_func)
  1.  生成方法分片 (get_slices, parallel)
  2.  生成初始测试代码 (get_code, parallel)
  3a. 运行初始测试 (fix_code.init_test, parallel)
  3b. 修复失败用例 (fix_code.single_unitest_fix, parallel)
  4.  解析覆盖缺口 (slice_patch, optional)
  5.  生成补丁测试 (optional, if slice_result.jsonl found)
  6.  汇总覆盖率报告 (report)
"""

import argparse
import json
import os
import sys
import glob
import shutil
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from json import JSONDecodeError
from pathlib import Path
from typing import Dict, List

# ── 项目根目录 ────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ── 配置 ──────────────────────────────────────────────────────────────────────
from utils.config import (
    playground_dir, api_keys, model, model_url,
    json_db_root, JACOCO_CLI,
    WO_SLICE_TEST_COUNT, MAX_REPAIR_TRIALS,
)
from utils.json_db import JsonDatabase

# ── 各模块直接 import ─────────────────────────────────────────────────────────
from scripts.parse_data   import parse_data          # 0b
from scripts.export_data  import export_data         # 0c
from scripts.class_parser import ClassParser
from utils.config         import GRAMMAR_FILE, LANGUAGE

from generator.open_generator import OpenGenerator
from generator.openlimit      import ChatRateLimiter
from procedures               import get_code, get_slices, fix_code
from procedures               import report as report_module
import utils.report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger("pipeline")


# ══════════════════════════════════════════════════════════════════════════════
# Helper: step banner
# ══════════════════════════════════════════════════════════════════════════════
def _banner(step: str):
    logger.info("=" * 60)
    logger.info(f"  {step}")
    logger.info("=" * 60)


def _is_method_collection(name: str) -> bool:
    return name.startswith("method_") and not name.startswith("class_")


# ══════════════════════════════════════════════════════════════════════════════
# Step 0a: parse project source → class_info/<project_name>/
# ══════════════════════════════════════════════════════════════════════════════
def step_0a_parse_source(project_name: str, put_root: str) -> str:
    """Returns path to class_info output dir."""
    _banner("Step 0a: Parse Project Source Code")
    from scripts.task import ParseTask, Task
    project_path = os.path.join(put_root, project_name)
    focal_classes_json = os.path.join(PROJECT_ROOT, "scripts", "focal_classes.json")

    parse_task = ParseTask()
    _, output_path = parse_task.process_d4j_revisions(project_path, focal_classes_json)

    if output_path is None:
        # fallback: generic parse
        logger.warning("process_d4j_revisions returned None; falling back to find_classes")
        _, output_path = parse_task.find_classes(project_path)

    if output_path:
        logger.info(f"Class info written to: {output_path}")
    else:
        logger.error("Step 0a: no output path produced")
    return output_path or ""


# ══════════════════════════════════════════════════════════════════════════════
# Step 0b: insert class_info JSON into JsonDB
# ══════════════════════════════════════════════════════════════════════════════
def step_0b_insert_db(class_info_dir: str, project_name: str):
    _banner("Step 0b: Insert Parsed Data into JsonDB")
    if not class_info_dir or not os.path.isdir(class_info_dir):
        logger.warning(f"class_info_dir not found: {class_info_dir}; skipping Step 0b")
        return
    count = parse_data(class_info_dir, project_name)
    logger.info(f"Step 0b: inserted {count} method records")


# ══════════════════════════════════════════════════════════════════════════════
# Step 0c: export data from JsonDB → playground/<project>/dataset/
# ══════════════════════════════════════════════════════════════════════════════
def step_0c_export_data(project_name: str):
    _banner("Step 0c: Export Data from JsonDB")
    export_data(project_name)
    logger.info("Step 0c done")


# ══════════════════════════════════════════════════════════════════════════════
# Step 0d: initialize workspace (meta.json + method_N dirs)
# ══════════════════════════════════════════════════════════════════════════════
def step_0d_init_workspace(project_name: str, put_root: str,
                            method_workspaces_prefix: str) -> dict:
    """Returns meta_info dict."""
    _banner("Step 0d: Initialize Workspace")
    db = JsonDatabase(json_db_root, project_name)
    playground_root = os.path.join(playground_dir, project_name)
    put_path = os.path.join(put_root, project_name)

    all_collections = db.list_collection_names()
    mut_names = [name for name in all_collections if _is_method_collection(name)]

    method_name_to_idx = {}
    idx_to_method_name = {}
    for idx, mut_name in enumerate(mut_names):
        method_name_to_idx[mut_name] = f"method_{idx}"
        idx_to_method_name[f"method_{idx}"] = mut_name

    os.makedirs(playground_root, exist_ok=True)
    meta_info = {
        "project_name":        project_name,
        "put_path":            os.path.abspath(put_path),
        "method_name_to_idx":  method_name_to_idx,
        "idx_to_method_name":  idx_to_method_name,
    }
    with open(os.path.join(playground_root, "meta.json"), 'w') as f:
        json.dump(meta_info, f, indent=2)

    for idx in idx_to_method_name:
        os.makedirs(os.path.join(playground_root, method_workspaces_prefix, idx), exist_ok=True)

    logger.info(f"Step 0d: workspace created — {len(mut_names)} methods found")
    return meta_info


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: generate slices (parallel)
# ══════════════════════════════════════════════════════════════════════════════
def step_1_generate_slices(project_name: str, meta_info: dict,
                             method_workspaces_prefix: str, prompt_root: str):
    _banner("Step 1: Generate Method Slices")
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(request_limit=9000, token_limit=900000,
                              bucket_size_in_seconds=60)

    def _work(method_to_test):
        slicer  = get_slices.SliceInfoGenerator(
            prompt_root, "system_gen.jinja2", "gen_slice.jinja2")
        chatter = OpenGenerator(key=api_keys, request_url=model_url,
                                model=model, monitor=monitor)
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix,
                               meta_info['method_name_to_idx'][method_to_test])
        os.makedirs(log_dir, exist_ok=True)
        slicer.work(log_dir, db.get_collection(method_to_test), chatter)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m): m for m in meta_info['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                logger.error(f"Slice gen failed for {futures[fut]}: {e}")
    logger.info("Step 1 done")


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: generate initial test code (parallel)
# ══════════════════════════════════════════════════════════════════════════════
def step_2_generate_tests(project_name: str, meta_info: dict,
                           method_workspaces_prefix: str, prompt_root: str,
                           wo_slice: bool, fixing: bool):
    _banner("Step 2: Generate Initial Test Code")
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(10000, 900000, 60)

    def _work(method_to_test):
        if fixing:
            code_getter = get_code.InitialCodeGenerator(
                prompt_root, "system_repair.jinja2", "repair.jinja2")
        else:
            code_getter = get_code.InitialCodeGenerator(
                prompt_root, "system_gen.jinja2", "gen_code.jinja2")
        chatter = OpenGenerator(key=api_keys, request_url=model_url,
                                model=model, monitor=monitor)
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix,
                               meta_info['method_name_to_idx'][method_to_test])

        if fixing and not os.path.exists(
                os.path.join(log_dir, 'slice_fixing', 'slice_result.jsonl')):
            logger.info(f"Skipping method {method_to_test} in fixing mode: missing slice_fixing/slice_result.jsonl")
            return

        if not fixing and wo_slice:
            method_steps_dir = os.path.join(playground_dir, project_name,
                                            'methods',
                                            meta_info['method_name_to_idx'][method_to_test],
                                            'steps')
            step_files = glob.glob(os.path.join(method_steps_dir, "*.java")) if os.path.exists(method_steps_dir) else []
            logger.info(f"wo_slice mode for {method_to_test}: existing methods steps count = {len(step_files)}")

        try:
            if fixing or not wo_slice:
                code_getter.work(db.get_collection(method_to_test), chatter, log_dir,
                                 fixing=fixing)
            else:
                # wo_slice: match count to slice-mode test count
                _tc_count = len(glob.glob(
                    os.path.join(playground_dir, project_name,
                                 'methods',
                                 meta_info['method_name_to_idx'][method_to_test],
                                 'steps', "*.java")))
                logger.info(f"wo_slice mode: seed slice count for {method_to_test} is {_tc_count}")
                code_getter.work(db.get_collection(method_to_test), chatter, log_dir,
                                 fix_num=_tc_count)
        except JSONDecodeError:
            logger.error(f"JSONDecodeError for {method_to_test}")

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(_work, m): m for m in meta_info['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                logger.error(f"Gen test failed for {futures[fut]}: {e}")
    logger.info("Step 2 done")


# ══════════════════════════════════════════════════════════════════════════════
# Step 3a: run initial tests (parallel)
# ══════════════════════════════════════════════════════════════════════════════
def step_3a_run_tests(project_name: str, meta_info: dict,
                       method_workspaces_prefix: str, prompt_root: str,
                       fixing: bool, perform_cleaning: bool) -> dict:
    _banner("Step 3a: Run Initial Tests")
    db = JsonDatabase(json_db_root, project_name)

    if perform_cleaning:
        steps_dirs = glob.glob(
            f"{playground_dir}/{project_name}/{method_workspaces_prefix}/**/fixing")
        logger.info(f"Cleaning {len(steps_dirs)} fixing dirs")
        for d in steps_dirs:
            shutil.rmtree(d, ignore_errors=True)

    failed_tests: Dict[str, List] = {}

    def _work(method_to_test):
        code_fixer = fix_code.TestFixer(
            prompt_root, "system_repair.jinja2", "repair.jinja2")
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix,
                               meta_info['method_name_to_idx'][method_to_test])
        code_dir = "slice_fixing" if fixing else "steps"
        if not os.path.exists(os.path.join(log_dir, code_dir)):
            return method_to_test, []
        result = code_fixer.init_test(log_dir, meta_info['put_path'],
                                      db.get_collection(method_to_test), fixing=fixing)
        return method_to_test, result

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m): m for m in meta_info['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                mname, res = fut.result()
                failed_tests[mname] = res if res else []
            except Exception as e:
                logger.error(f"Init test failed: {e}")

    logger.info("Step 3a done")
    return failed_tests


# ══════════════════════════════════════════════════════════════════════════════
# Step 3b: fix failed test cases (parallel)
# ══════════════════════════════════════════════════════════════════════════════
def step_3b_fix_tests(project_name: str, meta_info: dict,
                       method_workspaces_prefix: str, prompt_root: str, fixing: bool):
    _banner("Step 3b: Fix Failed Test Cases")
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(9000, 900000, 60)

    tasks: List = []
    for method_to_test in meta_info['method_name_to_idx']:
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix,
                               meta_info['method_name_to_idx'][method_to_test])
        failed_txt = os.path.join(log_dir, "fixing", "init_test_failed.txt")
        if not os.path.exists(failed_txt):
            continue
        with open(failed_txt, "r") as f:
            failed_list = [item for item in f.read().strip().split('\n')
                           if item and (not fixing or 'Fix' in item)]
        for failed_case in failed_list:
            tasks.append((method_to_test, log_dir, failed_case))

    fixed_result: Dict[str, Dict] = {m: {'to_fix': 0, 'fixed': 0}
                                      for m in meta_info['method_name_to_idx']}
    for method_to_test, _, _ in tasks:
        fixed_result[method_to_test]['to_fix'] += 1

    def _fix(method_to_test, log_dir, failed_case):
        code_fixer = fix_code.TestFixer(
            prompt_root,
            "system_repair.jinja2",
            "repair.jinja2" if not fixing else "repair_patch.jinja2")
        chatter = OpenGenerator(key=api_keys, request_url=model_url,
                                model=model, monitor=monitor)
        try:
            return method_to_test, code_fixer.single_unitest_fix(
                log_dir, db.get_collection(method_to_test), failed_case,
                meta_info['put_path'], chatter)
        except RuntimeError as e:
            logger.error(f"Fix error for {method_to_test}: {e}")
            return method_to_test, False

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(_fix, *t) for t in tasks]
        for fut in as_completed(futures):
            try:
                mname, ok = fut.result()
                if ok:
                    fixed_result[mname]['fixed'] += 1
            except Exception as e:
                logger.error(f"Fix worker error: {e}")

    for m, r in fixed_result.items():
        if r['to_fix'] > 0:
            logger.info(f"  {m}: {r['fixed']}/{r['to_fix']} fixed")
    logger.info("Step 3b done")


# ══════════════════════════════════════════════════════════════════════════════
# Step 4: parse missing coverage (optional)
# ══════════════════════════════════════════════════════════════════════════════
def step_4_parse_missing(project_name: str, meta_info: dict,
                          method_workspaces_prefix: str):
    _banner("Step 4: Parse Missing Coverage (Optional)")
    from importlib import reload
    from procedures import parse_missing
    from utils import load_code_graph
    reload(load_code_graph)
    reload(parse_missing)

    db = JsonDatabase(json_db_root, project_name)
    parsed = 0
    for method_name in db.list_collection_names():
        if method_name not in meta_info['method_name_to_idx']:
            continue
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix,
                               meta_info['method_name_to_idx'][method_name])
        fr_dir = os.path.join(log_dir, 'full_report')
        if not os.path.exists(fr_dir) or len(os.listdir(fr_dir)) == 0:
            continue
        try:
            parse_missing.parse_missing(log_dir, db.get_collection(method_name))
            parsed += 1
        except Exception as e:
            logger.warning(f"parse_missing failed for {method_name}: {e}")

    logger.info(f"Step 4 done — parsed {parsed} methods")


# ══════════════════════════════════════════════════════════════════════════════
# Step 6: generate coverage report
# ══════════════════════════════════════════════════════════════════════════════
def step_6_report(project_name: str, meta_info: dict,
                   method_workspaces_prefix: str):
    _banner("Step 6: Generate Coverage Report")
    from importlib import reload
    reload(report_module)
    reload(utils.report)

    db = JsonDatabase(json_db_root, project_name)
    cov_result = []
    for method_to_test in meta_info['method_name_to_idx']:
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix,
                               meta_info['method_name_to_idx'][method_to_test])
        collection = db.get_collection(method_to_test)
        try:
            report_module.single_method_report(
                log_dir, collection, meta_info['put_path'],
                JACOCO_CLI, src_dir='src/main')
        except Exception as e:
            logger.warning(f"report failed for {method_to_test}: {e}")
        try:
            cov_result.append(
                report_module.single_method_analyse(log_dir, collection))
        except Exception as e:
            logger.warning(f"analyse failed for {method_to_test}: {e}")

    result_file = os.path.join(playground_dir, project_name, 'result.json')
    with open(result_file, 'w') as f:
        json.dump(cov_result, f, indent=2)
    logger.info(f"Step 6 done — results in {result_file}")
    return cov_result


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="HITS Unified Pipeline")
    parser.add_argument("--project_name", required=True,
                        help="Project name, e.g. Csv_1_b")
    parser.add_argument("--put_root", required=True,
                        help="Root dir containing PUT projects")
    parser.add_argument("--wo_slice", action="store_true",
                        help="Use no-slice mode (wo_slice)")
    parser.add_argument("--fixing", action="store_true",
                        help="Run in patch-fixing mode")
    parser.add_argument("--perform_cleaning", action="store_true",
                        help="Clean existing fixing dirs before Step 3a")
    parser.add_argument("--skip_parse", action="store_true",
                        help="Skip Steps 0a/0b (already done)")
    parser.add_argument("--skip_slices", action="store_true",
                        help="Skip Step 1 (slices already generated)")
    parser.add_argument("--skip_gentest", action="store_true",
                        help="Skip Step 2 (test files already generated)")
    parser.add_argument("--steps", nargs='*', type=int,
                        help="Only run specific steps (e.g. --steps 1 2 3)")
    args = parser.parse_args()

    project_name = args.project_name
    method_workspaces_prefix = 'methods_no_slice' if args.wo_slice else 'methods'
    prompt_root = os.path.join(PROJECT_ROOT, 'prompts')

    def should_run(step_no: int) -> bool:
        if args.steps:
            return step_no in args.steps
        return True

    logger.info(f"🚀 HITS Pipeline for: {project_name}")
    logger.info(f"   put_root={args.put_root}  wo_slice={args.wo_slice}  fixing={args.fixing}")

    # ── 0a: parse source ─────────────────────────────────────────────────────
    class_info_dir = ""
    if should_run(0) and not args.skip_parse:
        class_info_dir = step_0a_parse_source(project_name, args.put_root)
    else:
        class_info_dir = os.path.join(PROJECT_ROOT, "class_info", project_name)

    # ── 0b: insert DB ────────────────────────────────────────────────────────
    if should_run(0) and not args.skip_parse:
        step_0b_insert_db(class_info_dir, project_name)

    # ── 0c: export data ──────────────────────────────────────────────────────
    if should_run(0) and not args.skip_parse:
        step_0c_export_data(project_name)

    # ── 0d: init workspace ───────────────────────────────────────────────────
    meta_info = {}
    if should_run(0):
        meta_info = step_0d_init_workspace(project_name, args.put_root,
                                           method_workspaces_prefix)
    else:
        meta_path = os.path.join(playground_dir, project_name, "meta.json")
        with open(meta_path) as f:
            meta_info = json.load(f)

    if not meta_info.get('method_name_to_idx'):
        logger.error("No methods found in workspace. Pipeline aborted.")
        sys.exit(1)

    logger.info(f"Working on {len(meta_info['method_name_to_idx'])} methods")

    # ── 1: generate slices ───────────────────────────────────────────────────
    if should_run(1) and args.wo_slice:
        logger.info("Skipping Step 1 (slices) because wo_slice mode is enabled")
    elif should_run(1) and not args.wo_slice and not args.skip_slices:
        step_1_generate_slices(project_name, meta_info,
                               method_workspaces_prefix, prompt_root)

    # ── 2: generate initial tests ────────────────────────────────────────────
    if should_run(2) and not args.skip_gentest:
        step_2_generate_tests(project_name, meta_info, method_workspaces_prefix,
                              prompt_root, args.wo_slice, args.fixing)

    # ── 3a: run initial tests ────────────────────────────────────────────────
    if should_run(3):
        step_3a_run_tests(project_name, meta_info, method_workspaces_prefix,
                          prompt_root, args.fixing, args.perform_cleaning)

    # ── 3b: fix failed tests ─────────────────────────────────────────────────
    if should_run(3):
        step_3b_fix_tests(project_name, meta_info, method_workspaces_prefix,
                          prompt_root, args.fixing)

    # ── 4: parse missing coverage (optional) ─────────────────────────────────
    if should_run(4):
        try:
            step_4_parse_missing(project_name, meta_info, method_workspaces_prefix)
        except Exception as e:
            logger.warning(f"Step 4 failed (non-fatal): {e}")

    # ── 5: patch tests (if slice_result exists) ───────────────────────────────
    if should_run(5):
        has_slice = any(
            os.path.exists(
                os.path.join(playground_dir, project_name, method_workspaces_prefix,
                             idx, "slice_fixing", "slice_result.jsonl"))
            for idx in meta_info['idx_to_method_name'])
        if has_slice:
            _banner("Step 5: Generate Patch Tests")
            step_2_generate_tests(project_name, meta_info, method_workspaces_prefix,
                                  prompt_root, wo_slice=False, fixing=True)
            step_3a_run_tests(project_name, meta_info, method_workspaces_prefix,
                              prompt_root, fixing=True, perform_cleaning=False)
        else:
            logger.info("Step 5: no slice_result.jsonl found, skipping patch generation")

    # ── 6: report ─────────────────────────────────────────────────────────────
    if should_run(6):
        step_6_report(project_name, meta_info, method_workspaces_prefix)

    logger.info("🎉 Pipeline completed!")


if __name__ == '__main__':
    main()