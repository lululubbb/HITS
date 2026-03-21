#!/usr/bin/env python3
"""
Slice Patch Generation Script
从 notebook 转换而来，用于生成补丁测试的分片
"""

import os
import sys
import json
import argparse
from importlib import reload

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from procedures import parse_missing
from utils import load_code_graph, test_runner
from utils.config import *
from utils.json_db import JsonDatabase


def parse_missing_coverage(project_name):
    """解析缺失的覆盖行"""
    print(f"Parsing missing coverage for project: {project_name}")
    
    database = JsonDatabase(json_db_root, project_name)
    
    with open(os.path.join(playground_dir, project_name, "meta.json"), 'r') as file:
        meta = json.load(file)
    
    print(f"Total methods to process: {len(meta['method_name_to_idx'])}")
    
    reload(load_code_graph)
    reload(parse_missing)
    
    parsed_count = 0
    for method_name in database.list_collection_names():
        if method_name not in meta['method_name_to_idx']:
            print(f"⚠ {method_name} not found in meta (may have been manually deleted)")
            continue
        
        method_idx = meta['method_name_to_idx'][method_name]
        log_dir = os.path.join(playground_dir, project_name, 'methods', method_idx)
        
        full_report_dir = os.path.join(log_dir, 'full_report')
        if not os.path.exists(full_report_dir) or len(os.listdir(full_report_dir)) == 0:
            print(f"⚠ No coverage report found for {method_name} in {log_dir}")
            continue
        
        print(f"Parsing missing coverage from {log_dir}")
        try:
            _ = parse_missing.parse_missing(log_dir, database.get_collection(method_name))
            parsed_count += 1
        except Exception as e:
            print(f"  Error parsing {method_name}: {e}")
    
    print(f"✓ Parsed {parsed_count} methods")
    return parsed_count


def export_slicing_tasks(project_name):
    """导出供Java Slicer使用的切片任务"""
    print(f"\nExporting slicing tasks for project: {project_name}")
    
    database = JsonDatabase(json_db_root, project_name)
    
    with open(os.path.join(playground_dir, project_name, "meta.json"), 'r') as file:
        meta = json.load(file)
    
    slicing = list([])
    
    for method_name in database.list_collection_names():
        if method_name not in meta['method_name_to_idx']:
            continue
        
        method_idx = meta['method_name_to_idx'][method_name]
        log_dir = os.path.join(playground_dir, project_name, 'methods', method_idx)
        slice_path = os.path.join(log_dir, 'slice_fixing', 'missing_slices.jsonl')
        
        if os.path.exists(slice_path):
            with open(slice_path, 'r') as file:
                content = file.read().strip()
                if content:
                    slicing.append(os.path.abspath(slice_path))
    
    output_file = os.path.join(playground_dir, project_name, "slicing_tasks.txt")
    with open(output_file, 'w') as file:
        file.write('\n'.join(slicing))
    
    print(f"✓ Exported {len(slicing)} slicing task(s)")
    print(f"  Output: {output_file}")
    return slicing


def write_wala_scope_file(project_name):
    """写入WALA分析范围文件"""
    print(f"\nWriting WALA scope file for project: {project_name}")
    
    with open(os.path.join(playground_dir, project_name, "meta.json"), 'r') as file:
        meta = json.load(file)
    
    put_path = meta['put_path']
    
    # Parse root pom to get module directories
    modules = [os.path.dirname(p) for p in test_runner.parse_root_pom(put_path)]
    bin_dirs = [os.path.join(module, 'target/classes') for module in modules 
                if os.path.exists(os.path.join(module, 'target/classes'))]
    
    output_file = os.path.join(playground_dir, project_name, 'scope_wala.txt')
    with open(output_file, 'w') as file:
        file.write('Primordial,Java,stdlib,base\n')
        file.write('Primordial,Java,jarFile,primordial.jar.model\n')
        for bin_dir in bin_dirs:
            file.write(f"Application,Java,binaryDir,{bin_dir}\n")
    
    print(f"✓ WALA scope file written")
    print(f"  Binary directories: {len(bin_dirs)}")
    print(f"  Output: {output_file}")
    
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Generate Slice Patches for Test Generation")
    parser.add_argument("--project_name", required=True, help="Project name to process")
    parser.add_argument("--parse_missing", action='store_true', help="Parse missing coverage")
    parser.add_argument("--export_tasks", action='store_true', help="Export slicing tasks")
    parser.add_argument("--write_scope", action='store_true', help="Write WALA scope file")
    parser.add_argument("--all", action='store_true', help="Run all steps")
    
    args = parser.parse_args()
    project_name = args.project_name
    
    if args.all:
        args.parse_missing = True
        args.export_tasks = True
        args.write_scope = True
    
    if args.parse_missing or args.all:
        parse_missing_coverage(project_name)
    
    if args.export_tasks or args.all:
        export_slicing_tasks(project_name)
    
    if args.write_scope or args.all:
        write_wala_scope_file(project_name)
    
    if not (args.parse_missing or args.export_tasks or args.write_scope or args.all):
        print("Running all steps by default...")
        parse_missing_coverage(project_name)
        export_slicing_tasks(project_name)
        write_wala_scope_file(project_name)


if __name__ == "__main__":
    main()
