"""
scripts/parse_data.py  — 修复版

变更：
  1. __main__ 不再 hardcode 路径；改为从 sys.argv 读取参数
  2. 移除 input() 阻塞；改为命令行 --yes / -y 标志确认，或
     直接传参时自动执行（pipeline 调用时无需交互）
  3. 暴露 parse_data() 函数供 pipeline.py 直接 import 调用
"""

import json
import os
import sys
import re
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from utils.json_db import JsonDatabase
from utils.config import json_db_root


def database(project_name: str):
    return JsonDatabase(json_db_root, project_name)


def _make_method_collection_key(method_name: str, parameters: str) -> str:
    match = re.search(r'\(([^)]*)\)', parameters)
    param_str = match.group(1).strip() if match else ""
    safe_param = re.sub(r'[^a-zA-Z0-9]', '_', param_str)
    return f"method_{method_name}__{safe_param}"


def parse_data(dir_path: str, project_name: str):
    """
    Parse .json files under dir_path and insert into JsonDB.
    可被 pipeline.py 直接 import 调用，无需子进程。
    """
    db = database(project_name)
    inserted = 0

    for root, dirs, files in os.walk(dir_path):
        for filename in files:
            if not filename.endswith('.json'):
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
            except Exception as e:
                print(f"[WARN] Cannot read {filepath}: {e}")
                continue

            for class_data in json_data:
                project_name_from_data = class_data.get('project_name', project_name)
                class_name    = class_data['class_name']
                class_path    = class_data['class_path']
                c_sig         = class_data['c_sig']
                super_class   = (class_data['superclass'].split(' ')[1]
                                 if class_data.get('superclass') else "")
                imports       = "\n".join(class_data['imports']) if class_data.get('imports') else ""
                package       = class_data.get("package", "")
                has_constructor = class_data['has_constructor']

                fields = "\n".join([f['original_string']
                                    for f in class_data.get('fields', [])
                                    if f['original_string'] not in []])
                c_deps = {}

                for method_data in class_data.get('methods', []):
                    m_sig        = method_data['m_sig']
                    method_name  = method_data['method_name']
                    source_code  = method_data['source_code']
                    use_field    = method_data['use_field']
                    parameters   = method_data['parameters']
                    is_public    = "public" in method_data.get('modifiers', '')
                    is_constructor = method_data['is_constructor']
                    is_get_set   = method_data['is_get_set']
                    m_deps       = method_data['m_deps']

                    if is_constructor:
                        for dep_class in m_deps:
                            if dep_class not in c_deps:
                                c_deps[dep_class] = []
                            c_deps[dep_class].append(m_deps[dep_class])

                    collection_key = _make_method_collection_key(method_name, parameters)
                    method_collection = db.get_collection(collection_key)
                    method_collection.insert_one({
                        "project_name": project_name_from_data,
                        "signature":    m_sig,
                        "method_name":  method_name,
                        "parameters":   parameters,
                        "source_code":  source_code,
                        "class_name":   class_name,
                        "dependencies": str(m_deps),
                        "use_field":    use_field,
                        "is_constructor": is_constructor,
                        "is_get_set":   is_get_set,
                        "is_public":    is_public,
                        "table_name":   "method",
                    })
                    inserted += 1

                class_collection = db.get_collection("class_" + class_name)
                class_collection.insert_one({
                    "project_name": project_name_from_data,
                    "class_name":   class_name,
                    "class_path":   class_path,
                    "signature":    c_sig,
                    "super_class":  super_class,
                    "package":      package,
                    "imports":      imports,
                    "fields":       fields,
                    "has_constructor": has_constructor,
                    "dependencies": str(c_deps),
                    "table_name":   "class",
                })
                print(f"  {class_name} FINISHED!")

    print(f"[parse_data] Inserted {inserted} method records for {project_name}")
    return inserted


# ── CLI 入口（支持 pipeline 子进程调用，也支持手动运行）──────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Parse class_info JSON and insert into JsonDB")
    parser.add_argument("dir_path", help="Path to class_info/<project_name> directory")
    parser.add_argument("project_name", help="Project name (e.g. Csv_1_b)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompt (for pipeline/automated use)")
    args = parser.parse_args()

    if not args.yes:
        confirm = input(f"Parse {args.dir_path} into project '{args.project_name}'? (y/n) ")
        if confirm.lower() != 'y':
            print("Canceled.")
            sys.exit(0)

    parse_data(args.dir_path, args.project_name)