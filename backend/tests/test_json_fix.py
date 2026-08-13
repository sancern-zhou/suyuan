"""
测试LLM响应解析器的Windows路径修复功能
"""
import sys
import os

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.llm_response_parser import LLMResponseParser

def test_windows_path_fixing():
    """测试Windows路径修复"""
    parser = LLMResponseParser()

    # 测试用例1：包含未转义的Windows路径
    test_case_1 = '''{
  "thought": "用户需要在当前工作目录D:\\溯源中搜索一个具体的Word文档文件\\"2025年臭氧垂直报告7-ok - 副本.docx\\"。这是一个文件搜索任务，需要使用bash工具来执行搜索命令。我将使用Windows的dir命令配合通配符来搜索该文件。",
  "reasoning": "用户明确要求搜索一个特定的Word文档文件。由于用户之前已经查看了当前工作目录结构，我需要在当前目录及其子目录中搜索该文件。我将使用dir命令配合通配符来搜索，这样可以递归搜索所有子目录。这是一个简单的文件搜索任务，不需要调用其他大气环境工具。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "bash",
    "args": {
      "command": "dir /S /B *臭氧垂直*7-ok*副本*.docx",
      "timeout": 30000,
      "working_dir": "D:\\\\溯源"
    }
  }
}'''

    print("="*80)
    print("测试用例1: 包含未转义的Windows路径")
    print("="*80)

    # 先测试预处理功能
    print("\n1. 测试预处理功能:")
    fixed = parser._preprocess_content(test_case_1)
    print(f"原始内容长度: {len(test_case_1)}")
    print(f"修复后长度: {len(fixed)}")
    print(f"内容是否变化: {fixed != test_case_1}")

    if fixed != test_case_1:
        print("\n✅ 预处理检测到问题并修复")
        # 显示差异
        import difflib
        diff = difflib.unified_diff(
            test_case_1.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile='原始',
            tofile='修复后',
            lineterm=''
        )
        print('\n'.join(diff))
    else:
        print("\n⚠️ 预处理未检测到问题（可能需要调整正则表达式）")

    # 测试完整解析
    print("\n2. 测试完整解析:")
    result = parser.parse(test_case_1)
    print(f"解析成功: {result['success']}")

    if result['success']:
        print(f"✅ 解析成功！")
        print(f"数据键: {list(result['data'].keys())}")
        if 'action' in result['data']:
            print(f"Action类型: {result['data']['action'].get('type')}")
            print(f"工具: {result['data']['action'].get('tool')}")
    else:
        print(f"❌ 解析失败")
        if result.get('error'):
            print(f"错误: {result['error']}")

    # 测试用例2：已经正确转义的路径（应该保持不变）
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
    print("测试用例2: 已正确转义的路径（应该保持不变）")
    print("="*80)

    fixed2 = parser._preprocess_content(test_case_2)
    result2 = parser.parse(test_case_2)

    print(f"预处理改变内容: {fixed2 != test_case_2}")
    print(f"解析成功: {result2['success']}")

    if result2['success']:
        print("✅ 正确转义的路径解析成功")
    else:
        print("❌ 正确转义的路径解析失败（不应该发生）")

    # 测试用例3：无路径的普通JSON
    test_case_3 = '''{
      "thought": "简单的测试",
      "reasoning": "不包含路径",
      "action": {
        "type": "FINISH",
        "answer": "完成"
      }
    }'''

    print("\n" + "="*80)
    print("测试用例3: 无路径的普通JSON")
    print("="*80)

    fixed3 = parser._preprocess_content(test_case_3)
    result3 = parser.parse(test_case_3)

    print(f"预处理改变内容: {fixed3 != test_case_3}")
    print(f"解析成功: {result3['success']}")

    # 显示统计信息
    print("\n" + "="*80)
    print("解析统计")
    print("="*80)
    stats = parser.get_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    test_windows_path_fixing()
