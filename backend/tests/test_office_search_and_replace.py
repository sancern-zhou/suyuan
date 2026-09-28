"""
测试 Office 工具的 search_and_replace 功能
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools.office.word_tool import WordWin32LLMTool
from app.tools.office.ppt_tool import PPTWin32LLMTool


async def test_word_search_and_replace():
    """测试 Word 的 search_and_replace 功能"""
    print("=" * 80)
    print("测试 Word search_and_replace 功能")
    print("=" * 80)

    word_tool = WordWin32LLMTool()

    # 检查工具是否可用
    if not word_tool.is_available():
        print("[FAIL] Word 工具不可用（非 Windows 系统）")
        return

    # 检查 schema
    schema = word_tool.get_function_schema()
    print("\n[INFO] Word 工具操作类型:")
    print(f"   {schema['parameters']['properties']['operation']['enum']}")

    # 验证 search_and_replace 是否在操作列表中
    if "search_and_replace" in schema['parameters']['properties']['operation']['enum']:
        print("[SUCCESS] search_and_replace 操作已添加到 Word 工具")

        # 检查相关参数
        params = schema['parameters']['properties']
        required_params = ['search_text', 'replace_text', 'match_case', 'match_whole_word', 'use_wildcards']

        print("\n[INFO] search_and_replace 相关参数:")
        for param in required_params:
            if param in params:
                print(f"   [OK] {param}: {params[param]['description'][:50]}...")
            else:
                print(f"   [FAIL] {param}: 参数缺失")

    else:
        print("[FAIL] search_and_replace 操作未添加到 Word 工具")


async def test_ppt_search_and_replace():
    """测试 PPT 的 search_and_replace 功能"""
    print("\n" + "=" * 80)
    print("测试 PPT search_and_replace 功能")
    print("=" * 80)

    ppt_tool = PPTWin32LLMTool()

    # 检查工具是否可用
    if not ppt_tool.is_available():
        print("[FAIL] PPT 工具不可用（非 Windows 系统）")
        return

    # 检查 schema
    schema = ppt_tool.get_function_schema()
    print("\n[INFO] PPT 工具操作类型:")
    print(f"   {schema['parameters']['properties']['operation']['enum']}")

    # 验证 search_and_replace 是否在操作列表中
    if "search_and_replace" in schema['parameters']['properties']['operation']['enum']:
        print("[SUCCESS] search_and_replace 操作已添加到 PPT 工具")

        # 检查相关参数
        params = schema['parameters']['properties']
        required_params = ['search_text', 'replace_text', 'match_case']

        print("\n[INFO] search_and_replace 相关参数:")
        for param in required_params:
            if param in params:
                print(f"   [OK] {param}: {params[param]['description'][:50]}...")
            else:
                print(f"   [FAIL] {param}: 参数缺失")

    else:
        print("[FAIL] search_and_replace 操作未添加到 PPT 工具")


async def main():
    """主测试函数"""
    print("\n[START] 开始测试 Office 工具的 search_and_replace 功能...\n")

    await test_word_search_and_replace()
    await test_ppt_search_and_replace()

    print("\n" + "=" * 80)
    print("[DONE] 测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
