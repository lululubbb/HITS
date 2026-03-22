"""
This file is for exporting the data from JsonDB.
And save them into .json files for HITS pipeline.
Adapted from MySQL version for JsonDB.

修复：适配 parse_data.py 中新的重载方法 collection key 格式（method_name__params）。

Author: Adapted for HITS project
Date: 2024-03-22
"""

import os
import json
import sys
import hashlib

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from utils.json_db import JsonDatabase
from utils.config import json_db_root, playground_dir


def _is_method_collection(name: str) -> bool:
    """
    判断一个 collection 名是否为方法 collection。
    支持旧格式 "method_xxx" 和新格式 "method_xxx__yyy"（含重载参数）。
    """
    return name.startswith("method_") and not name.startswith("class_")


def gen_file_name(method_id, project_name, class_name, method_name, direction):
    """
    Generate file name for HITS pipeline
    """
    if direction == "raw":
        return f"{method_id}%{project_name}%{class_name}%{method_name}%raw.json"
    return f"{method_id}%{project_name}%{class_name}%{method_name}%d{direction}.json"


def create_dataset_dirs(project_name: str):
    """
    Create dataset directories for the project
    """
    def _create_folder(dir_path):
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

    # 使用playground目录结构
    dataset_path = os.path.join(playground_dir, project_name, "dataset")
    _create_folder(dataset_path)
    _create_folder(os.path.join(dataset_path, "direction_1"))
    _create_folder(os.path.join(dataset_path, "direction_3"))
    _create_folder(os.path.join(dataset_path, "raw_data"))
    return dataset_path


