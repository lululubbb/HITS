"""
test_runner_focal_fix.py  (v2 — multi-modified-class fix)
==========================================================

修复内容（相比 v1）：

问题1修复：多 modified class 场景下测试与被测类的映射错位
  根因：test_runner.py 中 _resolve_target_class() 只返回第一个 modified class，
        导致所有测试（不论其名称前缀是 Metaphone_、SoundexUtils_ 还是 Caverphone_）
        都被当作只测试 Caverphone 的测试，进而在 Caverphone 类中查找
        Metaphone/SoundexUtils 的 focal method，当然找不到。

  修复方案：
    - 新增 build_class_name_to_simple_map()：从所有 modified classes 建立
      "简单类名 → 全限定简单类名" 的映射表。
    - 新增 resolve_target_class_for_test()：根据测试类名前缀（如 Metaphone_）
      匹配到正确的 modified class（如 Metaphone），而非总返回第一个。
    - test_runner.py 中 run_all_tests() 的每次 per-test 循环，通过
      resolve_target_class_for_test() 获取该测试对应的 target_class，
      再去 JaCoCo XML 中定位正确的类，从而准确提取覆盖率。

问题4修复（保留）：多个 modified class 的覆盖率计算
  - resolve_all_target_classes()：返回所有 modified class 的简单类名列表。
  - compute_coverage_for_all_classes()：分别提取每个 class 的覆盖率。

问题6修复（保留）：JaCoCo descriptor 匹配失败
  - safe_params_to_descriptor_fixed()：正确处理多维基本类型数组和无参方法。
  - is_focal_method_match_fixed()：无参方法 "()" 能正确匹配 desc="()I/()V"。
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Set, Tuple


# ════════════════════════════════════════════════════════════════════
# 问题6修复：descriptor 生成和匹配
# ════════════════════════════════════════════════════════════════════

# 扩展基本类型映射（包含数组维度支持）
_JAVA_PRIMITIVE_MAP = {
    'int': 'I', 'long': 'J', 'double': 'D', 'float': 'F',
    'boolean': 'Z', 'byte': 'B', 'char': 'C', 'short': 'S',
    'void': 'V',
}


def safe_params_to_descriptor_fixed(param_types: list) -> Optional[str]:
    """
    修复版 _safe_params_to_descriptor：
    
    1. 正确处理多维基本类型数组（如 double[][], int[]）
    2. 无参数方法返回 "()" 而非 None
    3. 对象类型仍返回 None（无法确定包名）
    """
    if not param_types:
        return "()"  # ★ 修复：无参方法返回 "()" 而非 None

    result_parts = []
    for t in param_types:
        t = t.strip()
        # 剥离数组维度
        base = t
        array_prefix = ''
        while base.endswith('[]'):
            array_prefix += '['
            base = base[:-2].strip()
        if base in _JAVA_PRIMITIVE_MAP:
            result_parts.append(array_prefix + _JAVA_PRIMITIVE_MAP[base])
        else:
            # 含对象类型，无法可靠转换
            return None
    return '(' + ''.join(result_parts)


def is_focal_method_match_fixed(
    method_name: str,
    focal_name: str,
    modified_class_name: str,
    focal_descriptor: Optional[str] = None,
    method_desc: Optional[str] = None,
) -> bool:
    """
    修复版 _is_focal_method_match：
    
    1. 无参方法 descriptor="()" 能正确匹配 JaCoCo 的 desc="()I", desc="()V" 等
    2. 构造函数识别逻辑保持不变
    """
    if not focal_name:
        return False

    # 构造函数识别
    if method_name == '<init>' and modified_class_name:
        simple_class = modified_class_name.split('.')[-1].split('$')[0]
        if focal_name in (modified_class_name, simple_class):
            if focal_descriptor and method_desc:
                # focal_descriptor 可能是 "()" 或 "(I" 等参数前缀
                # 需要只匹配参数部分，不匹配返回值
                method_params = method_desc[:method_desc.find(')') + 1] if ')' in method_desc else method_desc
                focal_params  = focal_descriptor if focal_descriptor.endswith(')') else focal_descriptor
                if focal_params.endswith(')'):
                    return method_params == focal_params
                return method_params.startswith(focal_params)
            return True

    if method_name != focal_name:
        return False

    # 方法名匹配时，验证 descriptor
    if focal_descriptor and method_desc:
        # 提取 JaCoCo desc 的参数部分（括号内）
        if focal_descriptor.endswith(')'):
            # 完整参数 descriptor，如 "()" "(I)" "([[D[D[DD)"
            method_params = method_desc[:method_desc.find(')') + 1] if ')' in method_desc else method_desc
            return method_params == focal_descriptor
        else:
            # 前缀匹配（不完整时）
            return method_desc.startswith(focal_descriptor)

    return True


# ════════════════════════════════════════════════════════════════════
# 问题1修复（新增）：测试类名 → 正确的 modified class 映射
# ════════════════════════════════════════════════════════════════════

def build_class_name_to_simple_map(project_dir: str) -> Dict[str, str]:
    """
    建立 "简单类名（小写）→ 原始简单类名" 的映射表，
    用于从测试类名前缀快速匹配所属的 modified class。

    例：project 有 modified classes: Caverphone, Metaphone, SoundexUtils
        返回: {"caverphone": "Caverphone", "metaphone": "Metaphone",
                "soundexutils": "SoundexUtils"}

    Parameters
    ----------
    project_dir : str
        Defects4J 项目根目录（如 /path/to/Codec_1_f）

    Returns
    -------
    Dict[str, str]
        {lower_simple_class_name: simple_class_name}
    """
    all_classes = resolve_all_target_classes(project_dir)
    return {cls.lower(): cls for cls in all_classes}


def resolve_target_class_for_test(
    test_class_name: str,
    all_modified_classes: List[str],
    fallback: str = "",
) -> str:
    """
    根据测试类名前缀，推断该测试对应的 modified class。

    命名约定（ChatUniTest/RefineTestGen 标准）：
        <ClassName>_<method_id>_<seq>Test
        例: Metaphone_5_1Test  → Metaphone
            Caverphone_2_1Test → Caverphone
            SoundexUtils_8_2Test → SoundexUtils

    算法（按优先级）：
        1. 从测试类名中提取 class_prefix（去掉 _<mid>_<seq>Test 后缀）
        2. 精确匹配：class_prefix 与某个 modified class 完全相同（大小写不敏感）
        3. 前缀匹配：某个 modified class 是 class_prefix 的前缀（处理含下划线的类名）
        4. 后缀匹配：class_prefix 包含某个 modified class 作为子串
        5. 降级：返回 fallback（第一个 modified class 或空字符串）

    Parameters
    ----------
    test_class_name : str
        测试类名，如 "Metaphone_5_1Test" 或 "Metaphone_5_1Test"（不含 .java）
    all_modified_classes : List[str]
        所有 modified class 的简单类名列表，如 ["Caverphone", "Metaphone", "SoundexUtils"]
    fallback : str
        当无法推断时返回的默认值

    Returns
    -------
    str
        匹配到的 modified class 简单类名，如 "Metaphone"
    """
    if not all_modified_classes:
        return fallback
    if len(all_modified_classes) == 1:
        return all_modified_classes[0]

    # 去掉 .java 后缀（如果有）
    name = test_class_name.removesuffix('.java') if hasattr(str, 'removesuffix') else (
        test_class_name[:-5] if test_class_name.endswith('.java') else test_class_name
    )

    # 去掉 Test 后缀
    if name.endswith('Test'):
        name = name[:-4]  # 去掉 "Test"

    # 尝试从末尾去掉 _<seq> 和 _<mid> 两段数字后缀
    # 例：Metaphone_5_1 → Metaphone_5 → Metaphone
    # 同时支持 method_id 为非数字（如方法名本身），逐步回退
    parts = name.split('_')
    # 从后向前找到最长的 class_prefix（去掉数字/方法名后缀）
    # 策略：尝试从后剥离 1、2、3 段，直到 prefix 匹配到某个 modified class

    lower_map = {cls.lower(): cls for cls in all_modified_classes}

    for strip_count in range(1, min(4, len(parts))):
        prefix = '_'.join(parts[:len(parts) - strip_count])
        if not prefix:
            continue

        # 精确匹配（大小写不敏感）
        prefix_lower = prefix.lower()
        if prefix_lower in lower_map:
            return lower_map[prefix_lower]

    # 前缀/子串匹配（兜底）
    # 取去掉最后2段（_mid_seq）后的前缀
    if len(parts) >= 3:
        class_prefix = '_'.join(parts[:-2])
    elif len(parts) >= 2:
        class_prefix = parts[0]
    else:
        class_prefix = name

    class_prefix_lower = class_prefix.lower()

    # 精确
    if class_prefix_lower in lower_map:
        return lower_map[class_prefix_lower]

    # modified class 是前缀（处理类名中含下划线，如 My_Class_1_Test → My_Class）
    for cls_lower, cls in lower_map.items():
        if class_prefix_lower == cls_lower or class_prefix_lower.startswith(cls_lower + '_'):
            return cls

    # 子串包含（最后兜底）
    for cls_lower, cls in lower_map.items():
        if cls_lower in class_prefix_lower:
            return cls

    return fallback if fallback else (all_modified_classes[0] if all_modified_classes else "")


# ════════════════════════════════════════════════════════════════════
# 问题4修复：多个 modified class 支持
# ════════════════════════════════════════════════════════════════════

def resolve_all_target_classes(project_dir: str) -> List[str]:
    """
    返回项目的所有 modified class 简单类名列表（不只是第一个）。
    
    数据来源（优先级递减）：
    1. modified_classes.src（每行一个全限定类名）
    2. defects4j.build.properties 的 d4j.classes.modified
    3. 空列表（调用方需要回退到旧逻辑）
    """
    classes = []

    # 优先1: modified_classes.src
    meta_file = os.path.join(project_dir, 'modified_classes.src')
    if os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        simple = line.split('.')[-1]
                        if simple and simple not in classes:
                            classes.append(simple)
            if classes:
                return classes
        except Exception:
            pass

    # 优先2: defects4j.build.properties
    prop_file = os.path.join(project_dir, 'defects4j.build.properties')
    if os.path.exists(prop_file):
        try:
            with open(prop_file) as f:
                for line in f:
                    if 'd4j.classes.modified' in line and '=' in line:
                        val = line.split('=', 1)[1].strip()
                        for cls in val.split(','):
                            cls = cls.strip()
                            if cls:
                                simple = cls.split('.')[-1]
                                if simple and simple not in classes:
                                    classes.append(simple)
            if classes:
                return classes
        except Exception:
            pass

    return classes  # 可能为空，调用方需要回退到旧逻辑


def resolve_target_class_primary(project_dir: str) -> str:
    """返回主要的 target class（向后兼容，返回第一个）。"""
    classes = resolve_all_target_classes(project_dir)
    return classes[0] if classes else ''


# ════════════════════════════════════════════════════════════════════
# 覆盖率计算：多个 modified class 的聚合
# ════════════════════════════════════════════════════════════════════

def compute_coverage_for_all_classes(
    jacoco_xml_path: str,
    target_classes: List[str],
    focal_name: str = "",
    focal_descriptor: Optional[str] = None,
) -> Dict[str, dict]:
    """
    从 JaCoCo XML 中提取所有 modified class 的覆盖率数据。
    
    Returns:
        {class_name: {
            'm_line_cov': int, 'm_line_total': int,
            'm_branch_cov': int, 'm_branch_total': int,
            'f_line_cov': int, 'f_line_total': int,
            'f_branch_cov': int, 'f_branch_total': int,
        }}
    """
    import xml.etree.ElementTree as ET

    result = {}
    if not jacoco_xml_path or not os.path.exists(jacoco_xml_path):
        return result

    try:
        with open(jacoco_xml_path, 'r', encoding='utf-8', errors='replace') as f:
            raw = f.read()
        _start = raw.find('<report')
        if _start < 0:
            return result
        root = ET.fromstring(raw[_start:])
    except Exception:
        return result

    for target_class in target_classes:
        simple = target_class.split('.')[-1].split('$')[0]
        class_data = {
            'm_line_cov': 0, 'm_line_total': 0,
            'm_branch_cov': 0, 'm_branch_total': 0,
            'f_line_cov': 0, 'f_line_total': 0,
            'f_branch_cov': 0, 'f_branch_total': 0,
        }

        for class_elem in root.findall('.//class'):
            cname = class_elem.get('name', '')
            cname_simple = cname.split('/')[-1].split('$')[0]
            if cname_simple != simple and not cname.endswith('/' + simple):
                continue

            # Class-level coverage (modified class)
            for c in class_elem.findall('counter'):
                ctype = c.get('type', '')
                cov = int(c.get('covered', 0))
                mis = int(c.get('missed', 0))
                if ctype == 'LINE':
                    class_data['m_line_cov']   += cov
                    class_data['m_line_total'] += cov + mis
                elif ctype == 'BRANCH':
                    class_data['m_branch_cov']   += cov
                    class_data['m_branch_total'] += cov + mis

            # Focal method coverage
            if focal_name:
                for me in class_elem.findall('method'):
                    mn = me.get('name', '')
                    md = me.get('desc', '')
                    if is_focal_method_match_fixed(mn, focal_name, simple,
                                                   focal_descriptor, md):
                        for cc in me.findall('counter'):
                            ct = cc.get('type', '')
                            cov = int(cc.get('covered', 0))
                            mis = int(cc.get('missed', 0))
                            if ct == 'LINE':
                                class_data['f_line_cov']   += cov
                                class_data['f_line_total'] += cov + mis
                            elif ct == 'BRANCH':
                                class_data['f_branch_cov']   += cov
                                class_data['f_branch_total'] += cov + mis

            result[simple] = class_data
            break  # 找到该类后不再继续

    return result


def aggregate_coverage(coverage_by_class: Dict[str, dict]) -> dict:
    """
    将多个 class 的覆盖率数据聚合为单一指标（用于向后兼容）。
    """
    if not coverage_by_class:
        return {}

    totals = {
        'm_line_cov': 0, 'm_line_total': 0,
        'm_branch_cov': 0, 'm_branch_total': 0,
        'f_line_cov': 0, 'f_line_total': 0,
        'f_branch_cov': 0, 'f_branch_total': 0,
    }
    for class_data in coverage_by_class.values():
        for k in totals:
            totals[k] += class_data.get(k, 0)

    return totals