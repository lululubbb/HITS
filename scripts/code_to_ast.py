#!/usr/bin/env python3
"""Python port of CodeToAST.java

Features:
- Parse Java test files and produce a structured XML-like AST representation
- Filter noise (logging calls, assertions, javadoc/comments)
- Normalize variable names to id_1, id_2, ...
- Export per-version CSV of test_case,test_ast and record per-test and per-version timings

Requirements: pip install javalang
运行示例：
python3 CodeToAST/code_to_ast.py ./test_suites ./asts_out ./ast_times
python3 CodeToAST/code_to_ast.py /path/to/test_suites_root /path/to/asts_output /path/to/time_output_prefix
python3 CodeToAST/code_to_ast.py /home/chenlu/ChatUniTest/defect4j_projects /tmp/asts_out /tmp/time_out_prefix
python3 CodeToAST/code_to_ast.py /home/chenlu/ChatUniTest/defect4j_projects/Csv_1_b/tests%20260116214455/test_cases /tmp/asts_out /tmp/time_out_prefix
"""
import os
import sys
import time
import csv
import argparse
from typing import List, Dict
import urllib.parse

try:
    import javalang
    from javalang.tree import *
except Exception:
    print('Missing dependency: please run `pip install javalang`')
    raise


assertMethods = set([
    'assert', 'assertEquals', 'assertEqualsNoOrder', 'assertArrayEquals', 'assertNotEquals',
    'assertTrue', 'assertFalse', 'assertNull', 'assertNotNull', 'assertSame', 'assertNotSame',
    'assertThat', 'assertThrows', 'fail'
])


operator_map = {
    '+': 'PLUS', '-': 'MINUS', '*': 'TIMES', '/': 'DIVIDE', '%': 'MOD',
    '==': 'EQUALS_EQUALS', '!=': 'NOT_EQUALS', '<': 'LESS', '>': 'GREATER',
    '<=': 'LESS_EQUALS', '>=': 'GREATER_EQUALS', '&&': 'AND_AND', '||': 'OR_OR',
}


def fix_chars(text: str) -> str:
    if text is None:
        return ''
    return (text.replace('>', '_')
                .replace('<', '_')
                .replace('[', '_')
                .replace(']', '_')
                .replace('(', '_')
                .replace(')', '_')
                .replace(',', '_')
                .replace('/', '_')
                .replace('"', '_')
                .replace('|', '_')
                .replace("'", '_')
                .replace('?', '_')
                .replace(' ', '_'))


def escape_xml(text: str) -> str:
    if text is None:
        return ''
    return (text.replace('&', '&amp;')
                .replace("'", '&apos;')
                .replace('"', '&quot;')
                .replace('<', '&lt;')
                .replace('>', '&gt;'))


