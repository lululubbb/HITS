# 项目说明文档：自动化 Java 单元测试生成系统

> 本文档记录项目的目录结构、模块功能、数据流转关系，以及三大核心操作的执行指令。

---

## 一、目录结构总览

```
项目根目录/
├── scripts/                    # 可执行脚本（入口点）
│   ├── create_workspace.py     # 步骤0：初始化工作目录
│   ├── prompt_slice_parallel.py # 步骤1：分片（Slice）生成
│   ├── prompt_init_parallel.py  # 步骤2：初始测试代码生成
│   ├── prompt_fix_parallel.py   # 步骤3：测试运行 & 修复
│   ├── slice_patch.ipynb        # Notebook：解析覆盖缺失行并准备分片修复
│   └── report.ipynb             # Notebook：汇总覆盖率结果
│
├── procedures/                 # 核心业务逻辑
│   ├── get_slices.py           # 生成方法分片信息（SliceInfoGenerator）
│   ├── get_code.py             # 生成初始测试代码（InitialCodeGenerator）
│   ├── fix_code.py             # 运行测试 & 修复失败用例（TestFixer）
│   ├── parse_missing.py        # 解析 JaCoCo 覆盖缺失行
│   ├── report.py               # 分析 JaCoCo 覆盖率报告
│   └── basic_procedure.py      # 基类：模板渲染、token 计数
│
├── generator/                  # LLM 调用层
│   ├── open_generator.py       # 同步/异步调用 OpenAI API（OpenGenerator）
│   ├── api_process_parallel.py # 异步并发批量请求处理
│   └── openlimit/              # 速率限制器（Token Bucket）
│       ├── rate_limiters.py    # ChatRateLimiter / CompletionRateLimiter
│       ├── buckets/            # Bucket / Buckets：令牌桶实现
│       └── utilities/          # 上下文装饰器、token 计数工具
│
├── utils/                      # 工具库
│   ├── config.py               # 读取 config.ini，导出全局配置变量
│   ├── json_db.py              # 轻量 JSON 文件数据库（替代 MongoDB）
│   ├── code_editor.py          # Java 代码 AST 操作（tree-sitter）
│   ├── post_process.py         # 提取/语法检查生成的 Java 代码
│   ├── test_runner.py          # 编译 & 运行测试 & 生成 JaCoCo 报告
│   ├── basic_runner.py         # 基础 Maven 项目工具类
│   ├── load_code_graph.py      # 加载 CDG（控制依赖图）& 查找控制依赖
│   ├── report.py               # 解析 JaCoCo HTML 报告
│   └── slice_runner.py         # 调用切片工具 jar（Java Slicer）
│
├── prompts/                    # Jinja2 提示词模板
│   ├── system_gen.jinja2       # 系统提示：Java 程序员角色
│   ├── system_repair.jinja2    # 系统提示：修复单元测试角色
│   ├── gen_slice.jinja2        # 用户提示：生成分片信息
│   ├── gen_code.jinja2         # 用户提示：生成测试代码（无分片）
│   ├── repair.jinja2           # 用户提示：修复失败测试
│   └── no_mock/ / no_slice/    # 不同模式下的模板变体目录
│
└── config.ini                  # 全局配置（路径、API Key、数据库等）
```

---

## 二、各模块功能说明

### `utils/config.py`
- **功能**：读取项目根目录下的 `config.ini`，将路径、API Key、模型参数等导出为全局变量。
- **关键导出变量**：`playground_dir`（实验工作目录）、`api_keys`、`model_url`、`json_db_root`、`JUNIT_JAR`、`JACOCO_AGENT`、`JACOCO_CLI` 等。

### `utils/json_db.py`
- **功能**：以本地 JSON 文件模拟 MongoDB Collection，无需真实数据库服务。
- **核心类**：`JsonDatabase`（数据库）、`JsonCollection`（集合，每个 `table_name` 对应一个 `.json` 文件）。
- **接口**：`find_one(filter)`、`insert_one(doc)`、`replace_one(filter, doc)`。

### `generator/open_generator.py`
- **功能**：封装对 OpenAI（或兼容接口）的调用。
  - `generate(prompt, system, ...)` → 同步单次调用，返回 `(status_code, [outputs], token_count)`。
  - `generate_async(prompts, metas, save_filepath, ...)` → 异步批量调用，结果写入 jsonl 文件。

