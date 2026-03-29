#!/usr/bin/env python3
"""
scripts/run_evaluation.py — HITS 评估 Pipeline（修复版）

适配当前目录结构：
  - tests* 目录位于 playground/<project_name>/tests%<timestamp>/ 下
  - 或 put_root/<project_name>/tests%<timestamp>/ 下
  - 支持直接指定 tests_dir
  - token/time 统计与 ChatUniTest/RefineAgent 保持一致格式

用法：
  # 评估单个项目
  python scripts/run_evaluation.py \
      --project_name Csv_1_b \
      --put_root /home/chenlu/HITS/defect4j_projects

  # 批量评估所有 Csv 项目
  python scripts/run_evaluation.py \
      --all \
      --put_root /home/chenlu/HITS/defect4j_projects

  # 指定 tests 目录
  python scripts/run_evaluation.py \
      --project_name Csv_1_b \
      --put_root /home/chenlu/HITS/defect4j_projects \
      --tests_dir /path/to/tests%timestamp
"""

import argparse
import csv
import glob
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.config import playground_dir, json_db_root
from utils.json_db import JsonDatabase

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
)
logger = logging.getLogger("eval")


# ══════════════════════════════════════════════════════════════════════════════
# 目录发现：适配当前目录结构
# ══════════════════════════════════════════════════════════════════════════════

def find_tests_dirs(project_name: str, put_root: str):
    """
    按优先级查找 tests* 目录：
    1. playground/<project_name>/tests%* 
    2. put_root/<project_name>/tests%*
    3. playground/<project_name>/methods/method_*/fixing/ （直接从 fixing 目录评估）
    返回所有找到的 tests* 目录列表（按 mtime 降序）
    """
    candidates = []

    # 优先级1：playground 目录
    pg_proj = os.path.join(playground_dir, project_name)
    if os.path.isdir(pg_proj):
        for d in glob.glob(os.path.join(pg_proj, 'tests%*')):
            if os.path.isdir(d):
                candidates.append(d)

    # 优先级2：put_root 目录
    if put_root:
        pu_proj = os.path.join(put_root, project_name)
        if os.path.isdir(pu_proj):
            for d in glob.glob(os.path.join(pu_proj, 'tests%*')):
                if os.path.isdir(d):
                    candidates.append(d)

    if candidates:
        candidates.sort(key=os.path.getmtime, reverse=True)
        return candidates

    return []


def find_or_create_tests_dir(project_name: str, put_root: str,
                              method_workspaces_prefix: str = 'methods') -> str:
    """
    如果没有 tests%* 目录，则从 playground/methods/ 下收集测试文件，
    创建一个临时的 tests%timestamp 目录。
    """
    existing = find_tests_dirs(project_name, put_root)
    if existing:
        return existing[0]

    # 从 fixing/ 目录收集所有通过的测试文件，创建 tests% 目录
    logger.info(f"[Eval] No tests* dir found, collecting from fixing/ directories...")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    tests_dir = os.path.join(playground_dir, project_name, f"tests%{timestamp}")
    test_cases_dir = os.path.join(tests_dir, "test_cases")
    os.makedirs(test_cases_dir, exist_ok=True)

    methods_root = os.path.join(playground_dir, project_name, method_workspaces_prefix)
    if not os.path.isdir(methods_root):
        logger.warning(f"[Eval] methods dir not found: {methods_root}")
        return tests_dir

    copied = 0
    for method_dir in sorted(os.listdir(methods_root)):
        fixing_dir = os.path.join(methods_root, method_dir, "fixing")
        if not os.path.isdir(fixing_dir):
            continue
        for test_name in os.listdir(fixing_dir):
            test_root = os.path.join(fixing_dir, test_name)
            if not os.path.isdir(test_root) or test_name == "init_test_failed.txt":
                continue
            # 找最高 trial 号中通过的 java 文件
            trials = sorted(
                [d for d in os.listdir(test_root)
                 if os.path.isdir(os.path.join(test_root, d)) and d.isdigit()],
                key=int, reverse=True
            )
            for trial in trials:
                temp_dir = os.path.join(test_root, trial, "temp")
                java_files = glob.glob(os.path.join(temp_dir, "*.java"))
                if not java_files:
                    continue
                compile_err = os.path.join(temp_dir, "compile_error.txt")
                runtime_err = os.path.join(temp_dir, "runtime_error.txt")
                if os.path.exists(compile_err) or os.path.exists(runtime_err):
                    continue
                # 通过的测试
                for jf in java_files:
                    dst = os.path.join(test_cases_dir, os.path.basename(jf))
                    if not os.path.exists(dst):
                        import shutil
                        shutil.copy2(jf, dst)
                        copied += 1
                break

    logger.info(f"[Eval] Created tests dir with {copied} test files: {tests_dir}")
    return tests_dir


