#!/usr/bin/env python3
"""
scripts/recollect_and_evaluate.py — 重新收集 fixing/ 最终测试用例并评估

从 experiments/playground/ 下各项目的 methods_<timestamp>/method_*/fixing/ 
收集最后一轮修复的测试用例，生成新的 tests%<timestamp> 并进行完整评估。
（编译、运行、覆盖率、是否能发现 Bug、代码相似度），最后输出一份完整报告。
用法：
  # 评估单个项目
  python scripts/recollect_and_evaluate.py --project_name Csv_1_f

  # 批量评估所有项目,遍历 playground/ 下所有子目录里所有的method方法
  python scripts/recollect_and_evaluate.py --all

  steps/ 文件夹里复制的内容是：
  项目下所有方法（method_0, method_1...）在修复阶段（fixing）产生的最后一个、且重命名过的 Java 测试类文件
"""

import argparse
import csv
import glob
import json
import logging
import os
import shutil
import sys
import time
import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.config import playground_dir, json_db_root, JACOCO_CLI, JACOCO_AGENT
from utils.json_db import JsonDatabase
from utils.test_runner import TestRunner
from utils.test_runner_focal_fix import resolve_all_target_classes

# ── 统一日志配置：全部走 stdout，flush=True，避免与 print/stderr 交错 ──────────
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
_handler.stream = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)  # 行缓冲

logging.basicConfig(
    level=logging.INFO,
    handlers=[_handler],
    force=True,   # 覆盖已有的 root logger 配置
)
logger = logging.getLogger("recollect_eval")


def _flush():
    """在关键节点主动 flush，确保顺序输出"""
    sys.stdout.flush()


def _run_subprocess(cmd: list, cwd: str = None, label: str = "") -> subprocess.CompletedProcess:
    """
    统一执行子进程：捕获全部输出，执行完毕后再通过 logger 打印，
    避免子进程直接抢占终端导致日志乱序。
    """
    logger.info(f"[{label}] 启动: {' '.join(str(c) for c in cmd)}")
    _flush()

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    )

    # stdout 有内容时整体打印
    if result.stdout and result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            logger.info(f"[{label}] {line}")

    if result.returncode != 0:
        logger.warning(f"[{label}] 退出码={result.returncode}")
        if result.stderr and result.stderr.strip():
            for line in result.stderr.strip().splitlines()[:20]:   # 最多打 20 行
                logger.warning(f"[{label}|stderr] {line}")
    else:
        logger.info(f"[{label}] 完成 (rc=0)")

    _flush()
    return result


# ─────────────────────────────────────────────────────────────────────────────