### `procedures/get_slices.py`（`SliceInfoGenerator`）
- **输入**：MongoDB/JsonDB 中的 `direction_3` 文档（含焦点方法、类信息、依赖）。
- **处理**：调用 LLM，用 `gen_slice.jinja2` 模板，要求 LLM 将方法分解为多个 slice（步骤），返回 JSON。
- **输出**：将 `add_info`（含 `steps`、`summarization` 等）写入数据库；同时写 `slice_response.txt` 到 `log_dir`。

### `procedures/get_code.py`（`InitialCodeGenerator`）
- **输入**：数据库中的 `direction_3`、`direction_1`、`add_info`、`info` 文档。
- **处理**：根据每个 slice（或整体）渲染提示词，调用 LLM 生成完整 Java 测试类，用 `CodeEditor` 拆分为单个测试方法文件。
- **输出**：在 `log_dir/steps/` 或 `log_dir/slice_fixing/` 下生成 `*.java` 测试文件。

### `procedures/fix_code.py`（`TestFixer`）
- **`init_test()`**：将生成的 `.java` 文件逐一编译 + 运行（通过 `TestRunner`），记录失败的用例到 `fixing/init_test_failed.txt`。
- **`single_unitest_fix()`**：读取错误信息，用 `repair.jinja2` 模板让 LLM 修复，最多迭代 10 次，直到测试通过或达到上限。
- **输出**：在 `fixing/{test_name}/{trial_id}/temp/` 下存放每轮修复的 Java 文件和错误日志。

### `utils/test_runner.py`（`TestRunner`）
- **功能**：封装 `javac` 编译 + `java` 运行 + JaCoCo 报告生成的完整流程。
- **关键方法**：`start_single_test()` → 编译→运行→生成 `jacoco.exec`→生成 HTML 报告。

### `procedures/parse_missing.py`
- **输入**：`full_report/` 下的 JaCoCo HTML 报告 + 数据库中的方法 CDG 信息。
- **处理**：解析红色（未覆盖）和黄色（部分覆盖分支）行，结合控制依赖图找到缺失覆盖的代码块。
- **输出**：`slice_fixing/missing_slices.jsonl`（供 Java Slicer 和后续修复生成使用）。

---

## 三、整体数据流转关系

```
config.ini
    │
    ▼
utils/config.py  ──────────────────────────────────────────────────────┐
    │                                                                   │
    ▼                                                                   │
utils/json_db.py (JsonDatabase)                                         │
    │  存储各方法的元数据 (direction_1/3, add_info, info, raw_data)      │
    │                                                                   │
    ▼                                                                   ▼
[步骤0] create_workspace.py                              utils/test_runner.py
    │  → 创建 playground/{project}/methods/method_x/ 目录               │
    │  → 写入 meta.json (方法名→ID映射)                                  │
    │                                                                   │
    ▼                                                                   │
[步骤1] prompt_slice_parallel.py                                        │
    │  调用 procedures/get_slices.py                                    │
    │  → LLM(gen_slice.jinja2) → 解析 JSON                             │
    │  → 写入 DB: add_info (steps列表)                                  │
    │  → 写入文件: methods/method_x/slice_response.txt                  │
    │                                                                   │
    ▼                                                                   │
[步骤2] prompt_init_parallel.py                                         │
    │  调用 procedures/get_code.py                                      │
    │  → 读取 DB: direction_3 + add_info                               │
    │  → LLM(gen_code.jinja2/gen_patch.jinja2)                         │
    │  → CodeEditor 拆分测试方法                                         │
    │  → 写入文件: methods/method_x/steps/*.java                        │
    │                                                                   │
    ▼                                                                   │
[步骤3a] prompt_fix_parallel.py --init_test                             │
    │  调用 procedures/fix_code.py → TestFixer.init_test()             │
    │  → 对每个 .java: javac编译 + java运行 + JaCoCo覆盖                │
    │  → 写入: fixing/{test_name}/0/temp/ (首轮结果)                    │
    │  → 写入: fixing/init_test_failed.txt                              │
    │                                                                   │
    ▼                                                                   │
[步骤3b] prompt_fix_parallel.py (修复阶段)                               │
    │  调用 procedures/fix_code.py → TestFixer.single_unitest_fix()   │
    │  → 读取 compile_error.txt / runtime_error.txt                    │
    │  → LLM(repair.jinja2) → 重新生成修复代码                          │
    │  → 写入: fixing/{test_name}/{trial_id}/temp/                     │
    │  → 循环至通过或达到10次上限                                         │
    │                                                                   │
    ▼                                                                   │
[步骤4] slice_patch.ipynb                                               │
    │  调用 procedures/parse_missing.py                                 │
    │  → 读取 full_report/ JaCoCo HTML                                  │
    │  → 分析未覆盖行 + CDG 控制依赖                                      │
    │  → 写入: slice_fixing/missing_slices.jsonl                       │
    │  → 写入: slicing_tasks.txt (供 Java Slicer 使用)                  │
    │                                                                   │
    ▼                                                                   │
[步骤5] 运行 Java Slicer (外部工具)                                       │
    │  → 读取 missing_slices.jsonl，计算数据切片                          │
    │  → 写入: slice_fixing/slice_result.jsonl                         │
    │                                                                   │
    ▼                                                                   │
[步骤6] prompt_init_parallel.py --fixing                                │
    │  调用 get_code.py (fixing模式)                                     │
    │  → 读取 slice_fixing/slice_result.jsonl                          │
    │  → LLM(gen_patch.jinja2) → 生成针对缺失覆盖的补丁测试               │
    │  → 写入: slice_fixing/*.java                                      │
    │                                                                   │
    ▼                                                                   │
[步骤7] report.ipynb                                                    │
    │  调用 procedures/report.py                                        │
    │  → 合并所有 jacoco.exec                                           │
    │  → 生成 full_report/ HTML                                         │
    │  → 计算指令覆盖率 & 分支覆盖率                                       │
    └───────────────────────────────────────────────────────────────────┘
```

