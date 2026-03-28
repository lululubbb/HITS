"""
procedures/get_code.py  — 修复版

变更：
  1. generate_code() 的 capacity 默认值改为从 config.TEST_CASES_PER_SLICE 读取
  2. work() 中 wo_slice 模式的 fix_num 默认值改为从 config.WO_SLICE_TEST_COUNT 读取
  3. 其余逻辑与原版一致
"""

import json
import logging
import os
from typing import Optional, List, Dict

try:
    from pymongo.collection import Collection
except ImportError:
    Collection = object

import sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from generator.open_generator import OpenGenerator
from procedures.basic_procedure import BasicProcedure
from utils.code_editor import CodeEditor
from utils.post_process import extract_code
from utils.config import TEST_CASES_PER_SLICE, WO_SLICE_TEST_COUNT  # ← 新增


class InitialCodeGenerator(BasicProcedure):
    def __init__(self, prompt_root, system_template_file_name, init_code_generate_template_file_name):
        super(InitialCodeGenerator, self).__init__(
            prompt_root, system_template_file_name,
            init_code_generate_template_file_name, "init_code_generator")
        self.code_editor = CodeEditor()
        # 确保logger可以输出INFO级别
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    def generate_code(self, direction_3, step_id, chatter, log_dir,
                      init_temp=0.0, capacity=None):
        """
        capacity: 本次生成保留的最大测试用例数。
          None  → 使用 config.TEST_CASES_PER_SLICE（-1 表示不限）
          >= 0  → 直接使用该值（允许调用者覆盖）
        """
        # 解析 capacity
        if capacity is None:
            capacity = TEST_CASES_PER_SLICE  # 来自 config.ini
        # -1 或 None 均表示不限制
        _limit = capacity if (capacity is not None and capacity >= 0) else None

        logger_name = log_dir.replace('.', '/') + f".{step_id}"
        logger = logging.getLogger(name=logger_name)
        logger.propagate = False
        logger.handlers = []
        logger.addHandler(logging.FileHandler(os.path.join(log_dir, f'log_{step_id}.txt')))
        logger.setLevel(logging.INFO)

        response = ""
        tests_by_condition = list([])

        for generate_trial in range(5):
            temperature = init_temp if generate_trial == 0 else 0.5
            logger.info(f"[GEN] Trial {generate_trial+1}/5: Generating code with temperature={temperature}")
            logger.info(f"▶ [{generate_trial+1}/5] 生成 Test #{generate_trial+1}")
            response_0 = chatter.generate(self.generate_template.render(direction_3),
                                          self.system_template.render(),
                                          temperature=temperature)
            if response_0[0] != 200:
                logger.error(f"Error when communicate with GPT. Error code: {response_0[0]}")
                continue
            else:
                response = response_0[1][0]
            has_code, extracted_code, has_syntactic_error = extract_code(response)
            if has_code and not has_syntactic_error:
                tests_by_condition = self.code_editor.split_test_cases(
                    extracted_code, direction_3['simple_class_name'])
                if tests_by_condition is None:
                    tests_by_condition = []
                    logger.warning(f"No valid public class for {log_dir} step {step_id} trial {generate_trial}")
                else:
                    logger.info(f"[GEN] SUCCESS: Generated {len(tests_by_condition)} test cases at trial {generate_trial+1}")
                    break
            else:
                if not has_code:
                    logger.debug(f"No code for {log_dir} step {step_id} trial {generate_trial}")
                if has_syntactic_error:
                    logger.debug(f"Syntactic error for {log_dir} step {step_id} trial {generate_trial}")
                tests_by_condition = []

        if isinstance(step_id, int):
            step_id = str(step_id)

        # 应用上限
        if _limit is not None and _limit >= 0:
            tests_by_condition = tests_by_condition[:_limit]

        unit_tests = []
        has_output = False
        for condition_idx, test_by_condition in enumerate(tests_by_condition):
            has_output = True
            cls_name = "_".join([direction_3['simple_class_name'], step_id,
                                  str(condition_idx), "Test"])
            output_content = self.code_editor.change_main_cls_name(test_by_condition, cls_name)
            if output_content is None:
                output_content = test_by_condition
            with open(os.path.join(log_dir, f"{cls_name}.java"), "w", encoding='utf-8') as file:
                file.write(output_content)
            with open(os.path.join(log_dir, f"{cls_name}.prompt.txt"), "w", encoding='utf-8') as file:
                file.write(self.generate_template.render(direction_3))
            if 'step_id' in direction_3:
                step_id_val = str(direction_3['step_id'])
                if direction_3.get('steps') and step_id_val.isdigit():
                    idx = int(step_id_val)
                    if 0 <= idx < len(direction_3['steps']):
                        with open(os.path.join(log_dir, f"{cls_name}.condition.txt"), 'w', encoding='utf-8') as file:
                            file.write(direction_3['steps'][idx].get('desp', ''))
            unit_tests.append(output_content)

        if has_output:
            with open(os.path.join(
                    log_dir,
                    f"{direction_3['simple_class_name']}_{step_id}.response.txt"), "w",
                    encoding='utf-8') as file:
                file.write(response)
            self.logger.info(f"Step {step_id} in {log_dir}: success")
        else:
            logger.error(f"Step {step_id}: failed to generate any code")
            self.logger.error(f"Step {step_id}: failed to generate any code")
        return unit_tests

    def work(self, collection: Collection, chatter: OpenGenerator, log_dir: str,
             fix_num=-1, fixing=False) -> Optional[List[str]]:
        """
        fix_num: wo_slice 模式下目标测试数量。
          -1  → 使用 config.WO_SLICE_TEST_COUNT
          >0  → 使用传入值
        """
        direction_3: Dict = collection.find_one({"table_name": "direction_3"})
        direction_1: Dict = collection.find_one({"table_name": "direction_1"})
        addon_info:  Dict = collection.find_one({"table_name": "add_info"})
        info:        Dict = collection.find_one({"table_name": "info"})
        assert direction_3 is not None
        assert direction_1 is not None

        if not isinstance(addon_info, dict):
            self.logger.error(f"add_info is not dict for {collection}; fallback to empty steps")
            addon_info = {}

        steps = addon_info.get('steps', []) if addon_info else []
        if steps is None:
            steps = []

        self.logger.info(f"Count {len(steps)} slices (from add_info)")

        direction_3.update(addon_info)
        direction_3['steps'] = steps
        direction_3['simple_class_name']  = direction_1['class_name']
        direction_3['simple_method_name'] = direction_1['focal_method']
        unit_tests = []

        if not fixing:
            direction_3['missing_lines'] = False
            os.makedirs(os.path.join(log_dir, "steps"), exist_ok=True)

            if fix_num < 0:
                # 正常 slice 模式：每个 slice 一次 generate_code
                if not direction_3.get('steps'):
                    # 可能是 wo_slice 不做切片（附加信息缺失）的情况
                    self.logger.warning("No slices available in add_info; falling back to wo_slice style generation")
                    _target = WO_SLICE_TEST_COUNT
                    _round = 0
                    self.logger.info(f"▶ Phase 1: 生成测试用例 (wo_slice)")
                    while len(unit_tests) < _target:
                        self.logger.info(f"▶ [{_round+1}/{_target}] 生成 Test #{_round+1}")
                        self.logger.info(f"Generating init unit test round {_round + 1} (fallback wo_slice)")
                        remaining = _target - len(unit_tests)
                        direction_3['step_id'] = _round
                        unit_tests += self.generate_code(
                            direction_3, str(_round), chatter,
                            os.path.join(log_dir, "steps"),
                            init_temp=0.5, capacity=remaining)
                        _round += 1
                    unit_tests = unit_tests[:_target]
                else:
                    for i in range(len(direction_3['steps'])):
                        self.logger.info(f"▶ Phase 1: 生成测试用例")
                        self.logger.info(f"▶ [{i+1}/{len(direction_3['steps'])}] 生成 Test #{i+1}")
                        self.logger.info(f"Generating init unit test for slice {i + 1}")
                        direction_3['step_id'] = i
                        unit_tests += self.generate_code(direction_3, str(i), chatter,
                                                         os.path.join(log_dir, "steps"))
            else:
                # wo_slice 模式：fix_num <= 0 时回落到 config 值
                _target = fix_num if fix_num > 0 else WO_SLICE_TEST_COUNT
                _round = 0
                self.logger.info(f"▶ Phase 1: 生成测试用例 (wo_slice)")
                while len(unit_tests) < _target:
                    self.logger.info(f"▶ [{_round+1}/{_target}] 生成 Test #{_round+1}")
                    self.logger.info(f"Generating init unit test round {_round + 1}")
                    remaining = _target - len(unit_tests)
                    direction_3['step_id'] = _round
                    unit_tests += self.generate_code(
                        direction_3, str(_round), chatter,
                        os.path.join(log_dir, "steps"),
                        init_temp=0.5, capacity=remaining)
                    _round += 1
                unit_tests = unit_tests[:_target]

        else:
            direction_3['has_missing_lines'] = True
            slice_info_path = os.path.join(log_dir, "slice_fixing", "slice_result.jsonl")
            assert os.path.exists(slice_info_path)
            slices_to_fix = []
            with open(slice_info_path, 'r') as file:
                slices_to_fix = [json.loads(line) for line in file.read().strip().split("\n")]
            if not info or 'method_graphs' not in info:
                self.logger.error("No method_graphs in info for fixing mode")
                return None
            method_lines = info['method_graphs'][0]['src_lines']

            def _build_line(_line_map, _line_no):
                return f"{_line_no}:{_line_map[str(_line_no)]}" if str(_line_no) in _line_map else ""

            self.logger.info(f"▶ Phase 1: 生成修复测试用例")
            for idx, slice_to_fix in enumerate(slices_to_fix):
                missing_lines     = [_build_line(method_lines, i) for i in slice_to_fix['missing_lines']]
                condition         = _build_line(method_lines, slice_to_fix['slicing_criteria'][0])
                data_slicers      = [_build_line(method_lines, i) for i in slice_to_fix['sliced_lines']]
                data_dependencies = [_build_line(method_lines, i) for i in slice_to_fix['data_def']]
                ctl_dependencies  = [
                    _build_line(method_lines, i[0]) +
                    f" # The predicate should be {'True' if i[1] != 0 else 'False'}"
                    for i in slice_to_fix['ctl_deps']]
                numbered_fm       = [_build_line(method_lines, i) for i in method_lines]
                direction_3['missing_lines']    = "\n".join(missing_lines)
                direction_3['condition']         = condition
                direction_3['data_dependencies'] = '\n'.join(data_dependencies)
                direction_3['data_slicers']      = '\n'.join(data_slicers)
                direction_3['ctl_dep']           = '\n'.join(ctl_dependencies)
                direction_3['numbered_fm']       = '\n'.join(numbered_fm)
                self.logger.info(f"▶ [{idx+1}/{len(slices_to_fix)}] 生成 Test #{idx+1}")
                self.logger.info(f"Generating fixing unit test for slice {idx}")
                unit_tests += self.generate_code(direction_3, f"Fix{idx}", chatter,
                                                  os.path.join(log_dir, "slice_fixing"))

        return unit_tests