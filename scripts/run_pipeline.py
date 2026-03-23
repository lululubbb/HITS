#!/usr/bin/env python3
"""
scripts/run_pipeline.py  — HITS 统一 Pipeline（修复版）

主要修复：
  1. --wo_slice + --fixing 不再冲突：两个标志独立控制不同阶段
     --wo_slice  控制 Step 1/2 的测试生成模式（有/无分片）
     --fixing    控制 Step 5 的补丁生成阶段，与初始生成无关
  2. Step 2 增加详细日志，定位文件生成问题
  3. Step 3a 增加 steps/ 目录存在性检查日志
  4. 集成 LLMStatsTracker 和 TestStatsAggregator 统计

用法:
  # 正常模式（有分片）
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /path/to/projects

  # 无分片模式（跳过 Step 1，直接生成测试）
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /path/to/projects --wo_slice

  # 补丁修复模式（Step 5，需要先完成 Steps 0-4）
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /path/to/projects --fixing

  # 跳过已完成的步骤
  python scripts/run_pipeline.py --project_name Csv_1_b --put_root /path/to/projects --steps 3 4 5 6
"""

import argparse
import json
import os
import sys
import glob
import shutil
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from json import JSONDecodeError
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
from utils.stats import LLMStatsTracker, TestStatsAggregator, wrap_generator_with_stats

# ── 各模块直接 import ─────────────────────────────────────────────────────────
from scripts.parse_data   import parse_data          # 0b
from scripts.export_data  import export_data         # 0c

from generator.open_generator import OpenGenerator
from generator.openlimit      import ChatRateLimiter
from procedures               import get_code, get_slices, fix_code
from procedures               import report as report_module
import utils.report

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger("pipeline")


# ══════════════════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════════════════
def _banner(step: str):
    logger.info("=" * 60)
    logger.info(f"  {step}")
    logger.info("=" * 60)


def _is_method_collection(name: str) -> bool:
    return name.startswith("method_") and not name.startswith("class_")


# ══════════════════════════════════════════════════════════════════════════════
# Step 0a: parse project source
# ══════════════════════════════════════════════════════════════════════════════
def step_0a_parse_source(project_name: str, put_root: str) -> str:
    _banner("Step 0a: Parse Project Source Code")
    from scripts.task import ParseTask
    project_path = os.path.join(put_root, project_name)
    focal_classes_json = os.path.join(PROJECT_ROOT, "scripts", "focal_classes.json")

    parse_task = ParseTask()
    _, output_path = parse_task.process_d4j_revisions(project_path, focal_classes_json)

    if output_path is None:
        logger.warning("process_d4j_revisions returned None; falling back to find_classes")
        _, output_path = parse_task.find_classes(project_path)

    if output_path:
        logger.info(f"Class info written to: {output_path}")
    else:
        logger.error("Step 0a: no output path produced")
    return output_path or ""


# ══════════════════════════════════════════════════════════════════════════════
# Step 0b: insert into JsonDB
# ══════════════════════════════════════════════════════════════════════════════
def step_0b_insert_db(class_info_dir: str, project_name: str):
    _banner("Step 0b: Insert Parsed Data into JsonDB")
    if not class_info_dir or not os.path.isdir(class_info_dir):
        logger.warning(f"class_info_dir not found: {class_info_dir}; skipping Step 0b")
        return
    count = parse_data(class_info_dir, project_name)
    logger.info(f"Step 0b: inserted {count} method records")


# ══════════════════════════════════════════════════════════════════════════════
# Step 0c: export data from JsonDB
# ══════════════════════════════════════════════════════════════════════════════
def step_0c_export_data(project_name: str):
    _banner("Step 0c: Export Data from JsonDB")
    export_data(project_name)
    logger.info("Step 0c done")


