"""
utils/config.py  — 在原文件末尾追加以下内容（或直接替换原文件）

变更：
  1. 读取 TEST_CASES_PER_SLICE / WO_SLICE_TEST_COUNT / MAX_REPAIR_TRIALS /
     TEST_NUMBER / DATASET_DIR 五个新参数
  2. 提供向后兼容的默认值（即使旧 config.ini 没有这些字段也能运行）
"""

import configparser
import inspect
import os

# ── 原有代码（保持不变）────────────────────────────────────────────────────────
frame_info = inspect.getframeinfo(inspect.currentframe())
file_path = frame_info.filename

config = configparser.ConfigParser()
project_root = os.path.abspath(os.path.dirname(os.path.dirname(file_path)))
config_path = os.path.join(project_root, "config.ini")
assert os.path.exists(config_path)
config.read(config_path)


def transform_path(path):
    if path.startswith("/"):
        return path
    paths = path.split(":")
    for idx in range(len(paths)):
        paths[idx] = os.path.normpath(os.path.join(project_root, paths[idx]))
    return ':'.join(paths)


TIMEOUT       = eval(config.get("DEFAULT", "TIMEOUT"))
LANGUAGE      = config.get("DEFAULT", "LANGUAGE")
GRAMMAR_FILE  = transform_path(config.get("DEFAULT", "GRAMMAR_FILE"))
COBERTURA_DIR = transform_path(config.get("DEFAULT", "COBERTURA_DIR"))
JUNIT_JAR     = transform_path(config.get("DEFAULT", "JUNIT_JAR"))
MOCKITO_JAR   = transform_path(config.get("DEFAULT", "MOCKITO_JAR"))
LOG4J_JAR     = transform_path(config.get("DEFAULT", "LOG4J_JAR"))
JACOCO_AGENT  = transform_path(config.get("DEFAULT", "JACOCO_AGENT"))
JACOCO_CLI    = transform_path(config.get("DEFAULT", "JACOCO_CLI"))
FORMATTER_PATH = transform_path(config.get("DEFAULT", "FORMATTER"))
REPORT_FORMAT = config.get("DEFAULT", "REPORT_FORMAT")
playground_dir = transform_path(config.get("DEFAULT", "playground"))

api_keys   = eval(config.get("openai", "api_keys"))
model      = config.get("openai", "model")
model_url  = config.get("openai", "model_url")
temperature = eval(config.get("openai", "temperature"))
top_p       = eval(config.get("openai", "top_p"))
frequency_penalty = eval(config.get("openai", "frequency_penalty"))
presence_penalty  = eval(config.get("openai", "presence_penalty"))

json_db_root = transform_path(
    config.get("database", "json_db_root",
               fallback=config.get("mongo", "json_db_root", fallback="json_db"))
)
mongo_url  = config.get("mongo", "mongo_url")
mongo_port = eval(config.get("mongo", "mongo_port"))
mongo_user = config.get("mongo", "mongo_user")
mongo_pwd  = config.get("mongo", "mongo_pwd")

# ── 新增参数（带安全默认值）────────────────────────────────────────────────────

def _get_int(section, key, fallback):
    try:
        return int(config.get(section, key))
    except (configparser.NoOptionError, configparser.NoSectionError, ValueError):
        return fallback


# 每 slice 生成的测试用例数上限；-1 = 不限制
TEST_CASES_PER_SLICE: int = _get_int("DEFAULT", "TEST_CASES_PER_SLICE", -1)

# wo_slice 模式下每 method 总测试数上限
WO_SLICE_TEST_COUNT: int = _get_int("DEFAULT", "WO_SLICE_TEST_COUNT", 5)

# 修复阶段最大迭代轮数
MAX_REPAIR_TRIALS: int = _get_int("DEFAULT", "MAX_REPAIR_TRIALS", 10)

# run_all_tests 循环中 per-method 测试用例数量（原 test_number）
TEST_NUMBER: int = _get_int("DEFAULT", "TEST_NUMBER", 5)

# dataset 目录（export_data 使用）；空字符串 = 由 playground 自动推断
_raw_dataset_dir = config.get("DEFAULT", "DATASET_DIR",
                               fallback="").strip()
dataset_dir: str = (transform_path(_raw_dataset_dir)
                    if _raw_dataset_dir else "")