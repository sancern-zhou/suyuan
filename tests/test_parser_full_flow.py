"""
完整测试：模拟实际的 LLM 响应解析流程

基于日志中的实际数据，测试 json-repair 是否被正确调用
"""

import sys
import json
from json_repair import repair_json

# 模拟日志中的实际内容（包含真实的换行符）
# 这是 LLM 返回的原始内容
llm_response_from_log = '''{
  "thought": "用户要求基于表1和表2补充报告中的数据特征分析内容。我已经成功读取了文档内容，现在需要根据表格数据进行分析并补充到文档中。",
  "reasoning": "用户需要补充报告的数据特征分析部分。我已经读取了document.xml文件，其中包含表1（空气质量数据）和表2（气象条件）。现在需要分析这些数据并补充到文档中。数据包括：SO2=4, NO2=14, CO=0.5, O3_8h=104, PM2.5=14, PM10=25, AQI=54；以及气象条件：最高气温34.0℃，平均湿度54.4%，南偏东风，平均风速1.7m/s，紫外线辐射量985.483 W/m2。我需要分析这些数据的特征，然后补充到文档的"数据特征分析："部分。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "edit_file",
    "args": {
      "path": "D:/溯源/报告模板/unpacked_2025年7月20日臭氧垂直/word/document.xml",
      "old_string": "数据特征分析：
有待补充",
      "new_string": "数据特征分析：根据表1和表2的数据，可以看出以下特征..."
    }
  }
}'''

def test_json_repair_directly():
    """测试 json-repair 对实际日志内容的处理能力"""
    print("=" * 80)
    print("Test 1: json-repair on actual log content")
    print("=" * 80)

    print("\nOriginal content length:", len(llm_response_from_log))

    # 尝试解析原始内容
    print("\n[Step 1] Try parsing ORIGINAL content:")
    try:
        data = json.loads(llm_response_from_log)
        print("[OK] Original can be parsed!")
        print(f"Action: {data.get('action', {}).get('type')}")
        return True
    except json.JSONDecodeError as e:
        print(f"[FAIL] Original parse failed: {e}")
        print(f"Error position: line {e.lineno}, column {e.colno}, char {e.pos}")

    # 应用 json-repair
    print("\n[Step 2] Apply json-repair:")
    repaired = repair_json(llm_response_from_log)
    print(f"Repaired length: {len(repaired)} (original: {len(llm_response_from_log)})")
    print(f"Changed: {repaired != llm_response_from_log}")

    if repaired != llm_response_from_log:
        print("\n[INFO] json-repair made changes!")
        print("\nRepaired content (first 500 chars):")
        print(repaired[:500])

        # 尝试解析修复后的内容
        print("\n[Step 3] Try parsing REPAIRED content:")
        try:
            data = json.loads(repaired)
            print("[OK] Repaired can be parsed!")
            print(f"Action: {data.get('action', {}).get('type')}")
            print(f"Tool: {data.get('action', {}).get('tool')}")
            print(f"Path: {data.get('action', {}).get('args', {}).get('path')}")
            return True
        except json.JSONDecodeError as e:
            print(f"[FAIL] Repaired parse failed: {e}")
            return False
    else:
        print("[WARN] json-repair made no changes")
        return False

def test_with_chinese_punctuation():
    """测试中文标点符号预处理后的内容"""
    print("\n" + "=" * 80)
    print("Test 2: After Chinese punctuation preprocessing")
    print("=" * 80)

    # 模拟 _preprocess_llm_output 的处理
    content = llm_response_from_log
    replacements = {
        '"': '"',
        '"': '"',
        ''': "'",
        ''': "'",
        '《': '<',
        '》': '>',
        '【': '[',
        '】': ']',
    }

    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            print(f"Replaced: {old} -> {new}")

    print(f"\nContent after preprocessing: {len(content)} chars")
    print(f"Changed: {content != llm_response_from_log}")

    # 应用 json-repair
    repaired = repair_json(content)
    print(f"\nAfter json-repair: {len(repaired)} chars")
    print(f"Changed: {repaired != content}")

    # 尝试解析
    try:
        data = json.loads(repaired)
        print("\n[OK] Can parse after preprocessing + json-repair!")
        print(f"Action: {data.get('action', {}).get('type')}")
        return True
    except json.JSONDecodeError as e:
        print(f"\n[FAIL] Cannot parse: {e}")
        return False

def test_edge_case_unescaped_newlines():
    """测试边缘情况：字符串中的真实换行符"""
    print("\n" + "=" * 80)
    print("Test 3: Edge case - Real newlines in string values")
    print("=" * 80)

    # 构造一个明确包含真实换行符的 JSON
    test_json = '''{
  "action": {
    "tool": "edit_file",
    "args": {
      "old_string": "line 1
line 2
line 3"
    }
  }
}'''

    print("Test JSON contains real newlines in old_string value")

    # 尝试解析
    try:
        json.loads(test_json)
        print("[OK] Can parse directly (unexpected)")
    except json.JSONDecodeError as e:
        print(f"[Expected] Parse failed: {e}")

    # 应用 json-repair
    repaired = repair_json(test_json)
    print(f"\nAfter json-repair: {len(repaired)} chars (original: {len(test_json)})")
    print(f"Changed: {repaired != test_json}")

    if repaired != test_json:
        print("\nRepaired content:")
        print(repaired)

        try:
            data = json.loads(repaired)
            print("[OK] Repaired can be parsed!")
            print(f"old_string value: {repr(data['action']['args']['old_string'])}")
            return True
        except json.JSONDecodeError as e:
            print(f"[FAIL] Repaired still fails: {e}")
            return False
    else:
        print("[WARN] json-repair made no changes")
        return False

if __name__ == "__main__":
    results = []

    print("\n" + "=" * 80)
    print("LLM Response Parser - Full Flow Test")
    print("=" * 80)

    results.append(("Direct json-repair", test_json_repair_directly()))
    results.append(("With preprocessing", test_with_chinese_punctuation()))
    results.append(("Edge case", test_edge_case_unescaped_newlines()))

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")

    all_passed = all(r for _, r in results)
    print("\n" + ("=" * 80))
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 80)