def export_data(project_name: str):
    """
    Export data from JsonDB for HITS pipeline.
    :param project_name: the project name
    :return: None
    """
    print(f"Starting export_data for project: {project_name}")
    dataset_path = create_dataset_dirs(project_name)
    print(f"Dataset path: {dataset_path}")
    db = JsonDatabase(json_db_root, project_name)
    print(f"Database root: {json_db_root}, project: {project_name}")

    # 添加：检查是否为 defects4j 项目，并加载 focal classes 过滤器
    is_defects4j = project_name.endswith('_f') or project_name.endswith('_b')
    focal_classes_filter = set()  # 默认空集，表示不过滤

    if is_defects4j:
        focal_classes_json_path = os.path.join(PROJECT_ROOT, "scripts", "focal_classes.json")
        try:
            with open(focal_classes_json_path, 'r') as f:
                focal_data = json.load(f)

            # 将 _b 转换为 _f（因为 focal_classes.json 使用 _f）
            target_project = project_name.replace('_b', '_f') if '_b' in project_name else project_name

            for project_entry in focal_data:
                if project_entry.get('project') == target_project:
                    # 清理类名（移除换行符和空格），并提取简单类名
                    classes = [c.rstrip('\n').strip() for c in project_entry.get('classes', [])]
                    focal_classes_filter = set(c.split('.')[-1] for c in classes)
                    print(f"✓ 检测到 defects4j 项目，已加载 {len(focal_classes_filter)} 个 focal classes")
                    print(f"  Focal classes: {focal_classes_filter}")
                    break

            if not focal_classes_filter:
                print(f"⚠ 未找到项目 {target_project} 的 focal classes 定义")
        except Exception as e:
            print(f"⚠ 加载 focal classes 失败: {e}，将导出所有类")

    # 获取所有方法 collection（支持新旧格式）
    method_collections = [
        name for name in db.list_collection_names()
        if _is_method_collection(name)
    ]

    print(f"Found {len(method_collections)} method collections")
    method_id = 1
    exported_count = 0
    skipped_count = 0

    for collection_name in method_collections:
        collection = db.get_collection(collection_name)
        method_data = collection.find_one({"table_name": "method"})
        if not method_data:
            continue

        proj_name = method_data['project_name']
        m_sig = method_data['signature']
        method_name = method_data['method_name']
        parameters = method_data['parameters']
        source_code = method_data['source_code']
        class_name = method_data['class_name']
        m_deps = method_data['dependencies']
        use_field = method_data['use_field']
        is_constructor = method_data['is_constructor']
        is_get_set = method_data['is_get_set']
        is_public = method_data['is_public']

        # 添加：对 defects4j 项目，检查该方法是否来自 focal class
        if is_defects4j and focal_classes_filter:
            if class_name not in focal_classes_filter:
                skipped_count += 1
                continue

        exported_count += 1

        if isinstance(m_deps, str):
            m_deps = eval(m_deps)

        # Get class data
        class_collection = db.get_collection("class_" + class_name)
        class_data = class_collection.find_one({"table_name": "class"})
        if not class_data:
            continue

        class_path = class_data['class_path']
        c_sig = class_data['signature']
        super_class = class_data['super_class']
        package = class_data['package']
        imports = class_data['imports']
        fields = class_data['fields']
        has_constructor = class_data['has_constructor']
        c_deps = class_data['dependencies']

        if isinstance(c_deps, str):
            c_deps = eval(c_deps)
            c_deps = list(set(c_deps))

        # Direction 1: imports + fc + c + f + fm + m
        json_data = {"focal_method": method_name, "class_name": class_name, "information": ""}
        direction_1 = ""
        if package:
            direction_1 += package + "\n" + "\n"
        if imports:  # imports
            direction_1 += imports + "\n"
        if c_sig:  # c
            direction_1 += c_sig + "{\n"

        # Add fm
        direction_1 += source_code + "\n"

        if fields:  # f
            direction_1 += fields + "\n"

        # Merge all methods from all method collections in the same class
        methods = []
        for coll_name in db.list_collection_names():
            if _is_method_collection(coll_name):
                coll = db.get_collection(coll_name)
                method_doc = coll.find_one({"table_name": "method", "class_name": class_name})
                if method_doc and method_doc['signature'] != m_sig:
                    methods.append(method_doc['signature'])

        methods = "\n".join(methods)
        direction_1 += methods + "\n}"

        json_data["information"] = direction_1
        save_name = gen_file_name(method_id, project_name, class_name, method_name, 1)
        with open(os.path.join(dataset_path, "direction_1", save_name), "w") as f:
            json.dump(json_data, f)
        print(save_name, "direction_1 success!")

        # Direction 3: imports + fc + c + f + fm + m AND + c_deps + m_deps
        direction_3 = {"c_deps": {}, "m_deps": {}, "full_fm": "", "focal_method": m_sig,
                       "class_name": class_name}

        other_methods_list = []
        if "this" in m_deps:  # Get the methods(parameters) in same class
            for method in m_deps["this"]:
                if method not in other_methods_list:
                    other_methods_list.append(method)

        # Generate full context for focal method
        direction_3["full_fm"] = gen_full_context(db, project_name, class_name, method_id, other_methods_list)

        # Generate detailed relative signatures for method's dependencies
        for dep in m_deps:
            if dep not in direction_3["m_deps"]:
                if class_in_project(db, dep, project_name):
                    direction_3["m_deps"][dep] = gen_required_sigs(db, project_name, dep, m_deps[dep])

        # Generate constructor's information for class's dependencies
        for dep in c_deps:
            # Exclude class existed in m_deps, because they are already processed above.
            if dep not in direction_3["c_deps"] and dep not in direction_3["m_deps"]:
                if class_in_project(db, dep, project_name):
                    direction_3["c_deps"][dep] = gen_min_sigs(db, project_name, dep)

        save_name = gen_file_name(method_id, project_name, class_name, method_name, 3)
        with open(os.path.join(dataset_path, "direction_3", save_name), "w") as f:
            json.dump(direction_3, f)
        print(save_name, "direction_3 success!")

        # Raw data
        raw_data = {
            "id": method_id,
            "project_name": project_name,
            "signature": m_sig,
            "method_name": method_name,
            "parameters": parameters,
            "source_code": source_code,
            "class_name": class_name,
            "dependencies": m_deps,
            "use_field": use_field,
            "is_constructor": is_constructor,
            "is_get_set": is_get_set,
            "is_public": is_public,
            "package": package,
            "imports": imports
        }
        save_name = gen_file_name(method_id, project_name, class_name, method_name, "raw")
        with open(os.path.join(dataset_path, "raw_data", save_name), "w") as f:
            json.dump(raw_data, f)
        print(save_name, "raw_data success!")

        method_id += 1

    # 添加：导出统计总结
    print(f"\n✓ export_data 完成")
    print(f"  - 导出方法数: {exported_count}")
    if is_defects4j and skipped_count > 0:
        print(f"  - 跳过方法数 (非focal class): {skipped_count}")
        print(f"  - 总方法数: {method_id - 1}")


def gen_min_sigs(db: JsonDatabase, project_name: str, class_name: str) -> str:
    class_collection = db.get_collection("class_" + class_name)
    class_row = class_collection.find_one({"table_name": "class"})
    if not class_row:
        raise RuntimeError("Error happened in function gen_min_sigs.")

    c_sig = class_row['signature']
    fields = class_row['fields']

    full_text = c_sig + "{\n"
    full_text += fields + "\n"

    constructors = []
    for collection_name in db.list_collection_names():
        if _is_method_collection(collection_name):
            method_coll = db.get_collection(collection_name)
            method_doc = method_coll.find_one({"table_name": "method", "class_name": class_name, "is_constructor": True})
            if method_doc:
                constructors.append(method_doc['signature'])

    for constructor in constructors:
        full_text += constructor + "\n"

    full_text += "\n}"
    return full_text


