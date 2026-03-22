# HITS 项目输出目录结构说明

本文档描述 HITS pipeline 运行过程中产生的所有文件及其含义。
根路径为 `playground/<project_name>/`（由 `config.ini` 中 `playground` 字段配置）。

---

## 顶层结构

```
playground/
└── <project_name>/                      # 例如 Csv_1_b
    ├── meta.json                        # 工作区元数据（方法索引）
    ├── result.json                      # 汇总覆盖率结果（Step 6 产出）
    ├── slicing_tasks.txt                # Java Slicer 任务列表（Step 4 可选产出）
    ├── scope_wala.txt                   # WALA 分析范围文件（Step 4 可选）
    ├── dataset/                         # Step 0c export_data 产出
    ├── methods/                         # 有 slice 模式的工作目录
    ├── methods_no_slice/                # wo_slice 模式的工作目录
    └── stats/                           # 新增：统计输出目录
```

---

## meta.json

```json
{
  "project_name": "Csv_1_b",
  "put_path": "/abs/path/to/Csv_1_b",
  "method_name_to_idx": { "method_read__": "method_0", ... },
  "idx_to_method_name": { "method_0": "method_read__", ... }
}
```

---

## dataset/（Step 0c）

```
dataset/
├── direction_1/
│   └── <id>%<proj>%<class>%<method>%d1.json    # imports + class sig + focal method
├── direction_3/
│   └── <id>%<proj>%<class>%<method>%d3.json    # full context + deps
└── raw_data/
    └── <id>%<proj>%<class>%<method>%raw.json   # 方法元数据（签名/包名/参数等）
```

---

## methods/ 或 methods_no_slice/（主工作目录）

每个 focal method 对应一个子目录 `method_<N>/`。

```
methods/
└── method_<N>/
    ├── slice_response.txt               # Step 1: LLM 分片响应原文
    ├── log_<stepId>.txt                 # Step 2: 每步 generate_code 日志
    │
    ├── steps/                           # Step 2: 生成的原始测试文件
    │   ├── <Class>_<stepId>_<idx>_Test.java        # 单个测试类文件
    │   ├── <Class>_<stepId>_<idx>_Test.prompt.txt  # 对应的 prompt
    │   ├── <Class>_<stepId>_<idx>_Test.condition.txt  # 对应 slice 描述
    │   └── <Class>_<stepId>.response.txt            # LLM 完整响应
    │
    ├── fixing/                          # Step 3 产出
    │   ├── init_test_failed.txt         # 初始运行失败的用例名单
    │   └── <TestClassName>/             # 每个测试类的修复工作目录
    │       ├── 0/                       # 第 0 轮（初始版本）
    │       │   ├── temp/
    │       │   │   ├── <TestClass>.java         # 测试源文件
    │       │   │   ├── compile_error.txt        # 编译错误（若有）
    │       │   │   └── runtime_error.txt        # 运行时错误（若有）
    │       │   └── runtemp/
    │       │       └── jacoco.exec              # JaCoCo 覆盖数据
    │       ├── 1/                       # 第 1 轮修复
    │       │   ├── temp/
    │       │   │   ├── <TestClass>.java
    │       │   │   ├── generate_prompt.txt      # 修复 prompt
    │       │   │   ├── system_prompt.txt        # system prompt
    │       │   │   └── response.txt             # LLM 修复响应
    │       │   └── runtemp/
    │       │       └── jacoco.exec
    │       └── ... (最多 MAX_REPAIR_TRIALS 轮)
    │
    ├── full_report/                     # Step 6: 汇总 JaCoCo HTML 报告
    │   ├── index.html
    │   ├── jacoco-sessions.html
    │   └── <package>/
    │       └── <ClassName>.html         # 每个类的行级覆盖报告
    │
    └── slice_fixing/                    # Step 4/5: 缺失覆盖修复（可选）
        ├── missing_slices.jsonl         # 缺失行切片任务
        ├── slice_result.jsonl           # Java Slicer 产出的 slice 信息
        ├── <Class>_Fix<idx>_<n>_Test.java   # 补丁测试文件
        └── log_Fix<idx>.txt
```

### fixing/<TestClassName>/<trial>/temp/ 文件说明

| 文件 | 说明 |
|------|------|
| `<TestClass>.java` | 本轮的测试源文件 |
| `compile_error.txt` | 编译失败的 javac 输出 |
| `runtime_error.txt` | 运行失败的 JUnit 输出 |
| `run_check_fail.txt` | 覆盖率为 0% 时的标记文件 |
| `generate_prompt.txt` | 修复阶段发给 LLM 的 prompt（trial ≥ 1） |
| `system_prompt.txt` | 修复阶段的 system prompt |
| `response.txt` | LLM 修复响应原文 |

