"""
直接测试中文引号修复
"""
from app.utils.llm_response_parser import LLMResponseParser

parser = LLMResponseParser()

# 测试中文引号
test_with_chinese = '{"thought": "测试"内容"}'
print(f"原始: {test_with_chinese}")
print(f"包含中文引号: {('" in test_with_chinese)}")

fixed = parser._preprocess_llm_output(test_with_chinese)
print(f"修复后: {fixed}")
print(f"修复后包含中文引号: {('" in fixed)}")
print(f"修复后包含英文引号: {('\'' in fixed) or ('\"' in fixed)}")

print("\n" + "="*80)

# 测试完整解析
import json
test_json = '''{
  "thought": "用户请求"列出文件目录"",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash"
  }
}'''

print(f"\n原始JSON:\n{test_json}")

try:
    json.loads(test_json)
    print("✅ 原始JSON有效")
except:
    print("❌ 原始JSON无效")

# 使用解析器
result = parser.parse(test_json)
print(f"\n解析器结果: {'成功' if result['success'] else '失败'}")

if result['success']:
    print(f"数据: {result['data']}")
