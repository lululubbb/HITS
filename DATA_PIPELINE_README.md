# HITS 数据解析 Pipeline 使用指南

## 概述

这个新的 Pipeline 整合了从源代码解析到测试生成的完整流程，解决了原始 Pipeline 中缺失的数据库初始化步骤。

## 主要改进

### 1. 完整的数据库初始化流程

**原始问题**：
- `json_db/Csv_1_b/` 目录为空
- `create_workspace.py` 无法读取到任何方法
- 后续步骤全部失败

**解决方案**：
- ✅ **步骤0a**: 使用 `class_parser.py` 解析 Java 源代码，提取类和方法元数据
- ✅ **步骤0b**: 使用 `parse_data.py` 将解析结果插入 JsonDB
- ✅ **步骤0c**: 使用 `export_data.py` 从 JsonDB 导出 d1、d3、raw 数据
- ✅ **步骤0d**: 初始化工作区（现在有数据可用）

### 2. 适配的组件

| 组件 | 原始版本 | 适配后 |
|------|----------|--------|
| `class_parser.py` | 使用 tree-sitter | ✅ 适配当前项目配置 |
| `parse_data.py` | MySQL 数据库 | ✅ 适配 JsonDB |
| `export_data.py` | MySQL 查询 | ✅ 适配 JsonDB 查询 |
| `task.py` | 外部配置 | ✅ 适配当前项目结构 |

## 使用方法

### 完整 Pipeline（推荐）

```bash
cd /home/chenlu/HITS
python scripts/data_pipeline.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects
```

这个命令会自动执行所有步骤：
1. 解析源代码 → 提取类和方法
2. 插入 JsonDB → 存储元数据
3. 导出数据 → 生成 d1/d3/raw 文件
4. 初始化工作区 → 创建目录结构
5. 生成分片 → LLM 处理
6. 生成测试 → 编译运行
7. 修复失败用例 → 迭代优化
8. 生成覆盖率报告

### 分步骤执行

如果需要调试或单独执行某些步骤：

```bash
# 步骤0a: 解析源代码
python scripts/task.py parse /home/chenlu/HITS/defect4j_projects

# 步骤0b: 插入数据库
python -c "from scripts.parse_data import parse_data; parse_data('class_info/Csv_1_b', 'Csv_1_b')"

# 步骤0c: 导出数据
python scripts/export_data.py Csv_1_b

# 步骤0d: 初始化工作区
python scripts/create_workspace.py --project_name Csv_1_b --put_root /home/chenlu/HITS/defect4j_projects

# 然后继续执行步骤1-6...
```

## 输出结构

### 解析后的数据

```
class_info/Csv_1_b/
├── ClassName.java.json    # 每个类的解析结果
└── ...

json_db/Csv_1_b/
├── class_ClassName/       # 类元数据
├── method_methodName/     # 方法元数据
└── ...

playground/Csv_1_b/dataset/
├── direction_1/           # d1 数据（基本信息）
├── direction_3/           # d3 数据（完整上下文+依赖）
└── raw_data/              # 原始数据
```

### d1、d3、raw 数据格式

**direction_1** (基本信息):
```json
{
  "focal_method": "parseCSV",
  "class_name": "CSVParser",
  "information": "package org.apache.commons.csv;\n\nimport java.io.*;\n\npublic class CSVParser {\n    // 源代码...\n}"
}
```

**direction_3** (完整上下文):
```json
{
  "c_deps": {
    "String": "public class String { /* 简化的String类 */ }",
    "List": "public interface List<T> { /* 简化的List接口 */ }"
  },
  "m_deps": {
    "this": ["read()", "close()"],
    "String": ["split(String)", "trim()"]
  },
  "full_fm": "package org.apache.commons.csv;\n\npublic class CSVParser {\n    // 完整类定义...\n}",
  "focal_method": "public List<CSVRecord> parseCSV(String csv) {...}",
  "class_name": "CSVParser"
}
```

**raw_data** (原始数据):
```json
{
  "id": 1,
  "project_name": "Csv_1_b",
  "signature": "public List<CSVRecord> parseCSV(String csv)",
  "method_name": "parseCSV",
  "parameters": "String csv",
  "source_code": "public List<CSVRecord> parseCSV(String csv) {\n    // 实现...\n}",
  "class_name": "CSVParser",
  "dependencies": {"this": ["read()"], "String": ["split()"]},
  "use_field": true,
  "is_constructor": false,
  "is_get_set": false,
  "is_public": true,
  "package": "package org.apache.commons.csv;",
  "imports": "import java.io.*;\nimport java.util.*;"
}
```

## 故障排除

### 问题1: 解析失败

**错误**: `Failed to parse /path/to/file.java`

**原因**: Java 语法错误或 tree-sitter 解析问题

**解决**:
```bash
# 检查 Java 文件语法
javac -cp /path/to/project/src /path/to/file.java

# 如果是语法问题，跳过该文件或修复源代码
```

### 问题2: 数据库为空

**错误**: `json_db/Csv_1_b/` 仍然为空

**原因**: 解析步骤失败或没有找到 Java 文件

**检查**:
```bash
# 检查源代码目录
ls -la /home/chenlu/HITS/defect4j_projects/Csv_1_b/src/

# 检查解析输出
ls -la class_info/Csv_1_b/

# 手动运行解析
python scripts/task.py parse /home/chenlu/HITS/defect4j_projects
```

### 问题3: 导出失败

**错误**: `export_data.py` 失败

**原因**: JsonDB 中没有数据或数据格式不匹配

**检查**:
```bash
# 检查数据库内容
ls -la json_db/Csv_1_b/

# 查看具体内容
find json_db/Csv_1_b/ -name "*.json" | head -5 | xargs cat
```

### 问题4: 工作区初始化失败

**错误**: `create_workspace.py` 仍然显示空方法列表

**原因**: 导出步骤失败，dataset 目录为空

**检查**:
```bash
# 检查数据集目录
ls -la experiments/playground/Csv_1_b/dataset/

# 重新导出
python scripts/export_data.py Csv_1_b
```

## 性能优化

### 1. 增量解析

如果项目很大，可以实现增量解析：

```python
# 在 parse_data.py 中添加检查
if os.path.exists(json_file_path):
    print(f"跳过已解析文件：{focal}")
    continue
```

### 2. 并行处理

解析步骤可以并行化：

```python
from concurrent.futures import ThreadPoolExecutor

def parse_all_classes_parallel(focals, project_name, output):
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(self.parse_single_class, focal, project_name, output) for focal in focals]
        # 等待完成...
```

## 扩展功能

### 添加新的数据维度

在 `export_data.py` 中添加新的导出函数：

```python
def export_custom_data(db, project_name):
    """导出自定义格式的数据"""
    # 实现自定义逻辑
    pass
```

### 支持其他语言

修改 `class_parser.py` 以支持其他语言：

```python
# 添加 Python 解析器
class PythonParser:
    def __init__(self):
        # 使用 AST 库
        pass
```

## 参考资料

- [原始 Pipeline 文档](../PIPELINE_GUIDE.py)
- [项目结构说明](../readme.md)
- [JsonDB 实现](../utils/json_db.py)
- [配置说明](../config.ini)