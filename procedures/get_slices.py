"""
procedures/get_slices.py  — updated with per-slice progress logging
"""

import json
import logging
import os
import re
import time
from json import JSONDecodeError
from typing import Optional, Dict

try:
    from pymongo.collection import Collection
except ImportError:
    Collection = object

import sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from generator.open_generator import OpenGenerator
from procedures.basic_procedure import BasicProcedure


class SliceInfoGenerator(BasicProcedure):
    def __init__(self, prompt_root, system_template_file_name, slicer_template_file_name):
        super(SliceInfoGenerator, self).__init__(
            prompt_root, system_template_file_name,
            slicer_template_file_name, "slicer")
        # Ensure INFO-level logs are visible
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s',
                                                   datefmt='%H:%M:%S'))
            self.logger.addHandler(handler)

    def work(self, log_dir, collection: Collection, chatter: OpenGenerator) -> Optional[Dict]:
        """
        Generate slice info for the method stored in log_dir.
        Logs progress at each retry attempt.
        """
        direction_3 = collection.find_one({"table_name": "direction_3"})
        assert direction_3 is not None

        method_name = direction_3.get('focal_method', os.path.basename(log_dir))
        class_name  = direction_3.get('class_name', '')

        self.logger.info(
            f"[Slicer] Generating slices for {class_name}.{method_name}  "
            f"dir={log_dir}")

        pattern_1 = r"```(?:json)?\s*([\s\S]*?)```"
        pattern_2 = r"```\s*json\s*([\s\S]*?)```"
        target_json = None
        failed_reason = ""
        result = ""
        t_start = time.time()

        for i in range(5):
            if i != 0:
                self.logger.warning(
                    f"[Slicer] Retry {i}/4 for {class_name}.{method_name}  "
                    f"reason={failed_reason}")
            else:
                self.logger.info(
                    f"[Slicer] Attempt 1/5: calling LLM for slice decomposition...")

            temperature = 0.0 if i == 1 else 0.4
            t_call = time.time()
            gen_result = chatter.generate(
                self.generate_template.render(direction_3),
                self.system_template.render(),
                temperature=temperature)
            t_elapsed = round(time.time() - t_call, 2)

            if gen_result[0] != 200 or gen_result[1] is None:
                failed_reason = f"LLM call failed (status={gen_result[0]})"
                self.logger.warning(f"[Slicer] {failed_reason} ({t_elapsed}s)")
                result = ""
                continue

            result = gen_result[1][0]
            self.logger.info(
                f"[Slicer] Attempt {i+1}: LLM responded in {t_elapsed}s  "
                f"(response length={len(result)} chars)")

            # Strategy 1: extract JSON from code blocks
            matches = re.findall(pattern_1, result)
            target_str = [match.strip() for match in matches]

            # Strategy 2: alternative code block pattern
            if not target_str:
                matches = re.findall(pattern_2, result)
                target_str = [match.strip() for match in matches]

            # Strategy 3: parse entire response as JSON
            if not target_str:
                try:
                    target_json = json.loads(result)
                    keys_to_check = ['invoked_outside_vars', "invoked_outside_methods",
                                     "summarization", 'steps']
                    if all(k in target_json for k in keys_to_check):
                        break
                    else:
                        target_json = None
                        failed_reason = "Direct JSON parse: missing required keys"
                        continue
                except JSONDecodeError:
                    target_json = None
                    failed_reason = "Direct JSON parse failed; regex also failed"
                    continue
            else:
                try:
                    target_json = json.loads(target_str[-1])
                    keys_to_check = ['invoked_outside_vars', "invoked_outside_methods",
                                     "summarization", 'steps']
                    if all(k in target_json for k in keys_to_check):
                        n_steps = len(target_json.get('steps', []))
                        self.logger.info(
                            f"[Slicer] ✓ Parsed JSON successfully: "
                            f"{n_steps} slices for {class_name}.{method_name}")
                        break
                    else:
                        target_json = None
                        failed_reason = "Code block JSON: missing required keys"
                        continue
                except JSONDecodeError:
                    target_json = None
                    failed_reason = "Code block JSON decode error"
                    continue

        t_total = round(time.time() - t_start, 2)

        if target_json is not None:
            n_steps = len(target_json.get('steps', []))
            self.logger.info(
                f"[Slicer] ✓ Done: {class_name}.{method_name}  "
                f"slices={n_steps}  total_time={t_total}s")

            target_json['table_name'] = 'add_info'
            if collection.find_one({"table_name": "add_info"}) is not None:
                collection.replace_one({"table_name": "add_info"}, target_json)
            else:
                collection.insert_one(target_json)
            with open(os.path.join(log_dir, "slice_response.txt"), 'w') as file:
                file.write(result)
        else:
            self.logger.error(
                f"[Slicer] ✗ Failed after 5 attempts: {class_name}.{method_name}  "
                f"total_time={t_total}s")
            with open(os.path.join(log_dir, "slice_response.txt"), 'w') as file:
                file.write(result)

        return target_json