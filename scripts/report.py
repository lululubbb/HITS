#!/usr/bin/env python3
"""
Report Generation Script
从 notebook 转换而来，用于汇总覆盖率报告
"""

import sys
import os
import json
import glob
import logging
import argparse
from importlib import reload
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from utils.config import *
from utils.json_db import JsonDatabase
from procedures import report as report_module
import utils.report


def single_method_report_mode(project_name):
    """单个项目的覆盖率报告"""
    print(f"Generating report for project: {project_name}")
    
    db = JsonDatabase(json_db_root, project_name)
    with open(os.path.join(playground_dir, project_name, "meta.json"), "r") as file:
        meta_info = json.load(file)
    
    print(f"Total methods to analyze: {len(meta_info['idx_to_method_name'])}")
    
    cov_result = list([])
    
    reload(report_module)
    reload(utils.report)
    
    for method_to_test in tqdm(meta_info['method_name_to_idx']):
        log_dir = os.path.join(playground_dir, project_name, 'methods', meta_info['method_name_to_idx'][method_to_test])
        collection = db.get_collection(method_to_test)
        
        # Generate report
        report_module.single_method_report(log_dir, collection, meta_info['put_path'], JACOCO_CLI, src_dir='src/main')
        cov_result.append(report_module.single_method_analyse(log_dir, db.get_collection(method_to_test)))
    
    # Save results
    result_file = os.path.join(playground_dir, project_name, 'result.json')
    with open(result_file, 'w') as f:
        json.dump(cov_result, f, indent=2)
    print(f"Results saved to: {result_file}")
    
    return cov_result


def batch_report_mode():
    """批量分析所有项目的覆盖率"""
    print(f"Batch Analysis - Playground: {playground_dir}")
    puts = os.listdir(playground_dir)
    
    for put in puts:
        try:
            result_file = os.path.join(playground_dir, put, 'result.json')
            meta_file = os.path.join(playground_dir, put, "meta.json")
            
            with open(result_file, 'r') as file:
                results = json.load(file)
            with open(meta_file, 'r') as file:
                meta = json.load(file)
                n = len(meta['method_name_to_idx'])
        except FileNotFoundError as e:
            logging.error(f"File not found for {put}: {e}")
            continue
        
        print(f"\n{'='*60}")
        print(f"Project: {put} (Total methods: {n})")
        print(f"{'='*60}")
        
        if results:
            inst_cov_list = [float(item[list(item.keys())[0]]['inst_cov'][:-1]) for item in results]
            bran_cov_list = [float(item[list(item.keys())[0]]['bran_cov'][:-1]) for item in results]
            
            avg_inst_cov = sum(inst_cov_list) / len(inst_cov_list) if inst_cov_list else 0
            avg_bran_cov = sum(bran_cov_list) / len(bran_cov_list) if bran_cov_list else 0
            
            print(f"Average Instruction Coverage: {avg_inst_cov:.2f}%")
            print(f"Average Branch Coverage: {avg_bran_cov:.2f}%")


def slice_count_mode():
    """统计切片数量"""
    print(f"\nSlice Count Statistics - Playground: {playground_dir}")
    projects = os.listdir(playground_dir)
    
    for project in projects:
        methods_dir = os.path.join(playground_dir, project, 'methods')
        if not os.path.exists(methods_dir):
            continue
        
        n = len(glob.glob("**/steps/log_*.txt", root_dir=methods_dir, recursive=True))
        method_dirs = os.listdir(methods_dir)
        avg = n / len(method_dirs) if method_dirs else 0
        print(f"Project: {project}, Total slices: {n}, Avg per method: {avg:.2f}")


def compile_run_count_mode():
    """统计编译和运行数量"""
    print(f"\nCompile & Run Count - Playground: {playground_dir}")
    projects = os.listdir(playground_dir)
    
    for project in projects:
        try:
            method_experiment_roots = glob.glob(os.path.join(playground_dir, project, 'methods', 'method_*', 'fixing'))
            print(f"\nProject: {project}")
            for root in method_experiment_roots:
                print(f"  {root}")
        except Exception as e:
            logging.error(f"Error processing project {project}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Generate Coverage Reports")
    parser.add_argument("--project_name", help="Specific project to analyze")
    parser.add_argument("--batch", action='store_true', help="Run batch analysis for all projects")
    parser.add_argument("--slice_count", action='store_true', help="Show slice count statistics")
    parser.add_argument("--compile_count", action='store_true', help="Show compile & run count")
    
    args = parser.parse_args()
    
    if args.batch:
        batch_report_mode()
    elif args.slice_count:
        slice_count_mode()
    elif args.compile_count:
        compile_run_count_mode()
    elif args.project_name:
        single_method_report_mode(args.project_name)
    else:
        print("No mode specified. Using default: analyze all projects in batch mode.")
        batch_report_mode()


if __name__ == "__main__":
    main()
