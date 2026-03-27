"""
procedures/report.py — 修复版
    - exec 文件存在且非空（>0 bytes）就收集
    - compile_error.txt 存在时跳过（没有编译就没有覆盖率）
    - runtime_error.txt 存在时仍收集（运行出错可能已经部分执行了代码）
    - 优先取最后一个通过（无 error）的 trial；若都有 error，取最后一个有 exec 的 trial
"""

import logging
import os.path
import re
import subprocess
import traceback
from typing import Optional, Dict

try:
    from pymongo.collection import Collection
except ImportError:
    Collection = object

import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)
from utils import test_runner
from utils.report import jacoco_analysis


def single_method_report(method_experiment_root, collection: Collection, put_path, jacoco_cli_path,
                         build_dir="target/classes", src_dir="src/main/java"):
    assert os.path.exists(jacoco_cli_path)
    assert os.path.exists(method_experiment_root)
    fixing_root = os.path.join(method_experiment_root, "fixing")
    if not os.path.exists(fixing_root):
        logging.warning(f"[REPORT] fixing/ not found: {fixing_root}")
        return None

    output_root = os.path.join(method_experiment_root, 'full_report')
    os.makedirs(output_root, exist_ok=True)

    slices = [os.path.join(fixing_root, d)
              for d in os.listdir(fixing_root)
              if os.path.isdir(os.path.join(fixing_root, d))]

    # ── 修复：放宽 exec 收集条件 ─────────────────────────────────────────────
    exec_paths = []
    for _slice in slices:
        trials = sorted(
            [d for d in os.listdir(_slice) if re.match(r"\d+", d)],
            reverse=True)
        # 优先找通过的 trial（无 error 文件）
        found = False
        for trial in trials:
            exec_path = os.path.join(_slice, trial, "runtemp", "jacoco.exec")
            if not os.path.exists(exec_path):
                exec_path = os.path.join(_slice, trial, "cov_check_dir", "jacoco.exec")
            compile_error = os.path.join(_slice, trial, "temp", "compile_error.txt")
            runtime_error = os.path.join(_slice, trial, "temp", "runtime_error.txt")

            # 跳过编译失败（没有 .class 就没有覆盖率）
            if os.path.exists(compile_error):
                continue

            if os.path.exists(exec_path) and os.path.getsize(exec_path) > 0:
                exec_paths.append(exec_path)
                found = True
                break

        # 回退：如果没有通过的，找任意有 exec 且无编译错误的 trial
        if not found:
            for trial in trials:
                exec_path = os.path.join(_slice, trial, "runtemp", "jacoco.exec")
                if not os.path.exists(exec_path):
                    exec_path = os.path.join(_slice, trial, "cov_check_dir", "jacoco.exec")
                compile_error = os.path.join(_slice, trial, "temp", "compile_error.txt")
                if os.path.exists(compile_error):
                    continue
                if os.path.exists(exec_path) and os.path.getsize(exec_path) > 0:
                    exec_paths.append(exec_path)
                    break

    if len(exec_paths) == 0:
        logging.warning(f"[REPORT] No valid exec files found in {method_experiment_root}")
        return None

    logging.info(f"[REPORT] Collected {len(exec_paths)} exec files")

    # get target class paths
    module_poms = test_runner.parse_root_pom(put_path)
    target_class_paths = [
        os.path.join(os.path.dirname(pom), build_dir)
        for pom in module_poms
        if os.path.exists(os.path.join(os.path.dirname(pom), build_dir))
    ]
    if not target_class_paths:
        logging.error("[REPORT] No target class dirs found!")
        return None

    # source root
    info = collection.find_one({"table_name": "info"})
    target_src_root = None
    if info:
        class_path = os.path.join(os.path.abspath(put_path), info.get('class_path', ''))
        for pom_path in module_poms:
            module_src_root = os.path.join(os.path.abspath(os.path.dirname(pom_path)), src_dir)
            if class_path.startswith(module_src_root):
                target_src_root = module_src_root
                break

    report_order = ["java", "-jar", jacoco_cli_path, "report"] + exec_paths
    for path in target_class_paths:
        report_order += ['--classfiles', path]
    report_order += ['--html', output_root, '--xml', os.path.join(output_root, 'jacoco.xml')]
    if target_src_root is not None:
        report_order += ['--sourcefiles', target_src_root]

    report = subprocess.run(report_order, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr_out = report.stderr.decode().strip()
    if stderr_out:
        logging.warning(f"[REPORT] jacoco stderr: {stderr_out[:200]}")
    success = (report.returncode == 0)
    if success:
        logging.info(f"[REPORT] Report generated: {output_root}")
    return success


def single_method_analyse(log_dir, collection: Collection) -> Optional[Dict]:
    if not os.path.exists(log_dir):
        return None
    full_report_dir = os.path.join(log_dir, "full_report")
    if not os.path.exists(full_report_dir) or not os.listdir(full_report_dir):
        return None

    raw_info = collection.find_one({"table_name": "raw_data"})
    if raw_info is None:
        return None

    signature  = raw_info['parameters']
    package    = raw_info['package'].replace("package ", "").replace(";", "")
    class_name = raw_info['class_name']

    try:
        coverage_result = jacoco_analysis(full_report_dir, package, class_name, signature)
    except FileNotFoundError:
        coverage_result = None
    except Exception:
        coverage_result = None

    key = ".".join([package, class_name, signature])
    if coverage_result is None:
        return {key: {'inst_cov': '0%', 'bran_cov': '0%'}}
    return {key: coverage_result}