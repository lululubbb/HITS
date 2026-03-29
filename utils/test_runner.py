"""
utils/test_runner.py  — HITS full-featured test runner (updated)

Produces per-test and per-group CSVs:
  - status.csv            (per-test compile/exec status)
  - coverage.csv          (project-level summary)
  - coveragedetail.csv    (per-test coverage at project/class/focal-method level)
  - coveragemethod.csv    (per-focal-method group aggregate coverage)
  - final_scores.csv      (per-test weighted score)
  - final_scores2.csv     (per-focal-method-group weighted score)

Multi modified-class support via test_runner_focal_fix.
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

from utils.test_runner_focal_fix import (
    resolve_all_target_classes,
    resolve_target_class_for_test,
    is_focal_method_match_fixed,
    safe_params_to_descriptor_fixed,
)
from utils.config import (
    TIMEOUT, JUNIT_JAR, MOCKITO_JAR, LOG4J_JAR,
    JACOCO_AGENT, JACOCO_CLI, COBERTURA_DIR, REPORT_FORMAT,
    playground_dir, test_number,
)

# dataset_dir may not exist in all configs — guard it
try:
    from utils.config import dataset_dir as _DATASET_DIR
except ImportError:
    _DATASET_DIR = ""


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
        self.coverage_tool = tool
        self.test_path = test_path
        self.target_path = target_path
        self.output_path = output_path or test_path
        self.debug = debug

        self.dependencies = self.make_dependency()
        self.build_dir_name = "target/classes"
        self.build_dir = self.process_single_repo()

        self.COMPILE_ERROR = 0
        self.TEST_RUN_ERROR = 0
        self.SYNTAX_TOTAL = 0
        self.SYNTAX_ERROR = 0
        self.jacoco_destfile = None

        self.logger = logging.getLogger('test_runner')
        self.modules = parse_root_pom(target_path) or []

        if output_path and not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

    # ── Public entry points ────────────────────────────────────────────────────

    def start_single_test(self):
        """
        Used by fix_code.advanced_run_check().
        self.test_path = step_workspace (e.g. method_0/fixing/TestName/0)
        Compiles + runs the .java in temp/, writes exec to runtemp/jacoco.exec,
        generates HTML report into cov_check_dir/ via jacoco-cli (NOT mvn).
        """
        temp_dir = os.path.join(self.test_path, "temp")
        compiled_test_dir = os.path.join(self.test_path, "runtemp")
        os.makedirs(compiled_test_dir, exist_ok=True)
        try:
            self.instrument(compiled_test_dir, compiled_test_dir)
            java_files = glob.glob(os.path.join(temp_dir, '*.java'))
            if not java_files:
                return False
            test_file = os.path.abspath(java_files[0])
            compiler_output = os.path.join(temp_dir, 'compile_error')
            test_output = os.path.join(temp_dir, 'runtime_error')
            if not self.run_single_test(test_file, compiled_test_dir,
                                        compiler_output, test_output):
                return False
            else:
                # Generate HTML/XML report using jacoco-cli so that
                # coverage_check / jacoco_analysis can read class-level HTML
                cov_check_dir = os.path.join(self.test_path, "cov_check_dir")
                self._report_jacoco_cli(compiled_test_dir, cov_check_dir)
        except Exception as e:
            print(f"[start_single_test] {e}")
            return False
        return True

    def start_all_test(self):
        if (os.path.isdir(self.test_path) and
                os.path.isdir(os.path.join(self.test_path, 'test_cases'))):
            tests_dir = self.test_path
        else:
            date = datetime.now().strftime("%Y%m%d%H%M%S")
            tests_dir = os.path.join(self.target_path, f"tests%{date}")
            self.copy_tests(tests_dir)

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

    # ── Logs ───────────────────────────────────────────────────────────────────

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

    # ── Target class / focal method resolution ─────────────────────────────────

    def _resolve_target_class(self, tests_dir):
        """Return simple class name of the modified/focal class."""
        all_classes = resolve_all_target_classes(self.target_path)
        if all_classes:
            return all_classes[0]
        meta_file = os.path.join(self.target_path, 'modified_classes.src')
        if os.path.exists(meta_file):
            try:
                with open(meta_file) as f:
                    line = f.readline().strip()
                if line:
                    return line.split('.')[-1]
            except Exception:
                pass
        prop_file = os.path.join(self.target_path, 'defects4j.build.properties')
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
        # Fallback: infer from test file names in steps/
        steps_dir = os.path.join(tests_dir, 'steps')
        search_dir = steps_dir if os.path.isdir(steps_dir) else tests_dir
        if os.path.isdir(search_dir):
            for fname in sorted(os.listdir(search_dir)):
                if fname.endswith('Test.java'):
                    m = re.match(r'^(.+?)_[^_]+_\d+Test\.java$', fname)
                    if m:
                        return m.group(1)
                    return fname.split('_')[0]
        return ''

    def _resolve_focal_method(self, tests_dir, explicit_focal_method: str = ''):
        """
        FIX #1: Accept an explicit focal method name so that each per-method
        invocation of run_all_tests uses the correct focal method rather than
        always reading the first entry from the global dataset_dir.

        Fallback chain:
          1. explicit_focal_method parameter (highest priority)
          2. raw_data .json in tests_dir/dataset/raw_data/
          3. test file name parsing in steps/
          4. global dataset_dir (last resort, kept for backward compat)
        """
        if explicit_focal_method:
            return explicit_focal_method

        # Priority 2: local raw_data relative to tests_dir
        for raw_data_dir in [
            os.path.join(tests_dir, "dataset", "raw_data"),
            os.path.join(tests_dir, "raw_data"),
        ]:
            if os.path.isdir(raw_data_dir):
                try:
                    for fname in sorted(os.listdir(raw_data_dir)):
                        if fname.endswith('.json') and '%' in fname:
                            parts = fname.split('%')
                            if len(parts) >= 4:
                                method_candidate = parts[3].strip()
                                if method_candidate and not method_candidate.isdigit():
                                    return method_candidate
                except Exception:
                    pass

        # Priority 3: infer from steps/ java filenames
        steps_dir = os.path.join(tests_dir, 'steps')
        if os.path.isdir(steps_dir):
            for fname in sorted(os.listdir(steps_dir)):
                if fname.endswith('Test.java'):
                    m = re.match(r'^.+?_([^_]+)_\d+Test\.java$', fname)
                    if m:
                        mid = m.group(1)
                        if not mid.isdigit():
                            return mid

        # Priority 4: global dataset_dir (last resort — may return wrong method)
        global_raw = os.path.join(_DATASET_DIR, "raw_data") if _DATASET_DIR else ""
        if global_raw and os.path.isdir(global_raw):
            try:
                for fname in sorted(os.listdir(global_raw)):
                    if fname.endswith('.json') and '%' in fname:
                        parts = fname.split('%')
                        if len(parts) >= 4:
                            method_candidate = parts[3].strip()
                            if method_candidate and not method_candidate.isdigit():
                                return method_candidate
            except Exception:
                pass
        return ''

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

    def _merge_jacoco_execs(self, exec_paths: list, out_exec: str) -> bool:
        valid_execs = [p for p in exec_paths
                       if p and os.path.exists(p) and os.path.getsize(p) > 0]
        if not valid_execs:
            return False
        os.makedirs(os.path.dirname(out_exec), exist_ok=True)
        if len(valid_execs) == 1:
            try:
                shutil.copy2(valid_execs[0], out_exec)
                return os.path.exists(out_exec) and os.path.getsize(out_exec) > 0
            except Exception:
                return False
        if JACOCO_CLI and os.path.exists(JACOCO_CLI):
            cmd = ["java", "-jar", JACOCO_CLI, "merge",
                   *valid_execs, "--destfile", out_exec]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True)
                return os.path.exists(out_exec) and os.path.getsize(out_exec) > 0
            except Exception:
                pass
        # Fallback: copy first valid exec
        try:
            shutil.copy2(valid_execs[0], out_exec)
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
            merged_ok = self._merge_jacoco_execs(exec_paths, grp_exec)

            if not merged_ok:
                result[grp_k] = {
                    'f_line_total': None, 'f_line_cov': None,
                    'f_branch_total': None, 'f_branch_cov': None,
                }
                continue

            grp_report_dir = os.path.join(report_base_dir, grp_k)
            os.makedirs(grp_report_dir, exist_ok=True)
            # Generate jacoco.xml via mvn for focal method extraction
            self._report_mvn(grp_exec, grp_report_dir)

            grp_xml = os.path.join(grp_report_dir, 'jacoco.xml')
            if not os.path.exists(grp_xml):
                # Try global xml
                global_xml = os.path.join(
                    self.target_path, 'target', 'site', 'jacoco', 'jacoco.xml')
                if os.path.exists(global_xml):
                    try:
                        shutil.copy2(global_xml, grp_xml)
                    except Exception:
                        pass

            flc = flt = fbc = fbt = 0
            found = False
            root_elem = self._parse_jacoco_xml(grp_xml)
            if root_elem is not None:
                for cls_elem in root_elem.findall('.//class'):
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
                        if not is_focal_method_match_fixed(
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
                                flc += cov; flt += cov + mis
                            elif ct == 'BRANCH':
                                fbc += cov; fbt += cov + mis

            result[grp_k] = {
                'f_line_total': flt if found else None,
                'f_line_cov': flc if found else None,
                'f_branch_total': fbt if found else None,
                'f_branch_cov': fbc if found else None,
            }
        return result

    # ── JVM descriptor helpers ─────────────────────────────────────────────────

    _JAVA_PRIMITIVE_MAP = {
        'int': 'I', 'long': 'J', 'double': 'D', 'float': 'F',
        'boolean': 'Z', 'byte': 'B', 'char': 'C', 'short': 'S', 'void': 'V',
    }

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
        """
        Build mapping from method-id → {name, descriptor} by reading
        raw_data JSON files. Searches tests_dir-local raw_data first,
        then global dataset_dir as fallback.
        """
        import json as _json
        result: dict = {}

        # Search in order: local then global
        raw_data_dirs = []
        for d in [
            os.path.join(tests_dir, "dataset", "raw_data"),
            os.path.join(tests_dir, "raw_data"),
        ]:
            if os.path.isdir(d):
                raw_data_dirs.append(d)
        global_raw = os.path.join(_DATASET_DIR, "raw_data") if _DATASET_DIR else ""
        if global_raw and os.path.isdir(global_raw) and global_raw not in raw_data_dirs:
            raw_data_dirs.append(global_raw)

        for raw_data_dir in raw_data_dirs:
            try:
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
                    if mid in result:
                        continue
                    entry = {'name': name_from_fname, 'descriptor': None, 'params': None}
                    try:
                        with open(os.path.join(raw_data_dir, fname), 'r',
                                  encoding='utf-8', errors='replace') as _jf:
                            data = _json.loads(_jf.read(65536))
                        entry['name'] = (data.get('method_name') or
                                         data.get('focal_method') or name_from_fname)
                        jvm_desc = (data.get('method_descriptor') or
                                    data.get('focal_method_descriptor') or
                                    data.get('descriptor'))
                        if jvm_desc and isinstance(jvm_desc, str) and jvm_desc.startswith('('):
                            paren_close = jvm_desc.find(')')
                            entry['descriptor'] = (jvm_desc[:paren_close + 1]
                                                   if paren_close >= 0 else jvm_desc)
                            result[mid] = entry
                            continue
                        for sig_key in ('focal_method_signature', 'method_signature',
                                        'signature', 'focal_method'):
                            sig_raw = data.get(sig_key)
                            if not sig_raw or '(' not in sig_raw:
                                continue
                            po = sig_raw.index('('); pc = sig_raw.rfind(')')
                            if pc <= po:
                                continue
                            rps = sig_raw[po + 1:pc].strip()
                            if not rps:
                                entry['descriptor'] = '()'; break
                            pts = [s.strip().split()[0] for s in rps.split(',') if s.strip()]
                            desc = self._safe_params_to_descriptor(pts)
                            if desc is not None:
                                entry['descriptor'] = desc; break
                    except Exception:
                        pass
                    result[mid] = entry
            except Exception:
                pass
        return result

    # ── Coverage extraction helpers ────────────────────────────────────────────

    @staticmethod
    def _extract_missed_coverage(jacoco_xml_path: str, target_class: str):
        missed_methods = []
        partial_methods = []
        if not jacoco_xml_path or not os.path.exists(jacoco_xml_path):
            return missed_methods, partial_methods
        try:
            with open(jacoco_xml_path, 'r', encoding='utf-8', errors='replace') as _f:
                raw = _f.read()
            start = raw.find('<report')
            if start < 0:
                return missed_methods, partial_methods
            root = ET.fromstring(raw[start:])
            simple = target_class.split('.')[-1] if target_class else ''
            for cls in root.iter('class'):
                cname = cls.get('name', '')
                if cname.split('/')[-1].split('$')[0] != simple:
                    continue
                for method_elem in cls.findall('method'):
                    mname = method_elem.get('name', '')
                    mline = method_elem.get('line', '?')
                    if mname == '<clinit>':
                        continue
                    display_name = f"{simple}()" if mname == '<init>' else mname
                    lm = lc = bm = bc_ = 0
                    for c in method_elem.findall('counter'):
                        ct = c.get('type', '')
                        if ct == 'LINE':
                            lm = int(c.get('missed', 0)); lc = int(c.get('covered', 0))
                        elif ct == 'BRANCH':
                            bm = int(c.get('missed', 0)); bc_ = int(c.get('covered', 0))
                    if lc == 0 and lm > 0:
                        missed_methods.append(
                            f"line {mline}: {display_name}() — completely uncovered")
                    elif bm > 0:
                        partial_methods.append(
                            f"line {mline}: {display_name}() — "
                            f"{bm}/{bm+bc_} branches missed")
                break
        except Exception as e:
            print(f"[WARN] _extract_missed_coverage: {e}")
        return missed_methods, partial_methods

    @staticmethod
    def _parse_jacoco_xml(xml_path: str):
        if not xml_path or not os.path.exists(xml_path):
            return None
        try:
            with open(xml_path, 'r', encoding='utf-8', errors='replace') as f:
                raw = f.read()
            start = raw.find('<report')
            if start < 0:
                return None
            return ET.fromstring(raw[start:])
        except Exception:
            return None

    # ── JaCoCo report helpers ──────────────────────────────────────────────────

    def _report_jacoco_cli(self, compiled_test_dir: str, report_dir: str,
                            jacoco_exec_override: str = None) -> bool:
        """
        Generate HTML + XML report using jacoco-cli.
        Required by fix_code.coverage_check → jacoco_analysis which reads
        package/ClassName.html from report_dir.
        Returns True on success.
        """
        os.makedirs(report_dir, exist_ok=True)
        if not JACOCO_CLI or not os.path.exists(JACOCO_CLI):
            print(f"[WARN] JACOCO_CLI not found: {JACOCO_CLI}, skipping CLI report")
            return False

        exec_path = jacoco_exec_override or os.path.join(compiled_test_dir, 'jacoco.exec')
        if not os.path.exists(exec_path) or os.path.getsize(exec_path) == 0:
            print(f"[WARN] jacoco.exec invalid or missing: {exec_path}")
            return False

        # Collect class dirs
        module_poms = parse_root_pom(self.target_path) or []
        class_dirs = [os.path.join(os.path.dirname(p), 'target', 'classes')
                      for p in module_poms]
        class_dirs = [d for d in class_dirs if os.path.exists(d)]
        if not class_dirs:
            class_dirs_fallback = os.path.join(self.target_path, 'target', 'classes')
            if os.path.exists(class_dirs_fallback):
                class_dirs = [class_dirs_fallback]

        # Collect source dirs
        src_dirs = []
        for p in module_poms:
            for src_suffix in ['src/main/java', 'src/main']:
                sd = os.path.join(os.path.dirname(p), src_suffix)
                if os.path.exists(sd):
                    src_dirs.append(sd)
                    break

        cmd = ["java", "-jar", JACOCO_CLI, "report", exec_path]
        for d in class_dirs:
            cmd += ["--classfiles", d]
        cmd += ["--html", report_dir, "--xml", os.path.join(report_dir, "jacoco.xml")]
        for sd in src_dirs:
            cmd += ["--sourcefiles", sd]

        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=self.target_path)
            if result.returncode == 0:
                print(f"[INFO] jacoco-cli report generated: {report_dir}")
                return True
            else:
                stderr = result.stderr.decode(errors='ignore')
                print(f"[WARN] jacoco-cli report rc={result.returncode}: {stderr[:200]}")
                return False
        except Exception as e:
            print(f"[WARN] jacoco-cli report exception: {e}")
            return False

    def _report_mvn(self, jacoco_exec_path: str, report_dir: str) -> bool:
        """
        Generate jacoco.xml via 'mvn jacoco:report'.
        Copies resulting XML to report_dir/jacoco.xml.
        Returns True on success.
        """
        if not os.path.exists(jacoco_exec_path) or os.path.getsize(jacoco_exec_path) == 0:
            print(f"[WARN] jacoco.exec invalid or missing: {jacoco_exec_path}")
            return False
        os.makedirs(report_dir, exist_ok=True)
        mvn_cmd = [
            "mvn", "jacoco:report",
            f"-Djacoco.dataFile={os.path.abspath(jacoco_exec_path)}",
            "-Dmaven.bundle.skip=true",
            "-f", os.path.join(self.target_path, "pom.xml"),
        ]
        try:
            result = subprocess.run(mvn_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=self.target_path, text=True)
            global_xml = os.path.join(
                self.target_path, "target", "site", "jacoco", "jacoco.xml")
            dest_xml = os.path.join(report_dir, "jacoco.xml")
            if os.path.exists(global_xml):
                shutil.copy2(global_xml, dest_xml)
                print(f"[INFO] mvn jacoco:report done → {dest_xml}")
                return True
            else:
                print(f"[WARN] mvn jacoco:report: jacoco.xml not generated")
                return False
        except Exception as e:
            print(f"[WARN] mvn jacoco:report exception: {e}")
            return False

    def report(self, datafile_dir: str, report_dir: str,
               jacoco_exec_override: str = None):
        """
        Unified report method:
        - For start_single_test (cov_check_dir): use jacoco-cli so HTML is available
          for jacoco_analysis()
        - For run_all_tests global report: use mvn jacoco:report for per-class XML
        This method tries jacoco-cli first (HTML+XML), falls back to mvn (XML only).
        """
        os.makedirs(report_dir, exist_ok=True)
        if self.coverage_tool == "cobertura":
            return subprocess.run(
                ["bash", os.path.join(COBERTURA_DIR, "cobertura-report.sh"),
                 "--format", REPORT_FORMAT,
                 "--datafile", f"{datafile_dir}/cobertura.ser",
                 "--destination", report_dir],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        exec_path = jacoco_exec_override or os.path.join(datafile_dir, "jacoco.exec")
        # Try jacoco-cli first (needed for HTML by coverage_check)
        ok = self._report_jacoco_cli(datafile_dir, report_dir,
                                     jacoco_exec_override=exec_path)
        if not ok:
            # Fallback to mvn
            self._report_mvn(exec_path, report_dir)

    # ── Main test loop ─────────────────────────────────────────────────────────

    def run_all_tests(self, tests_dir, compiled_test_dir, compiler_output,
                      test_output, report_dir, logs=None,
                      focal_method: str = '', target_class_override: str = ''):
        """
        FIX #2: Scan tests_dir/steps/ for ALL .java test files (not filtered by
        attempt index), since HITS stores generated tests in steps/.

        FIX #1: Accept focal_method parameter so each method-level call gets the
        correct focal method name instead of the global dataset first entry.

        FIX #3: Per-test jacoco.exec written to compiled_test_dir/jacoco_{name}.exec;
        merged exec assembled after all tests for global report.

        Outputs: status.csv, coverage.csv, coveragedetail.csv,
                 coveragemethod.csv, final_scores.csv, final_scores2.csv
        """
        # ── Setup ──────────────────────────────────────────────────────────────
        steps_dir = os.path.join(tests_dir, "steps")
        if not os.path.isdir(steps_dir):
            # Fallback: check if tests are in 'fixing' directory instead
            fixing_dir = os.path.join(tests_dir, 'fixing')
            if os.path.isdir(fixing_dir):
                print(f"[INFO] steps dir not found: {steps_dir}")
                print(f"[INFO] Found fixing dir instead: {fixing_dir}")
                # Will use fixing dir tests below
            else:
                # Fallback: check if tests are in 'test_cases' directory
                test_cases_dir = os.path.join(tests_dir, 'test_cases')
                if os.path.isdir(test_cases_dir):
                    print(f"[INFO] steps dir not found: {steps_dir}")
                    print(f"[INFO] Found test_cases dir instead: {test_cases_dir}")
                    steps_dir = test_cases_dir
                else:
                    print(f"[WARN] Neither steps nor fixing nor test_cases dir found: {steps_dir} or {fixing_dir} or {test_cases_dir}")
                    return 0, 0

        self.instrument(compiled_test_dir, compiled_test_dir)
        start_time = datetime.now()

        total_compile = 0
        total_tests = 0

        all_target_classes = resolve_all_target_classes(self.target_path)
        target_class = (target_class_override or
                        self._resolve_target_class(tests_dir))

        # FIX #1: use explicit focal_method; _resolve_focal_method falls back
        # through local → steps → global only if not provided
        resolved_focal = self._resolve_focal_method(tests_dir, focal_method)

        project_name = os.path.basename(self.target_path.rstrip('/'))
        global_csv_parent_dir = os.path.abspath(tests_dir)
        os.makedirs(global_csv_parent_dir, exist_ok=True)

        per_test_status_map = {}
        per_test_records = []

        mid_to_focal_map = self._build_mid_to_focal_map(tests_dir)
        mid_to_name = {mid: info['name'] for mid, info in mid_to_focal_map.items()}

        print(f"[INFO] focal_method='{resolved_focal}'  target_class='{target_class}'")

        # FIX #2: collect ALL .java files in steps/, no attempt-index filtering
        all_test_files = sorted([
            f for f in os.listdir(steps_dir) if f.endswith('.java')
        ])
        if not all_test_files:
            print(f"[WARN] No .java files in steps dir: {steps_dir}")
            return 0, 0

        print(f"[INFO] Found {len(all_test_files)} test files in {steps_dir}")

        for test_case_file in all_test_files:
            total_compile += 1
            total_tests += 1
            test_file = os.path.join(steps_dir, test_case_file)
            full_name = self.get_full_name(test_file)

            # ── 1) Syntax check ────────────────────────────────────────────
            syntax_tmp = tempfile.mkdtemp()
            try:
                syntax_cmd = self.javac_cmd(syntax_tmp, test_file)
                # Insert -Xlint after "javac"
                syntax_cmd_xlint = [syntax_cmd[0], '-Xlint:all'] + syntax_cmd[1:]
                proc = subprocess.run(syntax_cmd_xlint, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True)
                stderr_s = proc.stderr or ""
                self.SYNTAX_TOTAL += 1
                syntax_pattern = re.compile(
                    r"(illegal start of expression|';' expected|"
                    r"unclosed string literal|unterminated string literal|"
                    r"unclosed comment|illegal character|identifier expected|"
                    r"syntax error)",
                    re.IGNORECASE)
                if proc.returncode != 0:
                    if syntax_pattern.search(stderr_s):
                        self.SYNTAX_ERROR += 1
                        if logs:
                            with open(logs['syntax'], 'a') as f:
                                f.write(f"[SYNTAX_ERROR] {test_case_file}: "
                                        f"{stderr_s.splitlines()[0] if stderr_s else ''}\n")
                    else:
                        if logs:
                            with open(logs['syntax'], 'a') as f:
                                f.write(f"[SYNTAX_SEMANTIC] {test_case_file}: "
                                        f"{stderr_s.splitlines()[0] if stderr_s else ''}\n")
                else:
                    if logs:
                        with open(logs['syntax'], 'a') as f:
                            f.write(f"[SYNTAX_OK] {test_case_file}\n")
            finally:
                if os.path.exists(syntax_tmp):
                    shutil.rmtree(syntax_tmp)

            # ── 2) Compile ─────────────────────────────────────────────────
            os.makedirs(compiled_test_dir, exist_ok=True)
            cmd = self.javac_cmd(compiled_test_dir, test_file)
            result = subprocess.run(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            compiled_ok = (result.returncode == 0)

            if not compiled_ok:
                self.COMPILE_ERROR += 1
                if logs:
                    with open(logs['compile'], 'a') as f:
                        f.write(f"[COMPILE_FAILED] {full_name}: "
                                f"{result.stderr.splitlines()[0] if result.stderr else ''}\n")
                    with open(logs['compile_failed'], 'a') as f:
                        f.write(f"{full_name}\t{test_case_file}\n")
                co_file = (f"{compiler_output}.txt"
                           if os.path.basename(compiler_output) == 'compile_error'
                           else f"{compiler_output}-{os.path.basename(test_file)}.txt")
                os.makedirs(os.path.dirname(co_file), exist_ok=True)
                with open(co_file, "w") as f:
                    f.write(result.stdout + result.stderr)
                per_test_status_map[full_name] = {
                    'compile_status': 'fail', 'exec_status': 'skip',
                    'exec_timeout': False, 'jacoco_exec_size': 0,
                    'compile_score': 0.0, 'exec_score': 0.0,
                }
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

            # ── 3) Run test ────────────────────────────────────────────────
            # FIX #2 (multi-class): resolve correct target class per test
            test_target_class = resolve_target_class_for_test(
                full_name, all_target_classes, fallback=target_class)

            test_basename = os.path.splitext(test_case_file)[0]
            # FIX #3: unique exec file per test
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

            if logs:
                with open(logs['exec'], 'a') as f:
                    status_str = 'OK' if exec_ok else ('TIMEOUT' if is_timeout else 'FAILED')
                    f.write(f"[EXEC_{status_str}] {full_name}\n")

            # ── 4) Per-test coverage ───────────────────────────────────────
            exec_note = 'ok' if exec_ok else ('timeout' if is_timeout else 'fail')
            m_per_line_cov = m_per_line_total = None
            m_per_branch_cov = m_per_branch_total = None
            f_per_line_cov = f_per_line_total = None
            f_per_branch_cov = f_per_branch_total = None
            per_test_jacoco_xml = None

            if exec_size > 0:
                # Generate per-test report (jacoco-cli for HTML + XML)
                per_test_report_dir = os.path.join(
                    report_dir, "per_test_reports", test_basename)
                os.makedirs(per_test_report_dir, exist_ok=True)

                cli_ok = self._report_jacoco_cli(compiled_test_dir, per_test_report_dir,
                                                  jacoco_exec_override=per_test_exec)
                if cli_ok:
                    per_test_jacoco_xml = os.path.join(per_test_report_dir, "jacoco.xml")
                else:
                    # Fallback: mvn report and copy xml
                    mvn_ok = self._report_mvn(per_test_exec, per_test_report_dir)
                    if mvn_ok:
                        per_test_jacoco_xml = os.path.join(per_test_report_dir, "jacoco.xml")

                # Extract coverage numbers from per-test xml
                if per_test_jacoco_xml and os.path.exists(per_test_jacoco_xml):
                    try:
                        root_p = self._parse_jacoco_xml(per_test_jacoco_xml)
                        if root_p is not None and test_target_class:
                            grp_for_this = self._group_from_test_class(full_name)
                            focal_for_this, focal_desc_for_this = \
                                self._focal_info_from_group(
                                    grp_for_this, mid_to_name,
                                    resolved_focal, mid_to_focal_map)

                            for class_elem in root_p.findall('.//class'):
                                cname = class_elem.attrib.get('name', '')
                                simple = cname.split('/')[-1].split('$')[0]
                                if (simple != test_target_class and
                                        not cname.endswith('/' + test_target_class)):
                                    continue
                                # Class-level (modified class) coverage
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
                                # Focal method coverage
                                if focal_for_this:
                                    for me in class_elem.findall('method'):
                                        if not is_focal_method_match_fixed(
                                                me.get('name', ''), focal_for_this,
                                                test_target_class,
                                                focal_descriptor=focal_desc_for_this,
                                                method_desc=me.get('desc', '')):
                                            continue
                                        fl = ft = fb = fbt_ = 0
                                        for cc in me.findall('counter'):
                                            ct2 = cc.get('type', '')
                                            cv2 = int(cc.get('covered', 0))
                                            ms2 = int(cc.get('missed', 0))
                                            if ct2 == 'LINE':
                                                fl += cv2; ft += cv2 + ms2
                                            elif ct2 == 'BRANCH':
                                                fb += cv2; fbt_ += cv2 + ms2
                                        if ft > 0:
                                            f_per_line_cov = fl
                                            f_per_line_total = ft
                                        if fbt_ > 0:
                                            f_per_branch_cov = fb
                                            f_per_branch_total = fbt_
                                break
                    except Exception as xe:
                        if logs:
                            with open(logs.get('coverage', os.devnull), 'a') as _f:
                                _f.write(f"[PER_TEST_XML_ERR] {test_case_file}: {xe}\n")

            per_test_records.append({
                'test_class': full_name,
                'exec_file': per_test_exec if exec_size > 0 else None,
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

        # ── Write status.csv ────────────────────────────────────────────────
        self._write_per_test_status(
            global_csv_parent_dir, project_name, target_class,
            per_test_status_map, logs)

        # ── FIX #3: Merge all per-test exec files for global report ─────────
        # Collect all jacoco exec files generated from individual test runs
        exec_files = []
        for test_case_file in all_test_files:
            test_basename = os.path.splitext(test_case_file)[0]
            per_test_exec = os.path.join(compiled_test_dir, f"jacoco_{test_basename}.exec")
            if os.path.exists(per_test_exec):
                fsize = os.path.getsize(per_test_exec)
                if fsize > 0:
                    exec_files.append(per_test_exec)
                    if logs:
                        with open(logs.get('coverage', os.devnull), 'a') as _f:
                            _f.write(f"[EXEC_FOUND] {test_basename}: {fsize} bytes\n")
                else:
                    if logs:
                        with open(logs.get('coverage', os.devnull), 'a') as _f:
                            _f.write(f"[EXEC_EMPTY] {test_basename}: 0 bytes (skipped)\n")
            else:
                if logs:
                    with open(logs.get('coverage', os.devnull), 'a') as _f:
                        _f.write(f"[EXEC_MISSING] {test_basename}\n")

        print(f"[INFO] Collected {len(exec_files)}/{len(all_test_files)} valid exec files")

        # Also collect exec files from fixing/ dirs (from Step 3a) if they exist
        # This allows Step 6 to re-report without re-running if needed
        fixing_dir = os.path.join(tests_dir, 'fixing')
        if os.path.isdir(fixing_dir):
            print(f"[INFO] Also checking fixing dir: {fixing_dir}")
            for test_dir in os.listdir(fixing_dir):
                test_root = os.path.join(fixing_dir, test_dir)
                if not os.path.isdir(test_root):
                    continue
                for trial_dir in os.listdir(test_root):
                    trial_path = os.path.join(test_root, trial_dir)
                    if not os.path.isdir(trial_path):
                        continue
                    for exec_subdir in ['runtemp', 'cov_check_dir']:
                        ep = os.path.join(trial_path, exec_subdir, 'jacoco.exec')
                        if os.path.exists(ep) and os.path.getsize(ep) > 0:
                            if ep not in exec_files:
                                exec_files.append(ep)
                                print(f"[INFO] Added fixing exec: {ep}")
                            break

        global_report_dir = os.path.join(report_dir, "final")
        os.makedirs(global_report_dir, exist_ok=True)
        merged_exec = os.path.join(compiled_test_dir, "jacoco_merged.exec")

        # ── Extract coverage from single merged global report (NOT from per-test summaries) ──
        line_cov = branch_cov = line_total = branch_total = None
        line_rate = branch_rate = None
        m_line_cov = m_branch_cov = m_line_total = m_branch_total = None
        m_line_rate = m_branch_rate = None
        modified_class_name = target_class or None

        root_elem = None
        if exec_files:
            # Merge all exec files into single merged exec
            print(f"[INFO] Merging {len(exec_files)} exec files...")
            merged_ok = self._merge_jacoco_execs(exec_files, merged_exec)
            if merged_ok:
                print(f"[INFO] ✓ Merged exec files → {merged_exec}")
                print(f"      Size: {os.path.getsize(merged_exec)} bytes")
                # Generate single global report from merged exec
                cli_ok = self._report_jacoco_cli(compiled_test_dir, global_report_dir,
                                                  jacoco_exec_override=merged_exec)
                if not cli_ok:
                    self._report_mvn(merged_exec, global_report_dir)
                # Parse the global jacoco.xml to extract coverage statistics
                jacoco_xml_candidates = [
                    os.path.join(global_report_dir, "jacoco.xml"),
                    os.path.join(self.target_path, "target", "site", "jacoco", "jacoco.xml"),
                ]
                for candidate in jacoco_xml_candidates:
                    root_elem = self._parse_jacoco_xml(candidate)
                    if root_elem is not None:
                        print(f"[INFO] ✓ Parsed global jacoco.xml from {candidate}")
                        break
                if root_elem is None:
                    print(f"[WARN] Could not parse jacoco.xml from any candidate:")
                    for candidate in jacoco_xml_candidates:
                        exists = os.path.exists(candidate)
                        print(f"       {candidate}: {'exists' if exists else 'NOT FOUND'}")
            else:
                print("[WARN] Could not merge exec files for global report")
        else:
            print(f"[WARN] ✗ No valid jacoco.exec files found!")
            print(f"       Expected location: {compiled_test_dir}/jacoco_*.exec")
            print(f"       Test count: {len(all_test_files)}")
            if logs and 'coverage' in logs:
                log_content = open(logs['coverage'], 'r').read()
                if log_content:
                    print(f"       Coverage log:\n{log_content}")

        # ── Extract global project coverage from merged XML ──
        if root_elem is not None:
            # Read top-level project coverage (all classes)
            project_counters = root_elem.findall('counter')  # Direct children of report element
            if not project_counters:
                # Fallback: use deepest package/sourcefile counters
                project_counters = root_elem.findall('.//sourcefile/counter')
                if project_counters:
                    project_counters = project_counters[-4:]  # Last LINE and BRANCH pairs

            for c in project_counters:
                ct = c.attrib.get('type', '')
                cov = int(c.attrib.get('covered', 0))
                mis = int(c.attrib.get('missed', 0))
                if ct == 'LINE':
                    line_cov = cov
                    line_total = cov + mis
                    line_rate = round(100.0 * cov / (cov + mis), 2) if (cov + mis) > 0 else 0.0
                elif ct == 'BRANCH':
                    branch_cov = cov
                    branch_total = cov + mis
                    branch_rate = round(100.0 * cov / (cov + mis), 2) if (cov + mis) > 0 else 0.0

            # Extract modified class coverage from the merged XML
            if modified_class_name:
                for class_elem in root_elem.findall('.//class'):
                    cname = class_elem.attrib.get('name', '')
                    simple_name = cname.split('/')[-1].split('$')[0]
                    if simple_name == modified_class_name or cname.endswith('/' + modified_class_name):
                        for cc in class_elem.findall('counter'):
                            ct = cc.attrib.get('type', '')
                            cv = int(cc.attrib.get('covered', 0))
                            ms = int(cc.attrib.get('missed', 0))
                            if ct == 'LINE':
                                m_line_cov = cv
                                m_line_total = cv + ms
                                m_line_rate = round(100.0 * cv / (cv + ms), 2) if (cv + ms) > 0 else 0.0
                            elif ct == 'BRANCH':
                                m_branch_cov = cv
                                m_branch_total = cv + ms
                                m_branch_rate = round(100.0 * cv / (cv + ms), 2) if (cv + ms) > 0 else 0.0
                        break

        # ── coveragedetail.csv ──────────────────────────────────────────────
        try:
            tc_slug = (target_class or 'unknown').replace('.', '')
            pn_slug = project_name.replace('.', '')
            detail_csv = os.path.join(global_csv_parent_dir,
                                      f'{pn_slug}_{tc_slug}_coveragedetail.csv')
            file_exists = os.path.exists(detail_csv)

            groups_cd: dict = {}
            for rec in per_test_records:
                grp_r = self._group_from_test_class(rec.get('test_class', ''))
                groups_cd.setdefault(grp_r, []).append(rec)

            focal_totals_cd: dict = self._compute_focal_totals_from_merged_jacoco(
                groups_cd, modified_class_name, mid_to_name,
                resolved_focal, mid_to_focal_map=mid_to_focal_map)

            # Fallback: use per-test maximums
            for grp_r, members_r in groups_cd.items():
                gtot = focal_totals_cd.get(grp_r, {})
                if not gtot or gtot.get('f_line_total') is None:
                    valid_members = [m for m in members_r
                                     if (m.get('f_per_line_total') or 0) > 0]
                    focal_totals_cd[grp_r] = {
                        'f_line_total': max((m.get('f_per_line_total') or 0)
                                           for m in valid_members) if valid_members else 0,
                        'f_line_cov':   max((m.get('f_per_line_cov') or 0)
                                           for m in valid_members) if valid_members else 0,
                        'f_branch_total': max((m.get('f_per_branch_total') or 0)
                                             for m in valid_members) if valid_members else 0,
                        'f_branch_cov':   max((m.get('f_per_branch_cov') or 0)
                                             for m in valid_members) if valid_members else 0,
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
                    fm_r = self._focal_method_from_group(grp_r, mid_to_name, resolved_focal)
                    gtot = focal_totals_cd.get(grp_r, {})
                    grp_m_lc = gtot.get('f_line_cov') or 0
                    grp_m_bc = gtot.get('f_branch_cov') or 0
                    lcp = round(100.0 * mlc / grp_m_lc, 4) if grp_m_lc and mlc else 0.0
                    bcp = round(100.0 * mbc / grp_m_bc, 4) if grp_m_bc and mbc else 0.0
                    cov_s = round(0.25*(mlr/100)+0.25*(mbr/100)+0.25*(lcp/100)+0.25*(bcp/100), 6)
                    rec['coverage_score'] = cov_s
                    rec['m_coverage_score'] = cov_s

                    ffc = rec.get('f_per_line_cov') or 0
                    fft = rec.get('f_per_line_total') or 0
                    ffr = round(100.0 * ffc / fft, 4) if fft else 0.0
                    fbc2 = rec.get('f_per_branch_cov') or 0
                    fbt2 = rec.get('f_per_branch_total') or 0
                    fbr2 = round(100.0 * fbc2 / fbt2, 4) if fbt2 else 0.0
                    gf_lc = gtot.get('f_line_cov') or 0
                    gf_bc = gtot.get('f_branch_cov') or 0
                    f_lcp = round(100.0 * ffc / gf_lc, 4) if gf_lc and ffc else 0.0
                    f_bcp = round(100.0 * fbc2 / gf_bc, 4) if gf_bc and fbc2 else 0.0
                    f_cov_s = round(0.25*(ffr/100)+0.25*(fbr2/100)+0.25*(f_lcp/100)+0.25*(f_bcp/100), 6)

                    writer.writerow([
                        project_name, target_class, tc_r, fm_r,
                        rec.get('exec_note', 'ok'),
                        mlc if mlt else '', mlt if mlt else '', mlr if mlt else '',
                        mbc if mbt else '', mbt if mbt else '', mbr if mbt else '',
                        lcp, bcp, cov_s,
                        ffc if fft else '', fft if fft else '', ffr if fft else '',
                        fbc2 if fbt2 else '', fbt2 if fbt2 else '', fbr2 if fbt2 else '',
                        f_lcp, f_bcp, f_cov_s,
                    ])
        except Exception as e:
            print(f'Failed to write coveragedetail.csv: {e}')
            import traceback; traceback.print_exc()

        # ── coveragemethod.csv / final_scores.csv / final_scores2.csv ────────
        try:
            groups: dict = {}
            for rec in per_test_records:
                grp_r = self._group_from_test_class(rec.get('test_class', ''))
                groups.setdefault(grp_r, []).append(rec)

            focal_totals: dict = self._compute_focal_totals_from_merged_jacoco(
                groups, modified_class_name, mid_to_name,
                resolved_focal, mid_to_focal_map=mid_to_focal_map)

            for grp_k, members_k in groups.items():
                gtot = focal_totals.get(grp_k, {})
                if not gtot or gtot.get('f_line_total') is None:
                    valid_mk = [m for m in members_k if (m.get('f_per_line_total') or 0) > 0]
                    focal_totals[grp_k] = {
                        'f_line_total': max((m.get('f_per_line_total') or 0) for m in valid_mk) if valid_mk else 0,
                        'f_line_cov':   max((m.get('f_per_line_cov') or 0) for m in valid_mk) if valid_mk else 0,
                        'f_branch_total': max((m.get('f_per_branch_total') or 0) for m in valid_mk) if valid_mk else 0,
                        'f_branch_cov':   max((m.get('f_per_branch_cov') or 0) for m in valid_mk) if valid_mk else 0,
                    }

            tc_slug = (target_class or 'unknown').replace('.', '')
            pn_slug = project_name.replace('.', '')

            # coveragemethod.csv
            cov_method_csv = os.path.join(
                global_csv_parent_dir, f'{pn_slug}_{tc_slug}_coveragemethod.csv')
            cm_new = not (os.path.exists(cov_method_csv) and os.path.getsize(cov_method_csv) > 0)
            with open(cov_method_csv, 'a', newline='', encoding='utf-8') as cmf:
                w_cm = csv.writer(cmf)
                if cm_new:
                    w_cm.writerow([
                        'project', 'target_class', 'focal_method', 'exec_status',
                        'f_per_line_cov', 'f_per_line_total', 'f_per_line_rate',
                        'f_per_branch_cov', 'f_per_branch_total', 'f_per_branch_rate',
                        'line_contrib_pct', 'branch_contrib_pct', 'coverage_score',
                    ])
                for grp_k, members_k in groups.items():
                    ft_k = focal_totals.get(grp_k, {})
                    flc = ft_k.get('f_line_cov') or 0
                    flt = ft_k.get('f_line_total') or 0
                    flr = round(100.0 * flc / flt, 4) if flt else 0.0
                    fbc = ft_k.get('f_branch_cov') or 0
                    fbt = ft_k.get('f_branch_total') or 0
                    fbr = round(100.0 * fbc / fbt, 4) if fbt else 0.0
                    cs = round(0.5*(flr/100)+0.5*(fbr/100), 6)
                    fm_k = self._focal_method_from_group(grp_k, mid_to_name, resolved_focal)
                    en_k = [m.get('exec_note', '') for m in members_k]
                    es_k = 'ok' if 'ok' in en_k else (en_k[0] if en_k else '')
                    w_cm.writerow([project_name, target_class, fm_k, es_k,
                                   flc, flt, flr, fbc, fbt, fbr, flr, fbr, cs])

            # Load bug_revealing and similarity for final scores
            br_map: dict = {}
            try:
                for bf in sorted(glob.glob(
                        os.path.join(global_csv_parent_dir, '*bugrevealing*.csv'))):
                    with open(bf, newline='', encoding='utf-8') as _bf:
                        for _r in csv.DictReader(_bf):
                            tc2 = _r.get('test_class', '').strip()
                            br_map[tc2] = (1.0 if str(_r.get('bug_revealing', '')).strip().lower() == 'true'
                                           else 0.0)
            except Exception:
                pass

            sim_map: dict = {}
            try:
                _sim_dir = os.path.join(global_csv_parent_dir, 'Similarity')
                if os.path.isdir(_sim_dir):
                    for sf in sorted(glob.glob(os.path.join(_sim_dir, '*_bigSims.csv'))):
                        with open(sf, newline='', encoding='utf-8') as _sf:
                            for _r in csv.DictReader(_sf):
                                try:
                                    sim_map[_r.get('test_case_1', '').strip()] = \
                                        float(_r.get('redundancy_score', ''))
                                except Exception:
                                    pass
            except Exception:
                pass

            _WC = 0.15; _WE = 0.15; _WV = 0.30; _WB = 0.20; _WR = 0.20

            # final_scores.csv
            per_test_final = os.path.join(global_csv_parent_dir,
                                          f'{pn_slug}_{tc_slug}_final_scores.csv')
            pf_new = not (os.path.exists(per_test_final) and os.path.getsize(per_test_final) > 0)
            with open(per_test_final, 'a', newline='', encoding='utf-8') as pf:
                pfw = csv.writer(pf)
                if pf_new:
                    pfw.writerow(['test_class', 'focal_method', 'compile_score',
                                  'exec_score', 'coverage_score', 'bug_revealing_score',
                                  'redundancy_score', 'final_score', 'valid_weight_pct'])
                for grp_k, members_k in groups.items():
                    fm_k = self._focal_method_from_group(grp_k, mid_to_name, resolved_focal)
                    for mrec in members_k:
                        tc_n = mrec.get('test_class', '')
                        cs_p = 1.0 if mrec.get('exec_note') != 'compile_fail' else 0.0
                        es_p = 1.0 if mrec.get('exec_note') == 'ok' else 0.0
                        cv_p = mrec.get('m_coverage_score', '')
                        br_p = br_map.get(tc_n)
                        br_p = br_p if br_p is not None else ''
                        sm_p = sim_map.get(tc_n)
                        sm_p = sm_p if sm_p is not None else ''
                        rd_p = (1.0 - sm_p) if isinstance(sm_p, float) else None
                        sw, vw = [], 0.0
                        for _v, _w in [(cs_p, _WC), (es_p, _WE), (cv_p, _WV),
                                       (br_p, _WB), (rd_p, _WR)]:
                            if isinstance(_v, (int, float)):
                                sw.append(_v * _w); vw += _w
                        fs_p = round(sum(sw) / vw, 6) if vw > 0 else ''
                        pfw.writerow([tc_n, fm_k, cs_p, es_p, cv_p,
                                      br_p, sm_p, fs_p, round(vw, 4)])

            # final_scores2.csv
            final_csv = os.path.join(global_csv_parent_dir,
                                     f'{pn_slug}_{tc_slug}_final_scores2.csv')
            fs2_new = not (os.path.exists(final_csv) and os.path.getsize(final_csv) > 0)
            with open(final_csv, 'a', newline='', encoding='utf-8') as f2:
                w2 = csv.writer(f2)
                if fs2_new:
                    w2.writerow(['test_class', 'focal_method', 'compile_score',
                                 'exec_score', 'coverage_score', 'bug_revealing_score',
                                 'redundancy_score', 'final_score', 'valid_weight_pct'])
                for grp_k, members_k in groups.items():
                    tot_k = len(members_k) or 1
                    cs_g = round(sum(1.0 if m.get('exec_note') != 'compile_fail' else 0.0
                                     for m in members_k) / tot_k, 6)
                    es_g = round(sum(1.0 if m.get('exec_note') == 'ok' else 0.0
                                     for m in members_k) / tot_k, 6)
                    ft_g = focal_totals.get(grp_k, {})
                    flcg = ft_g.get('f_line_cov') or 0; fltg = ft_g.get('f_line_total') or 0
                    fbcg = ft_g.get('f_branch_cov') or 0; fbtg = ft_g.get('f_branch_total') or 0
                    flrg = round(100.0*flcg/fltg, 4) if fltg else 0.0
                    fbrg = round(100.0*fbcg/fbtg, 4) if fbtg else 0.0
                    cv_g = round(0.5*(flrg/100)+0.5*(fbrg/100), 6) if (fltg or fbtg) else ''
                    brv = [br_map.get(m.get('test_class', '')) for m in members_k]
                    brv = [v for v in brv if v is not None]
                    br_g = round(sum(brv)/len(brv), 6) if brv else ''
                    smv = [sim_map.get(m.get('test_class', '')) for m in members_k]
                    smv = [v for v in smv if isinstance(v, (int, float))]
                    sm_g = round(sum(smv)/len(smv), 6) if smv else ''
                    rd_g = (1.0 - sm_g) if isinstance(sm_g, float) else None
                    sw, vw = [], 0.0
                    for _v, _w in [(cs_g, _WC), (es_g, _WE), (cv_g, _WV),
                                   (br_g, _WB), (rd_g, _WR)]:
                        if isinstance(_v, (int, float)):
                            sw.append(_v * _w); vw += _w
                    fs_g = round(sum(sw)/vw, 6) if vw > 0 else ''
                    fm_g = self._focal_method_from_group(grp_k, mid_to_name, resolved_focal)
                    w2.writerow([grp_k, fm_g, cs_g, es_g, cv_g,
                                 br_g, sm_g, fs_g, round(vw, 4)])

            # Print focal method coverage summary
            print("-" * 50)
            print("FOCAL METHOD COVERAGE (per group):")
            if focal_totals:
                for grp_k, ft_p in focal_totals.items():
                    fm_p  = self._focal_method_from_group(grp_k, mid_to_name, resolved_focal)
                    flcp = ft_p.get('f_line_cov') or 0
                    fltp = ft_p.get('f_line_total') or 0
                    fbcp = ft_p.get('f_branch_cov') or 0
                    fbtp = ft_p.get('f_branch_total') or 0
                    flrp = round(100.0*flcp/fltp, 4) if fltp else None
                    fbrp = round(100.0*fbcp/fbtp, 4) if fbtp else None
                    print(f"  group={grp_k}  focal_method={fm_p or '(unknown)'}")
                    print(f"    行覆盖率: {flrp}% ({flcp}/{fltp})" if flrp is not None
                          else "    行覆盖率: N/A")
                    print(f"    分支覆盖率: {fbrp}% ({fbcp}/{fbtp})" if fbrp is not None
                          else "    分支覆盖率: N/A")
            print("-" * 50)

        except Exception as _e:
            print(f'[WARN] per-focal/final csv generation failed: {_e}')
            import traceback; traceback.print_exc()

        # ── coverage.csv (summary) ─────────────────────────────────────────
        try:
            run_time_seconds = round((datetime.now() - start_time).total_seconds(), 2)
            Attempts = total_tests
            Aborted = 0
            denom = Attempts if Attempts > 0 else None
            run_denom = (Attempts - self.COMPILE_ERROR) if denom else None
            SyntaxRate  = (1.0 - self.SYNTAX_ERROR / denom) if denom else None
            CompileRate = (1.0 - self.COMPILE_ERROR / denom) if denom else None
            RunRate     = (1.0 - self.TEST_RUN_ERROR / run_denom) \
                if run_denom and run_denom > 0 else None
            Passed = max(0, Attempts - self.COMPILE_ERROR - self.TEST_RUN_ERROR)
            PassRate = (Passed / denom) if denom else None

            tc_slug = (target_class or 'unknown').replace('.', '')
            pn_slug = project_name.replace('.', '')
            summary_fname = os.path.join(global_csv_parent_dir,
                                         f'{pn_slug}_{tc_slug}_coverage.csv')
            fe = os.path.exists(summary_fname)
            with open(summary_fname, 'a', newline='', encoding='utf-8') as sf:
                w = csv.writer(sf)
                if not fe:
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
                    Attempts, Aborted, self.SYNTAX_ERROR,
                    round(SyntaxRate, 4) if SyntaxRate is not None else '',
                    self.COMPILE_ERROR,
                    round(CompileRate, 4) if CompileRate is not None else '',
                    self.TEST_RUN_ERROR,
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
            print(f'Failed to write coverage.csv: {e}')

        total_test_run = total_compile - self.COMPILE_ERROR

        # ── Final statistics printout ──────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"FINAL TEST RUN STATISTICS:")
        print(f"{'='*60}")
        print(f"  SYNTAX TOTAL COUNT:  {self.SYNTAX_TOTAL}")
        print(f"  SYNTAX ERROR COUNT:  {self.SYNTAX_ERROR}")
        print(f"  COMPILE TOTAL COUNT: {total_compile}")
        print(f"  COMPILE ERROR COUNT: {self.COMPILE_ERROR}")
        print(f"  TEST RUN TOTAL COUNT: {total_test_run}")
        print(f"  TEST RUN ERROR COUNT: {self.TEST_RUN_ERROR}")
        print(f"  Passed: {max(0, total_compile - self.COMPILE_ERROR - self.TEST_RUN_ERROR)}")
        print(f"  Pass Rate: {round(100.0 * max(0, total_compile - self.COMPILE_ERROR - self.TEST_RUN_ERROR) / (total_compile or 1), 2)}%")
        print(f"{'='*60}")
        if total_compile == 0:
            print(f"  ⚠ WARNING: No tests were processed!")
            print(f"  ⚠ Check that test files exist in: {steps_dir}")
        print()
        print(f"GLOBAL COVERAGE STATISTICS:")
        print(f"{'='*60}")
        if line_rate is not None or branch_rate is not None or m_line_rate is not None or m_branch_rate is not None:
            if line_rate is not None:
                print(f"  [Project] Line Coverage:   {line_cov:5d}/{line_total:5d} = {line_rate:6.2f}%")
            if branch_rate is not None:
                print(f"  [Project] Branch Coverage: {branch_cov:5d}/{branch_total:5d} = {branch_rate:6.2f}%")
            if modified_class_name:
                print(f"  [Modified Class] {modified_class_name}:")
                if m_line_rate is not None:
                    print(f"    Line Coverage:   {m_line_cov:5d}/{m_line_total:5d} = {m_line_rate:6.2f}%")
                if m_branch_rate is not None:
                    print(f"    Branch Coverage: {m_branch_cov:5d}/{m_branch_total:5d} = {m_branch_rate:6.2f}%")
        else:
            print(f"  ✗ NO COVERAGE DATA AVAILABLE")
            if not exec_files:
                print(f"    Reason: No jacoco.exec files were generated")
            else:
                print(f"    Reason: Could not parse jacoco.xml from merged report")
        print(f"{'='*60}\n")

        return total_compile, total_test_run

    # ── Status CSV ─────────────────────────────────────────────────────────────

    def _write_per_test_status(self, output_dir, project_name, target_class,
                                status_map, logs=None):
        if not status_map:
            return
        try:
            tc_slug = (target_class or 'unknown').replace('.', '')
            pn_slug = (project_name or 'project').replace('.', '')
            csv_path = os.path.join(output_dir, f'{pn_slug}_{tc_slug}_status.csv')
            fe = os.path.exists(csv_path)
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not fe:
                    writer.writerow([
                        'project', 'target_class', 'test_class',
                        'compile_status', 'exec_status', 'exec_timeout',
                        'jacoco_exec_size', 'compile_score', 'exec_score',
                    ])
                for full_name, s in status_map.items():
                    writer.writerow([
                        project_name, target_class, full_name,
                        s['compile_status'], s['exec_status'], s['exec_timeout'],
                        s['jacoco_exec_size'], s['compile_score'], s['exec_score'],
                    ])
        except Exception as e:
            print(f'Failed to write status.csv: {e}')

    # ── Run helpers ────────────────────────────────────────────────────────────

    def run_test_only_with_reason(self, test_file, compiled_test_dir,
                                   test_output, logs=None):
        to_file = (f"{test_output}.txt"
                   if os.path.basename(test_output) == 'runtime_error'
                   else f"{test_output}-{os.path.basename(test_file)}.txt")
        os.makedirs(os.path.dirname(to_file), exist_ok=True)
        cmd = self.java_cmd(compiled_test_dir, test_file)
        try:
            result = subprocess.run(cmd, timeout=TIMEOUT,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True)
            if result.returncode != 0:
                self.TEST_RUN_ERROR += 1
                self.export_runtime_output(result, to_file)
                return False, False
            return True, False
        except subprocess.TimeoutExpired:
            self.TEST_RUN_ERROR += 1
            return False, True
        except Exception:
            self.TEST_RUN_ERROR += 1
            return False, False

    def run_single_test(self, test_file, compiled_test_dir,
                        compiler_output, test_output):
        if not self.compile(test_file, compiled_test_dir, compiler_output):
            return False
        to_file = (f"{test_output}.txt"
                   if os.path.basename(test_output) == 'runtime_error'
                   else f"{test_output}-{os.path.basename(test_file)}.txt")
        cmd = self.java_cmd(compiled_test_dir, test_file)
        try:
            result = subprocess.run(cmd, timeout=TIMEOUT,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True)
            if result.returncode != 0:
                self.TEST_RUN_ERROR += 1
                self.export_runtime_output(result, to_file)
                return False
        except subprocess.TimeoutExpired:
            return False
        return True

    @staticmethod
    def export_runtime_output(result, test_output_file):
        with open(test_output_file, "w") as f:
            f.write(result.stdout)
            f.write(re.sub(r'log4j:WARN.*\n?', '', result.stderr))

    def compile(self, test_file, compiled_test_dir, compiler_output):
        os.makedirs(compiled_test_dir, exist_ok=True)
        cmd = self.javac_cmd(compiled_test_dir, test_file)
        result = subprocess.run(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            self.COMPILE_ERROR += 1
            co_file = (f"{compiler_output}.txt"
                       if os.path.basename(compiler_output) == 'compile_error'
                       else f"{compiler_output}-{os.path.basename(test_file)}.txt")
            os.makedirs(os.path.dirname(co_file), exist_ok=True)
            with open(co_file, "w") as f:
                f.write(result.stdout + result.stderr)
            return False
        return True

    # ── Build / classpath ──────────────────────────────────────────────────────

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
        return ('pom.xml' in os.listdir(project_path) and
                'target' in os.listdir(project_path))

    def get_submodule(self, project_path):
        return [d for d in os.listdir(project_path)
                if self.is_module(os.path.join(project_path, d))]

    def has_submodule(self, project_path):
        return any(self.is_module(os.path.join(project_path, d))
                   for d in os.listdir(project_path))

    def javac_cmd(self, compiled_test_dir, test_file):
        classpath = (f"{JUNIT_JAR}:{MOCKITO_JAR}:{LOG4J_JAR}:"
                     f"{self.dependencies}:{self.build_dir}:.")
        classpath_file = os.path.join(compiled_test_dir, 'classpath.txt')
        self.export_classpath(classpath_file, classpath)
        return ["javac", "-d", compiled_test_dir, f"@{classpath_file}", test_file]

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
            dest = (self.jacoco_destfile
                    if self.jacoco_destfile
                    else os.path.join(compiled_test_dir, 'jacoco.exec'))
            return ["java",
                    f"-javaagent:{JACOCO_AGENT}=destfile={dest},append=true",
                    f"@{classpath_file}",
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
        target_classes = (os.path.join(self.target_path, '**/target/classes')
                          if self.has_submodule(self.target_path)
                          else os.path.join(self.target_path, 'target/classes'))
        subprocess.run(
            ["bash", os.path.join(COBERTURA_DIR, "cobertura-instrument.sh"),
             "--basedir", self.target_path,
             "--destination", f"{instrument_dir}/instrumented",
             "--datafile", f"{datafile_dir}/cobertura.ser",
             target_classes],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def make_dependency(self):
        if not self.has_made():
            subprocess.run(
                f"mvn dependency:copy-dependencies -DoutputDirectory=target/dependency "
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
        print(f"Copying tests to {target_project} ...")
        for tc in tests:
            parts = os.path.normpath(tc).split(os.sep)
            tc_project = None
            for part in reversed(parts[:-1]):
                if '%' in part:
                    tokens = part.split('%')
                    if len(tokens) >= 2 and tokens[1]:
                        tc_project = tokens[1]; break
            if not tc_project and target_project in parts:
                tc_project = target_project
            if not tc_project or tc_project != target_project:
                continue
            os.system(f"cp {tc} {os.path.join(target_dir, 'test_cases')}")