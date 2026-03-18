"""
测试 json-repair 库对 LLM 生成 JSON 的修复能力分析

问题：LLM 生成的 JSON 中，old_string 参数包含真实换行符导致解析失败
"""

import json
from json_repair import repair_json

# 测试用例1：LLM 直接在 JSON 中使用真实换行符（错误）
test_case_1 = '''{
  "thought": "用户要求基于表1和表2补充报告中的数据特征分析内容。",
  "reasoning": "需要分析数据特征",
  "action": {
    "type": "TOOL_CALL",
    "tool": "edit_file",
    "args": {
      "path": "D:/溯源/test.xml",
      "old_string": "<w:p>
  <w:r>
    <w:t>原始内容</w:t>
  </w:r>
</w:p>",
      "new_string": "<w:p>
  <w:r>
    <w:t>新内容</w:t>
  </w:r>
</w:p>"
    }
  }
}'''

# 测试用例2：正确的 JSON 格式（换行符转义）
test_case_2 = '''{
  "thought": "用户要求基于表1和表2补充报告中的数据特征分析内容。",
  "reasoning": "需要分析数据特征",
  "action": {
    "type": "TOOL_CALL",
    "tool": "edit_file",
    "args": {
      "path": "D:/溯源/test.xml",
      "old_string": "<w:p>\\n  <w:r>\\n    <w:t>原始内容</w:t>\\n  </w:r>\\n</w:p>",
      "new_string": "<w:p>\\n  <w:r>\\n    <w:t>新内容</w:t>\\n  </w:r>\\n</w:p>"
    }
  }
}'''

# 测试用例3：更复杂的情况 - 包含引号和反斜杠
test_case_3 = '''{
  "action": {
    "tool": "edit_file",
    "args": {
      "old_string": "path = "C:\\Users\\test"
      print("hello")"
    }
  }
}'''

# 测试用例4：正确的转义
test_case_4 = '''{
  "action": {
    "tool": "edit_file",
    "args": {
      "old_string": "path = \\"C:\\\\Users\\\\test\\"\\nprint(\\"hello\\")"
    }
  }
}'''

def test_json_repair():
    """测试 json-repair 的修复能力"""

    print("=" * 60)
    print("JSON-REPAIR Library Repair Capability Analysis")
    print("=" * 60)

    # 测试用例1
    print("\n[Test Case 1] Real newlines in string values")
    print("-" * 40)
    try:
        json.loads(test_case_1)
        print("[OK] Original JSON can be parsed directly")
    except json.JSONDecodeError as e:
        print(f"[FAIL] Original JSON parse failed: {e}")

        # 尝试修复
        repaired = repair_json(test_case_1)
        print(f"\nRepaired length: {len(repaired)} (original: {len(test_case_1)})")
        print(f"Changed: {repaired != test_case_1}")

        if repaired != test_case_1:
            print("\nRepaired content (first 500 chars):")
            print(repaired[:500])
            print("\n...")

            try:
                json.loads(repaired)
                print("[OK] Repaired JSON can be parsed")
            except json.JSONDecodeError as e:
                print(f"[FAIL] Repaired JSON still fails: {e}")
        else:
            print("[WARN] json-repair made no changes")

    # 测试用例2
    print("\n" + "=" * 60)
    print("[Test Case 2] Correct newline escaping")
    print("-" * 40)
    try:
        data = json.loads(test_case_2)
        print("[OK] Correct format JSON can be parsed")
        print(f"old_string content: {repr(data['action']['args']['old_string'][:50])}")
    except json.JSONDecodeError as e:
        print(f"[FAIL] Parse failed: {e}")

    # 测试用例3
    print("\n" + "=" * 60)
    print("[Test Case 3] Unescaped quotes and backslashes")
    print("-" * 40)
    try:
        json.loads(test_case_3)
        print("[OK] Original JSON can be parsed directly")
    except json.JSONDecodeError as e:
        print(f"[FAIL] Original JSON parse failed: {e}")

        repaired = repair_json(test_case_3)
        print(f"\nChanged: {repaired != test_case_3}")

        if repaired != test_case_3:
            print("\nRepaired content:")
            print(repaired)

            try:
                json.loads(repaired)
                print("[OK] Repaired JSON can be parsed")
            except json.JSONDecodeError as e:
                print(f"[FAIL] Still fails after repair: {e}")

    # 测试用例4
    print("\n" + "=" * 60)
    print("[Test Case 4] Correct quote and backslash escaping")
    print("-" * 40)
    try:
        data = json.loads(test_case_4)
        print("[OK] Correct format JSON can be parsed")
        print(f"old_string content: {repr(data['action']['args']['old_string'])}")
    except json.JSONDecodeError as e:
        print(f"[FAIL] Parse failed: {e}")

    print("\n" + "=" * 60)
    print("Conclusion")
    print("=" * 60)

if __name__ == "__main__":
    test_json_repair()
