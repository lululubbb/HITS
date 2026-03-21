# JSON 数据库初始化诊断与修复指南

## 问题描述

您遇到的问题是：
```
json_db/Csv_1_b/ 目录为空（无任何方法集合）
→ create_workspace.py 读取不到任何方法
→ method_name_to_idx 和 idx_to_method_name 都为空 {}
→ 后续 Pipeline 步骤无法运行
```

## 根本原因分析

### 缺失的初始化步骤

HITS Pipeline 的完整流程应该是：

```
第0步a：从源代码初始化 JSON 数据库 (NEW - 之前缺失!)
  ├─ 扫描 PUT 项目的 Java 源代码
  ├─ 提取所有 public 方法及其元数据
  └─ 生成 direction_1/3, raw_data, info 文档，写入 JSON DB

第0步b：初始化工作区（基于 JSON DB 中的数据）
  ├─ 读取 JSON DB 中的方法集合列表
  ├─ 创建 playground 目录结构
  └─ 生成 meta.json (方法名↔ID映射)

第1步：生成方法分片
  ├─ 读取每个方法的 direction_3 文档
  └─ 调用 LLM 进行分片处理

... (后续步骤)
```

### 之前为什么没有工作

旧的 `run.py` 直接跳过了第 0 步a，试图从空的 JSON DB 中读取方法：

```python
# run.py (旧版本)
# 缺失: 初始化 JSON 数据库的步骤

python scripts/create_workspace.py  # 直接调用，但数据库为空
  ↓
def main():
    db = JsonDatabase(json_db_root, project_name)
    mut_names = list(db.list_collection_names())  # ← 返回 []
    # ... 后续代码得不到任何方法 ❌
```

## 解决方案

### 1. 新增初始化脚本

已创建 [scripts/init_json_db.py](../../scripts/init_json_db.py)

**功能**：
- 扫描 PUT 项目的所有 Java 源文件
- 使用 `javalang` 库解析 AST
- 提取每个 public 方法的元数据
- 为每个方法创建 JSON 集合
- 写入 `direction_1`, `direction_3`, `raw_data`, `info` 等必要文档

### 2. 更新 run.py

已修改 [run.py](../../run.py) 的第 0 步：

```python
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
```

## 使用方法

### 方式1：使用完整更新的 Pipeline

```bash
cd /home/chenlu/HITS
python run.py --project_name Csv_1_b --put_root /home/chenlu/defects4j_projects
```

现在 run.py 会自动执行：
1. `init_json_db.py` - 初始化数据库 (新增)
2. `create_workspace.py` - 创建工作区
3. `prompt_slice_parallel.py` - 生成分片
4. ... (后续步骤)

### 方式2：单独执行 JSON 数据库初始化

如果您只想初始化数据库而不运行完整 Pipeline：

```bash
python scripts/init_json_db.py \
    --project_name Csv_1_b \
    --put_root /home/chenlu/defects4j_projects
```

**输出示例**：
```
2024-03-22 10:30:45 - INFO - Initialize JSON database for project: Csv_1_b
2024-03-22 10:30:45 - INFO - PUT root: /home/chenlu/defects4j_projects
2024-03-22 10:30:45 - INFO - Found 42 Java files
2024-03-22 10:30:47 - INFO - Processing /home/chenlu/defects4j_projects/Csv_1_b/src/main/java/...
2024-03-22 10:30:50 - INFO - Extracted 15 public methods
2024-03-22 10:30:50 - INFO - Creating collection for: com.example.Csv.parseCSV(String)
...
2024-03-22 10:31:02 - INFO - Successfully initialized JSON database for Csv_1_b
2024-03-22 10:31:02 - INFO - Total methods: 15
```

## 验证初始化成功

执行完成后，检查以下目录：

```bash
# 检查 JSON 数据库是否有数据
ls /home/chenlu/HITS/json_db/Csv_1_b/

# 输出应该类似：
# com.example.Csv.parseCSV(String)
# com.example.Csv.toCSV(List)
# ...（对应每个方法）

# 查看某个方法的集合内容
ls /home/chenlu/HITS/json_db/Csv_1_b/com.example.Csv.parseCSV*

# 输出应该是：
# direction_1.json
# direction_3.json
# raw_data.json
# info.json
```

查看 meta.json 是否有正确的映射：

```bash
cat /home/chenlu/HITS/experiments/playground/Csv_1_b/meta.json | python -m json.tool

# 输出应该包含非空的 method_name_to_idx 和 idx_to_method_name
```

## 常见问题排查

### 问题1：仍然显示 direction_3 is not None 断言失败

**原因**：`init_json_db.py` 没有正确运行

**解决**：
```bash
# 单独运行和调试
python scripts/init_json_db.py \
    --project_name Csv_1_b \
    --put_root /home/chenlu/defects4j_projects

# 检查错误信息
```

### 问题2：提取方法数太少或过多

**原因**：
- 可能只提取了 public 方法
- 可能包含了 lombok 生成的方法
- 可能有注解增强的方法

**调整方案**：编辑 `init_json_db.py` 的 `extract_methods_from_file()` 函数

```python
# 例如：扩展到包括 package-private 方法
if 'public' in method.modifiers or len(method.modifiers) == 0:  # package-private
    # ... 处理方法
```

### 问题3：javalang 解析失败

**错误示例**：
```
Failed to parse /path/to/file.java: Expected token IDENTIFIER, got EOF
```

**原因**：源代码不是标准 Java 语法

**解决**：
1. 检查源代码是否有语法错误
2. 使用 tree-sitter 替代 javalang 进行更容错的解析
3. 提交相关文件的错误日志以调试

## 架构改进说明

### 原始流程的设计缺陷

1. **假设强太高**：假设 JSON DB 已经被外部工具填充（如 MongoDB 中已有数据）
2. **文档不完整**：没有说明如何初始化数据库
3. **步骤顺序错误**：试图从空数据库读取数据

### 修复后的改进

1. ✅ **自包含的 Pipeline**：不依赖外部数据源
2. ✅ **清晰的初始化步骤**：明确说明第 0 步内容
3. ✅ **可验证的输出**：可以检查每个阶段的输出

## 下一步

数据库初始化完成后，继续运行 Pipeline：

```bash
# 完整流程
python run.py --project_name Csv_1_b --put_root /home/chenlu/defects4j_projects

# 或逐步执行
python scripts/prompt_slice_parallel.py --project_name Csv_1_b
python scripts/prompt_init_parallel.py --project_name Csv_1_b
# ... 等等
```

## 参考资源

- [JSON 数据库结构文档](../readme.md#二各模块功能说明)
- [Pipeline 完整指南](../PIPELINE_GUIDE.py)
- [代码库结构说明](../readme.md#一目录结构总览)
