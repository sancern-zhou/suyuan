"""
测试json-repair库集成
"""
import sys
import os

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.llm_response_parser import LLMResponseParser, JSON_REPAIR_AVAILABLE


def test_json_repair_integration():
    """测试json-repair库集成"""
    parser = LLMResponseParser()

    print("="*80)
    print("json-repair库集成测试")
    print("="*80)
    print(f"\njson-repair库可用: {JSON_REPAIR_AVAILABLE}")

    if not JSON_REPAIR_AVAILABLE:
        print("\n⚠️ json-repair库未安装，请运行: pip install json-repair")
        return

    # 测试用例1: 包含未转义的Windows路径
    test_case_1 = r'''{
  "thought": "用户需要在当前工作目录D:\溯源中搜索一个具体的Word文档文件"2025年臭氧垂直报告7-ok - 副本.docx"。这是一个文件搜索任务，需要使用bash工具来执行搜索命令。",
  "reasoning": "用户明确要求搜索一个特定的Word文档文件。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash",
    "args": {
      "command": "dir /S /B *test*",
      "working_dir": "D:\溯源"
    }
  }
}'''

    print("\n" + "="*80)
    print("测试用例1: 未转义的Windows路径和引号")
    print("="*80)

    print(f"\n原始内容（前200字符）:")
    print(test_case_1[:200])

    # 先验证原始JSON确实是无效的
    import json
    try:
        json.loads(test_case_1)
        print("⚠️ 原始JSON可以被解析（不符合预期）")
    except json.JSONDecodeError as e:
        print(f"✅ 原始JSON解析失败（符合预期）: {e}")

    # 测试完整解析流程
    print("\n使用LLMResponseParser解析:")
    result = parser.parse(test_case_1)

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
                print(f"参数: {args}")
    else:
        print("❌ 解析失败")
        if result.get('error'):
            error = result['error']
            print(f"错误类型: {error.get('error_type')}")
            print(f"错误消息: {error.get('error_msg')}")

    # 测试用例2: 已正确转义的JSON（应该保持不变）
    test_case_2 = '''{
  "thought": "测试已转义的路径",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash",
    "args": {
      "command": "dir",
      "working_dir": "D:\\\\溯源"
    }
  }
}'''

    print("\n" + "="*80)
    print("测试用例2: 已正确转义的JSON（应该保持不变）")
    print("="*80)

    result2 = parser.parse(test_case_2)
    print(f"解析成功: {result2['success']}")

    if result2['success']:
        print("✅ 正确转义的JSON解析成功")
    else:
        print("❌ 正确转义的JSON解析失败（不应该发生）")

    # 测试用例3: 普通JSON（无路径问题）
    test_case_3 = '''{
  "thought": "简单的测试",
  "reasoning": "不包含路径",
  "action": {
    "type": "FINISH",
    "answer": "完成"
  }
}'''

    print("\n" + "="*80)
    print("测试用例3: 普通JSON（无路径问题）")
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
    test_json_repair_integration()
