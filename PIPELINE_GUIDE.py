#!/usr/bin/env python3
"""
HITS Pipeline 完整使用指南
"""

import os

GUIDE = """
==============================================
HITS 自动化 Java 单元测试生成 Pipeline
完整使用指南（已移除所有交互步骤）
==============================================

📌 需要手动配置的部分：

1. 修改 config.ini 文件中的路径配置：
   
   [DEFAULT]
   playground = /home/chenlu/HITS/experiments/playground
   
   这样可以确保所有输出都在 HITS 项目根目录下。
   本来的配置可能是：
   playground = /home/chenlu/experiments/playground

2. 确保 config.ini 中的其他关键配置正确：
   - JUNIT_JAR: JUnit JAR 文件路径
   - JACOCO_AGENT: JaCoCo javaagent JAR 路径
   - JACOCO_CLI: JaCoCo CLI JAR 路径
   - json_db_root: JSON 数据库存储位置
   - api_keys: OpenAI API 密钥
   - model_url: API 端点地址


🚀 运行完整 Pipeline：

cd /home/chenlu/HITS
python run.py --project_name Csv_1_b --put_root /home/chenlu/defects4j_projects


📊 各个步骤说明：

✓ Step 0: 初始化工作区
   - 创建 playground/Csv_1_b/methods/ 目录
   - 生成 meta.json（方法名↔ID映射）
   - 输入：project_name, put_root

✓ Step 1: 生成方法分片
   - 调用 LLM 分解方法为多个步骤（slice）
   - 输出：methods/method_*/slice_response.txt

✓ Step 2: 生成初始测试代码
   - 基于分片为每个步骤生成测试用例
   - 输出：methods/method_*/steps/*.java

✓ Step 3a: 运行初始测试
   - 编译并执行所有测试用例
   - 收集代码覆盖率（JaCoCo）
   - 记录失败用例：fixing/init_test_failed.txt

✓ Step 3b: 自动修复失败用例
   - 调用 LLM 分析失败原因并修复
   - 最多迭代 10 次直到通过
   - 输出：fixing/{test_name}/{trial_id}/*.java

✓ Step 4: 解析覆盖缺失行（可选）
   - 分析未覆盖的代码行
   - 生成切片修复数据
   - 输出：slice_fixing/missing_slices.jsonl

✓ Step 5: 生成补丁测试（可选）
   - 针对缺失覆盖生成补充测试
   - 输出：slice_fixing/*.java

✓ Step 6: 汇总覆盖率报告
   - 合并所有 JaCoCo 覆盖率数据
   - 生成 HTML 覆盖率报告
   - 输出：full_report/ 和 result.json


📁 输出目录结构：

playground/Csv_1_b/
├── meta.json                      # 方法映射表
├── result.json                    # 最终覆盖率结果
├── slicing_tasks.txt             # 切片任务列表
└── methods/
    ├── method_0/
    │   ├── slice_response.txt     # LLM 分片响应
    │   ├── steps/                 # 初始测试用例
    │   ├── fixing/                # 修复过程
    │   ├── slice_fixing/          # 补丁测试
    │   └── full_report/           # JaCoCo HTML 报告


💡 仅运行单个步骤：

# 仅生成分片
python scripts/prompt_slice_parallel.py --project_name Csv_1_b

# 仅生成测试代码（不修复）
python scripts/prompt_init_parallel.py --project_name Csv_1_b

# 仅运行初始测试
python scripts/prompt_fix_parallel.py --project_name Csv_1_b --init_test

# 仅修复失败用例
python scripts/prompt_fix_parallel.py --project_name Csv_1_b

# 仅生成覆盖率报告
python scripts/report.py --project_name Csv_1_b

# 仅处理缺失覆盖
python scripts/slice_patch.py --project_name Csv_1_b --all


🔧 需要手动交互的已移除：

原来需要按 'y' 确认的提示已全部移除：
- prompt_init_parallel.py 中的 "Confirm to continue?"
- prompt_fix_parallel.py 中的 "Continue? (y to continue)"

现在这两个脚本会自动继续执行，无需等待用户确认。


⚙️ 高级选项：

# 不使用分片（直接全类）
python scripts/prompt_init_parallel.py --project_name Csv_1_b --wo_slice

# 生成补丁测试（需要先运行 Step 4）
python scripts/prompt_init_parallel.py --project_name Csv_1_b --fixing

# 修复补丁测试
python scripts/prompt_fix_parallel.py --project_name Csv_1_b --init_test --fixing


❓ 常见问题：

Q: 如何指定输出目录？
A: 修改 config.ini 的 playground 参数

Q: 如何更改并发数？
A: 在各脚本中修改 ThreadPoolExecutor 的 max_workers 参数

Q: 如何仅测试某个方法？
A: 修改各脚本中的 method_name_to_idx 循环

Q: 报告中没有数据？
A: 确保 full_report 目录中有 HTML 文件，且测试有通过


📞 问题排查：

1. 检查 config.ini 中的所有路径是否正确
2. 查看 playground/Csv_1_b/ 目录是否存在
3. 检查 meta.json 中方法列表是否为空
4. 查看各步骤的错误日志（通常在控制台输出）


==============================================
"""

if __name__ == "__main__":
    print(GUIDE)
    
    # 可选：写入文件
    with open(os.path.join(os.path.dirname(__file__), "PIPELINE_GUIDE.md"), "w", encoding="utf-8") as f:
        f.write(GUIDE)
    print(f"\n✓ 指南已保存为: {os.path.join(os.path.dirname(__file__), 'PIPELINE_GUIDE.md')}")
