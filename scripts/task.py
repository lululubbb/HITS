"""
scripts/task.py  — HITS Task wrapper (updated)

Provides:
  Task.all_test(test_path, target_path)  → full coverage pipeline
  Task.test(test_path, target_path)      → single test
  Task.parse(target_path)               → class info parsing

The all_test() path now uses the full-featured TestRunner that produces:
  status.csv, coverage.csv, coveragedetail.csv, coveragemethod.csv,
  final_scores.csv, final_scores2.csv
"""

import subprocess
import signal
import time
import psutil
import concurrent.futures
import sys
import os
import json
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from utils.test_runner import TestRunner
from utils.config import GRAMMAR_FILE, LANGUAGE, TIMEOUT

try:
    from scripts.class_parser import ClassParser
except ImportError:
    ClassParser = None


class Task:

    @staticmethod
    def test(test_path, target_path):
        """Run a single test case."""
        runner = TestRunner(test_path, target_path)
        return runner.start_single_test()

    @staticmethod
    def all_test(test_path, target_path):
        """
        Run all test cases in test_path against target_path.

        If test_path already contains a test_cases/ subdir, runs in-place.
        Otherwise creates a timestamped tests%* directory under target_path.

        Returns (total_compile, total_test_run) tuple.
        """
        runner = TestRunner(test_path, target_path)
        return runner.start_all_test()

    @staticmethod
    def parse(target_path):
        """Extract class information from target project."""
        if ClassParser is None:
            print("[WARN] ClassParser not available, skipping parse")
            return None
        parse_task = ParseTask()
        return parse_task.parse_project(target_path)


class ParseTask:

    def __init__(self):
        if ClassParser is None:
            raise ImportError("ClassParser not available")
        self.parser = ClassParser(GRAMMAR_FILE, LANGUAGE)
        self.output = os.path.join(PROJECT_ROOT, "class_info")

    def parse_project(self, target_path):
        target_path = target_path.rstrip('/')
        os.makedirs(self.output, exist_ok=True)
        if target_path.endswith("_f") or target_path.endswith("_b"):
            focal_classes_json = os.path.join(
                PROJECT_ROOT, 'scripts', 'focal_classes.json')
            _, output_path = self.process_d4j_revisions(
                target_path, focal_classes_json)
            return output_path
        _, output_path = self.find_classes(target_path)
        return output_path

    def find_classes(self, target_path):
        print("Parse", target_path, "...")
        if not os.path.exists(target_path):
            return 0, ""
        try:
            result = subprocess.check_output(
                r'grep -l -r @Test --include \*.java {}'.format(target_path),
                shell=True)
            tests = result.decode('ascii').splitlines()
        except Exception:
            tests = []
        try:
            result = subprocess.check_output(
                ['find', target_path, '-name', '*.java'])
            java = result.decode('ascii').splitlines()
        except Exception:
            return 0, ""
        focals = list(set(java) - set(tests))
        focals = [f for f in focals if "src/test" not in f]
        project_name = os.path.split(target_path)[1]
        output = os.path.join(self.output, project_name)
        os.makedirs(output, exist_ok=True)
        return self.parse_all_classes(focals, project_name, output), output

    def parse_all_classes(self, focals, project_name, output):
        classes = {}
        for focal in focals:
            json_path = os.path.join(output, os.path.split(focal)[1] + ".json")
            if os.path.exists(json_path):
                continue
            parsed_classes = self.parser.parse_file(focal)
            for _class in parsed_classes:
                _class["project_name"] = project_name
            classes[focal] = parsed_classes
            self.export_result(classes[focal], json_path)
        return classes

    @staticmethod
    def export_result(data, out):
        directory = os.path.dirname(out)
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(out, "w") as text_file:
            import json
            text_file.write(json.dumps(data))

    def get_class_path(self, start_path, filename):
        for root, dirs, files in os.walk(start_path):
            if filename in files:
                return os.path.join(root, filename)

    def process_d4j_revisions(self, repo_path, focal_classes_json):
        project_basename = os.path.basename(repo_path)
        if '_f' in project_basename:
            target_project_name = project_basename
        elif '_b' in project_basename:
            target_project_name = project_basename.replace('_b', '_f')
        else:
            print(f"[WARN] Unsupported version type: {repo_path}")
            return None, None

        print("Parsing focal class...")
        try:
            with open(focal_classes_json, 'r') as f:
                content = json.load(f)
        except Exception as e:
            print(f"[ERROR] Cannot read focal classes: {e}")
            return None, None

        classes = None
        for repo in content:
            if repo.get('project') == target_project_name:
                classes = repo.get('classes', [])
                break
        if classes is None:
            print(f"[WARN] Project {target_project_name} not in focal_classes.json")
            return None, None

        focals = []
        for _class in classes:
            clean_class = _class.rstrip('\n').strip()
            if not clean_class:
                continue
            class_file = clean_class.replace('.', '/') + '.java'
            class_path = self.get_class_path(
                repo_path, os.path.basename(class_file))
            if class_path:
                focals.append(class_path)

        if not focals:
            print(f"[WARN] No focal class files found for {target_project_name}")
            return None, None

        output = os.path.join(self.output, project_basename)
        os.makedirs(output, exist_ok=True)
        return self.parse_all_classes(focals, project_basename, output), output


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python task.py <command> <target_path>")
        print("Commands: parse, test")
        sys.exit(1)
    command = sys.argv[1]
    target_path = sys.argv[2]
    if command == "parse":
        Task.parse(target_path)
    elif command == "test":
        print("Test command requires test_path as third argument")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)