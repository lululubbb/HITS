import json
import os
import re
from json import JSONDecodeError
from typing import Optional, Dict

try:
    from pymongo.collection import Collection
except ImportError:
    Collection = object
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)
from generator.open_generator import OpenGenerator
from procedures.basic_procedure import BasicProcedure


class SliceInfoGenerator(BasicProcedure):
    def __init__(self, prompt_root, system_template_file_name, slicer_template_file_name):
        super(SliceInfoGenerator, self).__init__(prompt_root, system_template_file_name,
                                                 slicer_template_file_name, "slicer")

    def work(self, log_dir, collection: Collection, chatter: OpenGenerator) -> Optional[Dict]:
        """
        Generate slice for the method stored in the method_experiment_root. The method_experiment_root must contain
        method.txt and info.json. method.txt is the focal method. info.json describes the surrounding information
        of the focal method, e.g., the class name, the fields, etc...
        :param chatter: the API for chatting with OpenAI API
        :param log_dir: the root dir for the target method to process.
        :param collection: the MongoDB collection for the method to test
        :return: If the generation is success, return the corresponding JSON; otherwise, None
        """
        # assert os.path.exists(log_dir)
        # with open(os.path.join(log_dir, 'direction_3.json'), "r") as file:
        #     direction_3 = json.load(file)
        direction_3 = collection.find_one({"table_name": "direction_3"})
        assert direction_3 is not None

        # 改进：更加灵活和准确的正则表达式模式
        # 匹配 ``` 或 ```json 开头，任意内容，``` 结尾的代码块
        pattern_1 = r"```(?:json)?\s*([\s\S]*?)```"
        pattern_2 = r"```\s*json\s*([\s\S]*?)```"
        target_json = None
        failed_reason = ""
        result = ""
        for i in range(5):
            if i != 0:
                self.logger.warning(f"Failed to generate JSON format output for slicer. Regenerating round {i}. "
                                    f"Failed reason: {failed_reason}")
            temperature = 0.0 if i == 1 else 0.4
            result = chatter.generate(self.generate_template.render(direction_3), self.system_template.render(),
                                      temperature=temperature)[1][0]
            
            # 策略1：首先尝试通过代码块正则表达式提取 JSON
            matches = re.findall(pattern_1, result)
            target_str = [match.strip() for match in matches]
            
            # 策略2：如果代码块方法失败，尝试第二个正则模式
            if len(target_str) == 0:
                matches = re.findall(pattern_2, result)
                target_str = [match.strip() for match in matches]
            
            # 策略3：如果代码块都失败，尝试直接解析整个响应为 JSON
            if len(target_str) == 0:
                try:
                    target_json = json.loads(result)
                    keys_to_check = ['invoked_outside_vars', "invoked_outside_methods", "summarization", 'steps']
                    all_contains = True
                    for key in keys_to_check:
                        if key not in target_json:
                            all_contains = False
                            break
                    if all_contains:
                        break
                    else:
                        target_json = None
                        failed_reason = "Direct JSON parse: No key element found"
                except JSONDecodeError:
                    target_json = None
                    failed_reason = f"Direct JSON parse failed, Regex also failed. Response preview: {result[:200]}"
                    self.logger.debug(f"LLM output for debugging: {result[:500]}")
            else:
                # 从代码块中解析 JSON
                try:
                    target_json = json.loads(target_str[-1])
                    keys_to_check = ['invoked_outside_vars', "invoked_outside_methods", "summarization", 'steps']
                    all_contains = True
                    for key in keys_to_check:
                        if key not in target_json:
                            all_contains = False
                            break
                    if all_contains:
                        break
                    else:
                        target_json = None
                        failed_reason = "Code block JSON: No key element found"
                except JSONDecodeError:
                    target_json = None
                    failed_reason = "Code block JSON decode error"

        if target_json is not None:
            target_json['table_name'] = 'add_info'
            if collection.find_one({"table_name": "add_info"}) is not None:
                collection.replace_one({"table_name": "add_info"}, target_json)
            else:
                collection.insert_one(target_json)
            with open(os.path.join(log_dir, "slice_response.txt"), 'w') as file:
                file.write(result)
        else:
            self.logger.error(f"Failed to generate slice for {log_dir}")
            with open(os.path.join(log_dir, "slice_response.txt"), 'w') as file:
                file.write(result)

        return target_json
