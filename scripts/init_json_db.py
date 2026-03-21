#!/usr/bin/env python3
"""
初始化 JSON 数据库的脚本
功能：
1. 扫描 PUT 项目的源代码
2. 使用 AST 或简单的文本分析提取所有 public 方法
3. 为每个方法生成必要的元数据
4. 将元数据写入 JSON 数据库
"""

import argparse
import json
import os
import sys
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from utils.config import json_db_root
from utils.json_db import JsonDatabase
import javalang

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def find_java_files(project_root: str) -> List[str]:
    """查找项目中所有的 Java 源文件"""
    java_files = []
    for root, dirs, files in os.walk(project_root):
        # 跳过 target 和其他非源代码目录
        dirs[:] = [d for d in dirs if d not in ['target', 'build', '.git', '__pycache__']]
        for file in files:
            if file.endswith('.java'):
                java_files.append(os.path.join(root, file))
    return java_files


def extract_methods_from_file(file_path: str, project_root: str) -> List[Dict[str, Any]]:
    """从单个 Java 文件中提取 public 方法信息"""
    methods = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        # 解析 Java 代码
        tree = javalang.parse.parse(source_code)
        
        # 提取包名
        package_name = tree.package.name if tree.package else "default"
        
        # 遍历所有类
        for _, cls in tree.filter(javalang.tree.ClassDeclaration):
            class_name = cls.name
            full_class_name = f"{package_name}.{class_name}"
            
            # 遍历所有方法
            for _, method in tree.filter(javalang.tree.MethodDeclaration):
                if 'public' in method.modifiers:
                    # 提取方法签名
                    params = []
                    for param in method.parameters:
                        params.append(f"{param.type} {param.name}")
                    
                    method_signature = f"{method.name}({', '.join(params)})"
                    
                    methods.append({
                        'class_name': class_name,
                        'class_name_full': full_class_name,
                        'package_name': package_name,
                        'method_name': method.name,
                        'method_signature': method_signature,
                        'return_type': str(method.return_type) if method.return_type else 'void',
                        'parameters': ', '.join(params) if params else '',
                        'source_file': file_path,
                        'source_code': source_code,
                        'file_relative_path': os.path.relpath(file_path, project_root)
                    })
    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")
    
    return methods


def extract_methods_from_project(put_root: str) -> Dict[str, Dict[str, Any]]:
    """从整个项目中提取所有 public 方法"""
    all_methods = {}
    
    java_files = find_java_files(put_root)
    logger.info(f"Found {len(java_files)} Java files")
    
    for java_file in java_files:
        logger.info(f"Processing {java_file}...")
        methods = extract_methods_from_file(java_file, put_root)
        
        for method in methods:
            # 创建唯一的方法标识符
            method_id = f"{method['class_name_full']}.{method['method_signature']}"
            all_methods[method_id] = method
    
    logger.info(f"Extracted {len(all_methods)} public methods")
    return all_methods


def generate_direction_documents(method_info: Dict[str, Any]) -> Dict[str, Dict]:
    """为方法生成 direction_1 和 direction_3 文档"""
    
    # direction_1: 方法基本描述
    direction_1 = {
        'table_name': 'direction_1',
        'focal_method': method_info['method_signature'],
        'class_name': method_info['class_name'],
        'class_name_full': method_info['class_name_full'],
        'package_name': method_info['package_name'],
        'return_type': method_info['return_type'],
        'parameters': method_info['parameters'],
        'full_fm': method_info['source_code']
    }
    
    # direction_3: 完整提示数据（包含依赖）
    # 注：真实场景中应该提取类的依赖关系，这里简化处理
    direction_3 = {
        'table_name': 'direction_3',
        'focal_method': method_info['method_signature'],
        'class_name': method_info['class_name'],
        'class_name_full': method_info['class_name_full'],
        'package_name': method_info['package_name'],
        'full_fm': method_info['source_code'],
        'c_deps': {},  # 类依赖
        'm_deps': {},  # 方法依赖
    }
    
    # raw_data: 原始数据
    raw_data = {
        'table_name': 'raw_data',
        'package': f"package {method_info['package_name']};",
        'class_name': method_info['class_name'],
        'class_path': method_info['file_relative_path'],
        'method_name': method_info['method_name'],
        'method_signature': method_info['method_signature'],
        'parameters': method_info['parameters']
    }
    
    # info: 方法图信息（简化版）
    info = {
        'table_name': 'info',
        'method_graphs': [
            {
                'src_lines': [],
                'stmt_pos': {},
                'method_name': method_info['method_name']
            }
        ]
    }
    
    return {
        'direction_1': direction_1,
        'direction_3': direction_3,
        'raw_data': raw_data,
        'info': info
    }


def init_json_db_for_project(project_name: str, put_root: str):
    """初始化项目的 JSON 数据库"""
    
    logger.info(f"Initializing JSON database for project: {project_name}")
    logger.info(f"PUT root: {put_root}")
    
    # 获取项目路径
    project_path = os.path.join(put_root, project_name)
    if not os.path.exists(project_path):
        logger.error(f"Project path not found: {project_path}")
        sys.exit(1)
    
    # 创建数据库实例
    db = JsonDatabase(json_db_root, project_name)
    
    # 提取项目中的所有方法
    all_methods = extract_methods_from_project(project_path)
    
    if not all_methods:
        logger.warning("No public methods found in project!")
        return
    
    # 为每个方法创建集合并写入元数据
    for method_id, method_info in all_methods.items():
        # 使用哈希值作为集合名称以避免路径太长的问题
        # 保留原始 method_id 在文档中作为标识
        method_id_hash = hashlib.md5(method_id.encode()).hexdigest()[:16]
        
        logger.info(f"Creating collection for: {method_id}")
        logger.info(f"  (hash: {method_id_hash})")
        
        # 获取或创建集合
        collection = db.get_collection(method_id_hash)
        
        # 生成文档
        documents = generate_direction_documents(method_info)
        
        # 在每个文档中添加原始方法 ID 以便追踪
        for doc_name, doc_data in documents.items():
            doc_data['_method_id'] = method_id
        
        # 写入数据库
        for doc_name, doc_data in documents.items():
            try:
                collection.insert_one(doc_data)
                logger.info(f"  Inserted {doc_name}")
            except Exception as e:
                logger.error(f"  Failed to insert {doc_name}: {e}")
    
    logger.info(f"Successfully initialized JSON database for {project_name}")
    logger.info(f"Total methods: {len(all_methods)}")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize JSON database with method metadata from source code"
    )
    parser.add_argument(
        "--project_name",
        required=True,
        help="Project name (e.g., Csv_1_b)"
    )
    parser.add_argument(
        "--put_root",
        required=True,
        help="Root directory of PUTs (Program Under Test)"
    )
    
    args = parser.parse_args()
    
    init_json_db_for_project(args.project_name, args.put_root)


if __name__ == "__main__":
    main()
