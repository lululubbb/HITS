#!/usr/bin/env python3
"""
HITS Pipeline with Data Parsing Integration
整合数据解析、数据库初始化和测试生成流程。

cd /home/chenlu/HITS
python scripts/data_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_command(cmd, description):
    """运行命令并打印描述"""
    print(f"\n=== {description} ===")
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed with exit code {e.returncode}")
        return False

def main():
    parser = argparse.ArgumentParser(description="HITS Data Pipeline with Parsing")
    parser.add_argument("--project_name", required=True, help="项目名称，如 Csv_1_b")
    parser.add_argument("--put_root", required=True, help="PUT根目录，如 /home/chenlu/defects4j_projects")
    args = parser.parse_args()

    project_name = args.project_name
    put_root = args.put_root

    # 检查config.ini是否存在
    config_path = Path("config.ini")
    if not config_path.exists():
        print("✗ config.ini not found. Please ensure config.ini is in the project root.")
        sys.exit(1)

    # 检查是否在项目根目录
    if not Path("scripts/data_pipeline.py").exists():
        print("✗ Please run this script from the HITS project root directory.")
        sys.exit(1)

    print("🚀 Starting HITS Data Pipeline for project:", project_name)
    print("PUT root:", put_root)

    # 步骤0a: 解析项目源代码，提取类和方法信息
    if not run_command([
        sys.executable, "scripts/task.py", "parse", put_root
    ], "Step 0a: Parse Project Source Code"):
        print("⚠ Step 0a failed, but continuing...")

    # 步骤0b: 将解析结果插入JsonDB
    class_info_dir = os.path.join(PROJECT_ROOT, "class_info", project_name)
    if os.path.exists(class_info_dir):
        if not run_command([
            sys.executable, "-c",
            f"from scripts.parse_data import parse_data; parse_data('{class_info_dir}', '{project_name}')"
        ], "Step 0b: Insert Parsed Data into JsonDB"):
            print("⚠ Step 0b failed, but continuing...")
    else:
        print(f"⚠ Class info directory not found: {class_info_dir}, skipping Step 0b")

    # 步骤0c: 从JsonDB导出d1、d3、raw数据
    if not run_command([
        sys.executable, "scripts/export_data.py", project_name
    ], "Step 0c: Export Data from JsonDB"):
        print("⚠ Step 0c failed, but continuing...")

    # 步骤0d: 初始化工作区（基于导出的数据）
    if not run_command([
        sys.executable, "scripts/create_workspace.py",
        "--project_name", project_name,
        "--put_root", put_root
    ], "Step 0d: Initialize Workspace"):
        sys.exit(1)

    # 步骤1: 生成方法分片
    if not run_command([
        sys.executable, "scripts/prompt_slice_parallel.py",
        "--project_name", project_name
    ], "Step 1: Generate Method Slices"):
        sys.exit(1)

    # 步骤2: 生成初始测试代码
    if not run_command([
        sys.executable, "scripts/prompt_init_parallel.py",
        "--project_name", project_name
    ], "Step 2: Generate Initial Test Code"):
        sys.exit(1)

    # 步骤3a: 运行初始测试（编译 + 执行）
    if not run_command([
        sys.executable, "scripts/prompt_fix_parallel.py",
        "--project_name", project_name,
        "--init_test"
    ], "Step 3a: Run Initial Tests"):
        sys.exit(1)

    # 步骤3b: 自动修复失败用例
    if not run_command([
        sys.executable, "scripts/prompt_fix_parallel.py",
        "--project_name", project_name
    ], "Step 3b: Fix Failed Test Cases"):
        sys.exit(1)

    # 步骤4: 解析覆盖缺失行，准备切片修复（可选，但包含在流程中）
    if not run_command([
        sys.executable, "scripts/slice_patch.py",
        "--project_name", project_name,
        "--all"
    ], "Step 4: Parse Missing Coverage (Optional)"):
        print("⚠ Step 4: Parse Missing Coverage failed, continuing...")

    # 步骤5: 生成补丁测试（如果有slice_fixing数据）
    print("\n=== Step 5: Generate Patch Tests (Optional) ===")
    # 检查是否有slice_fixing数据
    playground_dir = None
    try:
        from utils.config import playground_dir as pg_dir
        playground_dir = pg_dir
    except ImportError:
        print("Could not import playground_dir from config, skipping patch generation check")

    if playground_dir:
        slice_result_path = Path(playground_dir) / project_name / "methods" / "method_0" / "slice_fixing" / "slice_result.jsonl"
        if slice_result_path.exists():
            if not run_command([
                sys.executable, "scripts/prompt_init_parallel.py",
                "--project_name", project_name,
                "--fixing"
            ], "Step 5: Generate Patch Tests"):
                print("⚠ Patch test generation failed, continuing...")
            else:
                # 运行补丁测试
                if not run_command([
                    sys.executable, "scripts/prompt_fix_parallel.py",
                    "--project_name", project_name,
                    "--init_test", "--fixing"
                ], "Step 5b: Run Patch Tests"):
                    print("⚠ Patch test running failed, continuing...")
        else:
            print("No slice_result.jsonl found, skipping patch generation")

    # 步骤6: 汇总覆盖率报告
    if not run_command([
        sys.executable, "scripts/report.py",
        "--project_name", project_name
    ], "Step 6: Generate Coverage Report"):
        sys.exit(1)

    print("\n🎉 HITS Data Pipeline completed successfully!")
    print(f"Check results in playground directory for project: {project_name}")

if __name__ == "__main__":
    main()