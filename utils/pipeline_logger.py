"""
utils/pipeline_logger.py — HITS 简洁日志模块

替换散落在各脚本中的 logging.basicConfig，提供统一的、
类似 RefineAgent 风格的进度日志：
  [HH:MM:SS] ▶ Step 2 / Generate Tests  (3/7 methods)
  [HH:MM:SS]   Csv_1_b / method_read__ → 2 files
  [HH:MM:SS] ✓ Step 2 done  (12 tests generated, 14.3s)

用法：
  from utils.pipeline_logger import PipelineLogger
  log = PipelineLogger("Csv_1_b")
  log.step_start(2, "Generate Tests")
  log.method(method_name, "2 files")
  log.step_done(2, "12 tests generated")
"""

import logging
import sys
import time
from datetime import datetime


class PipelineLogger:

    STEP_NAMES = {
        0: "Init workspace",
        1: "Slice methods",
        2: "Generate tests",
        "3a": "Run initial tests",
        "3b": "Fix failed tests",
        4: "Parse missing coverage",
        5: "Generate patch tests",
        6: "Coverage report",
        "eval": "Evaluation",
    }

    def __init__(self, project_name: str, verbose: bool = False):
        self.project = project_name
        self.verbose = verbose
        self._step_start_time = {}
        # 设置根 logger 只输出 WARNING 以上，避免第三方库杂音
        logging.getLogger().setLevel(logging.WARNING)
        # 我们自己的 logger
        self._log = logging.getLogger("hits.pipeline")
        self._log.setLevel(logging.DEBUG)
        if not self._log.handlers:
            h = logging.StreamHandler(sys.stdout)
            h.setFormatter(logging.Formatter("%(message)s"))
            self._log.addHandler(h)
            self._log.propagate = False

    def _ts(self):
        return datetime.now().strftime("%H:%M:%S")

    def _emit(self, msg: str):
        self._log.info(msg)

    def step_start(self, step, desc: str = None, total: int = None):
        name = desc or self.STEP_NAMES.get(step, f"Step {step}")
        suffix = f"  ({total} methods)" if total else ""
        self._emit(f"[{self._ts()}] ▶ Step {step} / {name}{suffix}")
        self._step_start_time[step] = time.time()

    def step_done(self, step, summary: str = ""):
        elapsed = ""
        if step in self._step_start_time:
            t = round(time.time() - self._step_start_time[step], 1)
            elapsed = f"  ({t}s)"
        detail = f"  {summary}" if summary else ""
        self._emit(f"[{self._ts()}] ✓ Step {step} done{detail}{elapsed}")

    def step_skip(self, step, reason: str = ""):
        self._emit(f"[{self._ts()}] ─ Step {step} skipped  {reason}")

    def method(self, method_name: str, detail: str = ""):
        """每个方法的进度行（verbose 模式下输出）"""
        if self.verbose:
            detail_str = f"  → {detail}" if detail else ""
            self._emit(f"[{self._ts()}]   {self.project} / {method_name}{detail_str}")

    def info(self, msg: str):
        self._emit(f"[{self._ts()}]   {msg}")

    def warn(self, msg: str):
        self._emit(f"[{self._ts()}] ⚠ {msg}")

    def error(self, msg: str):
        self._emit(f"[{self._ts()}] ✗ {msg}")

    def separator(self):
        self._emit(f"{'─'*55}")

    def summary_table(self, data: dict):
        """打印对齐的 key: value 摘要表"""
        self.separator()
        for k, v in data.items():
            if v is None:
                continue
            k_str = k.replace('_', ' ').capitalize().ljust(22)
            if isinstance(v, float):
                v_str = f"{v:.4f}" if v < 1.0 and v > 0 else f"{v:.2f}"
            else:
                v_str = str(v)
            self._emit(f"  {k_str} {v_str}")
        self.separator()