### fixing/<TestClassName>/<trial>/runtemp/ 文件说明

| 文件 | 说明 |
|------|------|
| `jacoco.exec` | JaCoCo 执行数据（二进制） |
| `classpath.txt` | 编译/运行时 classpath 文件 |
| `*.class` | 编译后的 .class 文件 |

---

## tests%<timestamp>/（bug_revealing 和相似度评估的临时目录）

由 `TestRunner.start_all_test()` 在项目根目录下创建，也可以是手动提供的
测试集目录（传入 `bug_revealing.py`/`run_ast_similarity_pipeline.py`）。

```
<project_root>/
└── tests%<timestamp>/                   # 例如 tests%20240318143022
    ├── test_cases/                      # 拷贝进来的 *Test.java 文件
    │   └── <TestClass>.java
    ├── tests_ChatGPT/                   # 编译后的 .class 文件
    │   ├── classpath.txt
    │   └── *.class
    ├── compiler_output/
    │   └── CompilerOutput-<file>.txt    # 编译错误日志
    ├── test_output/
    │   └── TestOutput-<file>.txt        # 运行错误日志
    ├── report/                          # JaCoCo HTML 报告
    │   └── ...
    ├── logs/                            # 新增：详细日志
    │   ├── syntax.log
    │   ├── compile.log
    │   ├── test_exec.log
    │   ├── coverage.log
    │   ├── execution_stats.log
    │   ├── compile_failed.txt
    │   └── diagnosis.log
    ├── AST/                             # code_to_ast.py 产出
    │   ├── <proj_short>_AST.csv         # test_case,test_ast
    │   ├── <proj_short>_per_version_time.csv
    │   └── <proj_short>_per_test_time.csv
    ├── Similarity/                      # measure_similarity.py 产出
    │   ├── <proj>_Sims.csv              # 所有对的 topdown/bottomup/combined 相似度
    │   ├── <proj>_<Class>_bigSims.csv   # 每个测试的最大相似度（冗余度）
    │   └── <proj>_<Class>_bigSimssum.csv  # 汇总统计（n_tests, sum/mean of squares）
    │
    ├── <proj>_<Class>_bugrevealing.csv          # bug_revealing.py 产出（方法级）
    ├── <proj>_<Class>_bugrevealing_class_level.csv  # 类级汇总
    ├── <proj>_<Class>_bugrevealing.details.txt      # 详细运行日志
    │
    ├── <proj>_<Class>_coverage.csv              # TestRunner 汇总覆盖统计
    ├── <proj>_<Class>_coveragedetail.csv        # 每个测试类的覆盖明细
    ├── <proj>_<Class>_coveragemethod.csv        # focal method 覆盖率（按组）
    ├── <proj>_<Class>_status.csv                # 每测试的 compile/exec 状态
    ├── <proj>_<Class>_final_scores.csv          # per-test 综合评分
    └── <proj>_<Class>_final_scores2.csv         # per-focal-method 组聚合评分
```

---

## stats/（新增，pipeline.py + stats.py 产出）

```
playground/<project_name>/stats/
├── llm_calls.csv        # 每次 LLM 调用记录（time, tokens, stage, method）
├── llm_summary.csv      # 按 stage 汇总
├── test_results.csv     # 每个测试类的 compile/exec/cov/br/sim
└── test_summary.csv     # 项目级汇总（pass rate, avg cov, br rate, avg sim）
```

### llm_calls.csv 字段

| 字段 | 说明 |
|------|------|
| timestamp | ISO 时间戳 |
| project | 项目名 |
| stage | slice / gen / fix / patch |
| method | focal method 标识 |
| prompt_tokens | 输入 token 数 |
| completion_tokens | 输出 token 数 |
| total_tokens | 合计 |
| elapsed_sec | 耗时（秒） |
| model | 模型名称 |
| success | True/False |

### test_results.csv 字段

| 字段 | 说明 |
|------|------|
| project | 项目名 |
| method | focal method |
| test_class | 测试类全名 |
| compile_status | pass / fail |
| exec_status | pass / fail / timeout |
| line_cov | 行覆盖率 % |
| branch_cov | 分支覆盖率 % |
| bug_revealing | True / False |
| similarity | combined_similarity (0~1) |
| redundancy | 1 - similarity |

---

## class_info/（parse_data 的输入，task.py 的输出）

```
class_info/
└── <project_name>/
    └── <ClassName>.java.json    # 类的元数据 JSON（方法签名、字段、依赖等）
```

---

## json_db/（JsonDB 存储）