def gen_required_sigs(db: JsonDatabase, project_name: str, class_name: str, methods_list: list):
    full_text = ""
    class_collection = db.get_collection("class_" + class_name)
    class_row = class_collection.find_one({"table_name": "class"})
    if not class_row:
        raise RuntimeError("Error happened in function gen_required_sigs")

    c_sig = class_row['signature']
    fields = class_row['fields']
    has_constructor = class_row['has_constructor']

    full_text += c_sig + "\n" + fields + "\n"

    gs_sigs = []
    for collection_name in db.list_collection_names():
        if _is_method_collection(collection_name):
            method_coll = db.get_collection(collection_name)
            method_doc = method_coll.find_one({"table_name": "method", "class_name": class_name, "is_get_set": True})
            if method_doc:
                gs_sigs.append(method_doc['signature'])
    for gs in gs_sigs:
        full_text += gs + "\n"

    constructors = []
    for collection_name in db.list_collection_names():
        if _is_method_collection(collection_name):
            method_coll = db.get_collection(collection_name)
            method_doc = method_coll.find_one({"table_name": "method", "class_name": class_name, "is_constructor": True})
            if method_doc:
                constructors.append(method_doc['signature'])
    for cons in constructors:
        full_text += cons + "\n"

    for parameters in methods_list:
        for collection_name in db.list_collection_names():
            if _is_method_collection(collection_name):
                method_coll = db.get_collection(collection_name)
                method_doc = method_coll.find_one({"table_name": "method", "class_name": class_name, "parameters": parameters})
                if method_doc:
                    full_text += method_doc['signature'] + "\n"

    full_text += "\n}"
    return full_text


def gen_full_sigs(db: JsonDatabase, project_name: str, class_name: str) -> str:
    class_collection = db.get_collection("class_" + class_name)
    class_row = class_collection.find_one({"table_name": "class"})
    if not class_row:
        raise RuntimeError("Error happened in gen_full_sigs.")

    class_path = class_row['class_path']
    c_sig = class_row['signature']
    super_class = class_row['super_class']
    imports = class_row['imports']
    fields = class_row['fields']
    has_constructor = class_row['has_constructor']
    c_deps = class_row['dependencies']

    full_text = c_sig + "{\n"
    full_text += fields + "\n"

    methods = []
    for collection_name in db.list_collection_names():
        if _is_method_collection(collection_name):
            method_coll = db.get_collection(collection_name)
            method_doc = method_coll.find_one({"table_name": "method", "class_name": class_name})
            if method_doc:
                methods.append(method_doc['signature'])

    for method in methods:
        full_text += method + "\n"

    full_text += "\n}"
    return full_text


def gen_full_context(db: JsonDatabase, project_name: str, class_name: str, method_id: int, dep_methods: list,
                     add_imports=True) -> str:
    class_collection = db.get_collection("class_" + class_name)
    class_row = class_collection.find_one({"table_name": "class"})
    if not class_row:
        raise RuntimeError("Error happened in gen_full_context.")
    class_path = class_row['class_path']
    c_sig = class_row['signature']
    super_class = class_row['super_class']
    package = class_row['package']
    imports = class_row['imports']
    fields = class_row['fields']
    has_constructor = class_row['has_constructor']
    c_deps = class_row['dependencies']

    fm_code = ""
    use_field = False

    # 查找该类的第一个方法作为 focal method（与原逻辑保持一致）
    focal_method_data = None
    for collection_name in db.list_collection_names():
        if _is_method_collection(collection_name):
            method_coll = db.get_collection(collection_name)
            method_doc = method_coll.find_one({"table_name": "method", "class_name": class_name})
            if method_doc:
                focal_method_data = method_doc
                break

    if not focal_method_data:
        raise RuntimeError("Error happened in gen_full_context.")
    if focal_method_data['use_field']:
        use_field = True
    fm_code += focal_method_data['source_code'] + "\n"

    for dep in dep_methods:
        for collection_name in db.list_collection_names():
            if _is_method_collection(collection_name):
                method_coll = db.get_collection(collection_name)
                method_doc = method_coll.find_one({"table_name": "method", "class_name": class_name, "parameters": dep})
                if method_doc:
                    if method_doc['use_field']:
                        use_field = True
                    fm_code += method_doc['signature'] + "\n"

    full_text = ""
    if add_imports:
        if package:
            full_text += package + "\n" + "\n"
        full_text += imports + "\n"
    full_text += c_sig + "{\n"

    if has_constructor:
        constructors = []
        for collection_name in db.list_collection_names():
            if _is_method_collection(collection_name):
                method_coll = db.get_collection(collection_name)
                method_doc = method_coll.find_one({"table_name": "method", "class_name": class_name, "is_constructor": True})
                if method_doc:
                    constructors.append(method_doc['signature'])
        for constructor in constructors:
            full_text += constructor + "\n"

    if use_field and fields:
        full_text += fields + "\n"
        methods = []
        for collection_name in db.list_collection_names():
            if _is_method_collection(collection_name):
                method_coll = db.get_collection(collection_name)
                method_doc = method_coll.find_one({"table_name": "method", "class_name": class_name, "is_get_set": True})
                if method_doc:
                    methods.append(method_doc['signature'])
        for method in methods:
            full_text += method + "\n"

    full_text += fm_code + "}"

    return full_text


def class_in_project(db: JsonDatabase, class_name: str, project_name: str):
    class_collection = db.get_collection("class_" + class_name)
    class_doc = class_collection.find_one({"table_name": "class"})
    if class_doc:
        return True
    return False


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print("Usage: python export_data.py <project_name>")
        sys.exit(1)
    project_name = sys.argv[1]
    export_data(project_name)