# ══════════════════════════════════════════════════════════════════════════════
# 编译/执行状态收集（直接从 fixing/ 目录读，不依赖 tests* 目录）
# ══════════════════════════════════════════════════════════════════════════════

def collect_compile_exec_stats(project_name: str,
                                method_workspaces_prefix: str = 'methods') -> dict:
    """
    从 playground/methods/method_*/fixing/ 目录收集编译和执行统计。
    返回：{test_class: {compile_status, exec_status, exec_timeout}}
    """
    stats = {}
    methods_root = os.path.join(playground_dir, project_name, method_workspaces_prefix)
    if not os.path.isdir(methods_root):
        return stats

    for method_dir in sorted(os.listdir(methods_root)):
        fixing_dir = os.path.join(methods_root, method_dir, "fixing")
        if not os.path.isdir(fixing_dir):
            continue
        for test_name in os.listdir(fixing_dir):
            test_root = os.path.join(fixing_dir, test_name)
            if not os.path.isdir(test_root):
                continue
            trials = sorted(
                [d for d in os.listdir(test_root)
                 if os.path.isdir(os.path.join(test_root, d)) and d.isdigit()],
                key=int, reverse=True
            )
            if not trials:
                continue
            latest = os.path.join(test_root, trials[0], "temp")
            compile_err = os.path.join(latest, "compile_error.txt")
            runtime_err = os.path.join(latest, "runtime_error.txt")
            timeout_marker = os.path.join(latest, "timeout.txt")

            if os.path.exists(compile_err):
                compile_status, exec_status, timed_out = "fail", "skip", False
            elif os.path.exists(runtime_err):
                compile_status, exec_status = "pass", "fail"
                timed_out = os.path.exists(timeout_marker)
            else:
                compile_status, exec_status, timed_out = "pass", "pass", False

            stats[test_name] = {
                "compile_status": compile_status,
                "exec_status": exec_status,
                "exec_timeout": timed_out,
            }
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# Token & Time 统计（与 ChatUniTest/RefineAgent 保持一致）
# ══════════════════════════════════════════════════════════════════════════════

