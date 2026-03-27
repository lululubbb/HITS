"""
utils/test_runner.py  — HITS full-featured test runner

Replaces the old utils/test_runner.py with comprehensive coverage, compile,
exec, coveragedetail, coveragemethod, final_scores, final_scores2, status,
bug_revealing, similarity CSV outputs — matching the uploaded test_runner.py.

Key changes from the HITS version:
  - Uses mvn jacoco:report (not jacoco-cli report) to produce jacoco.xml
  - Supports per-test exec files (jacoco_{testname}.exec) via jacoco_destfile
  - Produces: status, coverage, coveragedetail, coveragemethod,
              final_scores, final_scores2 CSVs
  - All output files placed under the tests* directory
  - Integrates with bug_revealing and similarity CSVs already present
"""

import glob
import logging
import os
import re
import shutil
import subprocess
import csv
import tempfile
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)
from utils.config import *


def parse_root_pom(pom_dir):
    pom_file = os.path.join(pom_dir, 'pom.xml')
    if not os.path.exists(pom_file):
        return None
    poms = [pom_file]
    with open(pom_file, 'r') as file:
        pom_soup = BeautifulSoup(file, 'lxml-xml')
        modules_tags = pom_soup.select("project > modules")
        for modules_tag in modules_tags:
            modules = modules_tag.find_all('module', recursive=False)
            for module in modules:
                if module.string != "":
                    sub_modules = parse_root_pom(os.path.join(pom_dir, module.string))
                    if sub_modules is not None:
                        poms += sub_modules
    return poms


