#!/usr/bin/env python3
"""
HITS Pipeline Runner
整合整个自动化Java单元测试生成流程的脚本。
从初始化工作区到分片、生成测试、修复、覆盖率计算等。
cd /home/chenlu/HITS
python run.py --project_name Csv_1_b --put_root /home/chenlu/defects4j_projects
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """运行命令并打印描述"""
    print(f"\n=== {description} ===")
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, cwd=Path(__file__).parent)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed with exit code {e.returncode}")
        return False

def main():
    parser = argparse.ArgumentParser(description="HITS Pipeline Runner")
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
    if not Path("scripts/create_workspace.py").exists():
        print("✗ Please run this script from the HITS project root directory.")
        sys.exit(1)

    print("🚀 Starting HITS Pipeline for project:", project_name)
    print("PUT root:", put_root)

    # 步骤0a: 初始化 JSON 数据库（从源代码提取方法元数据）
    if not run_command([
        sys.executable, "scripts/init_json_db.py",
        "--project_name", project_name,
        "--put_root", put_root
    ], "Step 0a: Initialize JSON Database from Source Code"):
        print("⚠ Step 0a failed, but continuing as it may be a detection issue...")

    # 步骤0b: 初始化工作区（基于 JSON 数据库中的方法）
    if not run_command([
        sys.executable, "scripts/create_workspace.py",
        "--project_name", project_name,
        "--put_root", put_root
    ], "Step 0b: Initialize Workspace"):
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

    print("\n🎉 HITS Pipeline completed successfully!")
    print(f"Check results in playground directory for project: {project_name}")

if __name__ == "__main__":
    main()