def collect_token_time_stats(project_name: str) -> dict:
    """
    从 playground/<project_name>/stats/llm_calls.csv 读取 token 和 time 统计。
    输出格式与 ChatUniTest/RefineAgent 的评估格式一致：
      {
        total_prompt_tokens, total_completion_tokens, total_tokens,
        total_time_sec,
        per_stage: {slice: {...}, gen: {...}, fix: {...}}
      }
    """
    stats_path = os.path.join(playground_dir, project_name, "stats", "llm_calls.csv")
    result = {
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "total_time_sec": 0.0,
        "total_calls": 0,
        "per_stage": {},
    }
    if not os.path.exists(stats_path):
        logger.warning(f"[Eval] LLM stats not found: {stats_path}")
        return result

    with open(stats_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                pt = int(row.get('prompt_tokens', 0) or 0)
                ct = int(row.get('completion_tokens', 0) or 0)
                tt = float(row.get('elapsed_sec', 0) or 0)
                stage = row.get('stage', 'unknown')
                result["total_prompt_tokens"]     += pt
                result["total_completion_tokens"] += ct
                result["total_tokens"]            += pt + ct
                result["total_time_sec"]          += tt
                result["total_calls"]             += 1
                s = result["per_stage"].setdefault(stage, {
                    "calls": 0, "prompt_tokens": 0,
                    "completion_tokens": 0, "total_tokens": 0, "time_sec": 0.0
                })
                s["calls"]             += 1
                s["prompt_tokens"]     += pt
                s["completion_tokens"] += ct
                s["total_tokens"]      += pt + ct
                s["time_sec"]          += tt
            except Exception:
                continue
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Bug-revealing
# ══════════════════════════════════════════════════════════════════════════════

def run_bug_revealing(project_name: str, put_root: str, tests_dir: str) -> str:
    """运行 bug_revealing.py，返回产出 CSV 路径"""
    logger.info(f"[Eval] Bug-revealing: {project_name}")

    # 解析 buggy/fixed 路径
    base = project_name
    if base.endswith('_b'):
        buggy_proj = os.path.join(put_root, base)
        fixed_proj = os.path.join(put_root, base[:-2] + '_f')
    elif base.endswith('_f'):
        fixed_proj = os.path.join(put_root, base)
        buggy_proj = os.path.join(put_root, base[:-2] + '_b')
    else:
        buggy_proj = os.path.join(put_root, base)
        fixed_proj = os.path.join(put_root, base + '_f')

    if not os.path.isdir(buggy_proj):
        logger.warning(f"[Eval] Buggy project not found: {buggy_proj}")
        return None
    if not os.path.isdir(fixed_proj):
        logger.warning(f"[Eval] Fixed project not found: {fixed_proj}")
        return None

    script = os.path.join(PROJECT_ROOT, "scripts", "bug_revealing.py")
    cmd = [sys.executable, script,
           '--buggy', buggy_proj,
           '--fixed', fixed_proj,
           '--tests', tests_dir]
    logger.info(f"[Eval]   cmd: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.warning(f"[Eval] bug_revealing rc={result.returncode}")
        if result.stderr:
            logger.warning(result.stderr[:500])

    # 找产出 CSV
    proj_prefix = base[:-2] if base.endswith('_b') or base.endswith('_f') else base
    found = (glob.glob(os.path.join(tests_dir, f'{proj_prefix}_*_bugrevealing.csv')) +
             glob.glob(os.path.join(tests_dir, f'{proj_prefix}_bugrevealing.csv')))
    return found[0] if found else None


# ══════════════════════════════════════════════════════════════════════════════
# AST + Similarity
# ══════════════════════════════════════════════════════════════════════════════

def run_ast_and_similarity(tests_dir: str) -> str:
    """运行 code_to_ast 和 measure_similarity，返回 bigSims CSV 路径"""
    logger.info(f"[Eval] AST + similarity: {tests_dir}")
    ast_script = os.path.join(PROJECT_ROOT, "scripts", "code_to_ast.py")
    sim_script = os.path.join(PROJECT_ROOT, "scripts", "measure_similarity.py")

    for script, label in [(ast_script, "code_to_ast"), (sim_script, "measure_similarity")]:
        result = subprocess.run(
            [sys.executable, script, tests_dir],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0:
            logger.warning(f"[Eval] {label} rc={result.returncode}")
        else:
            logger.info(f"[Eval] {label} done")

    sim_dir = os.path.join(tests_dir, 'Similarity')
    found = glob.glob(os.path.join(sim_dir, '*_bigSims.csv'))
    return found[0] if found else None


# ══════════════════════════════════════════════════════════════════════════════
# 覆盖率统计（从 jacoco.xml 读取）
# ══════════════════════════════════════════════════════════════════════════════

def collect_coverage_stats(project_name: str,
                            method_workspaces_prefix: str = 'methods') -> dict:
    """
    从 playground/methods/method_*/full_report/ 读取 jacoco.xml（若存在），
    汇总 line/branch 覆盖率。
    """
    import xml.etree.ElementTree as ET
    methods_root = os.path.join(playground_dir, project_name, method_workspaces_prefix)
    line_covs, branch_covs = [], []

    if not os.path.isdir(methods_root):
        return {}

    for method_dir in os.listdir(methods_root):
        # 优先使用 mvn jacoco:report 生成的 xml
        xml_path = os.path.join(
            methods_root, method_dir, "full_report", "jacoco.xml")
        # 兼容旧版 jacoco CLI 格式（coverage.csv）
        csv_path = os.path.join(
            methods_root, method_dir, "full_report", "coverage.csv")
        if os.path.exists(xml_path):
            try:
                tree = ET.parse(xml_path)
                root = ET.fromstring(open(xml_path).read()[open(xml_path).read().find('<report'):])
                counters = root.findall('.//counter')
                for c in counters:
                    if c.get('type') == 'LINE':
                        cov = int(c.get('covered', 0))
                        mis = int(c.get('missed', 0))
                        tot = cov + mis
                        if tot > 0:
                            line_covs.append(round(100.0 * cov / tot, 2))
                    if c.get('type') == 'BRANCH':
                        cov = int(c.get('covered', 0))
                        mis = int(c.get('missed', 0))
                        tot = cov + mis
                        if tot > 0:
                            branch_covs.append(round(100.0 * cov / tot, 2))
            except Exception:
                pass
        elif os.path.exists(csv_path):
            try:
                with open(csv_path) as f:
                    for row in csv.DictReader(f):
                        lc = int(row.get('LINE_COVERED', 0) or 0)
                        lm = int(row.get('LINE_MISSED', 0) or 0)
                        bc = int(row.get('BRANCH_COVERED', 0) or 0)
                        bm = int(row.get('BRANCH_MISSED', 0) or 0)
                        if lc + lm > 0:
                            line_covs.append(round(100.0 * lc / (lc + lm), 2))
                        if bc + bm > 0:
                            branch_covs.append(round(100.0 * bc / (bc + bm), 2))
            except Exception:
                pass

    return {
        "avg_line_cov": round(sum(line_covs) / len(line_covs), 2) if line_covs else None,
        "avg_branch_cov": round(sum(branch_covs) / len(branch_covs), 2) if branch_covs else None,
        "n_methods_with_cov": len(line_covs),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 综合评估入口
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_project(project_name: str, put_root: str,
                     tests_dir: str = None,
                     method_workspaces_prefix: str = 'methods',
                     output_dir: str = None) -> dict:
    """
    综合评估单个项目，返回评估结果 dict。
    输出格式与 ChatUniTest/RefineAgent 保持一致。
    """
    logger.info(f"=== Evaluating {project_name} ===")
    eval_start = time.time()

    # 1. 找或创建 tests 目录
    if not tests_dir:
        tests_dir = find_or_create_tests_dir(
            project_name, put_root, method_workspaces_prefix)
    if os.path.basename(tests_dir) == 'test_cases':
        tests_dir = os.path.dirname(tests_dir)
    logger.info(f"[Eval] tests_dir: {tests_dir}")

    # 2. 编译/执行统计
    logger.info(f"[Eval] Collecting compile/exec stats...")
    ce_stats = collect_compile_exec_stats(project_name, method_workspaces_prefix)
    total_tests = len(ce_stats)
    compile_pass = sum(1 for s in ce_stats.values() if s['compile_status'] == 'pass')
    exec_pass    = sum(1 for s in ce_stats.values() if s['exec_status'] == 'pass')
    compile_rate = round(compile_pass / total_tests, 4) if total_tests else 0.0
    exec_rate    = round(exec_pass / total_tests, 4) if total_tests else 0.0

    # 3. 覆盖率
    logger.info(f"[Eval] Collecting coverage stats...")
    cov_stats = collect_coverage_stats(project_name, method_workspaces_prefix)

    # 4. Bug-revealing
    br_csv = run_bug_revealing(project_name, put_root, tests_dir)
    br_total = br_pass = 0
    if br_csv and os.path.exists(br_csv):
        try:
            with open(br_csv, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    br_total += 1
                    if str(row.get('bug_revealing', '')).strip().lower() == 'true':
                        br_pass += 1
        except Exception as e:
            logger.warning(f"[Eval] br_csv read error: {e}")
    br_rate = round(br_pass / br_total, 4) if br_total else None

    # 5. AST + Similarity
    sims_csv = run_ast_and_similarity(tests_dir)
    sims = []
    if sims_csv and os.path.exists(sims_csv):
        try:
            with open(sims_csv, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    try:
                        sims.append(float(row.get('combined_similarity', 0)))
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[Eval] sims_csv read error: {e}")
    avg_sim = round(sum(sims) / len(sims), 4) if sims else None
    avg_red = round(1.0 - avg_sim, 4) if avg_sim is not None else None

    # 6. Token & Time
    token_time = collect_token_time_stats(project_name)

    eval_time = round(time.time() - eval_start, 2)

    # 如果 tests_dir 存在 test_cases/，运行全局测试评估生成文件夹
    if tests_dir and os.path.isdir(os.path.join(tests_dir, 'test_cases')):
        logger.info(f"[Eval] Running global test evaluation for folders...")
        try:
            from utils.test_runner import TestRunner
            runner = TestRunner(tests_dir, os.path.join(put_root, project_name),
                                output_path=tests_dir, tool='jacoco', debug=False)
            runner.start_all_test()
            logger.info(f"[Eval] Global test evaluation completed")
        except Exception as e:
            logger.warning(f"[Eval] Global test evaluation failed: {e}")

    result = {
        "project":                  project_name,
        "timestamp":                datetime.now().isoformat(),
        # 测试规模
        "total_tests":              total_tests,
        # 编译
        "compile_pass":             compile_pass,
        "compile_fail":             total_tests - compile_pass,
        "compile_rate":             compile_rate,
        # 执行
        "exec_pass":                exec_pass,
        "exec_fail":                total_tests - exec_pass - (total_tests - compile_pass),
        "exec_rate":                exec_rate,
        # 覆盖率
        "avg_line_cov":             cov_stats.get("avg_line_cov"),
        "avg_branch_cov":           cov_stats.get("avg_branch_cov"),
        "n_methods_with_cov":       cov_stats.get("n_methods_with_cov", 0),
        # Bug-revealing
        "bug_revealing_total":      br_total,
        "bug_revealing_pass":       br_pass,
        "bug_revealing_rate":       br_rate,
        # Similarity / Redundancy
        "avg_similarity":           avg_sim,
        "avg_redundancy":           avg_red,
        "n_similarity_pairs":       len(sims),
        # Token & Time
        "total_llm_calls":          token_time["total_calls"],
        "total_prompt_tokens":      token_time["total_prompt_tokens"],
        "total_completion_tokens":  token_time["total_completion_tokens"],
        "total_tokens":             token_time["total_tokens"],
        "total_llm_time_sec":       round(token_time["total_time_sec"], 2),
        "eval_time_sec":            eval_time,
    }

    # 打印摘要
    logger.info(f"\n{'='*55}")
    logger.info(f"  Evaluation Summary: {project_name}")
    logger.info(f"{'='*55}")
    logger.info(f"  Tests:       {total_tests}")
    logger.info(f"  Compile:     {compile_pass}/{total_tests} ({compile_rate*100:.1f}%)")
    logger.info(f"  Execute:     {exec_pass}/{total_tests} ({exec_rate*100:.1f}%)")
    if cov_stats.get("avg_line_cov") is not None:
        logger.info(f"  Line cov:    {cov_stats['avg_line_cov']:.1f}%")
    if cov_stats.get("avg_branch_cov") is not None:
        logger.info(f"  Branch cov:  {cov_stats['avg_branch_cov']:.1f}%")
    if br_rate is not None:
        logger.info(f"  Bug-reveal:  {br_pass}/{br_total} ({br_rate*100:.1f}%)")
    if avg_sim is not None:
        logger.info(f"  Similarity:  {avg_sim:.4f}  Redundancy: {avg_red:.4f}")
    logger.info(f"  Tokens:      {token_time['total_tokens']}  "
                f"Time: {token_time['total_time_sec']:.0f}s")
    logger.info(f"{'='*55}\n")

    # 保存结果
    if not output_dir:
        output_dir = os.path.join(playground_dir, project_name, "eval")
    os.makedirs(output_dir, exist_ok=True)
    result_json = os.path.join(output_dir, f"{project_name}_eval.json")
    with open(result_json, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    logger.info(f"[Eval] Saved to {result_json}")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# 批量评估 + 写出对比 CSV（与 ChatUniTest/RefineAgent 格式一致）
# ══════════════════════════════════════════════════════════════════════════════

# 与 ChatUniTest/RefineAgent 保持一致的列名
COMPARISON_COLUMNS = [
    "project", "timestamp",
    "total_tests",
    "compile_pass", "compile_fail", "compile_rate",
    "exec_pass", "exec_fail", "exec_rate",
    "avg_line_cov", "avg_branch_cov", "n_methods_with_cov",
    "bug_revealing_total", "bug_revealing_pass", "bug_revealing_rate",
    "avg_similarity", "avg_redundancy", "n_similarity_pairs",
    "total_llm_calls",
    "total_prompt_tokens", "total_completion_tokens", "total_tokens",
    "total_llm_time_sec", "eval_time_sec",
]


def write_comparison_csv(results: list, output_path: str):
    """将多个项目的评估结果写成一个对比 CSV，列顺序与 ChatUniTest/RefineAgent 一致"""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COMPARISON_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        for r in results:
            writer.writerow(r)
    logger.info(f"[Eval] Comparison CSV written: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="HITS Evaluation Pipeline")
    parser.add_argument("--project_name", help="Project to evaluate (e.g. Csv_1_b)")
    parser.add_argument("--put_root", required=True, help="Root dir of PUT projects")
    parser.add_argument("--tests_dir", help="Explicit tests* directory path")
    parser.add_argument("--wo_slice", action="store_true",
                        help="Use methods_no_slice workspace")
    parser.add_argument("--all", action="store_true",
                        help="Evaluate all Csv*_b projects under put_root")
    parser.add_argument("--output", default=None,
                        help="Output directory for comparison CSV")
    args = parser.parse_args()

    method_workspaces_prefix = 'methods_no_slice' if args.wo_slice else 'methods'
    output_dir = args.output or args.put_root

    if args.all:
        projects = sorted(glob.glob(os.path.join(args.put_root, 'Csv*_b')))
        logger.info(f"Found {len(projects)} projects to evaluate")
        all_results = []
        for proj_path in projects:
            pname = os.path.basename(proj_path)
            try:
                sm = evaluate_project(
                    pname, args.put_root,
                    method_workspaces_prefix=method_workspaces_prefix)
                all_results.append(sm)
            except Exception as e:
                logger.error(f"Evaluation failed for {pname}: {e}", exc_info=True)

        batch_csv = os.path.join(output_dir, 'HITS_evaluation_summary.csv')
        write_comparison_csv(all_results, batch_csv)

    elif args.project_name:
        evaluate_project(
            args.project_name, args.put_root,
            tests_dir=args.tests_dir,
            method_workspaces_prefix=method_workspaces_prefix,
            output_dir=args.output)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()