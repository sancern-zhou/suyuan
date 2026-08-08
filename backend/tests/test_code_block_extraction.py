"""
测试代码块提取改进
"""
import sys
import os

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.llm_response_parser import LLMResponseParser


def test_code_block_extraction():
    """测试代码块提取"""
    parser = LLMResponseParser()

    print("="*80)
    print("代码块提取测试")
    print("="*80)

    # 测试用例：从日志中提取的真实失败案例
    test_case = '''```json {
  "thought": "用户再次询问"有哪些目录"，但历史上下文显示已经执行过三次相同的dir命令，且输出结果不完整（显示为"11:..."）。我需要查看完整目录列表，但系统只返回了部分信息。考虑到这是系统工具的输出，我无法控制其显示格式，只能基于现有信息回复。",
  "reasoning": "历史上下文中已经多次执行dir命令，且输出结果不完整。用户再次询问相同问题，我需要基于已有信息提供回复。由于这是文件系统操作，且输出结果受限，我将使用FINISH工具给出简洁回复，说明目录情况。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "FINISH",
    "args": {
      "answer": "当前工作目录 D:\\溯源 包含以下文件夹：.（当前目录）和 ..（上级目录）。根据之前的dir命令输出，目录中还有其他文件夹，但完整列表未完全显示。"
    }
  }
}
```'''

    print("\n原始内容（代码块格式）:")
    print(test_case[:300])

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
                print(f"Answer: {args.get('answer')[:100]}...")
    else:
        print("❌ 解析失败")
        if result.get('error'):
            error = result['error']
            print(f"错误类型: {error.get('error_type')}")

    # 测试用例2：简单的代码块
    test_case_2 = '''```json
{
  "thought": "简单测试",
  "action": {
    "type": "FINISH",
    "answer": "完成"
  }
}
```'''

    print("\n" + "="*80)
    print("测试用例2: 简单的代码块")
    print("="*80)

    result2 = parser.parse(test_case_2)
    print(f"解析成功: {result2['success']}")

    if result2['success']:
        print("✅ 解析成功！")
        data = result2['data']
        print(f"Thought: {data.get('thought')}")
        print(f"Answer: {data.get('action', {}).get('args', {}).get('answer')}")

    # 显示统计信息
    print("\n" + "="*80)
    print("解析统计")
    print("="*80)
    stats = parser.get_stats()
    for key, value in stats.items():
        if value > 0:
            print(f"{key}: {value}")


if __name__ == "__main__":
    test_code_block_extraction()
