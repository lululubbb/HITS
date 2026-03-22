import argparse
import json
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)
from utils.config import *
from utils.json_db import JsonDatabase


def _is_method_collection(name: str) -> bool:
    """
    判断一个 collection 名是否为方法 collection。
    支持旧格式 "method_xxx" 和新格式 "method_xxx__yyy"（含重载参数）。
    """
    return name.startswith("method_") and not name.startswith("class_")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_name", required=True)
    parser.add_argument("--put_root", required=True, help="Root dir of PUTs in this PC. E.g. 'root/put'")
    args = parser.parse_args()
    project_name = args.project_name
    put_root = args.put_root

    db = JsonDatabase(json_db_root, project_name)

    # Create local working dir and write local meta info
    playground_root = os.path.join(playground_dir, project_name).__str__()
    put_path = os.path.join(put_root, project_name)

    # 修复：只统计方法 collection（支持重载），排除 class_ 等其他 collection
    all_collections = db.list_collection_names()
    mut_names = [name for name in all_collections if _is_method_collection(name)]

    method_name_to_idx = dict({})
    idx_to_method_name = dict({})
    for idx, mut_name in enumerate(mut_names):
        method_name_to_idx[mut_name] = f"method_{idx}"
        idx_to_method_name[f"method_{idx}"] = mut_name

    os.makedirs(playground_root, exist_ok=True)
    with open(os.path.join(playground_root, "meta.json"), 'w') as file:
        json.dump({"project_name": project_name, "put_path": os.path.abspath(put_path),
                   "method_name_to_idx": method_name_to_idx,
                   "idx_to_method_name": idx_to_method_name}, file)
    for idx in idx_to_method_name:
        os.makedirs(os.path.join(playground_root, 'methods', idx), exist_ok=True)

    print(f"✓ Workspace created for {project_name}: {len(mut_names)} methods found")


if __name__ == "__main__":
    main()