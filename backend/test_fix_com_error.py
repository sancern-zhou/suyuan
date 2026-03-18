# -*- coding: utf-8 -*-
"""
测试修复后的替换功能（解决 com_error: 对象已被删除）
"""

import sys
sys.path.insert(0, r'D:\溯源\backend')

from app.tools.office.word_win32_tool import WordWin32Tool

def test_with_contained_search_text():
    """测试替换文本包含完整搜索文本的情况"""
    word_tool = WordWin32Tool()

    # 测试文件
    file_path = r"D:\溯源\报告模板\2025年11月3日臭氧垂直.docx"

    # 测试用例：替换文本以搜索文本开头
    search_text = "臭氧雷达分析："
    # 替换文本以搜索文本开头
    replace_text = """臭氧雷达分析：2025年11月7日臭氧雷达316nm消光系数图显示，整体以蓝绿色为主，代表低消光系数，局部出现黄橙色点状或簇状高值区，集中在图像左侧及底部边缘，可能与局地排放或地表扬尘有关；中部呈现连续垂直条纹，显示背景清洁。臭氧浓度雷达图显示，近地面（0-2 km）浓度普遍较低，呈蓝色与绿色；中高层（2-8 km）存在多条红色至橙色高浓度带，呈波浪状或条带状分布，部分区域出现垂直柱状突起，可能反映对流或锋面输送过程。高浓度层随时间动态演变，部分向上抬升，显示垂直输送特征。整体表明臭氧在中高层存在显著积累，近地面受边界层稀释影响，浓度较低。"""

    print(f"\n{'='*80}")
    print(f"测试：替换文本以搜索文本开头（包含完整搜索文本）")
    print(f"搜索文本: {search_text}")
    print(f"替换文本长度: {len(replace_text)} 字符")
    print(f"替换文本是否包含搜索文本: {search_text in replace_text}")
    print(f"{'='*80}\n")

    try:
        result = word_tool.search_and_replace(
            file_path=file_path,
            search_text=search_text,
            replace_text=replace_text,
            save_as=r"D:\溯源\报告模板\2025年11月3日臭氧垂直_test_fix.docx"
        )

        print(f"\n替换结果:")
        print(f"状态: {result.get('status')}")
        print(f"替换次数: {result.get('replacements')}")
        print(f"摘要: {result.get('summary')}")

        # 验证替换是否成功
        print(f"\n{'='*80}")
        print("验证替换结果:")

        content = word_tool.read_all_text(r"D:\溯源\报告模板\2025年11月3日臭氧垂直_test_fix.docx")

        if content:
            if search_text in content:
                print(f"验证结果: 失败 - 原搜索文本仍然存在")
            else:
                if replace_text[:50] in content:
                    print(f"验证结果: 成功 - 原搜索文本已被替换")
                else:
                    print(f"验证结果: 不确定")
        else:
            print(f"验证结果: 无法读取文档内容")

        print(f"{'='*80}\n")

        return result

    except Exception as e:
        print(f"\n测试失败，异常信息:")
        print(f"{type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_with_contained_search_text()
