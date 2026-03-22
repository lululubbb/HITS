import subprocess
import signal
import time
import psutil
import concurrent.futures
import sys
import os
import json

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from utils.test_runner import TestRunner
from class_parser import ClassParser
from utils.config import GRAMMAR_FILE, LANGUAGE


class Task:

    @staticmethod
    def test(test_path, target_path):
        """
        Run test task, make sure the target project has be compiled and installed.(run `mvn compile install`)
        """
        test_task = TestTask(test_path, target_path)
        return test_task.single_test()

    @staticmethod
    def all_test(test_path, target_path):
        """
        Run test task, make sure the target project has be compiled and installed.(run `mvn compile install`)
        """
        test_task = TestTask(test_path, target_path)
        return test_task.all_test()

    @staticmethod
    def parse(target_path):
        """
        Run parse task, extract class information of target project.
        """
        parse_task = ParseTask()
        return parse_task.parse_project(target_path)


class TestTask:

    def __init__(self, test_path, target_path):
        # init()  # colorama init
        self.test_path = test_path
        self.target_path = target_path
        self.runner = TestRunner(test_path, target_path)

        # define the threshold for CPU utilization and available memory
        self.cpu_threshold = 80
        self.mem_threshold = 1024 * 1024 * 5000  # 5G

    def single_test(self):
        """
        Only run tests.
        tests directory path, e.g., /data/share/TestGPT_ASE/result/scope_test%20230414210243%d3_1/1460%lang_1_f%ToStringBuilder%append%d3/5
        """
        if check_java_version() != 11:
            raise Exception(Fore.RED + "Wrong java version! Need: java 11")
        if self.target_path.endswith("_f") or self.target_path.endswith("_b"):  # defects4j project
            print(f"\n【TestTask识别结果】✅ 识别为Defects4J项目")
            return self.start_d4j()
        else:  # general project
            return self.runner.start_single_test()

    def all_test(self):
        """
        Run all test cases.
        test_path: test cases directory path, e.g., /data/share/TestGPT_ASE/result/scope_test%20230414210243%d3_1/
        target_path: target project path
        """
        if check_java_version() != 11:
            raise Exception(Fore.RED + "Wrong java version! Need: java 11")
        return self.runner.start_all_test()

    def start_d4j(self):
        """
        Adaptive assignment for d4j tests.
        test case path: /root/TestGPT_ASE/result_429/scope_test%20230428134414%/4950%Chart_8_f%Week%getYear%d1/1/temp
        """
        # loop until the CPU utilization falls below the threshold
        while True:
            # get the current CPU utilization
            cpu_utilization = psutil.cpu_percent()
            mem_available = psutil.virtual_memory().available
            # if the CPU utilization is below the threshold, start a new process and break the loop
            if cpu_utilization < self.cpu_threshold and mem_available > self.mem_threshold:
                self.run_d4j()
                break
            # if the CPU utilization is still above the threshold, wait for some time (e.g. 1 second) and check again
            time.sleep(2)

    def run_d4j(self):
            """
            Run single test using defects4j test api
            test case path: /root/TestGPT_ASE/result_429/scope_test%20230428134414%/4950%Chart_8_f%Week%getYear%d1/1/temp
            """
            d4j_script = 'scripts/d4j_test.sh'
            test_case_src = os.path.join(self.test_path, "temp")

            process = subprocess.Popen(["bash", d4j_script, test_case_src, self.target_path], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            start_time = time.monotonic()
            while True:
                exit_code = process.poll()
                if exit_code is not None:
                    if exit_code != 0:
                        print(Fore.RED + f"【执行结果】❌ Defects4J测试执行失败，退出码: {exit_code}" + Style.RESET_ALL)
                        with open(os.path.join(test_case_src, 'compile_error.txt'), "w") as f:
                            pattern = r"compile\.gen\.tests:(.*?)BUILD FAILED"
                            match = re.search(pattern, stderr.decode(), re.DOTALL)
                            if match:
                                compile_output = match.group(1).strip().split('[javac] ', 1)[1]
                                compile_output = compile_output.replace('    [javac] ', '')
                                f.write(compile_output)
                                print(Fore.RED + f"【失败类型】编译失败，错误信息已写入 {os.path.join(test_case_src, 'compile_error.txt')}" + Style.RESET_ALL)
                            else:
                                f.write(stderr.decode())
                                print(Fore.RED + f"【失败类型】执行失败，错误信息已写入 {os.path.join(test_case_src, 'compile_error.txt')}" + Style.RESET_ALL)
                    else:
                        print(f"【执行结果】✅ Defects4J测试执行成功，退出码: {exit_code}")
                    break
                elif time.monotonic() - start_time >= TIMEOUT:
                    print(Fore.RED + f"【执行结果】❌ Defects4J测试执行超时（超时时间：{TIMEOUT}秒），强制终止进程" + Style.RESET_ALL)
                    sub_pids = find_processes_created_by(process.pid)
                    for pid in sub_pids:
                        os.kill(pid, signal.SIGTERM)
                    break
                else:
                    time.sleep(0.1)

    def run_d4j_b(self, tests_src, threaded=True):
        """
        run tests at defects4j buggy revisions
        :param tests_src: result directory, e.g., /root/TestGPT_ASE/result/
        """
        target_path = '/root/TestGPT_ASE/projects'
        if threaded:
            with concurrent.futures.ProcessPoolExecutor(max_workers=process_number) as executor:
                for scope_tests in os.listdir(tests_src):
                    scope_tests_path = os.path.join(tests_src, scope_tests)
                    for tests_dir in os.listdir(scope_tests_path):
                        tests_path = os.path.join(scope_tests_path, tests_dir)
                        m_id, project_name, class_name, method_name = parse_file_name(tests_path)
                        project_path = os.path.join(target_path, project_name.replace('_f', '_b'))
                        self.target_path = project_path
                        for i in range(1, test_number + 1):
                            if not os.path.exists(os.path.join(tests_path, str(i))):
                                continue
                            print("Processing project:", project_name, "method id:", m_id, "test number:", str(i))
                            test_case_src = os.path.join(tests_path, str(i), 'temp')
                            self.test_path = test_case_src
                            executor.submit(self.run_d4j)
        else:
            for scope_tests in os.listdir(tests_src):
                scope_tests_path = os.path.join(tests_src, scope_tests)
                for tests_dir in os.listdir(scope_tests_path):
                    tests_path = os.path.join(scope_tests_path, tests_dir)
                    m_id, project_name, class_name, method_name = parse_file_name(tests_path)
                    project_path = os.path.join(target_path, project_name.replace('_f', '_b'))
                    self.target_path = project_path
                    for i in range(1, test_number + 1):
                        if not os.path.exists(os.path.join(tests_path, str(i))):
                            continue
                        print("Processing project:", project_name, "method id:", m_id, "test number:", str(i))
                        test_case_src = os.path.join(tests_path, str(i), 'temp')
                        self.test_path = test_case_src
                        self.run_d4j()


class ParseTask:

    def __init__(self):
        self.parser = ClassParser(GRAMMAR_FILE, LANGUAGE)
        self.output = os.path.join(PROJECT_ROOT, "class_info")

    def parse_project(self, target_path):
        """
        Analyze a single project
        """
        # Create folders
        target_path = target_path.rstrip('/')
        os.makedirs(self.output, exist_ok=True)
        if target_path.endswith("_f") or target_path.endswith("_b"):
            print(f"\n【ParseTask识别结果】✅ 识别为Defects4J项目")
            _, output_path = self.process_d4j_revisions(target_path, '/home/chenlu/HITS/scripts/focal_classes.json')
            return output_path
        tot_m, output_path = self.find_classes(target_path)
        return output_path

    def find_classes(self, target_path):
        """
        Find all classes exclude tests
        Finds test cases using @Test annotation
        """
        # Run analysis
        print("Parse", target_path, " ...")
        if not os.path.exists(target_path):
            return 0, ""
        # Test Classes
        try:
            result = subprocess.check_output(r'grep -l -r @Test --include \*.java {}'.format(target_path), shell=True)
            tests = result.decode('ascii').splitlines()
        except:
            tests = []
        # Java Files
        try:
            result = subprocess.check_output(['find', target_path, '-name', '*.java'])
            java = result.decode('ascii').splitlines()
        except:
            return 0, ""
        # All Classes exclude tests
        focals = list(set(java) - set(tests))
        focals = [f for f in focals if not "src/test" in f]
        project_name = os.path.split(target_path)[1]
        output = os.path.join(self.output, project_name)
        os.makedirs(output, exist_ok=True)
        return self.parse_all_classes(focals, project_name, output), output

    def parse_all_classes(self, focals, project_name, output):
        classes = {}
        for focal in focals:
            json_path = os.path.join(output, os.path.split(focal)[1] + ".json")
            # 新增：如果JSON已存在，跳过解析（避免重复插入MySQL）
            if os.path.exists(json_path):
                print(f"跳过已解析文件：{focal}")
                continue
            parsed_classes = self.parser.parse_file(focal)
            for _class in parsed_classes:
                _class["project_name"] = project_name

            classes[focal] = parsed_classes
            json_path = os.path.join(output, os.path.split(focal)[1] + ".json")
            self.export_result(classes[focal], json_path)
        return classes

    @staticmethod
    def export_result(data, out):
        """
        Exports data as json file
        """
        directory = os.path.dirname(out)
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(out, "w") as text_file:
            data_json = json.dumps(data)
            text_file.write(data_json)

    def get_class_path(self, start_path, filename):
        for root, dirs, files in os.walk(start_path):
            if filename in files:
                return os.path.join(root, filename)


    # def process_d4j_revisions(self, repo_path, focal_classes_json):
    #     """
    #     Analysis defects4j revisions focal method.
    #     """
    #     if '_f' not in os.path.basename(repo_path):
    #         return
    #     # Run analysis
    #     print("Parsing focal class...")
    #     project_name = os.path.split(repo_path)[1]
    #     with open(focal_classes_json, 'r') as f:
    #         content = json.load(f)
    #     for repo in content:
    #         if repo['project'] == project_name:
    #             classes = repo['classes']
    #     focals = []
    #     for _class in classes:
    #         class_path = self.get_class_path(repo_path, os.path.basename(_class.rstrip('\n').replace('.', '/') + '.java'))
    #         focals.append(class_path)

    #     output = os.path.join(self.output, project_name)
    #     return self.parse_all_classes(focals, project_name, output), output

    def process_d4j_revisions(self, repo_path, focal_classes_json):
        """
        Analysis defects4j revisions focal method.
        """

        # 修复1：兼容_b和_f版本，且返回有意义的值而非None
        project_basename = os.path.basename(repo_path)
        if '_f' in project_basename:
            target_project_name = project_basename
        elif '_b' in project_basename:
            # buggy版本转为fixed版本名（因为focal_classes.json中是_f后缀）
            target_project_name = project_basename.replace('_b', '_f')
        else:
            print(f"【错误1】不支持的版本类型：{repo_path}（需包含_b或_f）")  # 新增日志
            return None, None  # 返回两个值，避免解包失败

        # Run analysis
        print("Parsing focal class...")
        try:
            with open(focal_classes_json, 'r') as f:
                content = json.load(f)
            print(f"  ✅ 成功读取焦点类配置文件，共包含 {len(content)} 个项目配置")
        except Exception as e:
            print(f"【错误2】读取焦点类配置失败：{e}，路径：{focal_classes_json}")  # 新增日志
            return None, None

        # 修复2：增加容错，找不到匹配项目时返回明确值
        classes = None
        for repo in content:
            if repo.get('project') == target_project_name:
                classes = repo.get('classes', [])
                break
        if classes is None:
            print(f"【错误3】未找到匹配的焦点类配置：{target_project_name}，配置文件中所有项目名：{[r.get('project') for r in content]}")  # 新增日志
            return None, None

        focals = []
        cleaned_classes = [c.rstrip('\n').strip() for c in classes]  # 提前处理，移出f-string
        for _class in classes:
            # 清理类名：移除换行符、空格
            clean_class = _class.rstrip('\n').strip()
            if not clean_class:
                continue
            # 转换类名到文件路径：org.xxx.Class → org/xxx/Class.java
            class_file = clean_class.replace('.', '/') + '.java'
            class_path = self.get_class_path(repo_path, os.path.basename(class_file))
            if class_path:
                focals.append(class_path)

        if not focals:
            print(f"【错误4】未找到任何焦点类文件：配置类={classes}，清理后类={cleaned_classes}，项目路径={repo_path}")
            return None, None

        output = os.path.join(self.output, project_basename)
        os.makedirs(output, exist_ok=True)
        return self.parse_all_classes(focals, project_basename, output), output


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python task.py <command> <target_path>")
        print("Commands: parse, test")
        sys.exit(1)

    command = sys.argv[1]
    target_path = sys.argv[2]

    if command == "parse":
        Task.parse(target_path)
    elif command == "test":
        # Handle test command if needed
        print("Test command not implemented yet")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
