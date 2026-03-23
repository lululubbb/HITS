#!/usr/bin/env python3
"""
scripts/run_evaluation.py — 完整评估 Pipeline

在 run_pipeline.py 完成测试生成后，运行此脚本进行全面评估：
  1. 运行 bug-revealing 检测（需要 buggy + fixed 两个版本）
  2. 运行 AST 生成（code_to_ast.py）
  3. 运行相似度计算（measure_similarity.py）
  4. 汇总所有指标写入统计 CSV

用法:
  cd /home/chenlu/HITS

  # 评估单个项目（Csv_1_b）
  python scripts/run_evaluation.py \\
      --project_name Csv_1_b \\
      --put_root /home/chenlu/HITS/defect4j_projects \\
      --tests_dir /path/to/tests%timestamp

  # 自动发现 tests* 目录
  python scripts/run_evaluation.py \\
      --project_name Csv_1_b \\
      --put_root /home/chenlu/HITS/defect4j_projects

  # 批量评估所有 Csv 项目
  python scripts/run_evaluation.py \\
      --all \\
      --put_root /home/chenlu/HITS/defect4j_projects
"""

import argparse
import csv
import glob
import json
import logging
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.config import playground_dir, json_db_root
from utils.json_db import JsonDatabase
from utils.stats import LLMStatsTracker, TestStatsAggregator

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger("eval")


def find_newest_tests_dir(project_root: str) -> str:
    """找到项目下最新的 tests* 目录"""
    candidates = sorted(
        glob.glob(os.path.join(project_root, 'tests%*')),
        key=os.path.getmtime, reverse=True
    )
    return candidates[0] if candidates else None


def run_script(script_path: str, *args):
    """运行 Python 脚本，打印输出"""
    cmd = [sys.executable, script_path] + list(args)
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.stdout:
        for line in result.stdout.splitlines()[:50]:
            logger.info(f"  [stdout] {line}")
    if result.stderr:
        for line in result.stderr.splitlines()[:30]:
            logger.warning(f"  [stderr] {line}")
    return result.returncode


def run_bug_revealing(project_name: str, put_root: str, tests_dir: str) -> str:
    """运行 bug_revealing.py，返回产出 CSV 路径"""
    logger.info(f"[Eval] Running bug_revealing for {project_name}")

    if project_name.endswith('_b'):
        buggy_proj = os.path.join(put_root, project_name)
        fixed_proj = os.path.join(put_root, project_name.replace('_b', '_f'))
    else:
        buggy_proj = os.path.join(put_root, project_name)
        fixed_proj = os.path.join(put_root, project_name.replace('_f', '_b'))

    if not os.path.isdir(fixed_proj):
        logger.warning(f"[Eval] Fixed project not found: {fixed_proj}; skipping bug_revealing")
        return None
    if not os.path.isdir(buggy_proj):
        logger.warning(f"[Eval] Buggy project not found: {buggy_proj}; skipping bug_revealing")
        return None

    script = os.path.join(PROJECT_ROOT, "scripts", "bug_revealing.py")
    rc = run_script(script,
                    '--buggy', buggy_proj,
                    '--fixed', fixed_proj,
                    '--tests', tests_dir)
    if rc != 0:
        logger.warning(f"[Eval] bug_revealing exited with code {rc}")

    # 找到产出的 CSV
    proj_prefix = project_name.rstrip('_b').rstrip('_f') if '_b' in project_name or '_f' in project_name else project_name
    # strip suffix properly
    for suffix in ('_b', '_f'):
        if project_name.endswith(suffix):
            proj_prefix = project_name[:-2]
            break

    pattern = os.path.join(tests_dir, f'{proj_prefix}_*_bugrevealing.csv')
    found = glob.glob(pattern)
    return found[0] if found else None


