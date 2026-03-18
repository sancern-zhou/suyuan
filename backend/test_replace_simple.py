# -*- coding: utf-8 -*-
"""
简化测试：手动循环替换方法
"""

import sys
sys.path.insert(0, r'D:\溯源\backend')

from app.tools.office.word_win32_tool import WordWin32Tool

def test_replace():
    """测试替换功能"""
    word_tool = WordWin32Tool()

    # 测试文件
    file_path = r"D:\溯源\报告模板\2025年11月3日臭氧垂直.docx"

    # 测试用例：替换文本包含搜索文本
    search_text = "臭氧雷达分析："
    replace_text = """臭氧雷达316nm消光系数图显示多个短时高能量脉冲与持续频率成分，呈现周期性波动特征。"""

    print(f"\n{'='*80}")
    print(f"测试：替换文本包含搜索文本（使用占位符策略）")
    print(f"搜索文本: {search_text}")
    print(f"替换文本长度: {len(replace_text)} 字符")
    print(f"替换文本是否包含搜索文本: {search_text in replace_text}")
    print(f"{'='*80}\n")

    result = word_tool.search_and_replace(
        file_path=file_path,
        search_text=search_text,
        replace_text=replace_text,
        save_as=r"D:\溯源\报告模板\2025年11月3日臭氧垂直_test_manual.docx"
    )

    print(f"\n替换结果:")
    print(f"状态: {result.get('status')}")
    print(f"替换次数: {result.get('replacements')}")
    print(f"摘要: {result.get('summary')}")

    # 验证替换是否成功
    print(f"\n{'='*80}")
    print("验证替换结果:")

    content = word_tool.read_all_text(r"D:\溯源\报告模板\2025年11月3日臭氧垂直_test_manual.docx")

    if content:
        if search_text in content:
            print(f"验证结果: 失败 - 原搜索文本仍然存在")
        else:
            if replace_text[:30] in content:
                print(f"验证结果: 成功 - 原搜索文本已被替换")
            else:
                print(f"验证结果: 不确定")
    else:
        print(f"验证结果: 无法读取文档内容")

    print(f"{'='*80}\n")

    return result

if __name__ == "__main__":
    test_replace()