class TestRunner:

    def __init__(self, test_path, target_path, output_path=None, tool="jacoco", debug=False):
        """
        :param test_path:   tests* directory (contains test_cases/)
        :param target_path: PUT project root
        :param output_path: unused (kept for compat with old HITS callers)
        :param tool:        "jacoco" (only supported value)
        :param debug:       verbose mode
        """
        self.coverage_tool = tool
        self.test_path = test_path
        self.target_path = target_path
        self.output_path = output_path or test_path
        self.debug = debug

        # Preprocess
        self.dependencies = self.make_dependency()
        self.build_dir_name = "target/classes"
        self.build_dir = self.process_single_repo()

        self.COMPILE_ERROR = 0
        self.TEST_RUN_ERROR = 0
        self.SYNTAX_TOTAL = 0
        self.SYNTAX_ERROR = 0
        # optional per-test jacoco exec destination (set inside run_all_tests loop)
        self.jacoco_destfile = None

        self.logger = logging.getLogger('test_runner')

        if output_path and not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        # For compat with old HITS code that expects self.modules
        self.modules = parse_root_pom(target_path) or []

    # ──────────────────────────────────────────────────────────────────────
    # Public entry points
    # ──────────────────────────────────────────────────────────────────────

    def start_single_test(self):
        temp_dir = os.path.join(self.test_path, "temp")
        compiled_test_dir = os.path.join(self.test_path, "runtemp")
        os.makedirs(compiled_test_dir, exist_ok=True)
        try:
            self.instrument(compiled_test_dir, compiled_test_dir)
            test_file = os.path.abspath(glob.glob(temp_dir + '/*.java')[0])
            compiler_output = os.path.join(temp_dir, 'compile_error')
            test_output = os.path.join(temp_dir, 'runtime_error')
            if not self.run_single_test(test_file, compiled_test_dir, compiler_output, test_output):
                return False
            else:
                self.report(compiled_test_dir, os.path.join(self.test_path, "cov_check_dir"))
        except Exception as e:
            print(e)
            return False
        return True

    def start_all_test(self):
        """
        Entry point called by run_tests.py / Task.all_test().
        If test_path already has a test_cases/ sub-dir, run in-place.
        Otherwise create a timestamped tests%* directory under target_path.
        """
        if (os.path.isdir(self.test_path) and
                os.path.isdir(os.path.join(self.test_path, 'test_cases'))):
            tests_dir = self.test_path
            compiler_output_dir = os.path.join(tests_dir, "compiler_output")
            test_output_dir = os.path.join(tests_dir, "test_output")
            report_dir = os.path.join(tests_dir, "report")
            compiler_output = os.path.join(compiler_output_dir, "CompilerOutput")
            test_output = os.path.join(test_output_dir, "TestOutput")
            compiled_test_dir = os.path.join(tests_dir, "tests_ChatGPT")
            logs_dir = os.path.join(tests_dir, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            logs = self._make_logs(logs_dir)
            return self.run_all_tests(tests_dir, compiled_test_dir,
                                      compiler_output, test_output, report_dir, logs)

        date = datetime.now().strftime("%Y%m%d%H%M%S")
        tests_dir = os.path.join(self.target_path, f"tests%{date}")
        compiler_output_dir = os.path.join(tests_dir, "compiler_output")
        test_output_dir = os.path.join(tests_dir, "test_output")
        report_dir = os.path.join(tests_dir, "report")
        compiler_output = os.path.join(compiler_output_dir, "CompilerOutput")
        test_output = os.path.join(test_output_dir, "TestOutput")
        compiled_test_dir = os.path.join(tests_dir, "tests_ChatGPT")
        self.copy_tests(tests_dir)
        logs_dir = os.path.join(tests_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        logs = self._make_logs(logs_dir)
        return self.run_all_tests(tests_dir, compiled_test_dir,
                                  compiler_output, test_output, report_dir, logs)

    # ──────────────────────────────────────────────────────────────────────
    # Logs
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_logs(logs_dir):
        paths = {
            "syntax":          os.path.join(logs_dir, "syntax.log"),
            "compile":         os.path.join(logs_dir, "compile.log"),
            "exec":            os.path.join(logs_dir, "test_exec.log"),
            "coverage":        os.path.join(logs_dir, "coverage.log"),
            "execution_stats": os.path.join(logs_dir, "execution_stats.log"),
            "compile_failed":  os.path.join(logs_dir, "compile_failed.txt"),
            "diagnosis":       os.path.join(logs_dir, "diagnosis.log"),
        }
        for p in paths.values():
            open(p, 'w').close()
        with open(paths["diagnosis"], 'w', encoding='utf-8') as f:
            f.write("# diagnosis.log\n")
            f.write("# status: compile_fail | exec_fail | exec_timeout | exec_ok\n")
            f.write("# ============================================================\n\n")
        return paths

    # ──────────────────────────────────────────────────────────────────────
    # Target class / focal method resolution
    # ──────────────────────────────────────────────────────────────────────

    def _resolve_target_class(self, tests_dir):
        """Return simple class name of modified class (e.g. 'CSVParser')."""
        project_root = self.target_path

        meta_file = os.path.join(project_root, 'modified_classes.src')
        if os.path.exists(meta_file):
            try:
                with open(meta_file) as f:
                    line = f.readline().strip()
                if line:
                    return line.split('.')[-1]
            except Exception:
                pass

        prop_file = os.path.join(project_root, 'defects4j.build.properties')
        if os.path.exists(prop_file):
            try:
                with open(prop_file) as f:
                    for l in f:
                        if 'd4j.classes.modified' in l and '=' in l:
                            val = l.split('=', 1)[1].strip()
                            first_class = val.split(',')[0].strip()
                            if first_class:
                                return first_class.split('.')[-1]
            except Exception:
                pass

        tc_dir = os.path.join(tests_dir, 'test_cases')
        if os.path.isdir(tc_dir):
            for fname in os.listdir(tc_dir):
                if fname.endswith('Test.java'):
                    m = re.match(r'^(.+?)_[^_]+_\d+Test\.java$', fname)
                    if m:
                        return m.group(1)
                    return fname.split('_')[0]
        return ''

    def _resolve_focal_method(self, tests_dir):
        try:
            raw_data_dir = os.path.join(dataset_dir, "raw_data")
            if raw_data_dir and os.path.isdir(raw_data_dir):
                for fname in sorted(os.listdir(raw_data_dir)):
                    if fname.endswith('.json') and '%' in fname:
                        parts = fname.split('%')
                        if len(parts) >= 4:
                            method_candidate = parts[3].strip()
                            if method_candidate and not method_candidate.isdigit():
                                return method_candidate
        except Exception:
            pass

        try:
            tc_dir = os.path.join(tests_dir, 'test_cases')
            if os.path.isdir(tc_dir):
                for fname in sorted(os.listdir(tc_dir)):
                    if fname.endswith('Test.java'):
                        m = re.match(r'^.+?_([^_]+)_\d+Test\.java$', fname)
                        if m:
                            mid = m.group(1)
                            if not mid.isdigit():
                                return mid
                            mid_map = self._build_mid_to_method_map(tests_dir)
                            name = mid_map.get(mid, '')
                            if name:
                                return name
                            return ''
        except Exception:
            pass
        return ''

    def _find_raw_data_dir(self, tests_dir: str) -> str:
        return os.path.join(dataset_dir, "raw_data")

    def _parse_test_name(self, tc_name: str):
        try:
            m = re.match(r'^(?P<class>.*)_(?P<mid>[^_]+)_(?P<seq>\d+)Test$', tc_name)
            if m:
                return m.group('class'), m.group('mid'), m.group('seq')
        except Exception:
            pass
        return tc_name, '', ''

    def _group_from_test_class(self, tc_name: str):
        cls, mid, seq = self._parse_test_name(tc_name)
        if mid:
            return f"{cls}_{mid}"
        m = re.match(r'^(.*?_)(\d+)_\d+Test$', tc_name)
        if m:
            return m.group(1).rstrip('_')
        parts = tc_name.rsplit('_', 2)
        if len(parts) >= 3:
            return parts[0] + '_' + parts[1]
        return tc_name

    def _focal_method_from_group(self, grp: str, mid_to_name: dict = None,
                                  global_focal: str = '') -> str:
        name, _ = self._focal_info_from_group(grp, mid_to_name, global_focal)
        return name

    def _focal_info_from_group(self, grp: str, mid_to_name: dict = None,
                                global_focal: str = '',
                                mid_to_focal_map: dict = None) -> tuple:
        if '_' not in grp:
            return global_focal or '', None
        mid = grp.split('_')[-1]
        if not mid.isdigit():
            return mid, None
        if mid_to_focal_map:
            info = mid_to_focal_map.get(mid)
            if info:
                return info.get('name', ''), info.get('descriptor')
        if mid_to_name:
            name = mid_to_name.get(mid)
            if name:
                return name, None
        return global_focal or '', None

    def _is_focal_method_match(self, method_name: str, focal_name: str,
                               modified_class_name: str,
                               focal_descriptor: str = None,
                               method_desc: str = None) -> bool:
        if not focal_name:
            return False
        if method_name == '<init>' and modified_class_name:
            simple_class = modified_class_name.split('.')[-1].split('$')[0]
            if focal_name in (modified_class_name, simple_class):
                if focal_descriptor and method_desc:
                    return method_desc.startswith(focal_descriptor)
                return True
        if method_name != focal_name:
            return False
        if focal_descriptor and method_desc:
            return method_desc.startswith(focal_descriptor)
        return True

    def _merge_jacoco_execs(self, exec_paths: list, out_exec: str) -> bool:
        valid_execs = [p for p in exec_paths
                       if p and os.path.exists(p) and os.path.getsize(p) > 0]
        if not valid_execs:
            return False
        if len(valid_execs) == 1:
            try:
                os.makedirs(os.path.dirname(out_exec), exist_ok=True)
                shutil.copy2(valid_execs[0], out_exec)
                return os.path.exists(out_exec) and os.path.getsize(out_exec) > 0
            except Exception:
                return False
        cmd = ["java", "-jar", JACOCO_CLI, "merge",
               *valid_execs, "--destfile", out_exec]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
            return os.path.exists(out_exec) and os.path.getsize(out_exec) > 0
        except Exception:
            return False

    def _compute_focal_totals_from_merged_jacoco(self, groups: dict,
                                                 modified_class_name: str,
                                                 mid_to_name: dict,
                                                 focal_method: str,
                                                 mid_to_focal_map: dict = None) -> dict:
        result = {}
        exec_base_dir = os.path.join(self.test_path, 'group_exec')
        report_base_dir = os.path.join(self.test_path, 'group_report')

        for grp_k, members_k in groups.items():
            focal_name_k, focal_desc_k = self._focal_info_from_group(
                grp_k, mid_to_name, focal_method, mid_to_focal_map)
            if not focal_name_k:
                result[grp_k] = {
                    'f_line_total': None, 'f_line_cov': None,
                    'f_branch_total': None, 'f_branch_cov': None,
                }
                continue

            exec_paths = [m.get('exec_file') for m in members_k]
            grp_exec = os.path.join(exec_base_dir, f"{grp_k}.exec")
            os.makedirs(os.path.dirname(grp_exec), exist_ok=True)
            merged_ok = self._merge_jacoco_execs(exec_paths, grp_exec)

            if not merged_ok:
                result[grp_k] = {
                    'f_line_total': None, 'f_line_cov': None,
                    'f_branch_total': None, 'f_branch_cov': None,
                }
                continue

            grp_report_dir = os.path.join(report_base_dir, grp_k)
            try:
                os.makedirs(grp_report_dir, exist_ok=True)
                self.report(grp_report_dir, grp_report_dir,
                             jacoco_exec_override=grp_exec)
                global_xml = os.path.join(
                    self.target_path, 'target', 'site', 'jacoco', 'jacoco.xml')
                grp_xml = os.path.join(grp_report_dir, 'jacoco.xml')
                if os.path.exists(global_xml):
                    try:
                        shutil.copy2(global_xml, grp_xml)
                    except Exception:
                        pass
            except Exception:
                pass

            grp_xml = os.path.join(grp_report_dir, 'jacoco.xml')
            if not os.path.exists(grp_xml):
                grp_xml = os.path.join(
                    self.target_path, 'target', 'site', 'jacoco', 'jacoco.xml')

            flc = flt = fbc = fbt = 0
            found = False

            try:
                tree = ET.parse(grp_xml)
                root = tree.getroot()
            except Exception:
                result[grp_k] = {
                    'f_line_total': None, 'f_line_cov': None,
                    'f_branch_total': None, 'f_branch_cov': None,
                }
                continue

            for cls_elem in root.findall('.//class'):
                cname_k = cls_elem.attrib.get('name', '')
                simple_k = cname_k.split('/')[-1].split('$')[0]
                if modified_class_name and not (
                    simple_k == modified_class_name or
                    cname_k.endswith('/' + modified_class_name)
                ):
                    continue

                for meth_elem in cls_elem.findall('method'):
                    mn = meth_elem.get('name', '')
                    md = meth_elem.get('desc', '')
                    if not self._is_focal_method_match(
                            mn, focal_name_k, modified_class_name,
                            focal_descriptor=focal_desc_k,
                            method_desc=md):
                        continue
                    found = True
                    for cnt in meth_elem.findall('counter'):
                        ct = cnt.attrib.get('type', '')
                        cov = int(cnt.attrib.get('covered', 0))
                        mis = int(cnt.attrib.get('missed', 0))
                        if ct == 'LINE':
                            flc += cov
                            flt += cov + mis
                        elif ct == 'BRANCH':
                            fbc += cov
                            fbt += cov + mis

            result[grp_k] = {
                'f_line_total': flt if found else None,
                'f_line_cov': flc if found else None,
                'f_branch_total': fbt if found else None,
                'f_branch_cov': fbc if found else None,
            }

        return result

    # ──────────────────────────────────────────────────────────────────────
    # JVM descriptor helpers
    # ──────────────────────────────────────────────────────────────────────

    _JAVA_PRIMITIVE_MAP = {
        'int': 'I', 'long': 'J', 'double': 'D', 'float': 'F',
        'boolean': 'Z', 'byte': 'B', 'char': 'C', 'short': 'S', 'void': 'V',
    }

    @classmethod
    def _java_type_to_jvm(cls, java_type: str) -> str:
        java_type = java_type.strip()
        java_type = re.sub(r'<.*>', '', java_type).strip()
        array_prefix = ''
        while java_type.endswith('[]'):
            array_prefix += '['
            java_type = java_type[:-2].strip()
        if java_type in cls._JAVA_PRIMITIVE_MAP:
            return array_prefix + cls._JAVA_PRIMITIVE_MAP[java_type]
        jvm_class = java_type.replace('.', '/')
        return array_prefix + 'L' + jvm_class + ';'

    @classmethod
    def _params_to_jvm_descriptor_prefix(cls, params: list) -> str:
        if not params:
            return '('
        return '(' + ''.join(cls._java_type_to_jvm(p) for p in params)

    def _safe_params_to_descriptor(self, param_types: list):
        primitives = set(self._JAVA_PRIMITIVE_MAP.keys())
        result_parts = []
        for t in param_types:
            t = t.strip()
            base = t
            array_prefix = ''
            while base.endswith('[]'):
                array_prefix += '['
                base = base[:-2].strip()
            if base in primitives:
                result_parts.append(array_prefix + self._JAVA_PRIMITIVE_MAP[base])
            else:
                return None
        return '(' + ''.join(result_parts)

    def _build_mid_to_method_map(self, tests_dir: str) -> dict:
        return {mid: info['name']
                for mid, info in self._build_mid_to_focal_map(tests_dir).items()}

    def _build_mid_to_focal_map(self, tests_dir: str) -> dict:
        import json as _json
        result: dict = {}
        try:
            raw_data_dir = os.path.join(dataset_dir, "raw_data")
            if not os.path.isdir(raw_data_dir):
                return result

            for fname in sorted(os.listdir(raw_data_dir)):
                if not fname.endswith(".json") or "%" not in fname:
                    continue
                parts = fname.split("%")
                if len(parts) < 4:
                    continue
                mid = parts[0].strip()
                name_from_fname = parts[3].strip()
                if not mid.isdigit() or not name_from_fname or name_from_fname.isdigit():
                    continue

                entry = {'name': name_from_fname, 'descriptor': None, 'params': None}
                json_path = os.path.join(raw_data_dir, fname)
                try:
                    with open(json_path, 'r', encoding='utf-8', errors='replace') as _jf:
                        raw_json = _jf.read(65536)
                    data = _json.loads(raw_json)
                    method_name = (data.get('method_name') or
                                   data.get('focal_method') or name_from_fname)
                    entry['name'] = method_name

                    jvm_desc = (data.get('method_descriptor') or
                                data.get('focal_method_descriptor') or
                                data.get('descriptor'))
                    if jvm_desc and isinstance(jvm_desc, str) and jvm_desc.startswith('('):
                        paren_close = jvm_desc.find(')')
                        desc_prefix = (jvm_desc[:paren_close + 1]
                                       if paren_close >= 0 else jvm_desc)
                        entry['descriptor'] = desc_prefix
                        result[mid] = entry
                        continue

                    for params_key in ('method_params', 'param_types', 'focal_method_params'):
                        params_raw = data.get(params_key)
                        if isinstance(params_raw, list):
                            param_types = []
                            for p in params_raw:
                                if isinstance(p, dict):
                                    t = (p.get('type') or p.get('param_type') or '')
                                    t = t.strip().split()[0] if t.strip() else ''
                                    param_types.append(t)
                                elif isinstance(p, str):
                                    param_types.append(
                                        p.strip().split()[0] if p.strip() else '')
                            param_types = [t for t in param_types if t]
                            desc = self._safe_params_to_descriptor(param_types)
                            if desc is not None:
                                entry['params'] = param_types
                                entry['descriptor'] = desc
                                break

                    if entry['descriptor'] is None:
                        for sig_key in ('focal_method_signature', 'method_signature',
                                        'signature', 'focal_method'):
                            sig_raw = data.get(sig_key)
                            if not sig_raw or not isinstance(sig_raw, str):
                                continue
                            sig_raw = sig_raw.strip()
                            if '(' not in sig_raw:
                                continue
                            paren_open = sig_raw.index('(')
                            paren_close = sig_raw.rfind(')')
                            if paren_close <= paren_open:
                                continue
                            raw_params_str = sig_raw[paren_open + 1:paren_close].strip()
                            if not raw_params_str:
                                entry['params'] = []
                                entry['descriptor'] = '()'
                                break
                            param_types = []
                            for seg in raw_params_str.split(','):
                                seg = seg.strip()
                                if not seg:
                                    continue
                                tokens = seg.split()
                                param_types.append(tokens[0])
                            desc = self._safe_params_to_descriptor(param_types)
                            if desc is not None:
                                entry['params'] = param_types
                                entry['descriptor'] = desc
                                break

                except Exception:
                    pass

                result[mid] = entry

        except Exception as e:
            print("[WARN] _build_mid_to_focal_map failed:", e)
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Coverage extraction helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_missed_coverage(jacoco_xml_path: str, target_class: str):
        missed_methods: list = []
        partial_methods: list = []
        if not jacoco_xml_path or not os.path.exists(jacoco_xml_path):
            return missed_methods, partial_methods
        try:
            with open(jacoco_xml_path, 'r', encoding='utf-8', errors='replace') as _f:
                raw = _f.read()
            _report_start = raw.find('<report')
            if _report_start < 0:
                return missed_methods, partial_methods
            raw = raw[_report_start:]
            root = ET.fromstring(raw)
            simple = target_class.split('.')[-1] if target_class else ''
            all_classes = list(root.iter('class'))
            target_class_elem = None
            for cls in all_classes:
                cname = cls.get('name', '')
                cname_simple = cname.split('/')[-1].split('$')[0]
                if cname_simple == simple:
                    target_class_elem = cls
                    break
            if target_class_elem is None:
                return missed_methods, partial_methods
            for method_elem in target_class_elem.findall('method'):
                mname = method_elem.get('name', '')
                mline = method_elem.get('line', '?')
                if mname == '<clinit>':
                    continue
                display_name = f"{simple}()" if mname == '<init>' else mname
                line_missed = line_covered = branch_missed = branch_covered = 0
                for counter in method_elem.findall('counter'):
                    ctype = counter.get('type', '')
                    if ctype == 'LINE':
                        line_missed = int(counter.get('missed', 0))
                        line_covered = int(counter.get('covered', 0))
                    elif ctype == 'BRANCH':
                        branch_missed = int(counter.get('missed', 0))
                        branch_covered = int(counter.get('covered', 0))
                if line_covered == 0 and line_missed > 0:
                    missed_methods.append(
                        f"line {mline}: {display_name}() — completely uncovered")
                elif branch_missed > 0:
                    total_br = branch_missed + branch_covered
                    partial_methods.append(
                        f"line {mline}: {display_name}() — "
                        f"{branch_missed}/{total_br} branches missed")
        except Exception as _e:
            print(f"[WARN] _extract_missed_coverage failed: {_e}")
        return missed_methods, partial_methods

    # ──────────────────────────────────────────────────────────────────────
    # Main test loop
    # ──────────────────────────────────────────────────────────────────────

    def run_all_tests(self, tests_dir, compiled_test_dir, compiler_output,
                      test_output, report_dir, logs=None):
        tests = os.path.join(tests_dir, "test_cases")
        self.instrument(compiled_test_dir, compiled_test_dir)
        start_time = datetime.now()

        total_compile = 0
        total_tests = 0
        syntax_errors = 0
        compile_failed_list = []

        target_class = self._resolve_target_class(tests_dir)
        project_name = os.path.basename(self.target_path.rstrip('/'))
        global_csv_parent_dir = os.path.abspath(tests_dir)
        os.makedirs(global_csv_parent_dir, exist_ok=True)

        per_test_status_map = {}
        per_test_records = []

        focal_method = self._resolve_focal_method(tests_dir)
        mid_to_focal_map = self._build_mid_to_focal_map(tests_dir)
        mid_to_name = {mid: info['name'] for mid, info in mid_to_focal_map.items()}
        if not focal_method:
            try:
                tc_dir = os.path.join(tests_dir, 'test_cases')
                if os.path.isdir(tc_dir):
                    for fname in sorted(os.listdir(tc_dir)):
                        if fname.endswith('Test.java'):
                            m2 = re.match(r'^.+?_([^_]+)_\d+Test\.java$', fname)
                            if m2:
                                mid_cand = m2.group(1)
                                if mid_cand.isdigit() and mid_to_name:
                                    focal_method = mid_to_name.get(mid_cand, '')
                                elif not mid_cand.isdigit():
                                    focal_method = mid_cand
                            break
            except Exception:
                pass
        print(f"[INFO] focal_method='{focal_method}'  target_class='{target_class}'")
        # 改成（匹配 _0 到 _N-1，与 HITS 命名对齐）：

        for t in range(0, test_number):
            print("Processing attempt:", str(t))
            for test_case_file in os.listdir(tests):
                if str(t) != test_case_file.split('_')[-1].replace('Test.java', ''):
                    continue

                total_compile += 1
                total_tests += 1
                test_file = os.path.join(tests, test_case_file)
                full_name = self.get_full_name(test_file)

                # ── 1) Syntax check ──────────────────────────────────────
                syntax_tmp = tempfile.mkdtemp()
                try:
                    syntax_cmd = self.javac_cmd(syntax_tmp, test_file)
                    syntax_cmd.insert(1, '-Xlint:all')
                    proc = subprocess.run(syntax_cmd, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True)
                    stderr_s = proc.stderr or ""
                    self.SYNTAX_TOTAL += 1
                    syntax_pattern = re.compile(
                        r"(illegal start of expression|';' expected|"
                        r"unclosed string literal|unterminated string literal|"
                        r"unclosed comment|illegal character|identifier expected|"
                        r"expected '\}'|expected '\)'|expected '\]'|missing ';'|"
                        r"syntax error)",
                        re.IGNORECASE)
                    if proc.returncode != 0:
                        if syntax_pattern.search(stderr_s):
                            self.SYNTAX_ERROR += 1
                            syntax_errors += 1
                            if logs:
                                with open(logs['syntax'], 'a') as f:
                                    f.write(f"[SYNTAX_ERROR] {test_case_file}: "
                                            f"{stderr_s.splitlines()[0] if stderr_s else 'syntax error'}\n")
                        else:
                            if logs:
                                with open(logs['syntax'], 'a') as f:
                                    f.write(f"[SYNTAX_SEMANTIC] {test_case_file}: "
                                            f"{stderr_s.splitlines()[0] if stderr_s else 'compile error'}\n")
                    else:
                        if logs:
                            with open(logs['syntax'], 'a') as f:
                                f.write(f"[SYNTAX_OK] {test_case_file}\n")
                finally:
                    if os.path.exists(syntax_tmp):
                        shutil.rmtree(syntax_tmp)

                # ── 2) Compile ──────────────────────────────────────────
                os.makedirs(compiled_test_dir, exist_ok=True)
                cmd = self.javac_cmd(compiled_test_dir, test_file)
                result = subprocess.run(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)
                compiled_ok = (result.returncode == 0)

                if not compiled_ok:
                    self.COMPILE_ERROR += 1
                    compile_failed_list.append(test_case_file)
                    if logs:
                        with open(logs['compile'], 'a') as f:
                            f.write(f"[COMPILE_FAILED] {full_name}: "
                                    f"{result.stderr.splitlines()[0] if result.stderr else 'compile error'}\n")
                        with open(logs['compile_failed'], 'a') as f:
                            f.write(f"{full_name}\t{test_case_file}\n")

                    if os.path.basename(compiler_output) == 'compile_error':
                        co_file = f"{compiler_output}.txt"
                    else:
                        co_file = f"{compiler_output}-{os.path.basename(test_file)}.txt"
                    os.makedirs(os.path.dirname(co_file), exist_ok=True)
                    with open(co_file, "w") as f:
                        f.write(result.stdout)
                        f.write(result.stderr)

                    per_test_status_map[full_name] = {
                        'compile_status': 'fail', 'exec_status': 'skip',
                        'exec_timeout': False, 'jacoco_exec_size': 0,
                        'compile_score': 0.0, 'exec_score': 0.0,
                    }

                    if logs and 'diagnosis' in logs:
                        _stderr_cf = result.stderr or ''
                        _lines_cf = _stderr_cf.strip().splitlines()
                        _core_cf = [l.strip() for l in _lines_cf
                                    if ': error:' in l][:10]
                        if not _core_cf:
                            _core_cf = ([_lines_cf[0].strip()]
                                        if _lines_cf else ['unknown compile error'])
                        try:
                            with open(logs['diagnosis'], 'a', encoding='utf-8') as _df:
                                _df.write(f"[DIAGNOSIS] test_class={full_name}\n")
                                _df.write(f"  project={project_name}  target_class={target_class}\n")
                                _df.write(f"  status=compile_fail\n")
                                _df.write(f"  core_errors ({len(_core_cf)}):\n")
                                for _ce in _core_cf:
                                    _df.write(f"    - {_ce}\n")
                                _show_n = min(len(_lines_cf), 100)
                                _df.write(f"  full_stderr ({_show_n}/{len(_lines_cf)} lines):\n")
                                for _ll in _lines_cf[:100]:
                                    _df.write(f"    {_ll}\n")
                                if len(_lines_cf) > 100:
                                    _df.write(f"    ... [{len(_lines_cf)-100} more lines truncated]\n")
                                _df.write("---\n")
                        except Exception:
                            pass

                    per_test_records.append({
                        'test_class': full_name, 'exec_file': None,
                        'exec_note': 'compile_fail',
                        'm_per_line_cov': None, 'm_per_line_total': None,
                        'm_per_branch_cov': None, 'm_per_branch_total': None,
                        'f_per_line_cov': None, 'f_per_line_total': None,
                        'f_per_branch_cov': None, 'f_per_branch_total': None,
                        'per_test_jacoco_xml': None,
                    })
                    continue

                else:
                    if logs:
                        with open(logs['compile'], 'a') as f:
                            f.write(f"[COMPILE_OK] {full_name}\n")
                    per_test_status_map[full_name] = {
                        'compile_status': 'pass', 'exec_status': 'pending',
                        'exec_timeout': False, 'jacoco_exec_size': 0,
                        'compile_score': 1.0, 'exec_score': 0.0,
                    }

                # ── 3) Run test ────────────────────────────────────────
                test_basename = os.path.splitext(test_case_file)[0]
                per_test_exec = os.path.join(compiled_test_dir,
                                             f"jacoco_{test_basename}.exec")
                try:
                    if os.path.exists(per_test_exec):
                        os.remove(per_test_exec)
                except Exception:
                    pass

                self.jacoco_destfile = per_test_exec
                exec_ok, is_timeout = self.run_test_only_with_reason(
                    test_file, compiled_test_dir, test_output, logs)
                self.jacoco_destfile = None

                try:
                    exec_size = (os.path.getsize(per_test_exec)
                                 if os.path.exists(per_test_exec) else 0)
                except Exception:
                    exec_size = 0

                per_test_status_map[full_name]['exec_status'] = 'pass' if exec_ok else 'fail'
                per_test_status_map[full_name]['exec_timeout'] = is_timeout
                per_test_status_map[full_name]['jacoco_exec_size'] = exec_size
                per_test_status_map[full_name]['exec_score'] = 1.0 if exec_ok else 0.0

                if logs and 'diagnosis' in logs and not exec_ok:
                    try:
                        with open(logs['diagnosis'], 'a', encoding='utf-8') as _df:
                            _df.write(f"[DIAGNOSIS] test_class={full_name}\n")
                            _df.write(f"  project={project_name}  target_class={target_class}\n")
                            if is_timeout:
                                _df.write(f"  status=exec_timeout\n  core_errors:\n")
                                _df.write(f"    - Exceeded TIMEOUT limit\n")
                            else:
                                _df.write(f"  status=exec_fail\n")
                                _rt_file = f"{test_output}-{test_case_file}.txt"
                                _exc_lines = []
                                if os.path.exists(_rt_file):
                                    try:
                                        _rt_all = open(_rt_file, errors='ignore').read()
                                        _exc_lines = re.findall(
                                            r'([\w\\.]+(?:Exception|Error)[^\n]{0,200})',
                                            _rt_all)[:5]
                                    except Exception:
                                        pass
                                if not _exc_lines:
                                    _exc_lines = ['runtime error (no details captured)']
                                _df.write(f"  core_errors:\n")
                                for _ec in _exc_lines:
                                    _df.write(f"    - {_ec.strip()}\n")
                            _df.write("---\n")
                    except Exception:
                        pass

                # ── 4) Per-test coverage ───────────────────────────────
                exec_note = 'ok' if exec_ok else ('timeout' if is_timeout else 'fail')
                m_per_line_cov = m_per_line_total = None
                m_per_branch_cov = m_per_branch_total = None
                f_per_line_cov = f_per_line_total = None
                f_per_branch_cov = f_per_branch_total = None
                per_test_jacoco_xml = None

                if exec_size > 0:
                    per_test_report_dir = os.path.join(
                        report_dir, "per_test_reports", test_basename)
                    self.report(compiled_test_dir, per_test_report_dir,
                                jacoco_exec_override=per_test_exec)
                    _global_xml = os.path.join(
                        self.target_path, "target", "site", "jacoco", "jacoco.xml")
                    if os.path.exists(_global_xml):
                        os.makedirs(per_test_report_dir, exist_ok=True)
                        _per_xml = os.path.join(per_test_report_dir, "jacoco.xml")
                        try:
                            shutil.copy2(_global_xml, _per_xml)
                            per_test_jacoco_xml = _per_xml
                        except Exception:
                            per_test_jacoco_xml = _global_xml

                    try:
                        jacoco_xml_path = per_test_jacoco_xml
                        if (jacoco_xml_path and os.path.exists(jacoco_xml_path)
                                and target_class):
                            tree_p = ET.parse(jacoco_xml_path)
                            root_p = tree_p.getroot()
                            grp_for_this = self._group_from_test_class(full_name)
                            focal_for_this, focal_desc_for_this = \
                                self._focal_info_from_group(
                                    grp_for_this, mid_to_name,
                                    focal_method, mid_to_focal_map)

                            for class_elem in root_p.findall('.//class'):
                                cname = class_elem.attrib.get('name', '')
                                simple = cname.split('/')[-1].split('$')[0]
                                if (simple != target_class and
                                        not cname.endswith('/' + target_class)):
                                    continue

                                for c in class_elem.findall('counter'):
                                    ctype = c.attrib.get('type', '')
                                    covered = int(c.attrib.get('covered', 0))
                                    missed = int(c.attrib.get('missed', 0))
                                    if ctype == 'LINE':
                                        m_per_line_cov = (m_per_line_cov or 0) + covered
                                        m_per_line_total = (m_per_line_total or 0) + covered + missed
                                    elif ctype == 'BRANCH':
                                        m_per_branch_cov = (m_per_branch_cov or 0) + covered
                                        m_per_branch_total = (m_per_branch_total or 0) + covered + missed

                                if focal_for_this:
                                    matched_methods = [
                                        me for me in class_elem.findall('method')
                                        if self._is_focal_method_match(
                                            me.get('name', ''), focal_for_this,
                                            target_class,
                                            focal_descriptor=focal_desc_for_this,
                                            method_desc=me.get('desc', ''))
                                    ]
                                    if matched_methods:
                                        fl_cov = fl_tot = fb_cov = fb_tot = 0
                                        for me in matched_methods:
                                            for cc in me.findall('counter'):
                                                ct2 = cc.get('type', '')
                                                cov2 = int(cc.get('covered', 0))
                                                mis2 = int(cc.get('missed', 0))
                                                if ct2 == 'LINE':
                                                    fl_cov += cov2
                                                    fl_tot += cov2 + mis2
                                                elif ct2 == 'BRANCH':
                                                    fb_cov += cov2
                                                    fb_tot += cov2 + mis2
                                        if fl_tot > 0:
                                            f_per_line_cov = fl_cov
                                            f_per_line_total = fl_tot
                                        if fb_tot > 0:
                                            f_per_branch_cov = fb_cov
                                            f_per_branch_total = fb_tot
                                break

                    except Exception as _xml_err:
                        if logs:
                            with open(logs.get('coverage', os.devnull), 'a') as _f:
                                _f.write(f"[PER_TEST_XML_ERR] {test_case_file}: {_xml_err}\n")

                per_test_records.append({
                    'test_class': full_name,
                    'exec_file': per_test_exec,
                    'exec_note': exec_note,
                    'm_per_line_cov': m_per_line_cov,
                    'm_per_line_total': m_per_line_total,
                    'm_per_branch_cov': m_per_branch_cov,
                    'm_per_branch_total': m_per_branch_total,
                    'f_per_line_cov': f_per_line_cov,
                    'f_per_line_total': f_per_line_total,
                    'f_per_branch_cov': f_per_branch_cov,
                    'f_per_branch_total': f_per_branch_total,
                    'per_test_jacoco_xml': per_test_jacoco_xml,
                })

        # ── Write per_test_status.csv ────────────────────────────────
        self._write_per_test_status(
            global_csv_parent_dir, project_name, target_class,
            per_test_status_map, logs)

        # ── Merge all execs & generate global coverage report ────────
        report_target = os.path.join(report_dir, "final")
        (line_cov, branch_cov, line_total, branch_total,
         line_rate, branch_rate) = (None,) * 6
        (m_line_cov, m_branch_cov, m_line_total, m_branch_total,
         m_line_rate, m_branch_rate) = (None,) * 6
        modified_class_name = target_class or None

        merged_exec = os.path.join(compiled_test_dir, "jacoco_merged.exec")
        exec_files = [r['exec_file'] for r in per_test_records
                      if r.get('exec_file') and os.path.exists(r.get('exec_file', ''))]
        res = None
        if exec_files:
            if JACOCO_CLI and os.path.exists(JACOCO_CLI):
                merge_cmd = (["java", "-jar", JACOCO_CLI, "merge"]
                             + exec_files + ["--destfile", merged_exec])
                try:
                    subprocess.run(merge_cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, check=True)
                except Exception:
                    pass
                res = self.report(compiled_test_dir, report_target,
                                  jacoco_exec_override=merged_exec)
            else:
                res = self.report(compiled_test_dir, report_target,
                                  jacoco_exec_override=exec_files[0])
        else:
            default_exec = os.path.join(compiled_test_dir, "jacoco.exec")
            if os.path.exists(default_exec):
                res = self.report(compiled_test_dir, report_target,
                                  jacoco_exec_override=default_exec)
            else:
                res = self.report(compiled_test_dir, report_target)

        jacoco_xml_path = os.path.join(
            self.target_path, "target", "site", "jacoco", "jacoco.xml")
        if os.path.exists(jacoco_xml_path):
            tree = ET.parse(jacoco_xml_path)
            root_elem = tree.getroot()
            counters = root_elem.findall('.//counter')
            line_counters = [c for c in counters if c.attrib.get('type') == 'LINE']
            branch_counters = [c for c in counters if c.attrib.get('type') == 'BRANCH']
            if line_counters:
                lc = line_counters[-1]
                line_cov = int(lc.attrib.get('covered', 0))
                line_total = line_cov + int(lc.attrib.get('missed', 0))
                line_rate = round(100 * line_cov / line_total, 2) if line_total else 0.0
            if branch_counters:
                bc = branch_counters[-1]
                branch_cov = int(bc.attrib.get('covered', 0))
                branch_total = branch_cov + int(bc.attrib.get('missed', 0))
                branch_rate = round(100 * branch_cov / branch_total, 2) if branch_total else 0.0
            if modified_class_name:
                for class_elem in root_elem.findall('.//class'):
                    if class_elem.attrib.get('name', '').endswith(modified_class_name):
                        for c in class_elem.findall('counter'):
                            if c.attrib.get('type') == 'LINE':
                                m_line_cov = int(c.attrib.get('covered', 0))
                                m_line_total = m_line_cov + int(c.attrib.get('missed', 0))
                                m_line_rate = (round(100 * m_line_cov / m_line_total, 2)
                                               if m_line_total else 0.0)
                            if c.attrib.get('type') == 'BRANCH':
                                m_branch_cov = int(c.attrib.get('covered', 0))
                                m_branch_total = m_branch_cov + int(c.attrib.get('missed', 0))
                                m_branch_rate = (round(100 * m_branch_cov / m_branch_total, 2)
                                                 if m_branch_total else 0.0)
                        break

        # ── coveragedetail.csv ────────────────────────────────────────
        try:
            tc_slug = (target_class or 'unknown').replace('.', '')
            pn_slug = project_name.replace('.', '')
            detail_csv = os.path.join(global_csv_parent_dir,
                                      f'{pn_slug}_{tc_slug}_coveragedetail.csv')
            file_exists = os.path.exists(detail_csv)

            groups_cd: dict = {}
            for rec in per_test_records:
                tc_r = rec.get('test_class', '')
                grp_r = self._group_from_test_class(tc_r)
                groups_cd.setdefault(grp_r, []).append(rec)

            focal_totals_cd: dict = self._compute_focal_totals_from_merged_jacoco(
                groups_cd, modified_class_name, mid_to_name,
                focal_method, mid_to_focal_map=mid_to_focal_map)

            for grp_r, members_r in groups_cd.items():
                gtot = focal_totals_cd.get(grp_r, {})
                if not gtot or gtot.get('f_line_total') is None:
                    valid_members = [m for m in members_r
                                     if (m.get('f_per_line_total') or 0) > 0]
                    if valid_members:
                        focal_totals_cd[grp_r] = {
                            'f_line_total': max(m.get('f_per_line_total') or 0
                                               for m in valid_members),
                            'f_line_cov':   max(m.get('f_per_line_cov') or 0
                                               for m in valid_members),
                            'f_branch_total': max(m.get('f_per_branch_total') or 0
                                                 for m in valid_members),
                            'f_branch_cov':   max(m.get('f_per_branch_cov') or 0
                                                 for m in valid_members),
                        }
                    else:
                        focal_totals_cd[grp_r] = {
                            'f_line_total': 0, 'f_line_cov': 0,
                            'f_branch_total': 0, 'f_branch_cov': 0,
                        }

            with open(detail_csv, 'a', newline='', encoding='utf-8') as csvf:
                writer = csv.writer(csvf)
                if not file_exists:
                    writer.writerow([
                        'project', 'target_class', 'test_class', 'focal_method',
                        'exec_status',
                        'm_per_line_cov', 'm_per_line_total', 'm_per_line_rate',
                        'm_per_branch_cov', 'm_per_branch_total', 'm_per_branch_rate',
                        'm_line_contrib_pct', 'm_branch_contrib_pct', 'm_coverage_score',
                        'f_per_line_cov', 'f_per_line_total', 'f_per_line_rate',
                        'f_per_branch_cov', 'f_per_branch_total', 'f_per_branch_rate',
                        'f_line_contrib_pct', 'f_branch_contrib_pct', 'f_coverage_score',
                    ])

                for rec in per_test_records:
                    mlc = rec.get('m_per_line_cov') or 0
                    mlt = rec.get('m_per_line_total') or 0
                    mlr = round(100.0 * mlc / mlt, 4) if mlt else 0.0
                    mbc = rec.get('m_per_branch_cov') or 0
                    mbt = rec.get('m_per_branch_total') or 0
                    mbr = round(100.0 * mbc / mbt, 4) if mbt else 0.0

                    tc_r = rec.get('test_class', '')
                    grp_r = self._group_from_test_class(tc_r)
                    fm_r = self._focal_method_from_group(grp_r, mid_to_name, focal_method)
                    gtot = focal_totals_cd.get(grp_r, {})
                    grp_m_line_cov = gtot.get('f_line_cov') or 0
                    grp_m_branch_cov = gtot.get('f_branch_cov') or 0
                    line_contrib_pct = (round(100.0 * mlc / grp_m_line_cov, 4)
                                        if grp_m_line_cov and mlc else 0.0)
                    branch_contrib_pct = (round(100.0 * mbc / grp_m_branch_cov, 4)
                                          if grp_m_branch_cov and mbc else 0.0)
                    coverage_score = round(
                        0.25 * (mlr / 100.0) + 0.25 * (mbr / 100.0) +
                        0.25 * (line_contrib_pct / 100.0) +
                        0.25 * (branch_contrib_pct / 100.0), 6)
                    rec['coverage_score'] = coverage_score
                    rec['m_coverage_score'] = coverage_score

                    ffc = rec.get('f_per_line_cov') or 0
                    fft = rec.get('f_per_line_total') or 0
                    ffr = round(100.0 * ffc / fft, 4) if fft else 0.0
                    fbc2 = rec.get('f_per_branch_cov') or 0
                    fbt2 = rec.get('f_per_branch_total') or 0
                    fbr2 = round(100.0 * fbc2 / fbt2, 4) if fbt2 else 0.0
                    gf_line_cov = gtot.get('f_line_cov') or 0
                    gf_branch_cov = gtot.get('f_branch_cov') or 0
                    f_line_contrib_pct = (round(100.0 * ffc / gf_line_cov, 4)
                                          if gf_line_cov and ffc else 0.0)
                    f_branch_contrib_pct = (round(100.0 * fbc2 / gf_branch_cov, 4)
                                            if gf_branch_cov and fbc2 else 0.0)
                    f_coverage_score = round(
                        0.25 * (ffr / 100.0) + 0.25 * (fbr2 / 100.0) +
                        0.25 * (f_line_contrib_pct / 100.0) +
                        0.25 * (f_branch_contrib_pct / 100.0), 6)

                    writer.writerow([
                        project_name, target_class,
                        rec.get('test_class', ''), fm_r,
                        rec.get('exec_note', 'ok'),
                        mlc if mlt else '', mlt if mlt else '', mlr if mlt else '',
                        mbc if mbt else '', mbt if mbt else '', mbr if mbt else '',
                        line_contrib_pct, branch_contrib_pct, coverage_score,
                        ffc if fft else '', fft if fft else '', ffr if fft else '',
                        fbc2 if fbt2 else '', fbt2 if fbt2 else '', fbr2 if fbt2 else '',
                        f_line_contrib_pct, f_branch_contrib_pct, f_coverage_score,
                    ])

                    if logs and 'diagnosis' in logs:
                        try:
                            _snap = rec.get('per_test_jacoco_xml')
                            _global_xml2 = os.path.join(
                                self.target_path, "target", "site", "jacoco", "jacoco.xml")
                            _jxml = (_snap if (_snap and os.path.isfile(_snap) and
                                               os.path.getsize(_snap) > 200)
                                     else _global_xml2)
                            _missed_methods, _partial_methods = \
                                self._extract_missed_coverage(_jxml, target_class)
                            _tc_name = rec.get('test_class', '')
                            _br_hint = 'N/A'
                            _sim_hint = None
                            try:
                                _br_files = sorted(glob.glob(
                                    os.path.join(global_csv_parent_dir,
                                                 '*bugrevealing*.csv')))
                                for _br_file in _br_files:
                                    with open(_br_file, newline='',
                                              encoding='utf-8') as _bf:
                                        for _brow in csv.DictReader(_bf):
                                            if _brow.get('test_class', '').strip() == _tc_name:
                                                _v = str(_brow.get('bug_revealing', '')).lower()
                                                _br_hint = 'true' if _v == 'true' else 'false'
                                                break
                                    if _br_hint == 'true':
                                        break
                                _sim_dir2 = os.path.join(global_csv_parent_dir, 'Similarity')
                                for _sf in sorted(glob.glob(
                                        os.path.join(_sim_dir2, '*_bigSims.csv'))):
                                    with open(_sf, newline='', encoding='utf-8') as _sf_f:
                                        for _srow in csv.DictReader(_sf_f):
                                            if _srow.get('test_case_1', '').strip() == _tc_name:
                                                _sim_hint = _srow.get('redundancy_score', '').strip()
                                                break
                                    if _sim_hint is not None:
                                        break
                            except Exception:
                                pass
                            with open(logs['diagnosis'], 'a', encoding='utf-8') as _df:
                                _df.write(f"[DIAGNOSIS] test_class={_tc_name}\n")
                                _df.write(f"  project={project_name}  target_class={target_class}\n")
                                _df.write(f"  status=exec_ok\n  error_type=coverage_gap\n")
                                _df.write(f"  line_rate={mlr:.4f}%  ({mlc}/{mlt})\n")
                                _df.write(f"  branch_rate={mbr:.4f}%  ({mbc}/{mbt if mbt else 0})\n")
                                _df.write(f"  coverage_score={coverage_score}\n")
                                if _missed_methods:
                                    _df.write(f"  uncovered_methods ({len(_missed_methods)}):\n")
                                    for _mm in _missed_methods[:20]:
                                        _df.write(f"    - {_mm}\n")
                                else:
                                    _df.write(f"  uncovered_methods: none\n")
                                if _partial_methods:
                                    _df.write(f"  partial_branch_methods ({len(_partial_methods)}):\n")
                                    for _pm in _partial_methods[:20]:
                                        _df.write(f"    - {_pm}\n")
                                else:
                                    _df.write(f"  partial_branch_methods: none\n")
                                if _br_hint == 'true':
                                    _df.write(f"  bug_revealing=true\n")
                                elif _br_hint == 'false':
                                    _df.write(f"  bug_revealing=false\n")
                                else:
                                    _df.write(f"  bug_revealing=N/A\n")
                                if _sim_hint:
                                    _df.write(f"  redundancy_score={_sim_hint}\n")
                                else:
                                    _df.write(f"  redundancy_score=N/A\n")
                                _df.write("---\n")
                        except Exception:
                            pass

        except Exception as e:
            print('Failed to write coveragedetail.csv:', e)
            import traceback
            traceback.print_exc()

        # ── coveragemethod.csv / final_scores.csv / final_scores2.csv ─
        try:
            groups: dict = {}
            for rec in per_test_records:
                tc_r = rec.get('test_class', '')
                grp_r = self._group_from_test_class(tc_r)
                groups.setdefault(grp_r, []).append(rec)

            focal_totals: dict = self._compute_focal_totals_from_merged_jacoco(
                groups, modified_class_name, mid_to_name,
                focal_method, mid_to_focal_map=mid_to_focal_map)

            for grp_k, members_k in groups.items():
                gtot = focal_totals.get(grp_k, {})
                if not gtot or gtot.get('f_line_total') is None:
                    valid_mk = [m for m in members_k
                                if (m.get('f_per_line_total') or 0) > 0]
                    if valid_mk:
                        focal_totals[grp_k] = {
                            'f_line_total': max(m.get('f_per_line_total') or 0
                                               for m in valid_mk),
                            'f_line_cov':   max(m.get('f_per_line_cov') or 0
                                               for m in valid_mk),
                            'f_branch_total': max(m.get('f_per_branch_total') or 0
                                                 for m in valid_mk),
                            'f_branch_cov':   max(m.get('f_per_branch_cov') or 0
                                                 for m in valid_mk),
                        }
                    else:
                        focal_totals[grp_k] = {
                            'f_line_total': 0, 'f_line_cov': 0,
                            'f_branch_total': 0, 'f_branch_cov': 0,
                        }

            tc_slug = (target_class or 'unknown').replace('.', '')
            pn_slug = project_name.replace('.', '')

            # coveragemethod.csv
            coveragemethod_csv = os.path.join(
                global_csv_parent_dir, f'{pn_slug}_{tc_slug}_coveragemethod.csv')
            cm_is_new = not (os.path.exists(coveragemethod_csv) and
                             os.path.getsize(coveragemethod_csv) > 0)
            with open(coveragemethod_csv, 'a', newline='', encoding='utf-8') as cmf:
                w_cm = csv.writer(cmf)
                if cm_is_new:
                    w_cm.writerow([
                        'project', 'target_class', 'focal_method', 'exec_status',
                        'f_per_line_cov', 'f_per_line_total', 'f_per_line_rate',
                        'f_per_branch_cov', 'f_per_branch_total', 'f_per_branch_rate',
                        'line_contrib_pct', 'branch_contrib_pct', 'coverage_score',
                    ])
                for grp_k, members_k in groups.items():
                    ft_k = focal_totals.get(grp_k, {})
                    flc_k = ft_k.get('f_line_cov') or 0
                    flt_k = ft_k.get('f_line_total') or 0
                    flr_k = round(100.0 * flc_k / flt_k, 4) if flt_k else 0.0
                    fbc_k = ft_k.get('f_branch_cov') or 0
                    fbt_k = ft_k.get('f_branch_total') or 0
                    fbr_k = round(100.0 * fbc_k / fbt_k, 4) if fbt_k else 0.0
                    cov_s_k = round(
                        0.25 * (flr_k / 100.0) + 0.25 * (fbr_k / 100.0) +
                        0.25 * (flr_k / 100.0) + 0.25 * (fbr_k / 100.0), 6)
                    fm_k = self._focal_method_from_group(grp_k, mid_to_name, focal_method)
                    en_k = [m.get('exec_note', '') for m in members_k]
                    es_k = 'ok' if 'ok' in en_k else (en_k[0] if en_k else '')
                    w_cm.writerow([project_name, target_class, fm_k, es_k,
                                   flc_k, flt_k, flr_k, fbc_k, fbt_k, fbr_k,
                                   flr_k, fbr_k, cov_s_k])

            # load bug_revealing and similarity
            br_map: dict = {}
            try:
                for _f in sorted(glob.glob(
                        os.path.join(global_csv_parent_dir, '*bugrevealing*.csv'))):
                    with open(_f, newline='', encoding='utf-8') as _bf:
                        for _r in csv.DictReader(_bf):
                            _tc2 = _r.get('test_class', '').strip()
                            br_map[_tc2] = (1.0 if str(_r.get('bug_revealing', '')).strip().lower() == 'true'
                                            else 0.0)
            except Exception:
                pass

            sim_map: dict = {}
            try:
                _sim_dir = os.path.join(global_csv_parent_dir, 'Similarity')
                if os.path.isdir(_sim_dir):
                    for _f in sorted(glob.glob(os.path.join(_sim_dir, '*_bigSims.csv'))):
                        with open(_f, newline='', encoding='utf-8') as _sf:
                            for _r in csv.DictReader(_sf):
                                try:
                                    sim_map[_r.get('test_case_1', '').strip()] = \
                                        float(_r.get('redundancy_score', ''))
                                except Exception:
                                    pass
            except Exception:
                pass

            _WC = 0.15; _WE = 0.15; _WV = 0.30; _WB = 0.20; _WR = 0.20

            # final_scores.csv (per-test)
            per_test_final = os.path.join(
                global_csv_parent_dir, f'{pn_slug}_{tc_slug}_final_scores.csv')
            pf_is_new = not (os.path.exists(per_test_final) and
                             os.path.getsize(per_test_final) > 0)
            with open(per_test_final, 'a', newline='', encoding='utf-8') as pf:
                pfw = csv.writer(pf)
                if pf_is_new:
                    pfw.writerow([
                        'test_class', 'focal_method', 'compile_score', 'exec_score',
                        'coverage_score', 'bug_revealing_score', 'redundancy_score',
                        'final_score', 'valid_weight_pct',
                    ])
                for grp_k, members_k in groups.items():
                    fm_k = self._focal_method_from_group(grp_k, mid_to_name, focal_method)
                    for mrec in members_k:
                        tc_n = mrec.get('test_class', '')
                        cs_p = 1.0 if mrec.get('exec_note') != 'compile_fail' else 0.0
                        es_p = 1.0 if mrec.get('exec_note') == 'ok' else 0.0
                        cv_p = mrec.get('m_coverage_score', '')
                        br_p = br_map.get(tc_n)
                        br_p = br_p if br_p is not None else ''
                        sm_p = sim_map.get(tc_n)
                        sm_p = sm_p if sm_p is not None else ''
                        sw_p = []
                        vw_p = 0.0
                        rd_p = (1.0 - sm_p) if isinstance(sm_p, float) else None
                        for _v, _w in [(cs_p, _WC), (es_p, _WE), (cv_p, _WV),
                                       (br_p, _WB), (rd_p, _WR)]:
                            if isinstance(_v, (int, float)):
                                sw_p.append(_v * _w)
                                vw_p += _w
                        fs_p = round(sum(sw_p) / vw_p, 6) if vw_p > 0 else ''
                        pfw.writerow([tc_n, fm_k, cs_p, es_p, cv_p,
                                      br_p, sm_p, fs_p, round(vw_p, 4)])

            # final_scores2.csv (per-focal-method group)
            final_csv = os.path.join(
                global_csv_parent_dir, f'{pn_slug}_{tc_slug}_final_scores2.csv')
            fs2_is_new = not (os.path.exists(final_csv) and
                              os.path.getsize(final_csv) > 0)
            with open(final_csv, 'a', newline='', encoding='utf-8') as f2:
                w2 = csv.writer(f2)
                if fs2_is_new:
                    w2.writerow([
                        'test_class', 'focal_method', 'compile_score', 'exec_score',
                        'coverage_score', 'bug_revealing_score', 'redundancy_score',
                        'final_score', 'valid_weight_pct',
                    ])
                for grp_k, members_k in groups.items():
                    tot_k = len(members_k) or 1
                    cs_g = round(
                        sum(1.0 if m.get('exec_note') != 'compile_fail' else 0.0
                            for m in members_k) / tot_k, 6)
                    es_g = round(
                        sum(1.0 if m.get('exec_note') == 'ok' else 0.0
                            for m in members_k) / tot_k, 6)
                    ft_g = focal_totals.get(grp_k, {})
                    flc_g = ft_g.get('f_line_cov') or 0
                    flt_g = ft_g.get('f_line_total') or 0
                    fbc_g = ft_g.get('f_branch_cov') or 0
                    fbt_g = ft_g.get('f_branch_total') or 0
                    flr_g = round(100.0 * flc_g / flt_g, 4) if flt_g else 0.0
                    fbr_g = round(100.0 * fbc_g / fbt_g, 4) if fbt_g else 0.0
                    cv_g = round(
                        0.25 * (flr_g / 100.0) + 0.25 * (fbr_g / 100.0) +
                        0.25 * (flr_g / 100.0) + 0.25 * (fbr_g / 100.0), 6
                    ) if (flt_g or fbt_g) else ''
                    brv_g = [br_map.get(m.get('test_class', '')) for m in members_k]
                    brv_g = [v for v in brv_g if v is not None]
                    br_g = round(sum(brv_g) / len(brv_g), 6) if brv_g else ''
                    smv_g = [sim_map.get(m.get('test_class', '')) for m in members_k]
                    smv_g = [v for v in smv_g if isinstance(v, (int, float))]
                    sm_g = round(sum(smv_g) / len(smv_g), 6) if smv_g else ''
                    sw_g = []
                    vw_g = 0.0
                    rd_g = (1.0 - sm_g) if isinstance(sm_g, float) else None
                    for _v, _w in [(cs_g, _WC), (es_g, _WE), (cv_g, _WV),
                                   (br_g, _WB), (rd_g, _WR)]:
                        if isinstance(_v, (int, float)):
                            sw_g.append(_v * _w)
                            vw_g += _w
                    fs_g = round(sum(sw_g) / vw_g, 6) if vw_g > 0 else ''
                    fm_g = self._focal_method_from_group(grp_k, mid_to_name, focal_method)
                    w2.writerow([grp_k, fm_g, cs_g, es_g, cv_g,
                                 br_g, sm_g, fs_g, round(vw_g, 4)])

            # Print focal method coverage per group
            print("-" * 50)
            print("FOCAL METHOD COVERAGE (per group):")
            if focal_totals:
                for grp_k, ft_p in focal_totals.items():
                    fm_p  = self._focal_method_from_group(grp_k, mid_to_name, focal_method)
                    flc_p = ft_p.get('f_line_cov') or 0
                    flt_p = ft_p.get('f_line_total') or 0
                    fbc_p = ft_p.get('f_branch_cov') or 0
                    fbt_p = ft_p.get('f_branch_total') or 0
                    flr_p = round(100.0 * flc_p / flt_p, 4) if flt_p else None
                    fbr_p = round(100.0 * fbc_p / fbt_p, 4) if fbt_p else None
                    print(f"  group={grp_k}  focal_method={fm_p or '(unknown)'}")
                    if flr_p is not None:
                        print(f"    行覆盖率: {flr_p}% ({flc_p}/{flt_p})")
                    else:
                        print(f"    行覆盖率: N/A")
                    if fbr_p is not None:
                        print(f"    分支覆盖率: {fbr_p}% ({fbc_p}/{fbt_p})")
                    else:
                        print(f"    分支覆盖率: N/A")
            print("-" * 50)

        except Exception as _e:
            import traceback
            print('[WARN] per-focal/final csv generation failed:', _e)
            traceback.print_exc()

        # ── coverage.csv (summary) ────────────────────────────────────
        try:
            run_time_seconds = round((datetime.now() - start_time).total_seconds(), 2)
            Attempts = total_tests
            Aborted = max(0, Attempts - total_compile)
            SyntaxError = self.SYNTAX_ERROR
            CompileError = self.COMPILE_ERROR
            RuntimeError = self.TEST_RUN_ERROR
            denom = Attempts - Aborted if (Attempts - Aborted) > 0 else None
            run_denom = ((Attempts - Aborted - CompileError)
                         if denom else None)
            SyntaxRate  = (1.0 - SyntaxError  / denom)     if denom else None
            CompileRate = (1.0 - CompileError  / denom)     if denom else None
            RunRate     = (1.0 - RuntimeError  / run_denom) \
                if run_denom and run_denom > 0 else None
            Passed = max(0, Attempts - Aborted - CompileError - RuntimeError)
            PassRate = (Passed / denom) if denom else None

            tc_slug = (target_class or 'unknown').replace('.', '')
            pn_slug = project_name.replace('.', '')
            summary_fname = os.path.join(
                global_csv_parent_dir, f'{pn_slug}_{tc_slug}_coverage.csv')
            file_exists = os.path.exists(summary_fname)
            with open(summary_fname, 'a', newline='', encoding='utf-8') as sf:
                w = csv.writer(sf)
                if not file_exists:
                    w.writerow([
                        'project', 'modified_class',
                        'Attempts', 'Aborted', 'SyntaxError', 'SyntaxRate',
                        'CompileError', 'CompileRate', 'RuntimeError', 'RunRate',
                        'Passed', 'PassRate',
                        'line_cov', 'line_total', 'line_rate',
                        'branch_cov', 'branch_total', 'branch_rate',
                        'm_line_cov', 'm_line_total', 'm_line_rate',
                        'm_branch_cov', 'm_branch_total', 'm_branch_rate', 'run_time',
                    ])
                w.writerow([
                    project_name, modified_class_name or "",
                    Attempts, Aborted, SyntaxError,
                    round(SyntaxRate, 4) if SyntaxRate is not None else '',
                    CompileError,
                    round(CompileRate, 4) if CompileRate is not None else '',
                    RuntimeError,
                    round(RunRate, 4) if RunRate is not None else '',
                    Passed,
                    round(PassRate, 4) if PassRate is not None else '',
                    line_cov if line_cov is not None else '',
                    line_total if line_total is not None else '',
                    line_rate if line_rate is not None else '',
                    branch_cov if branch_cov is not None else '',
                    branch_total if branch_total is not None else '',
                    branch_rate if branch_rate is not None else '',
                    m_line_cov if m_line_cov is not None else '',
                    m_line_total if m_line_total is not None else '',
                    m_line_rate if m_line_rate is not None else '',
                    m_branch_cov if m_branch_cov is not None else '',
                    m_branch_total if m_branch_total is not None else '',
                    m_branch_rate if m_branch_rate is not None else '',
                    run_time_seconds,
                ])
        except Exception as e:
            print('Failed to write coverage.csv:', e)

        total_test_run = total_compile - self.COMPILE_ERROR
        print("SYNTAX TOTAL COUNT:", self.SYNTAX_TOTAL)
        print("SYNTAX ERROR COUNT:", self.SYNTAX_ERROR)
        print("COMPILE TOTAL COUNT:", total_compile)
        print("COMPILE ERROR COUNT:", self.COMPILE_ERROR)
        print("TEST RUN TOTAL COUNT:", total_test_run)
        print("TEST RUN ERROR COUNT:", self.TEST_RUN_ERROR)
        print("-" * 50)
        print("COVERAGE STATISTICS (ALL ATTEMPTS):")
        if line_rate is not None:
            print(f"  全项目 行覆盖率: {line_rate}% ({line_cov}/{line_total})")
        if branch_rate is not None:
            print(f"  全项目 分支覆盖率: {branch_rate}% ({branch_cov}/{branch_total})")
        if modified_class_name:
            print(f"  target_class: {modified_class_name}")
            if m_line_rate is not None:
                print(f"    行覆盖率: {m_line_rate}% ({m_line_cov}/{m_line_total})")
            if m_branch_rate is not None:
                print(f"    分支覆盖率: {m_branch_rate}% ({m_branch_cov}/{m_branch_total})")
        if line_rate is None and branch_rate is None and not modified_class_name:
            print("  未获取到有效覆盖率数据")
        print("-" * 50)

        return total_compile, total_test_run

    # ──────────────────────────────────────────────────────────────────────
    # Status CSV
    # ──────────────────────────────────────────────────────────────────────

    def _write_per_test_status(self, output_dir, project_name, target_class,
                                status_map, logs=None):
        if not status_map:
            return
        try:
            tc_slug = (target_class or 'unknown').replace('.', '')
            pn_slug = (project_name or 'project').replace('.', '')
            csv_path = os.path.join(output_dir, f'{pn_slug}_{tc_slug}_status.csv')
            header = [
                'project', 'target_class', 'test_class',
                'compile_status', 'exec_status', 'exec_timeout',
                'jacoco_exec_size', 'compile_score', 'exec_score',
            ]
            file_exists = os.path.exists(csv_path)
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(header)
                for full_name, s in status_map.items():
                    writer.writerow([
                        project_name, target_class, full_name,
                        s['compile_status'], s['exec_status'], s['exec_timeout'],
                        s['jacoco_exec_size'], s['compile_score'], s['exec_score'],
                    ])
        except Exception as e:
            print('Failed to write per_test_status.csv:', e)

    # ──────────────────────────────────────────────────────────────────────
    # Run helpers
    # ──────────────────────────────────────────────────────────────────────

    def run_test_only_with_reason(self, test_file, compiled_test_dir,
                                   test_output, logs=None):
        if os.path.basename(test_output) == 'runtime_error':
            test_output_file = f"{test_output}.txt"
        else:
            test_output_file = f"{test_output}-{os.path.basename(test_file)}.txt"
        os.makedirs(os.path.dirname(test_output_file), exist_ok=True)
        cmd = self.java_cmd(compiled_test_dir, test_file)
        try:
            result = subprocess.run(cmd, timeout=TIMEOUT,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True)
            if result.returncode != 0:
                self.TEST_RUN_ERROR += 1
                self.export_runtime_output(result, test_output_file)
                if logs:
                    stderr_content = result.stderr or ""
                    core_exception = "no exception extracted"
                    for pat in [
                        re.compile(r"=> ([\w\.]+Exception): (.*?)(?=\n\s+at|$)", re.DOTALL),
                        re.compile(r"([\w\.]+Exception): (.*?)(?=\n\s+at|$)", re.DOTALL),
                    ]:
                        m = pat.search(stderr_content)
                        if m:
                            core_exception = f"{m.group(1)}: {m.group(2).strip()}"
                            break
                    with open(logs['exec'], 'a') as f:
                        f.write(f"[EXEC_FAILED] {test_file}:\n")
                        f.write(f"[EXEC_CORE_ERROR] {core_exception}\n")
                        for i, line in enumerate(stderr_content.splitlines()):
                            if i > 50:
                                break
                            f.write(f"    {line}\n")
                        f.write("=" * 80 + "\n")
                return False, False
            else:
                if logs:
                    with open(logs['exec'], 'a') as f:
                        f.write(f"[EXEC_OK] {test_file}\n")
                return True, False
        except subprocess.TimeoutExpired:
            self.TEST_RUN_ERROR += 1
            if logs:
                with open(logs['exec'], 'a') as f:
                    f.write(f"[EXEC_TIMEOUT] {test_file}\n")
            return False, True
        except Exception as e:
            self.TEST_RUN_ERROR += 1
            if logs:
                with open(logs['exec'], 'a') as f:
                    f.write(f"[EXEC_ERROR] {test_file}: {e}\n")
            return False, False

    def run_all_tests_simple(self, tests_dir, compiled_test_dir,
                              compiler_output, test_output, report_dir):
        """Simplified run_all_tests for old HITS callers (procedures/fix_code.py etc.)."""
        return self.run_all_tests(tests_dir, compiled_test_dir,
                                  compiler_output, test_output, report_dir)

    def run_single_test(self, test_file, compiled_test_dir,
                        compiler_output, test_output):
        if not self.compile(test_file, compiled_test_dir, compiler_output):
            return False
        if os.path.basename(test_output) == 'runtime_error':
            test_output_file = f"{test_output}.txt"
        else:
            test_output_file = f"{test_output}-{os.path.basename(test_file)}.txt"
        cmd = self.java_cmd(compiled_test_dir, test_file)
        try:
            result = subprocess.run(cmd, timeout=TIMEOUT,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True)
            if result.returncode != 0:
                self.TEST_RUN_ERROR += 1
                self.export_runtime_output(result, test_output_file)
                return False
        except subprocess.TimeoutExpired:
            return False
        return True

    @staticmethod
    def export_timeout_error(test_output_file):
        with open(test_output_file, 'w') as file:
            file.write("Time out!")

    def export_runtime_output(self, result, test_output_file):
        with open(test_output_file, "w") as f:
            f.write(result.stdout)
            error_msg = re.sub(r'log4j:WARN.*\n?', '', result.stderr)
            if error_msg:
                f.write(error_msg)

    def compile(self, test_file, compiled_test_dir, compiler_output):
        os.makedirs(compiled_test_dir, exist_ok=True)
        cmd = self.javac_cmd(compiled_test_dir, test_file)
        result = subprocess.run(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            self.COMPILE_ERROR += 1
            if os.path.basename(compiler_output) == 'compile_error':
                compiler_output_file = f"{compiler_output}.txt"
            else:
                compiler_output_file = f"{compiler_output}-{os.path.basename(test_file)}.txt"
            os.makedirs(os.path.dirname(compiler_output_file), exist_ok=True)
            with open(compiler_output_file, "w") as f:
                f.write(result.stdout)
                f.write(result.stderr)
            return False
        return True

    # ──────────────────────────────────────────────────────────────────────
    # Build / classpath
    # ──────────────────────────────────────────────────────────────────────

    def process_single_repo(self):
        if self.has_submodule(self.target_path):
            modules = self.get_submodule(self.target_path)
            postfixed = [f'{self.target_path}/{module}/{self.build_dir_name}'
                         for module in modules]
            return ':'.join(postfixed)
        return os.path.join(self.target_path, self.build_dir_name)

    @staticmethod
    def get_package(test_file):
        pkg = ''
        try:
            with open(test_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('package '):
                        pkg = line.replace('package ', '').replace(';', '').strip()
                        break
        except Exception:
            pass
        return pkg

    @staticmethod
    def is_module(project_path):
        if not os.path.isdir(project_path):
            return False
        if ('pom.xml' in os.listdir(project_path) and
                'target' in os.listdir(project_path)):
            return True
        return False

    def get_submodule(self, project_path):
        return [d for d in os.listdir(project_path)
                if self.is_module(os.path.join(project_path, d))]

    def has_submodule(self, project_path):
        for d in os.listdir(project_path):
            if self.is_module(os.path.join(project_path, d)):
                return True
        return False

    def javac_cmd(self, compiled_test_dir, test_file):
        classpath = (f"{JUNIT_JAR}:{MOCKITO_JAR}:{LOG4J_JAR}:"
                     f"{self.dependencies}:{self.build_dir}:.")
        classpath_file = os.path.join(compiled_test_dir, 'classpath.txt')
        self.export_classpath(classpath_file, classpath)
        return ["javac", "-d", compiled_test_dir,
                f"@{classpath_file}", test_file]

    def java_cmd(self, compiled_test_dir, test_file):
        full_test_name = self.get_full_name(test_file)
        classpath = (
            f"{COBERTURA_DIR}/cobertura-2.1.1.jar:"
            f"{compiled_test_dir}/instrumented:{compiled_test_dir}:"
            f"{JUNIT_JAR}:{MOCKITO_JAR}:{LOG4J_JAR}:"
            f"{self.dependencies}:{self.build_dir}:."
        )
        classpath_file = os.path.join(compiled_test_dir, 'classpath.txt')
        self.export_classpath(classpath_file, classpath)
        if self.coverage_tool == "cobertura":
            return ["java", f"@{classpath_file}",
                    f"-Dnet.sourceforge.cobertura.datafile={compiled_test_dir}/cobertura.ser",
                    "org.junit.platform.console.ConsoleLauncher",
                    "--disable-banner", "--disable-ansi-colors",
                    "--fail-if-no-tests", "--details=none",
                    "--select-class", full_test_name]
        else:
            jacoco_dest = (self.jacoco_destfile
                           if self.jacoco_destfile
                           else os.path.join(compiled_test_dir, 'jacoco.exec'))
            javaagent = (f"-javaagent:{JACOCO_AGENT}="
                         f"destfile={jacoco_dest},append=true")
            return ["java", javaagent, f"@{classpath_file}",
                    "org.junit.platform.console.ConsoleLauncher",
                    "--disable-banner", "--disable-ansi-colors",
                    "--fail-if-no-tests", "--details=none",
                    "--select-class", full_test_name]

    @staticmethod
    def export_classpath(classpath_file, classpath):
        with open(classpath_file, 'w') as f:
            f.write("-cp " + classpath)

    def get_full_name(self, test_file):
        package = self.get_package(test_file)
        test_case = os.path.splitext(os.path.basename(test_file))[0]
        return f"{package}.{test_case}" if package else test_case

    def instrument(self, instrument_dir, datafile_dir):
        if self.coverage_tool == "jacoco":
            return
        os.makedirs(instrument_dir, exist_ok=True)
        os.makedirs(datafile_dir, exist_ok=True)
        if 'instrumented' in os.listdir(instrument_dir):
            return
        if self.has_submodule(self.target_path):
            target_classes = os.path.join(self.target_path, '**/target/classes')
        else:
            target_classes = os.path.join(self.target_path, 'target/classes')
        subprocess.run(
            ["bash", os.path.join(COBERTURA_DIR, "cobertura-instrument.sh"),
             "--basedir", self.target_path,
             "--destination", f"{instrument_dir}/instrumented",
             "--datafile", f"{datafile_dir}/cobertura.ser",
             target_classes],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def report(self, datafile_dir, report_dir, jacoco_exec_override=None):
        os.makedirs(report_dir, exist_ok=True)
        result = None
        if self.coverage_tool == "cobertura":
            result = subprocess.run(
                ["bash", os.path.join(COBERTURA_DIR, "cobertura-report.sh"),
                 "--format", REPORT_FORMAT,
                 "--datafile", f"{datafile_dir}/cobertura.ser",
                 "--destination", report_dir],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            jacoco_exec_path = (jacoco_exec_override
                                or os.path.join(datafile_dir, "jacoco.exec"))
            if (os.path.exists(jacoco_exec_path) and
                    os.path.getsize(jacoco_exec_path) > 0):
                mvn_cmd = [
                    "mvn", "jacoco:report",
                    f"-Djacoco.dataFile={jacoco_exec_path}",
                    "-Dmaven.bundle.skip=true",
                    "-f", os.path.join(self.target_path, "pom.xml"),
                ]
                result = subprocess.run(
                    mvn_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=self.target_path, text=True)
                jacoco_xml = os.path.join(
                    self.target_path, "target", "site", "jacoco", "jacoco.xml")
                if os.path.exists(jacoco_xml):
                    print(f"Jacoco report generated: {os.path.dirname(jacoco_xml)}")
                else:
                    print(f"[WARN] Jacoco report generation failed")
            else:
                print(f"[WARN] jacoco.exec invalid or missing: {jacoco_exec_path}")
        return result

    def make_dependency(self):
        mvn_dependency_dir = 'target/dependency'
        if not self.has_made():
            subprocess.run(
                f"mvn dependency:copy-dependencies -DoutputDirectory={mvn_dependency_dir} "
                f"-f {self.target_path}/pom.xml",
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(
                f"mvn install -DskipTests -f {self.target_path}/pom.xml",
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dep_jars = glob.glob(self.target_path + "/**/*.jar", recursive=True)
        return ':'.join(list(set(dep_jars)))

    def has_made(self):
        for dirpath, dirnames, filenames in os.walk(self.target_path):
            if 'pom.xml' in filenames and 'target' in dirnames:
                if 'dependency' in os.listdir(os.path.join(dirpath, 'target')):
                    return True
        return False

    def copy_tests(self, target_dir):
        tests = glob.glob(self.test_path + "/**/*Test.java", recursive=True)
        target_project = os.path.basename(self.target_path.rstrip('/'))
        for dir_name in ("test_cases", "compiler_output", "test_output", "report"):
            os.makedirs(os.path.join(target_dir, dir_name), exist_ok=True)
        print("Copying tests to", target_project, '...')
        for tc in tests:
            tc_norm = os.path.normpath(tc)
            parts = tc_norm.split(os.sep)
            tc_project = None
            for part in reversed(parts[:-1]):
                if '%' in part:
                    tokens = part.split('%')
                    if len(tokens) >= 2 and tokens[1]:
                        tc_project = tokens[1]
                        break
            if not tc_project and target_project in parts:
                tc_project = target_project
            if not tc_project:
                continue
            if tc_project != target_project or not os.path.exists(self.target_path):
                continue
            os.system(f"cp {tc} {os.path.join(target_dir, 'test_cases')}")