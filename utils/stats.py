"""
utils/stats.py  — HITS 统计模块

功能:
  1. LLM 调用统计（time & token）: LLMStatsTracker
  2. 测试结果统计（compile / exec / coverage / bugrevealing / similarity）: TestStatsAggregator
  3. 将统计结果写出为 CSV

设计原则:
  - 线程安全（ThreadPoolExecutor 场景下多个 worker 同时写入）
  - 零依赖于 pymongo（纯 JsonDB 环境）
  - 写出目录与 playground 对齐

用法:
  # 在 pipeline.py 中：
  from utils.stats import LLMStatsTracker, TestStatsAggregator

  tracker = LLMStatsTracker(project_name, playground_dir)
  # 在 chatter.generate() 调用处记录
  tracker.record_llm_call(stage="slice", method=m, prompt_tokens=pt,
                           completion_tokens=ct, elapsed_sec=t)
  tracker.save()

  agg = TestStatsAggregator(project_name, playground_dir)
  agg.add_compile_result(test_class, status)
  agg.add_exec_result(test_class, status, timeout)
  agg.save()
"""

import csv
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


# ══════════════════════════════════════════════════════════════════════════════
# 1. LLM 调用统计
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LLMCallRecord:
    timestamp:          str
    stage:              str      # slice / gen / fix / patch
    method:             str      # focal method name or collection key
    prompt_tokens:      int
    completion_tokens:  int
    total_tokens:       int
    elapsed_sec:        float
    model:              str
    success:            bool


class LLMStatsTracker:
    """
    线程安全的 LLM 调用统计器。

    用法示例（在 OpenGenerator.generate() 调用处包装）:

        t0 = time.time()
        status, outputs, token_count = chatter.generate(prompt, system)
        elapsed = time.time() - t0
        if token_count:
            tracker.record_llm_call(
                stage="gen", method=method_to_test,
                prompt_tokens=token_count['prompt_tokens'],
                completion_tokens=token_count['completion_tokens'],
                elapsed_sec=elapsed, model=model,
                success=(status == 200))
    """

    def __init__(self, project_name: str, playground_root: str):
        self.project_name    = project_name
        self._out_dir        = os.path.join(playground_root, project_name, "stats")
        os.makedirs(self._out_dir, exist_ok=True)
        self._records: List[LLMCallRecord] = []
        self._lock = threading.Lock()

    def record_llm_call(self, stage: str, method: str,
                        prompt_tokens: int, completion_tokens: int,
                        elapsed_sec: float, model: str = "", success: bool = True):
        rec = LLMCallRecord(
            timestamp=datetime.now().isoformat(),
            stage=stage, method=method,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            elapsed_sec=round(elapsed_sec, 3),
            model=model, success=success,
        )
        with self._lock:
            self._records.append(rec)

    def summary(self) -> dict:
        with self._lock:
            recs = list(self._records)
        if not recs:
            return {}
        total_prompt      = sum(r.prompt_tokens     for r in recs)
        total_completion  = sum(r.completion_tokens for r in recs)
        total_tokens      = sum(r.total_tokens      for r in recs)
        total_time        = sum(r.elapsed_sec       for r in recs)
        by_stage: Dict[str, dict] = {}
        for r in recs:
            s = by_stage.setdefault(r.stage, {
                'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0,
                'total_tokens': 0, 'elapsed_sec': 0.0, 'failures': 0})
            s['calls']             += 1
            s['prompt_tokens']     += r.prompt_tokens
            s['completion_tokens'] += r.completion_tokens
            s['total_tokens']      += r.total_tokens
            s['elapsed_sec']       += r.elapsed_sec
            if not r.success:
                s['failures']      += 1
        return {
            'total_calls':        len(recs),
            'total_prompt_tokens':     total_prompt,
            'total_completion_tokens': total_completion,
            'total_tokens':            total_tokens,
            'total_elapsed_sec':       round(total_time, 3),
            'by_stage':                by_stage,
        }

    def save(self):
        """写出两个文件: llm_calls.csv (每条记录) + llm_summary.csv (汇总)"""
        with self._lock:
            recs = list(self._records)

        calls_csv = os.path.join(self._out_dir, "llm_calls.csv")
        with open(calls_csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['timestamp', 'project', 'stage', 'method',
                        'prompt_tokens', 'completion_tokens', 'total_tokens',
                        'elapsed_sec', 'model', 'success'])
            for r in recs:
                w.writerow([r.timestamp, self.project_name, r.stage, r.method,
                             r.prompt_tokens, r.completion_tokens, r.total_tokens,
                             r.elapsed_sec, r.model, r.success])

        sm = self.summary()
        summary_csv = os.path.join(self._out_dir, "llm_summary.csv")
        with open(summary_csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['project', 'stage', 'calls', 'prompt_tokens',
                        'completion_tokens', 'total_tokens', 'elapsed_sec', 'failures'])
            for stage, s in sm.get('by_stage', {}).items():
                w.writerow([self.project_name, stage, s['calls'],
                             s['prompt_tokens'], s['completion_tokens'],
                             s['total_tokens'], round(s['elapsed_sec'], 3),
                             s['failures']])
            # 汇总行
            w.writerow([self.project_name, '__TOTAL__',
                        sm.get('total_calls', 0),
                        sm.get('total_prompt_tokens', 0),
                        sm.get('total_completion_tokens', 0),
                        sm.get('total_tokens', 0),
                        sm.get('total_elapsed_sec', 0), ''])

        return calls_csv, summary_csv