# ══════════════════════════════════════════════════════════════════════════════
# Step 0d: initialize workspace
# ══════════════════════════════════════════════════════════════════════════════
def step_0d_init_workspace(project_name: str, put_root: str,
                            method_workspaces_prefix: str) -> dict:
    _banner("Step 0d: Initialize Workspace")
    db = JsonDatabase(json_db_root, project_name)
    playground_root = os.path.join(playground_dir, project_name)
    put_path = os.path.join(put_root, project_name)

    all_collections = db.list_collection_names()
    mut_names = [name for name in all_collections if _is_method_collection(name)]

    logger.info(f"Found {len(mut_names)} method collections in JsonDB")
    if not mut_names:
        logger.error("No method collections found! Check Steps 0a/0b completed correctly.")

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

    # 创建 methods/ 和 methods_no_slice/ 下的方法目录
    for prefix in ['methods', 'methods_no_slice']:
        for idx in idx_to_method_name:
            os.makedirs(os.path.join(playground_root, prefix, idx), exist_ok=True)

    logger.info(f"Step 0d: workspace created — {len(mut_names)} methods")
    logger.info(f"  Playground: {playground_root}")
    logger.info(f"  PUT path: {os.path.abspath(put_path)}")
    return meta_info


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: generate slices (parallel)
# ══════════════════════════════════════════════════════════════════════════════
def step_1_generate_slices(project_name: str, meta_info: dict,
                             method_workspaces_prefix: str, prompt_root: str,
                             llm_tracker: LLMStatsTracker = None):
    _banner("Step 1: Generate Method Slices")
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(request_limit=9000, token_limit=900000,
                              bucket_size_in_seconds=60)

    def _work(method_to_test):
        slicer  = get_slices.SliceInfoGenerator(
            prompt_root, "system_gen.jinja2", "gen_slice.jinja2")
        chatter = OpenGenerator(key=api_keys, request_url=model_url,
                                model=model, monitor=monitor)
        if llm_tracker:
            chatter.generate = wrap_generator_with_stats(
                chatter, llm_tracker, stage="slice", method=method_to_test, model_name=model)
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix,
                               meta_info['method_name_to_idx'][method_to_test])
        os.makedirs(log_dir, exist_ok=True)
        logger.info(f"[Step 1] Slicing {method_to_test} -> {log_dir}")
        result = slicer.work(log_dir, db.get_collection(method_to_test), chatter)
        if result is None:
            logger.warning(f"[Step 1] Slice generation returned None for {method_to_test}")
        else:
            logger.info(f"[Step 1] Slice done for {method_to_test}: {len(result.get('steps', []))} steps")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m): m for m in meta_info['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                logger.error(f"Slice gen failed for {futures[fut]}: {e}", exc_info=True)
    logger.info("Step 1 done")


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: generate initial test code (parallel)
# ══════════════════════════════════════════════════════════════════════════════
def step_2_generate_tests(project_name: str, meta_info: dict,
                           method_workspaces_prefix: str, prompt_root: str,
                           wo_slice: bool, fixing: bool,
                           llm_tracker: LLMStatsTracker = None):
    """
    修复说明：
    - fixing=True 仅用于 Step 5（补丁生成），此时需要 slice_result.jsonl
    - fixing=False（正常情况）：根据 wo_slice 决定模板和生成策略
    - 在 Step 2（初始生成）中 fixing 始终应为 False
    """
    _banner("Step 2: Generate Initial Test Code")
    db = JsonDatabase(json_db_root, project_name)
    monitor = ChatRateLimiter(10000, 900000, 60)

    # ── 选择正确的模板 ────────────────────────────────────────────────────────
    # 注意：fixing=True 只在 Step 5 补丁生成时使用
    # Step 2 始终使用 gen_code.jinja2（不是 repair.jinja2）
    system_tmpl = "system_gen.jinja2"
    user_tmpl   = "gen_code.jinja2"
    if fixing:
        # Step 5 补丁生成模式
        system_tmpl = "system_repair.jinja2"
        user_tmpl   = "repair.jinja2"

    logger.info(f"[Step 2] Templates: system={system_tmpl}, user={user_tmpl}")
    logger.info(f"[Step 2] wo_slice={wo_slice}, fixing={fixing}")
    logger.info(f"[Step 2] workspace_prefix={method_workspaces_prefix}")

    def _work(method_to_test):
        code_getter = get_code.InitialCodeGenerator(
            prompt_root, system_tmpl, user_tmpl)
        chatter = OpenGenerator(key=api_keys, request_url=model_url,
                                model=model, monitor=monitor)
        if llm_tracker:
            chatter.generate = wrap_generator_with_stats(
                chatter, llm_tracker,
                stage="patch" if fixing else "gen",
                method=method_to_test, model_name=model)

        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix,
                               meta_info['method_name_to_idx'][method_to_test])

        # Step 5 补丁模式：跳过没有 slice_result.jsonl 的方法
        if fixing:
            slice_result = os.path.join(log_dir, 'slice_fixing', 'slice_result.jsonl')
            if not os.path.exists(slice_result):
                logger.info(f"[Step 2/patch] Skipping {method_to_test}: no slice_result.jsonl")
                return

        logger.info(f"[Step 2] Generating tests for {method_to_test}")
        logger.info(f"[Step 2]   log_dir={log_dir}")

        try:
            if fixing:
                # Step 5: 补丁生成
                result = code_getter.work(db.get_collection(method_to_test), chatter,
                                          log_dir, fixing=True)
            elif not wo_slice:
                # 有分片模式：use add_info steps
                result = code_getter.work(db.get_collection(method_to_test), chatter,
                                          log_dir, fixing=False)
            else:
                # wo_slice 模式：不用分片，直接生成
                # 检查 methods/ 目录（有分片版本）中已有多少测试，以便对齐数量
                slice_steps_dir = os.path.join(playground_dir, project_name,
                                               'methods',
                                               meta_info['method_name_to_idx'][method_to_test],
                                               'steps')
                if os.path.isdir(slice_steps_dir):
                    existing = glob.glob(os.path.join(slice_steps_dir, "*.java"))
                    fix_num = max(len(existing), WO_SLICE_TEST_COUNT)
                else:
                    fix_num = WO_SLICE_TEST_COUNT
                logger.info(f"[Step 2] wo_slice fix_num={fix_num} for {method_to_test}")
                result = code_getter.work(db.get_collection(method_to_test), chatter,
                                          log_dir, fix_num=fix_num, fixing=False)

            # 验证输出
            steps_dir = os.path.join(log_dir, "steps" if not fixing else "slice_fixing")
            java_files = glob.glob(os.path.join(steps_dir, "*.java"))
            logger.info(f"[Step 2] {method_to_test}: generated {len(java_files)} Java files in {steps_dir}")
            if not java_files:
                logger.warning(f"[Step 2] NO Java files generated for {method_to_test}! "
                               f"Check LLM API key/connection and template rendering.")

        except JSONDecodeError as e:
            logger.error(f"[Step 2] JSONDecodeError for {method_to_test}: {e}")
        except Exception as e:
            logger.error(f"[Step 2] Exception for {method_to_test}: {e}", exc_info=True)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m): m for m in meta_info['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                logger.error(f"Gen test failed: {e}", exc_info=True)
    logger.info("Step 2 done")


# ══════════════════════════════════════════════════════════════════════════════
# Step 3a: run initial tests (parallel)
# ══════════════════════════════════════════════════════════════════════════════
def step_3a_run_tests(project_name: str, meta_info: dict,
                       method_workspaces_prefix: str, prompt_root: str,
                       fixing: bool, perform_cleaning: bool,
                       test_tracker: TestStatsAggregator = None) -> dict:
    _banner("Step 3a: Run Initial Tests")
    db = JsonDatabase(json_db_root, project_name)

    if perform_cleaning:
        dirs = glob.glob(
            f"{playground_dir}/{project_name}/{method_workspaces_prefix}/**/fixing")
        logger.info(f"Cleaning {len(dirs)} fixing dirs")
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)

    failed_tests: Dict[str, List] = {}

    def _work(method_to_test):
        code_fixer = fix_code.TestFixer(
            prompt_root, "system_repair.jinja2", "repair.jinja2")
        log_dir = os.path.join(playground_dir, project_name,
                               method_workspaces_prefix,
                               meta_info['method_name_to_idx'][method_to_test])

        code_dir = "slice_fixing" if fixing else "steps"
        code_dir_path = os.path.join(log_dir, code_dir)

        if not os.path.exists(code_dir_path):
            logger.warning(f"[Step 3a] {code_dir}/ not found for {method_to_test}: {code_dir_path}")
            logger.warning(f"[Step 3a]   Run Step 2 first to generate test files.")
            return method_to_test, []

        java_files = glob.glob(os.path.join(code_dir_path, "*.java"))
        logger.info(f"[Step 3a] {method_to_test}: {len(java_files)} Java files to run")

        result = code_fixer.init_test(log_dir, meta_info['put_path'],
                                      db.get_collection(method_to_test), fixing=fixing)

        # 更新测试追踪器
        if test_tracker and isinstance(result, list):
            for failed in result:
                test_tracker.add_test_result(method_to_test, failed,
                                             compile_status='fail', exec_status='skip')

        return method_to_test, result if result else []

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_work, m): m for m in meta_info['method_name_to_idx']}
        for fut in as_completed(futures):
            try:
                mname, res = fut.result()
                failed_tests[mname] = res
                if res:
                    logger.info(f"[Step 3a] {mname}: {len(res)} tests failed")
                else:
                    logger.info(f"[Step 3a] {mname}: all tests passed (or no tests)")
            except Exception as e:
                logger.error(f"Init test failed: {e}", exc_info=True)

    logger.info("Step 3a done")
    return failed_tests


