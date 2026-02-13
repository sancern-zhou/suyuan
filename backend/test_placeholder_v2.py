# -*- coding: utf-8 -*-
"""
测试占位符策略（替换文本包含完整的搜索文本）
"""

import sys
sys.path.insert(0, r'D:\溯源\backend')

from app.tools.office.word_win32_tool import WordWin32Tool

def test_placeholder_strategy():
    """测试占位符策略"""
    word_tool = WordWin32Tool()

    # 测试文件
    file_path = r"D:\溯源\报告模板\2025年11月3日臭氧垂直.docx"

    # 测试用例：替换文本包含完整的搜索文本
    search_text = "数据"
    # 替换文本包含完整的 "数据" 二字
    replace_text = """数据分析显示臭氧雷达316nm消光系数图显示多个短时高能量脉冲。数据分析表明这些数据具有明显的数据特征。"""

    print(f"\n{'='*80}")
    print(f"测试：替换文本包含完整的搜索文本（使用占位符策略）")
    print(f"搜索文本: '{search_text}'")
    print(f"替换文本长度: {len(replace_text)} 字符")
    print(f"替换文本是否包含搜索文本: {search_text in replace_text}")
    print(f"{'='*80}\n")

    result = word_tool.search_and_replace(
        file_path=file_path,
        search_text=search_text,
        replace_text=replace_text,
        save_as=r"D:\溯源\报告模板\2025年11月3日臭氧垂直_test_placeholder_v2.docx"
    )

    print(f"\n替换结果:")
    print(f"状态: {result.get('status')}")
    print(f"替换次数: {result.get('replacements')}")
    print(f"摘要: {result.get('summary')}")

    # 验证替换是否成功（只验证第一处）
    print(f"\n{'='*80}")
    print("注意：由于替换文本包含搜索文本，会替换所有出现的位置")
    print(f"{'='*80}\n")

    return result

if __name__ == "__main__":
    test_placeholder_strategy()
