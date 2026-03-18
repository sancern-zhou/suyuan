"""
测试中文引号修复
"""
import sys
import os

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.llm_response_parser import LLMResponseParser


def test_chinese_quotes():
    """测试中文引号修复"""
    parser = LLMResponseParser()

    print("="*80)
    print("中文引号修复测试")
    print("="*80)

    # 测试用例：包含中文引号的JSON
    test_case = '''{
  "thought": "用户刚刚执行了dir /a命令查看D:\\溯源目录，系统返回了目录列表。现在用户再次请求"列出文件目录"，这可能是希望刷新目录列表或查看更详细的内容。",
  "reasoning": "用户连续两次请求列出文件目录。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash",
    "args": {
      "command": "dir",
      "timeout": 30
    }
  }
}'''

    print("\n原始内容（包含中文引号）:")
    print(test_case[:200])

    # 验证原始JSON是否无效
    import json
    try:
        json.loads(test_case)
        print("⚠️ 原始JSON可以被解析（不符合预期）")
    except json.JSONDecodeError as e:
        print(f"✅ 原始JSON解析失败（符合预期）: {str(e)[:100]}")

    # 测试解析
    print("\n使用LLMResponseParser解析:")
    result = parser.parse(test_case)

    print(f"解析成功: {result['success']}")

    if result['success']:
        print("✅ 解析成功！")
        print(f"数据键: {list(result['data'].keys())}")
        if 'action' in result['data']:
            action = result['data']['action']
            print(f"Action类型: {action.get('type')}")
            print(f"工具: {action.get('tool')}")
            if 'args' in action:
                args = action['args']
                print(f"命令: {args.get('command')}")
    else:
        print("❌ 解析失败")
        if result.get('error'):
            error = result['error']
            print(f"错误类型: {error.get('error_type')}")
            print(f"错误消息: {error.get('error_msg')}")

    # 测试用例2：混合中文和英文引号
    test_case_2 = '''{
  "thought": "测试"混合"引号",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash"
  }
}'''

    print("\n" + "="*80)
    print("测试用例2: 混合中文和英文引号")
    print("="*80)

    result2 = parser.parse(test_case_2)
    print(f"解析成功: {result2['success']}")

    # 测试用例3：只有英文引号（正常情况）
    test_case_3 = '''{
  "thought": "测试正常引号",
  "action": {
    "type": "FINISH"
  }
}'''

    print("\n" + "="*80)
    print("测试用例3: 只有英文引号（正常情况）")
    print("="*80)

    result3 = parser.parse(test_case_3)
    print(f"解析成功: {result3['success']}")

    # 显示统计信息
    print("\n" + "="*80)
    print("解析统计")
    print("="*80)
    stats = parser.get_stats()
    for key, value in stats.items():
        if value > 0:
            print(f"{key}: {value}")


if __name__ == "__main__":
    test_chinese_quotes()
