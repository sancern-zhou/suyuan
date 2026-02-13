# -*- coding: utf-8 -*-
"""
测试手动循环替换方法（完全使用 Delete + InsertAfter）
不依赖 wdReplaceAll，避免其 bug
"""

import sys
sys.path.insert(0, r'D:\溯源\backend')

from app.tools.office.word_win32_tool import WordWin32Tool
import structlog

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

def test_replace_with_search_text_in_replace_text():
    """测试替换文本包含搜索文本的情况（使用占位符策略）"""
    word_tool = WordWin32Tool()

    # 测试文件
    file_path = r"D:\溯源\报告模板\2025年11月3日臭氧垂直.docx"

    # 测试用例：替换文本包含搜索文本
    # search_text = "臭氧雷达分析："
    # replace_text 包含 "臭氧雷达" 会被检测到

    search_text = "臭氧雷达分析："
    replace_text = """臭氧雷达316nm消光系数图显示多个短时高能量脉冲与持续频率成分，呈现周期性波动特征，可能反映局部声波或湍流结构对激光路径的影响，这种波动特征通常与边界层内不均匀分布有关。波长355nm消光系数图能量分布相对较低，表明在该波长下气溶胶散射效应显著减弱。波长532nm消光系数图记录到高浓度粒子层，特别是探测到多层气溶胶垂直分层结构，这些分层可能与不同高度的污染源输送过程密切相关。波长1064nm消光系数图对大粒径粒子响应强，适合观测粗模态气溶胶分布，图中清晰显示粗模态粒子主要集中在近地面层，随着高度增加浓度迅速下降，这符合重力沉降对粗模态气溶胶的影响规律。偏振成像雷达图通过探测粒子形状信息，能够区分球形和非球形粒子，为判断气溶胶类型提供重要依据。雷达比图显示不同高度层的雷达比值变化，为反演气溶胶微物理特性提供关键参数。"""

    print(f"\n{'='*80}")
    print(f"测试用例：替换文本包含搜索文本")
    print(f"搜索文本: {search_text}")
    print(f"替换文本长度: {len(replace_text)} 字符")
    print(f"替换文本是否包含搜索文本: {search_text in replace_text}")
    print(f"{'='*80}\n")

    result = word_tool.search_and_replace(
        file_path=file_path,
        search_text=search_text,
        replace_text=replace_text,
        save_as=r"D:\溯源\报告模板\2025年11月3日臭氧垂直_test.docx"
    )

    print(f"\n替换结果:")
    print(f"状态: {result.get('status')}")
    print(f"替换次数: {result.get('replacements')}")
    print(f"输出文件: {result.get('output_file')}")
    print(f"摘要: {result.get('summary')}")

    # 验证替换是否成功
    print(f"\n{'='*80}")
    print("验证替换结果:")

    # 读取替换后的文档
    word_tool_verify = WordWin32Tool()
    content = word_tool_verify.read_all_text(r"D:\溯源\报告模板\2025年11月3日臭氧垂直_test.docx")

    if content:
        if search_text in content:
            print(f"验证结果: 失败 - 原搜索文本仍然存在")
            print(f"原文本 '{search_text}' 未被替换")
        else:
            # 检查替换文本是否存在（至少部分）
            if replace_text[:50] in content:
                print(f"验证结果: 成功 - 原搜索文本已被替换")
                print(f"替换文本的前50个字符已找到")
            else:
                print(f"验证结果: 不确定 - 原搜索文本不存在，但替换文本也未找到")
    else:
        print(f"验证结果: 无法读取文档内容")

    print(f"{'='*80}\n")

    return result

def test_replace_without_search_text_in_replace_text():
    """测试替换文本不包含搜索文本的情况（直接手动循环）"""
    word_tool = WordWin32Tool()

    # 测试文件
    file_path = r"D:\溯源\报告模板\2025年11月3日臭氧垂直.docx"

    # 测试用例：替换文本不包含搜索文本
    search_text = "小结："
    replace_text = """本次观测共完成24次垂直探测，累计获取海拔高度12公里范围内的大气气溶胶垂直分布数据，探测结果显示该区域气溶胶主要集中在1500米以下边界层内，占总浓度的75%以上。波长532nm消光系数在500米高度出现最大值，达到0.35/km，表明该高度存在高浓度气溶胶层。波长1064nm消光系数垂直廓线显示粗模态粒子主要集中在近地面层，随着高度增加浓度迅速下降，符合重力沉降对粗模态气溶胶的影响规律。偏振成像雷达探测到非球形粒子主要集中在2000-3000米高度范围，可能与高空沙尘输送有关。"""

    print(f"\n{'='*80}")
    print(f"测试用例：替换文本不包含搜索文本")
    print(f"搜索文本: {search_text}")
    print(f"替换文本长度: {len(replace_text)} 字符")
    print(f"替换文本是否包含搜索文本: {search_text in replace_text}")
    print(f"{'='*80}\n")

    result = word_tool.search_and_replace(
        file_path=file_path,
        search_text=search_text,
        replace_text=replace_text,
        save_as=r"D:\溯源\报告模板\2025年11月3日臭氧垂直_test2.docx"
    )

    print(f"\n替换结果:")
    print(f"状态: {result.get('status')}")
    print(f"替换次数: {result.get('replacements')}")
    print(f"输出文件: {result.get('output_file')}")
    print(f"摘要: {result.get('summary')}")

    # 验证替换是否成功
    print(f"\n{'='*80}")
    print("验证替换结果:")

    # 读取替换后的文档
    word_tool_verify = WordWin32Tool()
    content = word_tool_verify.read_all_text(r"D:\溯源\报告模板\2025年11月3日臭氧垂直_test2.docx")

    if content:
        if search_text in content:
            print(f"验证结果: 失败 - 原搜索文本仍然存在")
            print(f"原文本 '{search_text}' 未被替换")
        else:
            # 检查替换文本是否存在（至少部分）
            if replace_text[:50] in content:
                print(f"验证结果: 成功 - 原搜索文本已被替换")
                print(f"替换文本的前50个字符已找到")
            else:
                print(f"验证结果: 不确定 - 原搜索文本不存在，但替换文本也未找到")
    else:
        print(f"验证结果: 无法读取文档内容")

    print(f"{'='*80}\n")

    return result

if __name__ == "__main__":
    print("\n" + "="*80)
    print("手动循环替换方法测试")
    print("="*80)

    # 测试1：替换文本包含搜索文本
    print("\n[测试 1/2] 替换文本包含搜索文本（使用占位符策略）")
    test_replace_with_search_text_in_replace_text()

    # 测试2：替换文本不包含搜索文本
    print("\n[测试 2/2] 替换文本不包含搜索文本（直接手动循环）")
    test_replace_without_search_text_in_replace_text()

    print("\n" + "="*80)
    print("所有测试完成")
    print("="*80)