class CodeToAST:
    def __init__(self):
        self.visited_classes = set()
        self.visited_methods = set()

    def _new_var_id_map(self):
        return {'_counter': 0, 'map': {}}

    def _get_var_id(self, var_map, name: str) -> str:
        if name in var_map['map']:
            return var_map['map'][name]
        var_map['_counter'] += 1
        vid = f'id_{var_map["_counter"]}'
        var_map['map'][name] = vid
        return vid

    def _is_logging_call(self, node: MethodInvocation) -> bool:
        # simple heuristics: System.out.print*, logger.*, log.info/debug/error, slf4j/log4j/logback
        q = ''
        try:
            if node.qualifier:
                q = str(node.qualifier).lower()
            name = str(node.member).lower()
        except Exception:
            return False
        if q.startswith('system.out') or q.startswith('system.err'):
            return True
        if q.startswith('logger') or q.startswith('log'):
            return True
        if 'slf4j' in q or 'log4j' in q or 'logback' in q:
            return True
        return False

    def _node_to_xml(self, node, var_map) -> str:
        """Recursive conversion of javalang AST node to simplified XML-like string."""
        # None guard
        if node is None:
            return ''

        # Primitive types
        from javalang.tree import (
            IfStatement, ForStatement, WhileStatement, DoStatement, TryStatement,
            MethodInvocation, Assignment, VariableDeclarator, ReturnStatement,
            BlockStatement, BinaryOperation, Literal, ReferenceType, MemberReference,
            MethodDeclaration, ClassCreator, StatementExpression
        )

        # Method invocation
        if isinstance(node, MethodInvocation):
            # filter out noise
            if (str(node.member) in assertMethods) or self._is_logging_call(node):
                return ''
            params = []
            if node.arguments:
                for a in node.arguments:
                    params.append(self._node_to_xml(a, var_map))
            name = fix_chars(str(node.member))
            xml = f'<CALL><METHOD-{name}/><PARAMS>'
            xml += ''.join(params)
            xml += '</PARAMS></CALL>'
            return xml

        # Assignment
        if isinstance(node, Assignment):
            op = getattr(node, 'operator', '=')
            opname = operator_map.get(op, op)
            lhs = self._node_to_xml(node.expressionl, var_map)
            rhs = self._node_to_xml(node.value, var_map)
            return f'<ASSIGNMENT-{opname}>' + lhs + rhs + f'</ASSIGNMENT-{opname}>'

        # Variable declaration
        if isinstance(node, VariableDeclarator):
            name = getattr(node, 'name', None)
            vid = self._get_var_id(var_map, name or '') if name else ''
            init = self._node_to_xml(node.initializer, var_map) if getattr(node, 'initializer', None) else ''
            return f'<ASSIGNMENT><VAR-{fix_chars(vid)}/>' + init + '</ASSIGNMENT>'

        # If statement
        if isinstance(node, IfStatement):
            cond = self._node_to_xml(node.condition, var_map)
            then_part = self._node_to_xml(node.then_statement, var_map)
            else_part = self._node_to_xml(node.else_statement, var_map) if node.else_statement else ''
            xml = f'<IF><EXPR>{cond}</EXPR><THEN>{then_part}</THEN>'
            if else_part:
                xml += f'<ELSE>{else_part}</ELSE>'
            xml += '</IF>'
            return xml

        # For, While, Do
        if isinstance(node, ForStatement):
            cond = self._node_to_xml(node.control, var_map)
            body = self._node_to_xml(node.body, var_map)
            return f'<FOR><EXPR>{cond}</EXPR><BODY>{body}</BODY></FOR>'
        if isinstance(node, WhileStatement):
            cond = self._node_to_xml(node.condition, var_map)
            body = self._node_to_xml(node.body, var_map)
            return f'<WHILE><EXPR>{cond}</EXPR><BODY>{body}</BODY></WHILE>'
        if isinstance(node, DoStatement):
            cond = self._node_to_xml(node.condition, var_map)
            body = self._node_to_xml(node.body, var_map)
            return f'<DO><BODY>{body}</BODY><EXPR>{cond}</EXPR></DO>'

        # Try
        if isinstance(node, TryStatement):
            block = self._node_to_xml(node.block, var_map)
            finally_part = self._node_to_xml(node.finally_block, var_map) if getattr(node, 'finally_block', None) else ''
            xml = f'<TRY><BODY>{block}</BODY>'
            if finally_part:
                xml += f'<FINALLY>{finally_part}</FINALLY>'
            xml += '</TRY>'
            return xml

        # Return
        if isinstance(node, ReturnStatement):
            return f'<RETURN>{self._node_to_xml(node.expression, var_map)}</RETURN>'

        # MethodDeclaration (signature excluded, body only)
        if isinstance(node, MethodDeclaration):
            # signature
            sig = ''
            try:
                sig = node.name
            except Exception:
                sig = ''
            body = ''
            if node.body:
                parts = []
                for s in node.body:
                    parts.append(self._node_to_xml(s, var_map))
                body = ''.join(parts)
            return f'<TESTCASE><SIGNATURE>{fix_chars(sig)}</SIGNATURE><BODY>{body}</BODY></TESTCASE>'

        # BlockStatement and other statements container
        if isinstance(node, list):
            return ''.join([self._node_to_xml(n, var_map) for n in node])

        # BinaryOperation or InfixExpression
        if hasattr(node, 'operator') and hasattr(node, 'left') and hasattr(node, 'right'):
            op = getattr(node, 'operator', '')
            opname = operator_map.get(op, op)
            left = self._node_to_xml(node.left, var_map)
            right = self._node_to_xml(node.right, var_map)
            return f'<{opname}>' + left + right + f'</{opname}>'

        # MemberReference (variable or field access)
        if isinstance(node, MemberReference):
            name = getattr(node, 'member', None)
            if name:
                vid = self._get_var_id(var_map, name)
                return f'<NAME-{fix_chars(vid)}/>'
            return ''

        # ReferenceType (type names)
        if isinstance(node, ReferenceType):
            return f'<TYPE-{fix_chars(str(node.name))}/>'

        # Literal
        if isinstance(node, Literal):
            return f'<VALUE-{fix_chars(str(node.value))}/>'

        # Member (identifier) fallback: try to get .name or .member or .value
        name = None
        if hasattr(node, 'name'):
            name = getattr(node, 'name')
        elif hasattr(node, 'member'):
            name = getattr(node, 'member')
        elif hasattr(node, 'value'):
            name = getattr(node, 'value')
        if isinstance(name, str):
            # treat as variable/identifier
            vid = self._get_var_id(var_map, name)
            return f'<NAME-{fix_chars(vid)}/>'

        # Fallback: traverse attributes and children
        result = ''
        for child in getattr(node, 'children', []) or []:
            try:
                result += self._node_to_xml(child, var_map)
            except Exception:
                pass
        return result

    def extract_ast(self, test_file_content: str, version_path: str, test_file_name: str,
                    actual_tests_path: str, relevant_tests_path: str, project_version: str,
                    ast_time_per_test_writer) -> List[str]:
        """Parse a single test file content and return list of generated METHOD_TREE CSV lines.
        Also write the per-test timing to provided writer (file-like, writeable).
        """
        start_ns = time.time_ns()
        try:
            tree = javalang.parse.parse(test_file_content)
        except Exception as e:
            # Try a simple repair: remove any subsequent 'package ' lines after the first
            try:
                lines = test_file_content.splitlines()
                first_pkg = None
                out_lines = []
                for ln in lines:
                    if ln.strip().startswith('package '):
                        if first_pkg is None:
                            first_pkg = ln
                            out_lines.append(ln)
                        else:
                            # skip duplicate package declarations
                            continue
                    else:
                        out_lines.append(ln)
                repaired = '\n'.join(out_lines)
                tree = javalang.parse.parse(repaired)
            except Exception:
                # log parse error to timing writer if possible and return empty
                try:
                    ast_time_per_test_writer.write(f'{project_version},{test_file_name},PARSE_ERROR\n')
                    ast_time_per_test_writer.flush()
                except Exception:
                    pass
                return []

        method_trees = []
        # iterate classes
        from javalang.tree import ClassDeclaration, MethodDeclaration
        for path, class_node in tree.filter(ClassDeclaration):
            class_key = f'{project_version}@{test_file_name}#{class_node.name}'
            if class_key in self.visited_classes:
                continue
            self.visited_classes.add(class_key)

            # methods
            for _, method_node in class_node.filter(MethodDeclaration):
                name = getattr(method_node, 'name', '')
                modifiers = ' '.join(method_node.modifiers) if getattr(method_node, 'modifiers', None) else ''
                # detect annotations properly
                has_test_annotation = False
                if getattr(method_node, 'annotations', None):
                    for ann in method_node.annotations:
                        ann_name = getattr(ann, 'name', '') or ''
                        ann_name_l = ann_name.lower()
                        if 'test' in ann_name_l or 'parameterized' in ann_name_l:
                            has_test_annotation = True
                            break
                # skip constructors/privates
                if getattr(method_node, 'constructor', False) or getattr(method_node, 'is_constructor', False):
                    continue
                if 'private' in modifiers:
                    continue
                if not (name.startswith('test') or name.endswith('Test') or has_test_annotation):
                    continue

                method_key = f'{project_version}@{test_file_name}.{name}'
                if method_key in self.visited_methods:
                    continue
                self.visited_methods.add(method_key)

                var_map = self._new_var_id_map()

                body_xml = ''
                if method_node.body:
                    for stmt in method_node.body:
                        body_xml += self._node_to_xml(stmt, var_map)

                sig = fix_chars(name)
                method_tree = f'"{test_file_name}.{name}","{escape_xml("<TESTCASE><SIGNATURE>"+sig+"</SIGNATURE><BODY>"+body_xml+"</BODY></TESTCASE>")}"'
                method_trees.append(method_tree)

                end_ns = time.time_ns()
                elapsed = end_ns - start_ns
                try:
                    ast_time_per_test_writer.write(f'{project_version},{test_file_name}.{name},{elapsed}\n')
                    ast_time_per_test_writer.flush()
                except Exception:
                    pass

        return method_trees

    def extract_folder(self, project_name: str, version_folder: str, asts_output: str, time_output: str):
        # version_folder is expected to be a directory containing .java test files
        version = os.path.basename(version_folder)
        # asts_output may be ignored here; we'll write into a per-tests AST folder
        out_dir = os.path.join(asts_output, project_name)
        os.makedirs(out_dir, exist_ok=True)
        version_asts_path = os.path.join(out_dir, f'{version}.csv')

        per_version_time_path = f'{time_output}_per_version_for_{project_name}.csv'
        per_test_time_path = f'{time_output}_per_test_case_for_{project_name}.csv'

        # ensure header for timing
        if not os.path.exists(per_version_time_path):
            with open(per_version_time_path, 'w', encoding='utf-8') as f:
                f.write('project,version,ast_generation_time_nanosec\n')
        if not os.path.exists(per_test_time_path):
            with open(per_test_time_path, 'w', encoding='utf-8') as f:
                f.write('project,version,test_case,ast_generation_time_nanosec\n')

        version_code_asts = ['test_case,test_ast']
        files = [f for f in os.listdir(version_folder) if f.endswith('.java')]
        start_version_ns = time.time_ns()
        with open(per_test_time_path, 'a', encoding='utf-8') as per_test_f:
            for test_file in files:
                test_path = os.path.join(version_folder, test_file)
                try:
                    content = open(test_path, 'r', encoding='utf-8').read()
                except Exception:
                    continue
                method_trees = self.extract_ast(content, version_asts_path, test_file.replace('.java',''), version_folder, version_folder, f'{project_name},{version}', per_test_f)
                for m in method_trees:
                    version_code_asts.append(m)

        with open(version_asts_path, 'w', encoding='utf-8') as outf:
            outf.write('\n'.join(version_code_asts))
        end_version_ns = time.time_ns()
        with open(per_version_time_path, 'a', encoding='utf-8') as per_ver_f:
            per_ver_f.write(f'{project_name},{version},{end_version_ns - start_version_ns}\n')

    def process_tests_dir(self, tests_dir: str, time_output: str = None):
        """Process a single tests* directory (may contain test_cases subdir).
        Writes AST CSV into tests_dir/AST/<proj_prefix>_AST.csv
        """
        # accept URL-encoded names
        # if tests_dir points to test_cases, use its parent
        if os.path.basename(tests_dir) == 'test_cases':
            top_tests_dir = os.path.dirname(tests_dir)
            test_cases_dir = tests_dir
        elif os.path.basename(tests_dir).startswith('tests'):
            top_tests_dir = tests_dir
            # prefer nested test_cases if exists
            if os.path.isdir(os.path.join(tests_dir, 'test_cases')):
                test_cases_dir = os.path.join(tests_dir, 'test_cases')
            else:
                test_cases_dir = tests_dir
        else:
            # assume parent is top tests dir
            top_tests_dir = os.path.dirname(tests_dir)
            if os.path.isdir(os.path.join(top_tests_dir, 'test_cases')):
                test_cases_dir = os.path.join(top_tests_dir, 'test_cases')
            else:
                test_cases_dir = tests_dir

        project_dir = os.path.dirname(top_tests_dir)
        proj_prefix = os.path.basename(project_dir)
        # normalize project prefix to strip trailing _b/_f
        if proj_prefix.endswith('_b') or proj_prefix.endswith('_f'):
            proj_short = proj_prefix[:-2]
        else:
            proj_short = proj_prefix

        ast_dir = os.path.join(top_tests_dir, 'AST')
        os.makedirs(ast_dir, exist_ok=True)
        out_csv = os.path.join(ast_dir, f'{proj_short}_AST.csv')

        # determine time output paths; if caller provided a time_output prefix, use it under AST dir
        if time_output:
            per_version_time_path = os.path.join(ast_dir, f'{time_output}_per_version_for_{proj_short}.csv')
            per_test_time_path = os.path.join(ast_dir, f'{time_output}_per_test_case_for_{proj_short}.csv')
        else:
            per_version_time_path = os.path.join(ast_dir, f'{proj_short}_per_version_time.csv')
            per_test_time_path = os.path.join(ast_dir, f'{proj_short}_per_test_time.csv')

        # ensure timing headers
        if not os.path.exists(per_version_time_path):
            with open(per_version_time_path, 'w', encoding='utf-8') as f:
                f.write('project,version,ast_generation_time_nanosec\n')
        if not os.path.exists(per_test_time_path):
            with open(per_test_time_path, 'w', encoding='utf-8') as f:
                f.write('project,version,test_case,ast_generation_time_nanosec\n')

        version_code_asts = ['test_case,test_ast']
        files = [f for f in os.listdir(test_cases_dir) if f.endswith('.java')]
        start_version_ns = time.time_ns()
        with open(per_test_time_path, 'a', encoding='utf-8') as per_test_f:
            for test_file in files:
                test_path = os.path.join(test_cases_dir, test_file)
                try:
                    content = open(test_path, 'r', encoding='utf-8').read()
                except Exception:
                    continue
                file_start = time.time_ns()
                method_trees = self.extract_ast(content, out_csv, test_file.replace('.java',''), test_cases_dir, test_cases_dir, f'{proj_short},{os.path.basename(top_tests_dir)}', per_test_f)
                # if no method trees were extracted, still add an empty row for the test file
                if not method_trees:
                    tf = test_file.replace('.java','')
                    version_code_asts.append(f'"{tf}",""')
                else:
                    for m in method_trees:
                        version_code_asts.append(m)
                # write per-test elapsed (ensure an entry per file)
                file_elapsed = time.time_ns() - file_start
                try:
                    per_test_f.write(f'{proj_short},{os.path.basename(top_tests_dir)},{test_file.replace(".java","")},{file_elapsed}\n')
                    per_test_f.flush()
                except Exception:
                    pass

        with open(out_csv, 'w', encoding='utf-8') as outf:
            outf.write('\n'.join(version_code_asts))
        end_version_ns = time.time_ns()
        with open(per_version_time_path, 'a', encoding='utf-8') as per_ver_f:
            per_ver_f.write(f'{proj_prefix},{os.path.basename(top_tests_dir)},{end_version_ns - start_version_ns}\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_suites_root')
    parser.add_argument('--asts_output', required=False, default=None, help='Optional AST output base (default: tests*/AST when processing a tests dir)')
    parser.add_argument('--time_output', required=False, default=None, help='Optional time output prefix (default: placed under tests*/AST)')
    args = parser.parse_args()

    c = CodeToAST()
    root = args.test_suites_root
    # If root is a tests* dir or a test_cases dir, process it directly
    if os.path.isdir(root) and (os.path.basename(root).startswith('tests') or os.path.basename(root) == 'test_cases'):
        print(f'Processing tests directory {root} ...')
        c.process_tests_dir(root, args.time_output)
        return

    # Otherwise assume root contains project directories (e.g., defect4j_projects)
    for project in sorted(os.listdir(root)):
        project_path = os.path.join(root, project)
        if not os.path.isdir(project_path):
            continue
        # find newest tests* dir under project_path
        tests_dirs = [os.path.join(project_path, d) for d in os.listdir(project_path) if d.startswith('tests') and os.path.isdir(os.path.join(project_path, d))]
        if not tests_dirs:
            # also consider a direct 'tests' or 'test_cases' folder
            if os.path.isdir(os.path.join(project_path, 'tests')):
                tests_dirs = [os.path.join(project_path, 'tests')]
            elif os.path.isdir(os.path.join(project_path, 'test_cases')):
                tests_dirs = [os.path.join(project_path, 'test_cases')]
            else:
                continue
        # pick newest by mtime
        tests_dirs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        top_tests = tests_dirs[0]
        # if top_tests is a tests* directory, prefer its test_cases subdir if present
        if os.path.isdir(os.path.join(top_tests, 'test_cases')):
            candidate = os.path.join(top_tests, 'test_cases')
        else:
            candidate = top_tests
        print(f'Processing project {project} using tests dir {top_tests} ...')
        # ensure we pass the top_tests dir (candidate might be test_cases)
        c.process_tests_dir(candidate, args.time_output)


if __name__ == '__main__':
    main()
