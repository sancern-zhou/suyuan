"""
测试中文标点符号修复
"""
import sys
import os
import json

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.llm_response_parser import LLMResponseParser


def test_chinese_punctuation_cases():
    """测试各种中文标点符号的修复"""
    parser = LLMResponseParser()

    print("="*80)
    print("中文标点符号修复测试")
    print("="*80)

    # 测试用例1：从日志中提取的真实失败案例
    test_case_1 = '''{
  "thought": "用户询问当前工作目录（D:\\\\溯源）是否包含"报告模板"目录。",
  "reasoning": "用户的问题是一个简单的查询。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash",
    "args": {
      "command": "dir /ad \\"D:\\\\溯源\\\\报告模板\\""
    }
  }
}'''

    print("\n" + "="*80)
    print("测试用例1：中文引号（从日志中提取）")
    print("="*80)

    print(f"\n原始内容（前200字符）:")
    print(test_case_1[:200])

    # 验证原始JSON是否有效
    try:
        json.loads(test_case_1)
        print("⚠️ 原始JSON可以被解析")
    except json.JSONDecodeError as e:
        print(f"✅ 原始JSON解析失败（符合预期）: {str(e)[:80]}")

    # 测试解析
    print("\n使用LLMResponseParser解析:")
    result = parser.parse(test_case_1)

    print(f"解析成功: {result['success']}")

    if result['success']:
        print("✅ 解析成功！")
        print(f"数据键: {list(result['data'].keys())}")
    else:
        print("❌ 解析失败")
        if result.get('error'):
            error = result['error']
            print(f"错误类型: {error.get('error_type')}")

    # 测试用例2：中文书名号
    test_case_2 = '''{
  "thought": "用户询问《报告模板》目录是否存在",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash"
  }
}'''

    print("\n" + "="*80)
    print("测试用例2：中文书名号《》")
    print("="*80)

    result2 = parser.parse(test_case_2)
    print(f"解析成功: {result2['success']}")

    # 测试用例3：中文方括号
    test_case_3 = '''{
  "thought": "查看【重要文件】列表",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash"
  }
}'''

    print("\n" + "="*80)
    print("测试用例3：中文方括号【】")
    print("="*80)

    result3 = parser.parse(test_case_3)
    print(f"解析成功: {result3['success']}")

    # 测试用例4：混合中文标点
    test_case_4 = '''{
  "thought": "用户说"查看《重要》文件夹【报告】",
  "reasoning": "用户使用了多种中文标点",
  "action": {
    "type": "FINISH",
    "answer": "完成"
  }
}'''

    print("\n" + "="*80)
    print("测试用例4：混合中文标点")
    print("="*80)

    result4 = parser.parse(test_case_4)
    print(f"解析成功: {result4['success']}")

    # 测试用例5：纯英文标点（应该保持不变）
    test_case_5 = '''{
  "thought": "Simple test with English quotes",
  "action": {
    "type": "FINISH"
  }
}'''

    print("\n" + "="*80)
    print("测试用例5：纯英文标点（对照组）")
    print("="*80)

    result5 = parser.parse(test_case_5)
    print(f"解析成功: {result5['success']}")

    # 显示统计信息
    print("\n" + "="*80)
    print("解析统计")
    print("="*80)
    stats = parser.get_stats()
    for key, value in stats.items():
        if value > 0:
            print(f"{key}: {value}")

    # 测试预处理函数
    print("\n" + "="*80)
    print("预处理函数测试")
    print("="*80)

    test_str = '用户说"查看《重要》文件夹【报告】'
    print(f"原始: {test_str}")
    processed = parser._preprocess_llm_output(test_str)
    print(f"修复后: {processed}")
    print(f"是否修改: {test_str != processed}")


if __name__ == "__main__":
    test_chinese_punctuation_cases()