```
json_db/
└── <project_name>/
    ├── method_<name>__<params>/
    │   └── method.json          # 方法 collection（table_name=method）
    │   └── raw_data.json        # 原始数据（table_name=raw_data）
    │   └── direction_3.json     # 方向3数据（table_name=direction_3）
    │   └── info.json            # CFG/CDG 信息（table_name=info）
    │   └── add_info.json        # LLM 分片结果（table_name=add_info）
    └── class_<ClassName>/
        └── class.json           # 类 collection（table_name=class）
```

---

## 文件生命周期总结

| 阶段 | 产出目录/文件 | 是否必要 |
|------|------------|---------|
| Step 0a (parse) | `class_info/<proj>/` | 必要 |
| Step 0b (insert DB) | `json_db/<proj>/` | 必要 |
| Step 0c (export) | `playground/<proj>/dataset/` | 必要 |
| Step 0d (workspace) | `playground/<proj>/meta.json`, `methods/method_N/` | 必要 |
| Step 1 (slice) | `methods/method_N/slice_response.txt`, `add_info.json` | slice 模式必要 |
| Step 2 (gen test) | `methods/method_N/steps/*.java` | 必要 |
| Step 3a (run) | `methods/method_N/fixing/<TestClass>/0/` | 必要 |
| Step 3b (fix) | `methods/method_N/fixing/<TestClass>/1..N/` | 必要 |
| Step 4 (missing) | `methods/method_N/slice_fixing/missing_slices.jsonl` | 可选 |
| Step 5 (patch) | `methods/method_N/slice_fixing/*.java` | 可选 |
| Step 6 (report) | `methods/method_N/full_report/`, `result.json` | 必要 |
| bug_revealing | `tests%*/`下多个 CSV | 评估用 |
| similarity | `tests%*/AST/`, `tests%*/Similarity/` | 评估用 |
| stats (新增) | `playground/<proj>/stats/*.csv` | 推荐 |

一、配置参数详解
1. TEST_CASES_PER_SLICE = 2
含义：在有分片模式下，每个 slice 提示词生成的测试用例上限。

工作流程（参考 get_code.py:44-97）：

```python
if fix_num < 0:  # 有slice模式（fix_num = -1，默认值）  for i in range(len(addon_info['steps'])):  # 遍历每个slice    generate_code()  # 调用LLM，保留最多2个测试用例
```
举例：
假设方法被分成 3 个 slice
每个 slice 调用 1 次 LLM 生成，最多保留 2 个测试用例
最多可生成：3 × 2 = 6 个测试用例

2. WO_SLICE_TEST_COUNT = 2
含义：在无分片模式下，每个 focal method 生成的测试用例总数上限。

工作流程（参考 get_code.py:161-176）：
```python
else:  # wo_slice模式（fix_num > 0）  _target = WO_SLICE_TEST_COUNT  # 目标：2个  while len(unit_tests) < _target:    unit_tests += generate_code()  # 循环生成，直到达到目标数量
```
举例：
循环多次调用 LLM，直到生成 2 个有效的测试用例
每轮可能生成多个，但总数不超过 2 个

3. MAX_REPAIR_TRIALS = 2
含义：单个失败测试用例的最大修复轮数。
测试版本演变：
trial 0：初始生成版本
trial 1：第1次修复后的版本
trial 2：第2次修复后的版本
含义：1 次初始生成 + 2 次修复 = 共 3 次迭代

4. TEST_NUMBER = 2
含义：在相似度评估时，每个方法参与对比的测试用例数量。
这用于后续的模型评估阶段（如 test_runner.py 中的 run_all_tests 循环），用来验证生成的测试代码质量。

wo_slice = without slice（无分片模式）
有 slice 模式 vs wo_slice 模式
维度	有 slice 模式	wo_slice 模式
第1步	LLM 将方法分解为多个 slice（步骤）	跳过分片，直接生成
第2步	对每个 slice 生成 1 个测试	循环生成，直到达到目标数
目录	methods/	methods_no_slice/
使用场景	方法较复杂，需要逐步覆盖	方法较简单，直接全覆盖
配置参数	TEST_CASES_PER_SLICE	WO_SLICE_TEST_COUNT

根据您的需求：针对一个 focal method 最多生成 2 个测试用例，每个测试用例生成 + 修复一共三次

推荐配置：
# 如果使用 wo_slice 模式
WO_SLICE_TEST_COUNT = 2          # ✓ 生成2个测试用例
TEST_CASES_PER_SLICE = 2         # 保持不变（用不到）
MAX_REPAIR_TRIALS = 2            # ✓ 意味着：1次生成 + 2次修复 = 3次总迭代
TEST_NUMBER = 2                  # 保持不变
# 如果使用有 slice 模式
TEST_CASES_PER_SLICE = 2         # ✓ 每个 slice 最多保留
MAX_REPAIR_TRIALS = 2            # ✓ 意味着：1次生成 + 2次修复 = 3次总迭代
TEST_NUMBER = 2                  # 保持不变