def run_ast_and_similarity(tests_dir: str) -> str:
    """运行 code_to_ast 和 measure_similarity，返回 bigSims CSV 路径"""
    logger.info(f"[Eval] Running AST + similarity for {tests_dir}")

    ast_script = os.path.join(PROJECT_ROOT, "scripts", "code_to_ast.py")
    sim_script = os.path.join(PROJECT_ROOT, "scripts", "measure_similarity.py")

    run_script(ast_script, tests_dir)
    run_script(sim_script, tests_dir)

    # 找到产出的 bigSims CSV
    sim_dir = os.path.join(tests_dir, 'Similarity')
    found = glob.glob(os.path.join(sim_dir, '*_bigSims.csv'))
    return found[0] if found else None


def aggregate_stats(project_name: str, tests_dir: str,
                    bugrevealing_csv: str, bigsims_csv: str,
                    method_workspaces_prefix: str = 'methods'):
    """将 bug-revealing 和 similarity 结果合并到 TestStatsAggregator"""
    tracker = TestStatsAggregator(project_name, playground_dir)

    # 从 bug-revealing CSV 加载
    if bugrevealing_csv and os.path.exists(bugrevealing_csv):
        tracker.load_bugrevealing_csv(bugrevealing_csv)
        logger.info(f"[Eval] Loaded bug_revealing from {bugrevealing_csv}")

    # 从 bigSims CSV 加载
    if bigsims_csv and os.path.exists(bigsims_csv):
        tracker.load_similarity_csv(bigsims_csv)
        logger.info(f"[Eval] Loaded similarity from {bigsims_csv}")

    # 从 playground 的 fixing/ 目录加载 compile/exec 结果
    db = JsonDatabase(json_db_root, project_name)
    meta_path = os.path.join(playground_dir, project_name, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        for method_name, method_idx in meta.get('method_name_to_idx', {}).items():
            fixing_dir = os.path.join(playground_dir, project_name,
                                      method_workspaces_prefix, method_idx, 'fixing')
            if not os.path.isdir(fixing_dir):
                continue
            failed_txt = os.path.join(fixing_dir, 'init_test_failed.txt')
            failed_set = set()
            if os.path.exists(failed_txt):
                with open(failed_txt) as f:
                    failed_set = {l.strip() for l in f if l.strip()}

            # 遍历所有测试用例目录
            for test_dir in os.listdir(fixing_dir):
                test_path = os.path.join(fixing_dir, test_dir)
                if not os.path.isdir(test_path) or test_dir == 'init_test_failed.txt':
                    continue
                # 找最高 trial 号的结果
                trials = sorted([d for d in os.listdir(test_path)
                                 if os.path.isdir(os.path.join(test_path, d))
                                 and d.isdigit()],
                                key=int, reverse=True)
                if not trials:
                    continue
                latest_trial = os.path.join(test_path, trials[0], 'temp')
                compile_err = os.path.join(latest_trial, 'compile_error.txt')
                runtime_err = os.path.join(latest_trial, 'runtime_error.txt')

                if os.path.exists(compile_err):
                    compile_status, exec_status = 'fail', 'skip'
                elif os.path.exists(runtime_err):
                    compile_status, exec_status = 'pass', 'fail'
                else:
                    compile_status, exec_status = 'pass', 'pass'

                tracker.add_test_result(method_name, test_dir,
                                        compile_status=compile_status,
                                        exec_status=exec_status)

    # 保存
    results_csv, summary_csv = tracker.save()
    logger.info(f"[Eval] Saved test stats: {results_csv}")
    logger.info(f"[Eval] Saved test summary: {summary_csv}")

    # 打印汇总
    sm = tracker.summary()
    logger.info(f"[Eval] === Stats Summary for {project_name} ===")
    logger.info(f"  Total tests:         {sm.get('total', 0)}")
    logger.info(f"  Compile pass rate:   {sm.get('compile_pass_rate', 0)*100:.1f}%")
    logger.info(f"  Exec pass rate:      {sm.get('exec_pass_rate', 0)*100:.1f}%")
    if sm.get('avg_line_cov') is not None:
        logger.info(f"  Avg line coverage:   {sm.get('avg_line_cov'):.1f}%")
    if sm.get('avg_branch_cov') is not None:
        logger.info(f"  Avg branch coverage: {sm.get('avg_branch_cov'):.1f}%")
    if sm.get('bug_revealing_rate') is not None:
        logger.info(f"  Bug-revealing rate:  {sm.get('bug_revealing_rate')*100:.1f}%")
    if sm.get('avg_similarity') is not None:
        logger.info(f"  Avg similarity:      {sm.get('avg_similarity'):.4f}")
        logger.info(f"  Avg redundancy:      {sm.get('avg_redundancy'):.4f}")

    return sm


def evaluate_project(project_name: str, put_root: str,
                      tests_dir: str = None,
                      method_workspaces_prefix: str = 'methods'):
    """评估单个项目"""
    logger.info(f"=== Evaluating {project_name} ===")

    # 找 tests 目录
    if not tests_dir:
        project_root = os.path.join(put_root, project_name)
        tests_dir = find_newest_tests_dir(project_root)
        if not tests_dir:
            logger.warning(f"No tests* dir found under {project_root}")
            # 尝试从 playground 找
            tests_dir = os.path.join(playground_dir, project_name)
            if not os.path.isdir(tests_dir):
                logger.error(f"Cannot find tests directory for {project_name}")
                return None

    if os.path.basename(tests_dir) == 'test_cases':
        tests_dir = os.path.dirname(tests_dir)
    elif os.path.isdir(os.path.join(tests_dir, 'test_cases')):
        pass  # tests_dir is already the top-level tests* dir
    logger.info(f"Using tests_dir: {tests_dir}")

    # 1. Bug-revealing
    br_csv = run_bug_revealing(project_name, put_root, tests_dir)

    # 2. AST + Similarity
    sims_csv = run_ast_and_similarity(tests_dir)

    # 3. Aggregate
    sm = aggregate_stats(project_name, tests_dir, br_csv, sims_csv,
                         method_workspaces_prefix)
    return sm


def main():
    parser = argparse.ArgumentParser(description="HITS Evaluation Pipeline")
    parser.add_argument("--project_name", help="Project to evaluate (e.g. Csv_1_b)")
    parser.add_argument("--put_root", required=True, help="Root dir of PUT projects")
    parser.add_argument("--tests_dir", help="Path to tests* directory (auto-discovered if omitted)")
    parser.add_argument("--wo_slice", action="store_true",
                        help="Use methods_no_slice workspace")
    parser.add_argument("--all", action="store_true",
                        help="Evaluate all Csv*_b projects under put_root")
    args = parser.parse_args()

    method_workspaces_prefix = 'methods_no_slice' if args.wo_slice else 'methods'

    if args.all:
        # 批量评估
        projects = sorted(glob.glob(os.path.join(args.put_root, 'Csv*_b')))
        logger.info(f"Found {len(projects)} projects to evaluate")
        all_stats = {}
        for proj_path in projects:
            pname = os.path.basename(proj_path)
            sm = evaluate_project(pname, args.put_root,
                                   method_workspaces_prefix=method_workspaces_prefix)
            if sm:
                all_stats[pname] = sm

        # 写出批量汇总
        batch_csv = os.path.join(args.put_root, 'batch_eval_summary.csv')
        with open(batch_csv, 'w', newline='', encoding='utf-8') as f:
            if all_stats:
                keys = list(next(iter(all_stats.values())).keys())
                writer = csv.DictWriter(f, fieldnames=['project'] + keys)
                writer.writeheader()
                for pname, sm in all_stats.items():
                    row = {'project': pname}
                    row.update(sm)
                    writer.writerow(row)
        logger.info(f"Batch summary written to {batch_csv}")

    elif args.project_name:
        evaluate_project(args.project_name, args.put_root,
                         tests_dir=args.tests_dir,
                         method_workspaces_prefix=method_workspaces_prefix)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()