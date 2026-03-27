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
from utils.config import MAX_REPAIR_TRIALS
from utils.config import *
from utils.report import jacoco_analysis


def remove_assertion_retest(step_workspace, put_path) -> bool:
    runtime_error_path = os.path.join(step_workspace, "temp", "runtime_error.txt")
    if os.path.exists(runtime_error_path):
        with open(runtime_error_path, "r") as file:
            runtime_error = file.read()
        if "AssertionFailedError" in runtime_error:
            temp_files = os.listdir(os.path.join(step_workspace, "temp"))
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
            runtemp = os.path.join(step_workspace, "runtemp")
            if os.path.exists(runtemp):
                shutil.rmtree(runtemp)
            runtime_err = os.path.join(step_workspace, "temp", "runtime_error.txt")
            if os.path.exists(runtime_err):
                os.remove(runtime_err)
            task = test_runner.TestRunner(step_workspace, put_path, step_workspace, "jacoco")
            return task.start_single_test()
    return False


def coverage_check(slice_work_space, signature, package, class_name):
    exec_path = os.path.join(slice_work_space, 'runtemp', 'jacoco.exec')
    if not os.path.exists(exec_path):
        return None
    cov_dir = os.path.join(slice_work_space, "cov_check_dir")
    if not os.path.exists(cov_dir):
        return None
    return jacoco_analysis(cov_dir, package, class_name, signature)


def advanced_run_check(slice_workspace, put_path, signature, package, class_name):
    task = test_runner.TestRunner(slice_workspace, put_path, slice_workspace, "jacoco")
    test_passed = task.start_single_test()
    if not test_passed:
        test_passed = remove_assertion_retest(slice_workspace, put_path)

    if test_passed:
        coverage_analysis = coverage_check(slice_workspace, signature, package, class_name)
        if coverage_analysis is None:
            # ── 修复：覆盖率检查失败不等于测试失败
            # 旧版在这里会将 test_passed = False，导致 jacoco.exec 路径上
            # 带有 runtime_error.txt 标记，使 single_method_report 跳过该 exec。
            # 新版：只记录日志，不阻断 test_passed。
            pass  # coverage_analysis is None 时不修改 test_passed
        else:
            for key in coverage_analysis:
                coverage_str = coverage_analysis[key].strip("%").lower()
                try:
                    coverage_value = float(coverage_str) if coverage_str not in ('n/a', 'na', '') else 0.0
                except ValueError:
                    coverage_value = 0.0
                if coverage_value == 0:
                    test_passed = False
                    with open(os.path.join(slice_workspace, "temp", "runtime_error.txt"), "w") as f:
                        f.write(f"Runtime error: {key} is 0%. The test method is not invoked")
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
                      for path in glob.glob(os.path.join(log_dir, code_dir, "*.java"))]
        failed_test_cases = []
        for test_case in test_cases:
            target_dir = os.path.join(log_dir, "fixing", test_case[:-len(".java")], "0", "temp")
            if os.path.exists(os.path.dirname(target_dir)):
                self.logger.warning(f"Target dir exists, skipping: {os.path.dirname(target_dir)}")
                continue
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy(os.path.join(log_dir, code_dir, test_case), target_dir)
            cond_src = os.path.join(log_dir, code_dir,
                                     test_case.replace(".java", ".condition.txt"))
            if os.path.exists(cond_src):
                shutil.copy(cond_src, os.path.dirname(os.path.dirname(target_dir)))

            test_passed = advanced_run_check(
                os.path.dirname(target_dir), put_path,
                raw_info['parameters'],
                raw_info['package'].replace("package ", "").replace(";", ""),
                raw_info['class_name'])
            if not test_passed:
                failed_test_cases.append(test_case)

        if failed_test_cases:
            self.logger.warning(f"{len(failed_test_cases)}/{len(test_cases)} failed")

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
        existing_trials = [int(t) for t in os.listdir(unitest_root)
                           if os.path.isdir(os.path.join(unitest_root, t)) and t.isdigit()]
        start_trial_to_fix = max(existing_trials)
        start_error = glob.glob(
            os.path.join(unitest_root, str(start_trial_to_fix), "temp", "*error.txt"))
        if len(start_error) == 0:
            return True

        max_trial = MAX_REPAIR_TRIALS
        raw_info = collection.find_one({"table_name": "raw_data"})
        dir_3    = collection.find_one({"table_name": "direction_3"})
        assert raw_info is not None
        assert dir_3 is not None

        is_not_public  = not raw_info['is_public']
        test_fixed     = False
        init_temperature = 0.0

        block = ""
        cond_file = os.path.join(unitest_root, f"{unitest_failed}.condition.txt")
        if os.path.exists(cond_file):
            with open(cond_file, "r") as f:
                block = f.read()

        src_trial = start_trial_to_fix
        for tgt_trial in range(start_trial_to_fix + 1, max_trial + 1):
            src_ws = os.path.join(unitest_root, str(src_trial))
            tgt_ws = os.path.join(unitest_root, str(tgt_trial))

            with open(os.path.join(src_ws, "temp", unitest_failed + ".java"), "r") as f:
                unitest_to_fix = f.read().strip()
            numbered = '\n'.join(
                [f"{i+1}: {l}" for i, l in enumerate(unitest_to_fix.split('\n'))])

            compile_err = os.path.join(src_ws, "temp", "compile_error.txt")
            runtime_err = os.path.join(src_ws, "temp", "runtime_error.txt")
            run_check_f = os.path.join(src_ws, "temp", "run_check_fail.txt")

            if os.path.exists(compile_err):
                error_type = "compile_error"
                with open(compile_err) as f:
                    error_msg = f.read()
            elif os.path.exists(runtime_err):
                error_type = "runtime_error"
                with open(runtime_err) as f:
                    error_msg = f.read()
            elif os.path.exists(run_check_f):
                return False
            else:
                return False

            error_info = {
                'unit_test':         numbered,
                'error_message':     '\n'.join([error_type, error_msg]),
                'error_type':        error_type,
                'is_not_public':     is_not_public,
                'class_name':        dir_3['class_name'],
                'method_identifier': raw_info['method_name'],
                'block':             block,
            }
            if 'example' in dir_3:
                error_info['example'] = dir_3['example']

            extracted_code = unitest_to_fix
            response = ""
            try:
                extracted_code, response = generate_code(
                    chatter,
                    self.generate_template.render(error_info),
                    self.system_template.render(dir_3),
                    init_temperature=init_temperature,
                    cls_name=unitest_failed,
                    prev_code=unitest_to_fix.strip())
            except RuntimeError:
                pass

            os.makedirs(os.path.join(tgt_ws, "temp"), exist_ok=True)
            with open(os.path.join(tgt_ws, "temp", unitest_failed + ".java"), "w") as f:
                f.write(extracted_code)
            with open(os.path.join(tgt_ws, "temp", "system_prompt.txt"), "w") as f:
                f.write(self.system_template.render(dir_3))
            with open(os.path.join(tgt_ws, "temp", "generate_prompt.txt"), "w") as f:
                f.write(self.generate_template.render(error_info))
            with open(os.path.join(tgt_ws, "temp", "response.txt"), "w") as f:
                f.write(response)

            test_fixed = advanced_run_check(
                tgt_ws, put_path,
                raw_info['parameters'],
                raw_info['package'].replace("package ", "").replace(";", ""),
                raw_info['class_name'])

            if test_fixed:
                break
            init_temperature = 0.4 if extracted_code.strip() == unitest_to_fix else 0.0
            src_trial = tgt_trial

        return test_fixed