# ══════════════════════════════════════════════════════════════════════════════
# 2. 测试结果统计
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TestRecord:
    project:        str
    method:         str     # focal method / collection key
    test_class:     str
    compile_status: str     # pass / fail / skip
    exec_status:    str     # pass / fail / timeout / skip
    line_cov:       Optional[float] = None
    branch_cov:     Optional[float] = None
    bug_revealing:  Optional[bool]  = None
    similarity:     Optional[float] = None   # combined_similarity (0~1)
    redundancy:     Optional[float] = None   # 1 - similarity


class TestStatsAggregator:
    """
    收集编译、执行、覆盖率、bugrevealing、相似度统计，写出 CSV。

    调用方式:
        agg = TestStatsAggregator(project_name, playground_dir)

        # 编译/执行结果（来自 fix_code.init_test）
        agg.add_test_result(method, test_class,
                            compile_status='pass', exec_status='fail')

        # 覆盖率（来自 jacoco 分析）
        agg.add_coverage(test_class, line_cov=78.5, branch_cov=62.0)

        # bugrevealing（来自 bug_revealing.py 输出 CSV）
        agg.load_bugrevealing_csv(path)

        # 相似度（来自 measure_similarity.py 输出 CSV）
        agg.load_similarity_csv(path)

        agg.save()
    """

    def __init__(self, project_name: str, playground_root: str):
        self.project_name = project_name
        self._out_dir     = os.path.join(playground_root, project_name, "stats")
        os.makedirs(self._out_dir, exist_ok=True)
        self._records: Dict[str, TestRecord] = {}
        self._lock = threading.Lock()

    def add_test_result(self, method: str, test_class: str,
                        compile_status: str = 'skip', exec_status: str = 'skip'):
        with self._lock:
            rec = self._records.setdefault(test_class, TestRecord(
                project=self.project_name, method=method, test_class=test_class,
                compile_status=compile_status, exec_status=exec_status))
            rec.compile_status = compile_status
            rec.exec_status    = exec_status

    def add_coverage(self, test_class: str, line_cov: Optional[float],
                     branch_cov: Optional[float]):
        with self._lock:
            if test_class in self._records:
                self._records[test_class].line_cov   = line_cov
                self._records[test_class].branch_cov = branch_cov

    def load_bugrevealing_csv(self, csv_path: str):
        """读取 bug_revealing.py 产生的 CSV，更新 bug_revealing 字段。"""
        if not os.path.exists(csv_path):
            return
        try:
            with open(csv_path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tc = row.get('test_class', '').strip()
                    br = row.get('bug_revealing', '').strip().lower() == 'true'
                    with self._lock:
                        if tc in self._records:
                            self._records[tc].bug_revealing = br
        except Exception as e:
            print(f"[WARN] load_bugrevealing_csv: {e}")

    def load_similarity_csv(self, csv_path: str):
        """读取 measure_similarity.py 产生的 bigSims CSV，更新 similarity 字段。"""
        if not os.path.exists(csv_path):
            return
        try:
            with open(csv_path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tc  = row.get('test_case_1', '').strip()
                    sim_str = row.get('combined_similarity', '').strip()
                    try:
                        sim = float(sim_str)
                    except ValueError:
                        continue
                    with self._lock:
                        if tc in self._records:
                            self._records[tc].similarity  = round(sim, 6)
                            self._records[tc].redundancy  = round(1.0 - sim, 6)
        except Exception as e:
            print(f"[WARN] load_similarity_csv: {e}")

    def summary(self) -> dict:
        with self._lock:
            recs = list(self._records.values())
        n = len(recs)
        if n == 0:
            return {'total': 0}
        compile_pass = sum(1 for r in recs if r.compile_status == 'pass')
        exec_pass    = sum(1 for r in recs if r.exec_status    == 'pass')
        exec_timeout = sum(1 for r in recs if r.exec_status    == 'timeout')
        line_covs    = [r.line_cov   for r in recs if r.line_cov   is not None]
        branch_covs  = [r.branch_cov for r in recs if r.branch_cov is not None]
        br_vals      = [r.bug_revealing for r in recs if r.bug_revealing is not None]
        sim_vals     = [r.similarity    for r in recs if r.similarity    is not None]
        return {
            'total':                n,
            'compile_pass':         compile_pass,
            'compile_pass_rate':    round(compile_pass / n, 4),
            'exec_pass':            exec_pass,
            'exec_pass_rate':       round(exec_pass / n, 4),
            'exec_timeout':         exec_timeout,
            'avg_line_cov':         round(sum(line_covs)   / len(line_covs),   2) if line_covs   else None,
            'avg_branch_cov':       round(sum(branch_covs) / len(branch_covs), 2) if branch_covs else None,
            'bug_revealing_count':  sum(br_vals),
            'bug_revealing_rate':   round(sum(br_vals) / len(br_vals), 4) if br_vals else None,
            'avg_similarity':       round(sum(sim_vals) / len(sim_vals), 4) if sim_vals else None,
            'avg_redundancy':       round(sum(1.0 - s for s in sim_vals) / len(sim_vals), 4) if sim_vals else None,
        }

    def save(self):
        """写出 test_results.csv + test_summary.csv"""
        with self._lock:
            recs = list(self._records.values())

        results_csv = os.path.join(self._out_dir, "test_results.csv")
        with open(results_csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['project', 'method', 'test_class', 'compile_status',
                        'exec_status', 'line_cov', 'branch_cov',
                        'bug_revealing', 'similarity', 'redundancy'])
            for r in recs:
                w.writerow([r.project, r.method, r.test_class,
                             r.compile_status, r.exec_status,
                             r.line_cov, r.branch_cov,
                             r.bug_revealing, r.similarity, r.redundancy])

        sm = self.summary()
        summary_csv = os.path.join(self._out_dir, "test_summary.csv")
        with open(summary_csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(list(sm.keys()))
            w.writerow([sm.get(k, '') for k in sm.keys()])

        return results_csv, summary_csv


# ══════════════════════════════════════════════════════════════════════════════
# 3. 辅助：包装 OpenGenerator.generate() 自动记录统计
# ══════════════════════════════════════════════════════════════════════════════

def wrap_generator_with_stats(chatter, tracker: LLMStatsTracker,
                               stage: str, method: str, model_name: str = ""):
    """
    返回一个与 chatter.generate() 签名相同的包装函数，自动记录每次调用的
    token 数量和耗时。

    用法:
        gen = wrap_generator_with_stats(chatter, tracker, stage="slice", method=m)
        status, outputs, token_count = gen(prompt, system, temperature=0.2)
    """
    original_generate = chatter.generate

    def wrapped_generate(prompt, system=None, temperature=0.2,
                         gen_count=1, top_p=1.0, history=None, timeout=600):
        t0 = time.time()
        result = original_generate(prompt, system, temperature=temperature,
                                   gen_count=gen_count, top_p=top_p,
                                   history=history, timeout=timeout)
        elapsed = time.time() - t0
        status, outputs, token_count = result
        if token_count:
            tracker.record_llm_call(
                stage=stage, method=method,
                prompt_tokens=token_count.get('prompt_tokens', 0),
                completion_tokens=token_count.get('completion_tokens', 0),
                elapsed_sec=elapsed,
                model=model_name or getattr(chatter, 'model', ''),
                success=(status == 200),
            )
        return result

    return wrapped_generate