---

## 四、三大核心功能的执行指令

> **前提**：在项目根目录下执行所有命令，且 `config.ini` 已正确配置。

---

### 功能一：对输入项目进行分片操作

分片操作分两步：

#### 步骤 0：初始化工作区（首次运行必须）

```bash
python scripts/create_workspace.py \
    --project_name <project_name> \
    --put_root <PUT根目录>
```

**说明**：
- `--project_name`：项目名称，如 `batch-processing-gateway`
- `--put_root`：被测项目（PUT）的根目录，如 `/data/projects`
- **调用文件**：`scripts/create_workspace.py` → `utils/json_db.py`、`utils/config.py`
- **输出**：`{playground_dir}/{project_name}/meta.json`（方法名↔ID映射）、为每个方法创建 `methods/method_x/` 目录

#### 步骤 1：生成方法分片

```bash
python scripts/prompt_slice_parallel.py \
    --project_name <project_name>
```

**说明**：
- 并发（8线程）为每个待测方法生成分片信息
- **调用文件链**：`prompt_slice_parallel.py` → `procedures/get_slices.py` → `generator/open_generator.py` → OpenAI API
- **使用模板**：`prompts/no_mock/gen_slice.jinja2`（用户提示）、`prompts/system_gen.jinja2`（系统提示）
- **输入来源**：JsonDB 中每个方法的 `direction_3` 文档（含焦点方法源码、类信息、依赖）
- **输出**：
  - JsonDB 中写入 `add_info`（含 `steps`、`summarization`、`invoked_outside_vars` 等字段）
  - 文件：`{playground_dir}/{project_name}/methods/method_x/slice_response.txt`

---

### 功能二：生成测试用例

#### 步骤 2：生成初始测试代码（基于分片）

```bash
python scripts/prompt_init_parallel.py \
    --project_name <project_name>
```

**说明**：
- 并发（16线程）为每个方法的每个 slice 生成完整 Java 测试类
- **调用文件链**：`prompt_init_parallel.py` → `procedures/get_code.py` → `generator/open_generator.py` → OpenAI API → `utils/code_editor.py`（拆分测试方法）
- **使用模板**：`prompts/no_mock/gen_code.jinja2`
- **输入来源**：JsonDB 中的 `direction_3`、`add_info`、`direction_1`、`info`
- **输出**：`{playground_dir}/{project_name}/methods/method_x/steps/*.java`（每个测试方法单独一个文件）

#### 可选：不使用分片直接生成（no_slice 模式）

```bash
python scripts/prompt_init_parallel.py \
    --project_name <project_name> \
    --wo_slice
```

- 使用 `prompts/no_slice/` 目录下的模板
- 输出到 `methods_no_slice/` 目录

#### 可选：生成针对缺失覆盖的补丁测试（在步骤5之后）

```bash
python scripts/prompt_init_parallel.py \
    --project_name <project_name> \
    --fixing
```

- 读取 `slice_fixing/slice_result.jsonl`（Java Slicer 的输出）
- 使用 `prompts/no_mock/gen_patch.jinja2` 模板生成补丁测试
- 输出到 `methods/method_x/slice_fixing/*.java`

---