def _parse_coverage_xml(
        xml_path: str, target_classes: List[str]) -> Tuple:
    """返回 (lc, lt, bc, bt, class_stats)，其中 class_stats 是 {class_name: (lc, lt, bc, bt)} 的字典"""
    import xml.etree.ElementTree as ET
    none8 = (None,) * 8
    if not os.path.exists(xml_path):
        logger.warning(f"jacoco.xml 不存在: {xml_path}")
        return none8
    try:
        with open(xml_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        start = raw.find("<report")
        if start < 0:
            return none8
        root_elem = ET.fromstring(raw[start:])
    except Exception as e:
        logger.warning(f"解析 {xml_path} 失败: {e}")
        return none8

    lc = lt = bc = bt = 0
    class_stats = {}

    for tc in target_classes:
        class_stats[tc] = [0, 0, 0, 0]

    for c in root_elem.findall("counter"):
        ct  = c.get("type", "")
        cov = int(c.get("covered", 0))
        mis = int(c.get("missed", 0))
        if ct == "LINE":     lc = cov; lt = cov + mis
        elif ct == "BRANCH": bc = cov; bt = cov + mis

    for cls_elem in root_elem.findall(".//class"):
        cname  = cls_elem.get("name", "")
        simple = cname.split("/")[-1].split("$")[0]
        if target_classes and simple in target_classes and '$' not in cname.split('/')[-1]:
            cls_lc = cls_lt = cls_bc = cls_bt = 0
            for c in cls_elem.findall("counter"):
                ct  = c.get("type", "")
                cov = int(c.get("covered", 0))
                mis = int(c.get("missed", 0))
                if ct == "LINE":     cls_lc = cov; cls_lt = cov + mis
                elif ct == "BRANCH": cls_bc = cov; cls_bt = cov + mis
            class_stats[simple] = [cls_lc, cls_lt, cls_bc, cls_bt]

    return (lc or None, lt or None, bc or None, bt or None, class_stats)


def _generate_jacoco_report(put_path: str, merged_exec: str, report_dir: str, xml_out: str):
    """生成 JaCoCo 覆盖率报告"""
    class_dirs = []
    fb = os.path.join(put_path, "target", "classes")
    if os.path.exists(fb):
        class_dirs = [fb]

    src_dirs = []
    pom_path = os.path.join(put_path, "pom.xml")
    if os.path.exists(pom_path):
        for suffix in ["src/main/java", "src/main"]:
            sd = os.path.join(put_path, suffix)
            if os.path.exists(sd):
                src_dirs.append(sd)
                break

    if JACOCO_CLI and os.path.exists(JACOCO_CLI):
        cmd = ["java", "-jar", JACOCO_CLI, "report", merged_exec]
        for d in class_dirs:
            cmd += ["--classfiles", d]
        cmd += ["--html", report_dir, "--xml", xml_out]
        for sd in src_dirs:
            cmd += ["--sourcefiles", sd]
        _run_subprocess(cmd, label="jacoco-report")
        if os.path.exists(xml_out):
            logger.info(f"全局报告已生成 → {report_dir}")
    else:
        logger.warning("JACOCO_CLI 未找到 — 尝试 mvn jacoco:report")
        mvn_cmd = [
            "mvn", "jacoco:report",
            f"-Djacoco.dataFile={os.path.abspath(merged_exec)}",
            "-f", os.path.join(put_path, "pom.xml"),
        ]
        _run_subprocess(mvn_cmd, cwd=put_path, label="mvn-jacoco-report")
        mvn_xml = os.path.join(put_path, "target", "site", "jacoco", "jacoco.xml")
        if os.path.exists(mvn_xml):
            shutil.copy2(mvn_xml, xml_out)


def find_latest_methods_dir(project_path: str) -> str:
    candidates = []
    for d in os.listdir(project_path):
        if d.startswith('methods_') and os.path.isdir(os.path.join(project_path, d)):
            candidates.append(os.path.join(project_path, d))
    if not candidates:
        return None
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def find_all_methods_dirs(project_path: str) -> list:
    candidates = []
    if not os.path.isdir(project_path):
        return []
    for d in os.listdir(project_path):
        full_path = os.path.join(project_path, d)
        if d.startswith('methods_') and os.path.isdir(full_path):
            candidates.append(full_path)
    candidates.sort()
    return candidates


def collect_final_tests_from_fixing(methods_root: str, test_cases_dir: str) -> int:
    copied = 0
    method_dirs = [
        d for d in os.listdir(methods_root)
        if d.startswith('method_') and os.path.isdir(os.path.join(methods_root, d))
    ]

    for method_dir in sorted(method_dirs):
        method_path = os.path.join(methods_root, method_dir)
        fixing_root = os.path.join(method_path, "fixing")
        if not os.path.isdir(fixing_root):
            continue

        for test_class_dir in sorted(os.listdir(fixing_root)):
            test_class_path = os.path.join(fixing_root, test_class_dir)
            if not os.path.isdir(test_class_path):
                continue

            trials = [
                d for d in os.listdir(test_class_path)
                if d.isdigit() and os.path.isdir(os.path.join(test_class_path, d))
            ]
            if not trials:
                continue
            last_trial = max(int(t) for t in trials)
            last_trial_path = os.path.join(test_class_path, str(last_trial), "temp")
            if not os.path.isdir(last_trial_path):
                continue

            java_files = glob.glob(os.path.join(last_trial_path, "*.java"))
            if not java_files:
                continue

            jf = java_files[0]
            base = os.path.basename(jf)
            method_idx = method_dir.replace('method_', '')
            unique_name = f"method_{method_idx}__{base}"
            dst = os.path.join(test_cases_dir, unique_name)
            shutil.copy2(jf, dst)

            old_class = base.replace('.java', '')
            new_class = unique_name.replace('.java', '')
            if old_class != new_class:
                try:
                    with open(dst, 'r', encoding='utf-8') as f:
                        content = f.read()
                    pattern = r'\bclass\s+' + re.escape(old_class) + r'\b'
                    content = re.sub(pattern, f'class {new_class}', content)
                    with open(dst, 'w', encoding='utf-8') as f:
                        f.write(content)
                except Exception as e:
                    logger.warning(f"重命名类名失败 {dst}: {e}")
            copied += 1

    return copied


def run_similarity(tests_dir: str):
    """运行 code_to_ast 和 measure_similarity，输出 mean_of_squares"""
    ast_script = os.path.join(PROJECT_ROOT, 'scripts', 'code_to_ast.py')
    sim_script = os.path.join(PROJECT_ROOT, 'scripts', 'measure_similarity.py')

    for script, label in [(ast_script, 'code_to_ast'), (sim_script, 'measure_similarity')]:
        _run_subprocess([sys.executable, script, tests_dir], cwd=PROJECT_ROOT, label=label)

    sim_dir = os.path.join(tests_dir, 'Similarity')
    if not os.path.isdir(sim_dir):
        logger.error(f"Similarity 输出目录不存在: {sim_dir}")
        return

    big_sum = glob.glob(os.path.join(sim_dir, '*_bigSimssum.csv'))
    mean_sq = None
    if big_sum:
        try:
            with open(big_sum[0], newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    try:
                        mean_sq = float(row.get('mean_of_squares', ''))
                        break
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"读取 mean_of_squares 失败 {big_sum[0]}: {e}")

    if mean_sq is not None:
        logger.info(f"[Similarity] mean_of_squares: {mean_sq}")
    else:
        logger.warning("未在 similarity 输出中找到 mean_of_squares")
    _flush()


def run_evaluation(tests_dir: str, project_name: str, put_path: str):
    """运行完整评估：编译、运行、覆盖率、bug revealing、similarity"""
    test_cases_dir = os.path.join(tests_dir, "test_cases")
    if not os.path.isdir(test_cases_dir):
        logger.error(f"test_cases/ 不存在: {tests_dir}")
        return

    java_files = sorted(glob.glob(os.path.join(test_cases_dir, "*.java")))
    if not java_files:
        logger.error(f"test_cases/ 中无 .java 文件: {test_cases_dir}")
        return

    # 复制到 steps/
    steps_dir = os.path.join(tests_dir, "steps")
    os.makedirs(steps_dir, exist_ok=True)
    for jf in java_files:
        dst = os.path.join(steps_dir, os.path.basename(jf))
        if not os.path.exists(dst):
            shutil.copy2(jf, dst)

    n_total = len([f for f in os.listdir(steps_dir) if f.endswith('.java')])
    logger.info(f"待评估测试文件总数: {n_total}")
    _flush()

    # 各输出目录
    compiled_dir    = os.path.join(tests_dir, "tests_ChatGPT")
    logs_dir        = os.path.join(tests_dir, "logs")
    report_dir      = os.path.join(tests_dir, "report")
    compiler_output = os.path.join(tests_dir, "compiler_output", "CompilerOutput")
    test_output_dir = os.path.join(tests_dir, "test_output", "TestOutput")
    for d in [compiled_dir, logs_dir, report_dir,
              os.path.dirname(compiler_output),
              os.path.dirname(test_output_dir)]:
        os.makedirs(d, exist_ok=True)

    target_classes = resolve_all_target_classes(put_path)
    target_class   = target_classes[0] if target_classes else 'unknown'

    # ── TestRunner ────────────────────────────────────────────────────────────
    runner = TestRunner(tests_dir, put_path, output_path=tests_dir, tool='jacoco', debug=False)
    runner.instrument(compiled_dir, compiled_dir)
    logs = runner._make_logs(logs_dir)

    logger.info("开始执行 TestRunner.run_all_tests() ...")
    _flush()

    total_compile, total_test_run = runner.run_all_tests(
        tests_dir,
        compiled_test_dir=compiled_dir,
        compiler_output=compiler_output,
        test_output=test_output_dir,
        report_dir=report_dir,
        logs=logs,
        focal_method='',
        target_class_override=target_class,
    )

    compile_errors = runner.COMPILE_ERROR
    test_run_errors = runner.TEST_RUN_ERROR
    exec_pass = max(0, total_test_run - test_run_errors)
    exec_fail = test_run_errors

    logger.info(
        f"编译总数={total_compile}  编译错误={compile_errors}  "
        f"运行通过={exec_pass}  运行失败={exec_fail}"
    )
    _flush()

    # ── 合并覆盖率 ─────────────────────────────────────────────────────────────
    global_report_dir = os.path.join(tests_dir, "global_report")
    os.makedirs(global_report_dir, exist_ok=True)
    merged_exec = os.path.join(global_report_dir, "jacoco_merged_global.exec")
    global_xml  = os.path.join(global_report_dir, "jacoco.xml")

    exec_files    = glob.glob(os.path.join(compiled_dir, "jacoco_*.exec"))
    n_exec_merged = len(exec_files)

    if exec_files:
        logger.info(f"合并 {n_exec_merged} 个 .exec 文件 ...")
        _flush()
        with open(merged_exec, 'wb') as outfile:
            for ef in exec_files:
                if os.path.getsize(ef) > 0:
                    with open(ef, 'rb') as infile:
                        outfile.write(infile.read())
        _generate_jacoco_report(put_path, merged_exec, global_report_dir, global_xml)
        logger.info("全局覆盖率报告生成完毕")
        _flush()

    # ── 解析 XML 并输出摘要 ────────────────────────────────────────────────────
    if os.path.exists(global_xml):
        lc, lt, bc, bt, class_stats = _parse_coverage_xml(global_xml, target_classes)

        lr  = round(100.0 * lc / lt, 2) if lt else None
        br  = round(100.0 * bc / bt, 2) if bt else None

        mlc = mlt = mbc = mbt = 0
        for cls_name, (cls_lc, cls_lt, cls_bc, cls_bt) in class_stats.items():
            mlc += cls_lc or 0; mlt += cls_lt or 0
            mbc += cls_bc or 0; mbt += cls_bt or 0
        mlr = round(100.0 * mlc / mlt, 2) if mlt else None
        mbr = round(100.0 * mbc / mbt, 2) if mbt else None

        target_class_str = ",".join(target_classes) if target_classes else "unknown"
        gcov_csv = os.path.join(tests_dir, f"{project_name.replace('.', '')}_global_coverage.csv")
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
                lc, lt, lr, bc, bt, br,
                mlc, mlt, mlr, mbc, mbt, mbr,
                n_exec_merged,
            ])

        # 汇总日志（原来用 print，统一改为 logger.info）
        sep = "=" * 60
        logger.info(sep)
        logger.info(f"COVERAGE STATISTICS (ALL ATTEMPTS): {project_name}")
        logger.info(sep)
        logger.info(f"  Tests compiled   : {total_compile}")
        logger.info(f"  Compile errors   : {compile_errors}")
        logger.info(f"  Exec pass        : {exec_pass}")
        logger.info(f"  Exec fail        : {exec_fail}")
        logger.info(f"  Exec files merged: {n_exec_merged}")
        if lr is not None:
            logger.info(f"  全项目 行覆盖率    : {lr:.2f}% ({lc}/{lt})")
        if br is not None:
            logger.info(f"  全项目 分支覆盖率  : {br:.2f}% ({bc}/{bt})")
        for cls_name in target_classes:
            if cls_name in class_stats:
                cls_lc, cls_lt, cls_bc, cls_bt = class_stats[cls_name]
                cls_lr = round(100.0 * cls_lc / cls_lt, 2) if cls_lt else None
                cls_br = round(100.0 * cls_bc / cls_bt, 2) if cls_bt else None
                logger.info(f"  target_class: {cls_name}")
                if cls_lr is not None:
                    logger.info(f"    行覆盖率  : {cls_lr:.2f}% ({cls_lc}/{cls_lt})")
                if cls_br is not None:
                    logger.info(f"    分支覆盖率: {cls_br:.2f}% ({cls_bc}/{cls_bt})")
        if lr is None and br is None:
            logger.warning("无可用覆盖率数据")
        logger.info(sep)
        _flush()

    # ── Bug Revealing ─────────────────────────────────────────────────────────
    logger.info("开始执行 bug_revealing.py ...")
    _flush()
    buggy_proj = put_path.replace('_f', '_b')
    _run_subprocess(
        [
            sys.executable, os.path.join(PROJECT_ROOT, 'scripts', 'bug_revealing.py'),
            '--buggy', buggy_proj,
            '--fixed', put_path,
            '--tests', tests_dir,
        ],
        label="bug-revealing",
    )

    # ── Similarity ────────────────────────────────────────────────────────────
    logger.info("开始执行 similarity pipeline ...")
    _flush()
    run_similarity(tests_dir)

    logger.info(f"项目 {project_name} 评估全部完成")
    _flush()


