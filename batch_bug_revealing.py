#!/usr/bin/env python3
import os
import glob
import subprocess
import sys

# --- 1. 路径配置 ---
# 这里是你存放 _f 项目的目录
PROJECT_PATHS = [
    "/home/chenlu/HITS/experiments/playground/Csv_3_f",
    "/home/chenlu/HITS/experiments/playground/Csv_5_f",
    "/home/chenlu/HITS/experiments/playground/Csv_7_f",
    "/home/chenlu/HITS/experiments/playground/Csv_8_f"
]

# 核心执行脚本的绝对路径 (即你刚才提供的那个脚本)
RUN_SCRIPT = "/home/chenlu/HITS/scripts/bug_revealing.py"
PYTHON_BIN = sys.executable

def run_batch_direct():
    print(f"🚀 开始批量生成 Bug-revealing CSV (直接路径模式)...")
    print(f"{'='*70}")

    for f_proj in PROJECT_PATHS:
        f_proj = os.path.abspath(f_proj)
        base_name = os.path.basename(f_proj)
        
        # 2. 逻辑推导：从 _f 找到同级目录下的 _b
        parent_dir = os.path.dirname(f_proj)
        # 如果是 Compress_1_f，则推导出 Compress_1_b
        b_proj = os.path.join(parent_dir, base_name.replace('_f', '_b'))
        
        # 检查推导出的 _b 路径是否真的存在
        if not os.path.isdir(b_proj):
            # 如果 playground 里没有，尝试去你之前的库目录找 (可选)
            alt_b_path = os.path.join("/home/chenlu/HITS/defect4j_projects", base_name.replace('_f', '_b'))
            if os.path.isdir(alt_b_path):
                b_proj = alt_b_path
            else:
                print(f"❌ 跳过 {base_name}: 无法在任何位置找到对应的 _b 项目")
                continue

        # 3. 遍历该项目下所有的 tests% 文件夹
        test_variants = sorted(glob.glob(os.path.join(f_proj, "tests%*")))
        
        if not test_variants:
            print(f"❓ 项目 {base_name} 下未发现 tests%* 目录")
            continue

        print(f"\n📂 项目: {base_name}")
        print(f"   Buggy 路径: {b_proj}")

        for tv in test_variants:
            test_dir_name = os.path.basename(tv)
            print(f"  ▶️ 正在处理变体: {test_dir_name} ... ", end="", flush=True)
            
            # 4. 直接调用 bug_revealing.py，传入明确的 --buggy 和 --fixed
            # 注意：根据你提供的脚本，--tests 是可选的，不传会自动找最新的，
            # 但为了准确性，我们这里显式传入具体的 tests% 目录。
            cmd = [
                PYTHON_BIN, RUN_SCRIPT, 
                '--buggy', b_proj, 
                '--fixed', f_proj, 
                '--tests', tv
            ]
            
            try:
                # 执行脚本，捕获输出以防出错时排查
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("✅ 成功")
                else:
                    print(f"❌ 失败 (rc={result.returncode})")
                    # 打印错误原因（比如编译失败等）
                    if result.stderr:
                        print(f"      错误摘要: {result.stderr.strip()[:150]}...")
            except Exception as e:
                print(f"💥 运行崩溃: {e}")

if __name__ == "__main__":
    if not os.path.exists(RUN_SCRIPT):
        print(f"❌ 错误: 找不到脚本 {RUN_SCRIPT}")
        sys.exit(1)
        
    run_batch_direct()
    print(f"\n{'='*70}")
    print("✨ 批量任务执行完毕。")