### 功能三：计算编译通过率和覆盖率

#### 步骤 3a：运行初始测试（编译 + 执行）

```bash
python scripts/prompt_fix_parallel.py \
    --project_name <project_name> \
    --init_test
```

**说明**：
- 并发（8线程）对每个生成的 `.java` 文件进行编译和运行
- **调用文件链**：`prompt_fix_parallel.py` → `procedures/fix_code.py` → `utils/test_runner.py`（javac + java + JaCoCo）
- **输入**：`methods/method_x/steps/*.java`
- **输出**：
  - `fixing/{test_name}/0/temp/compile_error.txt`（编译失败时）
  - `fixing/{test_name}/0/runtemp/jacoco.exec`（运行成功时）
  - `fixing/init_test_failed.txt`（失败用例列表）

#### 步骤 3b：自动修复失败用例

```bash
python scripts/prompt_fix_parallel.py \
    --project_name <project_name>
```

**说明**：
- 读取 `init_test_failed.txt`，并发（12线程）修复每个失败用例，最多尝试 10 轮
- **调用文件链**：`prompt_fix_parallel.py` → `procedures/fix_code.py` → `generator/open_generator.py` → OpenAI API
- **使用模板**：`prompts/no_mock/repair.jinja2`（用户提示）、`prompts/system_repair.jinja2`（系统提示）
- **输出**：`fixing/{test_name}/{trial_id}/temp/` 下每轮修复结果

#### 步骤 4：汇总覆盖率报告（Jupyter Notebook）

```bash
jupyter notebook scripts/report.ipynb
```

或直接运行：

```bash
jupyter nbconvert --to notebook --execute scripts/report.ipynb
```

**说明**：
- 运行 `procedures/report.py` 中的 `single_method_report()` 合并所有 `jacoco.exec`
- 运行 `single_method_analyse()` 解析 HTML 报告，提取指令覆盖率（inst_cov）和分支覆盖率（bran_cov）
- **调用文件**：`procedures/report.py` → `utils/report.py`（`jacoco_analysis()`）→ BeautifulSoup 解析 HTML
- **输出**：
  - `methods/method_x/full_report/` HTML 覆盖率报告
  - 控制台打印每个方法的 `(inst_cov%, bran_cov%)`

#### 可选：no_slice 模式的 init_test

```bash
python scripts/prompt_fix_parallel.py \
    --project_name <project_name> \
    --init_test \
    --wo_slice
```

#### 可选：fixing 补丁测试的 init_test

```bash
python scripts/prompt_fix_parallel.py \
    --project_name <project_name> \
    --init_test \
    --fixing
```

---

## 五、完整执行流程速查

```
# 1. 初始化工作区
python scripts/create_workspace.py --project_name <proj> --put_root <put_root>

# 2. 生成分片信息（需要 DB 中已有 direction_3 等数据）
python scripts/prompt_slice_parallel.py --project_name <proj>

# 3. 生成初始测试代码
python scripts/prompt_init_parallel.py --project_name <proj>

# 4. 运行测试，记录失败用例
python scripts/prompt_fix_parallel.py --project_name <proj> --init_test

# 5. 自动修复失败用例
python scripts/prompt_fix_parallel.py --project_name <proj>

# 6. （可选）解析覆盖缺失行，准备切片修复
jupyter nbconvert --to notebook --execute scripts/slice_patch.ipynb

# 7. （可选）运行 Java Slicer（外部工具，读取 slicing_tasks.txt）
# java -jar slicer.jar ...（按实际工具命令执行）

# 8. （可选）生成补丁测试
python scripts/prompt_init_parallel.py --project_name <proj> --fixing
python scripts/prompt_fix_parallel.py --project_name <proj> --init_test --fixing

# 9. 汇总覆盖率
jupyter nbconvert --to notebook --execute scripts/report.ipynb
```

---

## 六、关键配置项（config.ini 参考）

| 配置节 | 配置键 | 说明 |
|--------|--------|------|
| DEFAULT | `playground` | 实验工作目录根路径 |
| DEFAULT | `TIMEOUT` | 测试运行超时秒数 |
| DEFAULT | `JUNIT_JAR` | JUnit 5 jar 路径 |
| DEFAULT | `MOCKITO_JAR` | Mockito jar 路径 |
| DEFAULT | `JACOCO_AGENT` | JaCoCo javaagent jar 路径 |
| DEFAULT | `JACOCO_CLI` | JaCoCo CLI jar 路径 |
| openai | `api_keys` | OpenAI API Key（支持列表） |
| openai | `model_url` | API 端点 URL |
| openai | `model` | 模型名称 |
| database | `json_db_root` | JSON 文件数据库根目录 |
| mongo | `mongo_url` | MongoDB URL（已被 JSON DB 替代，仍需填写） |