def process_project(project_name: str):
    project_path = os.path.join(playground_dir, project_name)
    if not os.path.isdir(project_path):
        logger.error(f"项目 {project_name} 不存在于 {playground_dir}")
        return

    all_methods_roots = find_all_methods_dirs(project_path)
    if not all_methods_roots:
        logger.error(f"{project_name} 下未找到 methods_* 目录")
        return

    for methods_root in all_methods_roots:
        dir_name      = os.path.basename(methods_root)
        folder_suffix = dir_name.replace("methods_", "")

        logger.info(f">>> 评估: {project_name} -> {dir_name}")
        _flush()

        tests_dir      = os.path.join(project_path, f"tests%eval2_{folder_suffix}")
        test_cases_dir = os.path.join(tests_dir, "test_cases")

        if os.path.exists(tests_dir):
            logger.info(f"跳过（已存在）: {tests_dir}")
            continue

        os.makedirs(test_cases_dir, exist_ok=True)

        copied = collect_final_tests_from_fixing(methods_root, test_cases_dir)
        if copied == 0:
            logger.warning(f"未从 {methods_root} 收集到任何测试文件，跳过")
            shutil.rmtree(tests_dir)
            continue

        logger.info(f"已收集 {copied} 个测试文件（来自 {dir_name}）")
        _flush()

        put_path = f"/home/chenlu/HITS/defect4j_projects/{project_name}"
        if not os.path.isdir(put_path):
            logger.error(f"PUT 路径不存在: {put_path}")
            continue

        try:
            run_evaluation(tests_dir, project_name, put_path)
        except Exception as e:
            logger.error(f"评估 {dir_name} 时出错: {e}", exc_info=True)
        _flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project_name', help='单个项目名，如 Csv_1_f')
    parser.add_argument('--all', action='store_true', help='处理所有项目')
    args = parser.parse_args()

    if args.all:
        projects = [
            item for item in os.listdir(playground_dir)
            if os.path.isdir(os.path.join(playground_dir, item)) and not item.startswith('.')
        ]

        def extract_project_num(proj_name):
            match = re.match(r'Csv_(\d+)_f', proj_name)
            return int(match.group(1)) if match else 999

        for item in sorted(projects, key=extract_project_num):
            logger.info(f"\n{'='*10} Project: {item} {'='*10}")
            _flush()
            process_project(item)

    elif args.project_name:
        process_project(args.project_name)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()