"""
procedures/fix_code.py  — 修复版

变更：
  1. max_trial 改从 config.MAX_REPAIR_TRIALS 读取（不再 hardcode 10）
  2. 其余逻辑与原版一致
"""

import glob
import os.path
import shutil
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

try:
    from pymongo.collection import Collection
except ImportError:
    Collection = object

from generator.open_generator import OpenGenerator
from procedures.basic_procedure import BasicProcedure, generate_code
from utils import test_runner
from utils.code_editor import remove_assertion
from utils.config import MAX_REPAIR_TRIALS  # ← 新增导入
from utils.config import *
from utils.report import jacoco_analysis


def remove_assertion_retest(step_workspace, put_path) -> bool:
    runtime_error_path = os.path.join(step_workspace, "temp", "runtime_error.txt")
    if os.path.exists(runtime_error_path):
        with open(runtime_error_path, "r") as file:
            runtime_error = file.read()
        if "AssertionFailedError" in runtime_error:
            temp_files = os.listdir(os.path.join(step_workspace, "temp").__str__())
            test_file_path = None
            for file_name in temp_files:
                if file_name.endswith(".java"):
                    test_file_path = os.path.join(step_workspace, "temp", file_name)
            if test_file_path is None:
                return False
            with open(test_file_path, "r") as file_handler:
                failed_test = file_handler.read().strip()
            assertion_removed_test = remove_assertion(failed_test)
            with open(test_file_path, "w") as java_file:
                java_file.write(assertion_removed_test)
            shutil.rmtree(os.path.join(step_workspace, "runtemp"))
            os.remove(runtime_error_path)
            task = test_runner.TestRunner(step_workspace, put_path, step_workspace, "jacoco")
            return task.start_single_test()
    return False


def coverage_check(slice_work_space, signature, package, class_name):
    assert os.path.exists(os.path.join(slice_work_space, 'runtemp', 'jacoco.exec'))
    if not os.path.exists(os.path.join(slice_work_space, "cov_check_dir")):
        return None
    return jacoco_analysis(os.path.join(slice_work_space, "cov_check_dir"),
                           package, class_name, signature)


def advanced_run_check(slice_workspace, put_path, signature, package, class_name):
    task = test_runner.TestRunner(slice_workspace, put_path, slice_workspace, "jacoco")
    test_passed = task.start_single_test()
    if not test_passed:
        test_passed = remove_assertion_retest(slice_workspace, put_path)

    if test_passed:
        coverage_analysis = coverage_check(slice_workspace, signature, package, class_name)
        if coverage_analysis is None:
            test_passed = False
            with open(os.path.join(slice_workspace, "temp", "run_check_fail.txt"), "w") as file:
                file.write(f"Failed to run check for {signature}.")
        else:
            for key in coverage_analysis:
                coverage_str = coverage_analysis[key].strip("%").lower()
                if coverage_str in ['n/a', 'na', '']:
                    coverage_value = 0.0
                else:
                    try:
                        coverage_value = float(coverage_str)
                    except ValueError:
                        coverage_value = 0.0
                if coverage_value == 0:
                    test_passed = False
                    with open(os.path.join(slice_workspace, "temp", "runtime_error.txt"), "w") as file:
                        file.write(f"Runtime error: {key} is 0%. The test method is not invoked")
                    break
    return test_passed