# ══════════════════════════════════════════════════════════════════════════════
# Step 3b: fix failed test cases (parallel)
# ══════════════════════════════════════════════════════════════════════════════
def step_3b_fix_tests(project_name: str, meta_info: dict,
                       method_workspaces_prefix: str, prompt_root: str,
                       fixing: bool,
                       llm_tracker: LLMStatsTracker = None,
                       test_tracker: TestStatsAggregator = None):
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
            logger.info(f"[Step 3b] No failed.txt for {method_to_test}")
            continue
        with open(failed_txt, "r") as f:
            content = f.read().strip()
        failed_list = [item for item in content.split('\n')
                       if item and (not fixing or 'Fix' in item)]
        logger.info(f"[Step 3b] {method_to_test}: {len(failed_list)} tests to fix")
        for failed_case in failed_list:
            tasks.append((method_to_test, log_dir, failed_case))

    if not tasks:
        logger.info("[Step 3b] No failed tests to fix")
        logger.info("Step 3b done")
        return

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
        if llm_tracker:
            chatter.generate = wrap_generator_with_stats(
                chatter, llm_tracker, stage="fix", method=method_to_test, model_name=model)
        try:
            ok = code_fixer.single_unitest_fix(
                log_dir, db.get_collection(method_to_test), failed_case,
                meta_info['put_path'], chatter)
            if test_tracker:
                status = 'pass' if ok else 'fail'
                test_tracker.add_test_result(method_to_test, failed_case,
                                             compile_status='pass', exec_status=status)
            return method_to_test, ok
        except RuntimeError as e:
            logger.error(f"Fix error for {method_to_test}/{failed_case}: {e}")
            return method_to_test, False

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(_fix, *t) for t in tasks]
        for fut in as_completed(futures):
            try:
                mname, ok = fut.result()
                if ok:
                    fixed_result[mname]['fixed'] += 1
            except Exception as e:
                logger.error(f"Fix worker error: {e}", exc_info=True)

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
            logger.info(f"[Step 4] No full_report for {method_name}, skip")
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
                   method_workspaces_prefix: str,
                   test_tracker: TestStatsAggregator = None):
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
            result = report_module.single_method_analyse(log_dir, collection)
            cov_result.append(result)
            # 更新测试追踪器覆盖率
            if test_tracker and result:
                for key, cov in result.items():
                    inst = cov.get('inst_cov', '0%').rstrip('%')
                    bran = cov.get('bran_cov', '0%').rstrip('%')
                    try:
                        test_tracker.add_coverage(method_to_test,
                                                  float(inst), float(bran))
                    except Exception:
                        pass
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
                        help="Use no-slice mode for test generation (skip Step 1)")
    parser.add_argument("--fixing", action="store_true",
                        help="Run patch-fixing mode (Step 5 only, requires slice_result.jsonl)")
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
    # wo_slice 影响 Step 1/2 的测试生成策略
    method_workspaces_prefix = 'methods_no_slice' if args.wo_slice else 'methods'
    prompt_root = os.path.join(PROJECT_ROOT, 'prompts')

    # ── 关键修复：--fixing 只影响 Step 5，不影响 Step 2 ─────────────────────
    # 如果用户同时传了 --wo_slice 和 --fixing，两者不冲突：
    #   Step 2 使用 wo_slice 策略（不用分片），fixing=False
    #   Step 5 使用 fixing=True 的补丁生成
    logger.info(f"🚀 HITS Pipeline for: {project_name}")
    logger.info(f"   put_root={args.put_root}")
    logger.info(f"   wo_slice={args.wo_slice}  (test generation mode)")
    logger.info(f"   fixing={args.fixing}   (patch generation: Step 5 only)")
    logger.info(f"   workspace_prefix={method_workspaces_prefix}")

    def should_run(step_no: int) -> bool:
        if args.steps:
            return step_no in args.steps
        return True

    # ── 初始化统计追踪器 ─────────────────────────────────────────────────────
    llm_tracker  = LLMStatsTracker(project_name, playground_dir)
    test_tracker = TestStatsAggregator(project_name, playground_dir)

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
    if should_run(1):
        if args.wo_slice:
            logger.info("Skipping Step 1 (slices): wo_slice mode enabled")
        elif args.skip_slices:
            logger.info("Skipping Step 1 (slices): --skip_slices flag set")
        else:
            step_1_generate_slices(project_name, meta_info,
                                   method_workspaces_prefix, prompt_root,
                                   llm_tracker=llm_tracker)

    # ── 2: generate initial tests ────────────────────────────────────────────
    # 关键修复：Step 2 的 fixing 参数始终为 False（初始测试生成）
    # --fixing flag 只影响 Step 5
    if should_run(2) and not args.skip_gentest:
        step_2_generate_tests(project_name, meta_info, method_workspaces_prefix,
                              prompt_root,
                              wo_slice=args.wo_slice,
                              fixing=False,          # ← 始终 False！
                              llm_tracker=llm_tracker)

    # ── 3a: run initial tests ────────────────────────────────────────────────
    if should_run(3):
        step_3a_run_tests(project_name, meta_info, method_workspaces_prefix,
                          prompt_root,
                          fixing=False,              # ← 运行 steps/ 下的测试
                          perform_cleaning=args.perform_cleaning,
                          test_tracker=test_tracker)

    # ── 3b: fix failed tests ─────────────────────────────────────────────────
    if should_run(3):
        step_3b_fix_tests(project_name, meta_info, method_workspaces_prefix,
                          prompt_root,
                          fixing=False,              # ← 修复 steps/ 下的失败
                          llm_tracker=llm_tracker,
                          test_tracker=test_tracker)

    # ── 4: parse missing coverage ─────────────────────────────────────────────
    if should_run(4):
        try:
            step_4_parse_missing(project_name, meta_info, method_workspaces_prefix)
        except Exception as e:
            logger.warning(f"Step 4 failed (non-fatal): {e}")

    # ── 5: patch tests（--fixing 模式，需要 slice_result.jsonl）──────────────
    if should_run(5) and args.fixing:
        has_slice = any(
            os.path.exists(
                os.path.join(playground_dir, project_name, method_workspaces_prefix,
                             idx, "slice_fixing", "slice_result.jsonl"))
            for idx in meta_info['idx_to_method_name'])
        if has_slice:
            _banner("Step 5: Generate Patch Tests")
            step_2_generate_tests(project_name, meta_info, method_workspaces_prefix,
                                  prompt_root,
                                  wo_slice=False,
                                  fixing=True,   # ← Step 5 才用 fixing=True
                                  llm_tracker=llm_tracker)
            step_3a_run_tests(project_name, meta_info, method_workspaces_prefix,
                              prompt_root,
                              fixing=True,
                              perform_cleaning=False,
                              test_tracker=test_tracker)
        else:
            logger.info("Step 5: no slice_result.jsonl found, skipping patch generation")
    elif should_run(5) and not args.fixing:
        # 自动检测是否有 slice_result.jsonl
        has_slice = any(
            os.path.exists(
                os.path.join(playground_dir, project_name, method_workspaces_prefix,
                             idx, "slice_fixing", "slice_result.jsonl"))
            for idx in meta_info['idx_to_method_name'])
        if has_slice:
            _banner("Step 5: Generate Patch Tests (auto-detected)")
            step_2_generate_tests(project_name, meta_info, method_workspaces_prefix,
                                  prompt_root, wo_slice=False, fixing=True,
                                  llm_tracker=llm_tracker)
            step_3a_run_tests(project_name, meta_info, method_workspaces_prefix,
                              prompt_root, fixing=True, perform_cleaning=False,
                              test_tracker=test_tracker)
        else:
            logger.info("Step 5: no slice_result.jsonl found, skipping")

    # ── 6: report ─────────────────────────────────────────────────────────────
    if should_run(6):
        step_6_report(project_name, meta_info, method_workspaces_prefix,
                      test_tracker=test_tracker)

    # ── 保存统计数据 ──────────────────────────────────────────────────────────
    try:
        calls_csv, summary_csv = llm_tracker.save()
        results_csv, test_sum_csv = test_tracker.save()
        logger.info(f"Stats saved:")
        logger.info(f"  LLM calls:    {calls_csv}")
        logger.info(f"  LLM summary:  {summary_csv}")
        logger.info(f"  Test results: {results_csv}")
        logger.info(f"  Test summary: {test_sum_csv}")

        # 打印 LLM 调用汇总
        sm = llm_tracker.summary()
        if sm:
            logger.info(f"LLM Stats Summary:")
            logger.info(f"  Total calls:  {sm.get('total_calls', 0)}")
            logger.info(f"  Total tokens: {sm.get('total_tokens', 0)}")
            logger.info(f"  Total time:   {sm.get('total_elapsed_sec', 0):.1f}s")
            for stage, s in sm.get('by_stage', {}).items():
                logger.info(f"  [{stage}] calls={s['calls']}, tokens={s['total_tokens']}, "
                            f"time={s['elapsed_sec']:.1f}s, failures={s['failures']}")

        # 打印测试结果汇总
        tsm = test_tracker.summary()
        if tsm:
            logger.info(f"Test Stats Summary:")
            logger.info(f"  Total tests:    {tsm.get('total', 0)}")
            logger.info(f"  Compile pass:   {tsm.get('compile_pass', 0)} "
                        f"({tsm.get('compile_pass_rate', 0)*100:.1f}%)")
            logger.info(f"  Exec pass:      {tsm.get('exec_pass', 0)} "
                        f"({tsm.get('exec_pass_rate', 0)*100:.1f}%)")

    except Exception as e:
        logger.warning(f"Failed to save stats: {e}")

    logger.info("🎉 Pipeline completed!")


if __name__ == '__main__':
    main()