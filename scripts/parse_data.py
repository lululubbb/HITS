"""
This file is for parsing the .json data.
And insert them into JsonDB (adapted from MySQL version).

修复：支持重载方法识别 —— 改用方法签名（parameters字段）而非方法名作为 collection key，
      避免同名重载方法互相覆盖。

Author: Adapted for HITS project
Date: 2024-03-22
"""

import json
import os
import sys
import re

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from utils.json_db import JsonDatabase
from utils.config import json_db_root


def database(project_name: str):
    """
    Get JsonDB instance for the project
    """
    return JsonDatabase(json_db_root, project_name)


def _make_method_collection_key(method_name: str, parameters: str) -> str:
    """
    为方法生成唯一的 collection key，以支持重载方法。

    例如：
      method_name="read", parameters="read()"            -> "method_read__"
      method_name="read", parameters="read(char[], int, int)" -> "method_read__char___int__int"

    规则：取 parameters 中括号内的参数部分，将非字母数字字符替换为下划线，
    拼接在方法名后，保证唯一且合法（JsonCollection key 不含空格、斜杠、引号）。
    """
    # 从 parameters 字段提取括号内的参数类型列表，如 "read(char[], int, int)" -> "char[], int, int"
    match = re.search(r'\(([^)]*)\)', parameters)
    if match:
        param_str = match.group(1).strip()
    else:
        param_str = ""

    # 将非字母数字字符替换为下划线，避免 JsonCollection key 中的非法字符
    safe_param = re.sub(r'[^a-zA-Z0-9]', '_', param_str)

    return f"method_{method_name}__{safe_param}"


def parse_data(dir_path: str, project_name: str):
    """
    Parse the data from .json files and insert into JsonDB.
    :param dir_path: the path of the .json files.
    :param project_name: the project name
    :return: None
    """
    db = database(project_name)
    for root, dirs, files in os.walk(dir_path):
        for filename in files:
            if filename.endswith('.json'):
                with open(os.path.join(root, filename), "r") as f:
                    json_data = json.load(f)

                for class_data in json_data:
                    # Get class data
                    project_name = class_data['project_name']
                    class_name = class_data['class_name']
                    class_path = class_data['class_path']
                    c_sig = class_data['c_sig']

                    if class_data['superclass']:
                        super_class = class_data['superclass'].split(' ')[1]
                    else:
                        super_class = ""

                    if class_data['imports']:
                        imports = "\n".join(class_data['imports'])
                    else:
                        imports = ""

                    if "package" in class_data:
                        package = class_data["package"]
                    else:
                        package = ""

                    has_constructor = class_data['has_constructor']

                    # Get field data
                    fields = []
                    for field in class_data['fields']:
                        if field['original_string'] not in fields:
                            fields.append(field['original_string'])
                    fields = "\n".join(fields)

                    # Will append from all constructors
                    c_deps = {}

                    # Get method data
                    methods = class_data['methods']
                    for method_data in methods:
                        m_sig = method_data['m_sig']
                        method_name = method_data['method_name']
                        source_code = method_data['source_code']
                        use_field = method_data['use_field']
                        parameters = method_data['parameters']
                        if "public" in method_data['modifiers']:
                            is_public = True
                        else:
                            is_public = False
                        is_constructor = method_data['is_constructor']
                        is_get_set = method_data['is_get_set']
                        m_deps = method_data['m_deps']

                        # Add dependencies from constructor
                        if is_constructor:
                            for dep_class in m_deps:
                                if dep_class not in c_deps:
                                    c_deps[dep_class] = []
                                c_deps[dep_class].append(m_deps[dep_class])

                        # 修复：使用方法签名（含参数）生成唯一 collection key，支持重载方法
                        collection_key = _make_method_collection_key(method_name, parameters)
                        method_collection = db.get_collection(collection_key)
                        method_collection.insert_one({"project_name": project_name,
                                                     "signature": m_sig,
                                                     "method_name": method_name,
                                                     "parameters": parameters,
                                                     "source_code": source_code,
                                                     "class_name": class_name,
                                                     "dependencies": str(m_deps),
                                                     "use_field": use_field,
                                                     "is_constructor": is_constructor,
                                                     "is_get_set": is_get_set,
                                                     "is_public": is_public,
                                                     "table_name": "method"})

                    # insert class data into table class
                    class_collection = db.get_collection("class_" + class_name)
                    class_collection.insert_one({"project_name": project_name,
                                                "class_name": class_name,
                                                "class_path": class_path,
                                                "signature": c_sig,
                                                "super_class": super_class,
                                                "package": package,
                                                "imports": imports,
                                                "fields": fields,
                                                "has_constructor": has_constructor,
                                                "dependencies": str(c_deps),
                                                "table_name": "class"})
                    print(class_name, "FINISHED!")


if __name__ == '__main__':
    print("This action will alter the information in database.")
    confirm = input("Are you sure to parse the data? (y/n) ")
    if confirm == "y":
        parse_data("/Users/chenyi/Desktop/ChatTester/TestGPT_ASE/information/Lang", "Lang")
    else:
        print("Canceled.")