"""
模拟 LLM 响应解析流程分析

模拟实际的解析流程，找出为什么 json-repair 没有生效
"""

import json
from json_repair import repair_json

# 模拟 LLM 返回的内容（从日志中提取的示例）
llm_response = '''{
  "thought": "用户要求基于表1和表2补充报告中的数据特征分析内容。我已经成功读取了文档内容，现在需要根据表格数据进行分析并补充到文档中。",
  "reasoning": "用户需要补充报告的数据特征分析部分。我已经读取了document.xml文件，其中包含表1（空气质量数据）和表2（气象条件）。现在需要分析这些数据并补充到文档中。数据包括：SO2=4, NO2=14, CO=0.5, O3_8h=104, PM2.5=14, PM10=25, AQI=54；以及气象条件：最高气温34.0℃，平均湿度54.4%，南偏东风，平均风速1.7m/s，紫外线辐射量985.483 W/m2。我需要分析这些数据的特征，然后补充到文档的"数据特征分析："部分。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "edit_file",
    "args": {
      "path": "D:/溯源/报告模板/unpacked_2025年7月20日臭氧垂直/word/document.xml",
      "old_string": "数据特征分析：
有待补充",
      "new_string": "数据特征分析：\\n1. 空气质量数据特征：SO2浓度为4μg/m³，NO2浓度为14μg/m³，CO浓度为0.5mg/m³，O3_8h浓度为104μg/m³（超标），PM2.5浓度为14μg/m³，PM10浓度为25μg/m³，AQI为54（良）。\\n2. 气象条件特征：最高气温34.0℃，平均湿度54.4%，南偏东风，平均风速1.7m/s，紫外线辐射量985.483 W/m²。"
    }
  }
}'''

def simulate_parser_flow():
    """模拟解析流程"""

    print("=" * 70)
    print("Simulating Parser Flow")
    print("=" * 70)

    # Step 0: Strip content
    content = llm_response.strip()
    print(f"\n[Step 0] Content stripped")
    print(f"Length: {len(content)}, Starts with '{{': {content.startswith('{')}")

    # Step 1: Apply json-repair
    print("\n" + "=" * 70)
    print("[Step 1] Apply json-repair")
    print("-" * 40)

    repaired_content = repair_json(content)
    print(f"Original length: {len(content)}")
    print(f"Repaired length: {len(repaired_content)}")
    print(f"Content changed: {repaired_content != content}")

    if repaired_content != content:
        print("\n[INFO] json-repair made changes!")

        # Try to parse original
        print("\nTrying to parse ORIGINAL content:")
        try:
            json.loads(content)
            print("[OK] Original can be parsed")
        except json.JSONDecodeError as e:
            print(f"[FAIL] Original parse failed: {e}")

        # Try to parse repaired
        print("\nTrying to parse REPAIRED content:")
        try:
            data = json.loads(repaired_content)
            print("[OK] Repaired can be parsed!")
            print(f"Action type: {data.get('action', {}).get('type')}")
            print(f"Tool: {data.get('action', {}).get('tool')}")
        except json.JSONDecodeError as e:
            print(f"[FAIL] Repaired parse failed: {e}")

    else:
        print("[WARN] json-repair made no changes")
        print("\nTrying to parse content:")
        try:
            json.loads(content)
            print("[OK] Content can be parsed directly")
        except json.JSONDecodeError as e:
            print(f"[FAIL] Content parse failed: {e}")

    # Step 2: Direct JSON parse (simulate strategy 2)
    print("\n" + "=" * 70)
    print("[Step 2] Direct JSON Parse (Strategy 2)")
    print("-" * 40)

    if content.startswith('{') and content.endswith('}'):
        print("Content starts with '{' and ends with '}'")
        print("\nTrying direct parse on ORIGINAL content:")
        try:
            data = json.loads(content)
            print(f"[OK] Direct parse succeeded")
        except json.JSONDecodeError as e:
            print(f"[FAIL] Direct parse failed: {e}")

            print("\nTrying direct parse on REPAIRED content:")
            try:
                data = json.loads(repaired_content)
                print(f"[OK] Direct parse on REPAIRED succeeded")
            except json.JSONDecodeError as e2:
                print(f"[FAIL] Direct parse on REPAIRED also failed: {e2}")

    print("\n" + "=" * 70)
    print("Conclusion")
    print("=" * 70)

if __name__ == "__main__":
    simulate_parser_flow()