class TestFixer(BasicProcedure):
    def __init__(self, prompt_root, system_template_file_name, fixer_template_file_name):
        super(TestFixer, self).__init__(prompt_root, system_template_file_name,
                                        fixer_template_file_name, "fixer")

    def init_test(self, log_dir, put_path, collection: Collection, fixing=False):
        code_dir = "steps" if not fixing else "slice_fixing"
        assert os.path.exists(log_dir)
        assert os.path.exists(os.path.join(log_dir, code_dir))
        os.makedirs(os.path.join(log_dir, "test_cases"), exist_ok=True)
        os.makedirs(os.path.join(log_dir, "temp"), exist_ok=True)
        raw_info = collection.find_one({"table_name": "raw_data"})
        assert raw_info is not None

        test_cases = [os.path.basename(path)
                      for path in glob.glob(os.path.join(log_dir, code_dir, "*.java"),
                                            recursive=False)]
        failed_test_cases = []
        for test_case in test_cases:
            target_dir = os.path.join(log_dir, "fixing", test_case[:-len(".java")], "0", "temp")
            if os.path.exists(os.path.dirname(target_dir)):
                self.logger.warning(f"Target dir {os.path.dirname(target_dir)} exists. Skipping...")
                continue
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy(os.path.join(log_dir, code_dir, test_case), target_dir)
            if os.path.exists(os.path.join(log_dir, code_dir,
                                            test_case.replace(".java", ".condition.txt"))):
                shutil.copy(os.path.join(log_dir, code_dir,
                                          test_case.replace(".java", ".condition.txt")),
                            os.path.dirname(os.path.dirname(target_dir)))
            test_passed = advanced_run_check(
                os.path.dirname(target_dir), put_path,
                raw_info['parameters'],
                raw_info['package'].replace("package ", "").replace(";", ""),
                raw_info['class_name'])
            if not test_passed:
                failed_test_cases.append(test_case)

        if failed_test_cases:
            self.logger.warning(f"{len(failed_test_cases)} / {len(test_cases)} failed")

        failed_test_cases = [t[:-len('.java')] for t in failed_test_cases]
        output_file = os.path.join(log_dir, "fixing", "init_test_failed.txt")
        with open(output_file, "a") as file:
            if os.path.exists(output_file) and os.stat(output_file).st_size > 0:
                file.write('\n')
            file.write("\n".join(failed_test_cases))
        return failed_test_cases

    def single_unitest_fix(self, log_dir, collection: Collection, unitest_failed, put_path,
                           chatter: OpenGenerator) -> bool:
        unitest_root = os.path.join(log_dir, "fixing", unitest_failed)
        assert os.path.exists(unitest_root)
        existing_trials = [int(trial_id) for trial_id in os.listdir(unitest_root.__str__())
                           if os.path.isdir(os.path.join(unitest_root.__str__(), trial_id))]
        start_trial_to_fix = max(existing_trials)
        start_error = glob.glob(
            os.path.join(unitest_root.__str__(), str(start_trial_to_fix), "temp", "*error.txt"))
        if len(start_error) == 0:
            return True

        # ── 从 config 读取最大修复轮数 ────────────────────────────────
        max_trial = MAX_REPAIR_TRIALS  # 原来 hardcode 10，现在从 config 读取

        raw_info = collection.find_one({"table_name": "raw_data"})
        dir_3    = collection.find_one({"table_name": "direction_3"})
        assert raw_info is not None
        assert dir_3 is not None
        is_not_public = not raw_info['is_public']
        test_fixed = False
        init_temperature = 0.0

        self.logger.info(f"[FIX] Starting fix for test: {unitest_failed}, max_trial={max_trial}")

        if os.path.exists(os.path.join(unitest_root.__str__(),
                                        f"{unitest_failed}.condition.txt")):
            with open(os.path.join(unitest_root.__str__(),
                                   f"{unitest_failed}.condition.txt"), "r") as file:
                block = file.read()
        else:
            block = ""

        src_trial = start_trial_to_fix
        for tgt_trial in range(start_trial_to_fix + 1, max_trial + 1):
            self.logger.info(f"[FIX] Trial {tgt_trial}/{max_trial} for {unitest_failed}")
            src_trial_workspace = os.path.join(unitest_root.__str__(), str(src_trial))
            tgt_trial_workspace = os.path.join(unitest_root.__str__(), str(tgt_trial))

            with open(os.path.join(src_trial_workspace, "temp",
                                   unitest_failed + ".java"), "r") as file:
                unitest_to_fix = file.read().strip()
            numbered_unitest_to_fix = '\n'.join(
                [f"{idx+1}: {line}" for idx, line in enumerate(unitest_to_fix.split('\n'))])

            compile_error_path = os.path.join(src_trial_workspace, "temp", "compile_error.txt")
            runtime_error_path = os.path.join(os.path.dirname(compile_error_path), "runtime_error.txt")
            run_check_fail     = os.path.join(os.path.dirname(compile_error_path), 'run_check_fail.txt')

            if os.path.exists(compile_error_path):
                error_type = "compile_error"
                with open(compile_error_path, "r") as file:
                    error_msg = file.read()
            elif os.path.exists(runtime_error_path):
                error_type = "runtime_error"
                with open(runtime_error_path, "r") as file:
                    error_msg = file.read()
            elif os.path.exists(run_check_fail):
                self.logger.error(f"Run check failed for {log_dir}")
                return False
            else:
                self.logger.error("No error found?")
                return False

            error_info = {
                'unit_test':       numbered_unitest_to_fix,
                'error_message':   '\n'.join([error_type, error_msg]),
                'error_type':      error_type,
                'is_not_public':   is_not_public,
                'class_name':      dir_3['class_name'],
                'method_identifier': raw_info['method_name'],
                'block':           block,
            }
            if 'example' in dir_3:
                error_info['example'] = dir_3['example']

            extracted_code = unitest_to_fix.strip()
            response = "Failed to generate any new code"
            try:
                extracted_code, response = generate_code(
                    chatter,
                    self.generate_template.render(error_info),
                    self.system_template.render(dir_3),
                    init_temperature=init_temperature,
                    cls_name=unitest_failed,
                    prev_code=unitest_to_fix.strip())
            except RuntimeError as e:
                print(e)

            os.makedirs(os.path.join(tgt_trial_workspace, "temp"), exist_ok=True)
            with open(os.path.join(tgt_trial_workspace, "temp",
                                   unitest_failed + ".java"), "w") as file:
                file.write(extracted_code)
            with open(os.path.join(tgt_trial_workspace, "temp", "system_prompt.txt"), "w") as file:
                file.write(self.system_template.render(dir_3))
            with open(os.path.join(tgt_trial_workspace, "temp", "generate_prompt.txt"), "w") as file:
                file.write(self.generate_template.render(error_info))
            with open(os.path.join(tgt_trial_workspace, "temp", "response.txt"), "w") as file:
                file.write(response)

            test_fixed = advanced_run_check(
                tgt_trial_workspace, put_path,
                raw_info['parameters'],
                raw_info['package'].replace("package ", "").replace(";", ""),
                raw_info['class_name'])

            if test_fixed:
                self.logger.info(f"[FIX] SUCCESS: {unitest_failed} fixed at trial {tgt_trial}")
                break
            else:
                self.logger.debug(f"[FIX] Trial {tgt_trial} failed for {unitest_failed}")
            init_temperature = 0.4 if extracted_code.strip() == unitest_to_fix.strip() else 0.0
            src_trial = tgt_trial

        if not test_fixed:
            self.logger.warning(f"[FIX] FAILED: {unitest_failed} not fixed after {max_trial} trials")
        return test_fixed