---

## 七、重要数据格式说明

### JsonDB 中各表的作用

| table_name | 说明 |
|------------|------|
| `raw_data` | 方法原始信息（类名、包名、方法名、参数签名等） |
| `info` | 方法详细信息（CDG图、src_lines行号映射、class_path等） |
| `direction_1` | 方法基本描述（focal_method, class_name, full_fm等） |
| `direction_3` | 完整提示数据（包含依赖类信息 c_deps/m_deps，是 LLM 主要输入） |
| `add_info` | 分片信息（由 `get_slices.py` 写入，含 steps 列表） |

### 文件系统中关键目录结构

```
{playground_dir}/{project_name}/
├── meta.json                         # 方法名↔ID映射
├── slicing_tasks.txt                 # Java Slicer 输入
├── scope_wala.txt                    # WALA 分析范围文件
└── methods/
    └── method_x/
        ├── slice_response.txt        # LLM 分片响应原文
        ├── steps/                    # 初始生成的测试文件
        │   ├── ClassName_0_0_Test.java
        │   └── log_0.txt
        ├── slice_fixing/
        │   ├── missing_slices.jsonl  # 缺失覆盖分析结果
        │   ├── slice_result.jsonl    # Java Slicer 输出
        │   └── *.java                # 补丁测试文件
        ├── fixing/
        │   ├── init_test_failed.txt  # 初次运行失败的用例列表
        │   └── ClassName_0_0_Test/
        │       ├── 0/temp/           # 初始版本
        │       │   ├── ClassName_0_0_Test.java
        │       │   ├── compile_error.txt (若编译失败)
        │       │   └── runtime_error.txt (若运行失败)
        │       └── 1/temp/           # 第1轮修复版本
        └── full_report/              # 汇总 JaCoCo HTML 报告
            └── com.example.pkg/
                └── ClassName.html
```

完整流程指令
阶段一：数据准备与工作区初始化
bashcd /home/chenlu/HITS

# 步骤 0a-0d：解析源码、写入 JsonDB、导出数据集、初始化工作区
python scripts/run_pipeline.py \
    --project_name Csv_1_b \
    --put_root /home/chenlu/HITS/defect4j_projects \
    --steps 0
阶段二：有分片模式（推荐）
bash# 步骤 1：生成方法分片
python scripts/run_pipeline.py \
    --project_name Csv_1_b \
    --put_root /home/chenlu/HITS/defect4j_projects \
    --steps 1

# 步骤 2-3：生成 + 编译运行 + 修复测试
python scripts/run_pipeline.py \
    --project_name Csv_1_b \
    --put_root /home/chenlu/HITS/defect4j_projects \
    --steps 2 3

# 步骤 6：生成覆盖率报告
python scripts/run_pipeline.py \
    --project_name Csv_1_b \
    --put_root /home/chenlu/HITS/defect4j_projects \
    --steps 6
阶段二（备选）：无分片模式
bashpython scripts/run_pipeline.py \
    --project_name Csv_1_b \
    --put_root /home/chenlu/HITS/defect4j_projects \
    --wo_slice \
    --steps 2 3 6
阶段三（可选）：补丁生成（需先完成 Step 4）
bash# Step 4：解析覆盖缺口
python scripts/run_pipeline.py ... --steps 4

# 运行 Java Slicer（外部工具）读取 slicing_tasks.txt
# java -jar slicer.jar ...

# Step 5：生成补丁测试（--fixing 标志）
python scripts/run_pipeline.py \
    --project_name Csv_1_b \
    --put_root /home/chenlu/HITS/defect4j_projects \
    --fixing \
    --steps 5
阶段四：评估（Bug-Revealing + 相似度 + 统计）
bash# 评估单个项目
python scripts/run_evaluation.py \
    --project_name Csv_1_b \
    --put_root /home/chenlu/HITS/defect4j_projects

# 批量评估所有 Csv*_b 项目
python scripts/run_evaluation.py \
    --all \
    --put_root /home/chenlu/HITS/defect4j_projects
评估完成后，统计文件写在 playground/<project>/stats/ 下：llm_calls.csv、llm_summary.csv（LLM token/时间）、test_results.csv、test_summary.csv（编译率/执行率/覆盖率/bug-revealing/冗余度）。