"""
智能 ReadFile 工具演示

展示自动分析图片功能
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.utility.read_file_tool import ReadFileTool


async def demo_auto_analyze():
    """演示自动分析功能"""
    print("\n" + "="*70)
    print("演示1：自动分析图片（默认行为）")
    print("="*70)

    tool = ReadFileTool()

    # 假设有一张测试图片
    test_image = "backend_data_registry/test_chart.png"

    if not Path(test_image).exists():
        print(f"\n⚠️ 测试图片不存在: {test_image}")
        print("请放置测试图片到该位置后重试")
        return

    print(f"\n读取图片: {test_image}")
    print("预期行为：自动调用 Vision API 分析图片内容\n")

    result = await tool.execute(path=test_image)

    print(f"状态: {result['status']}")
    print(f"摘要: {result['summary']}")

    if result['success'] and 'analysis' in result['data']:
        print(f"\n✅ 自动分析结果:")
        print(f"{result['data']['analysis'][:300]}...")


async def demo_ocr_mode():
    """演示 OCR 模式"""
    print("\n" + "="*70)
    print("演示2：OCR 文字识别模式")
    print("="*70)

    tool = ReadFileTool()

    test_image = "backend_data_registry/test_document.png"

    if not Path(test_image).exists():
        print(f"\n⚠️ 测试图片不存在: {test_image}")
        print("请放置测试图片到该位置后重试")
        return

    print(f"\n读取图片（OCR模式）: {test_image}")
    print("预期行为：提取图片中的所有文字\n")

    result = await tool.execute(
        path=test_image,
        analysis_type="ocr"
    )

    print(f"状态: {result['status']}")
    print(f"摘要: {result['summary']}")

    if result['success'] and 'analysis' in result['data']:
        print(f"\n✅ OCR 识别结果:")
        print(f"{result['data']['analysis'][:300]}...")


async def demo_no_auto_analyze():
    """演示关闭自动分析"""
    print("\n" + "="*70)
    print("演示3：关闭自动分析")
    print("="*70)

    tool = ReadFileTool()

    test_image = "backend_data_registry/test_image.png"

    if not Path(test_image).exists():
        print(f"\n⚠️ 测试图片不存在: {test_image}")
        print("请放置测试图片到该位置后重试")
        return

    print(f"\n读取图片（不自动分析）: {test_image}")
    print("预期行为：只返回图片 base64 数据，不调用 Vision API\n")

    result = await tool.execute(
        path=test_image,
        auto_analyze=False
    )

    print(f"状态: {result['status']}")
    print(f"摘要: {result['summary']}")
    print(f"图片格式: {result['data']['format']}")
    print(f"文件大小: {result['data']['size']} bytes")
    print(f"Base64长度: {len(result['data']['content'])} chars")

    if 'analysis' in result['data']:
        print(f"\n⚠️ 意外：包含分析结果")
    else:
        print(f"\n✅ 确认：未调用自动分析")


async def demo_chart_analysis():
    """演示图表分析"""
    print("\n" + "="*70)
    print("演示4：图表数据分析")
    print("="*70)

    tool = ReadFileTool()

    test_image = "backend_data_registry/test_plot.png"

    if not Path(test_image).exists():
        print(f"\n⚠️ 测试图片不存在: {test_image}")
        print("请放置测试图片到该位置后重试")
        return

    print(f"\n读取图片（图表分析）: {test_image}")
    print("预期行为：提取图表中的数据、趋势、坐标轴等信息\n")

    result = await tool.execute(
        path=test_image,
        analysis_type="chart"
    )

    print(f"状态: {result['status']}")
    print(f"摘要: {result['summary']}")

    if result['success'] and 'analysis' in result['data']:
        print(f"\n✅ 图表分析结果:")
        print(f"{result['data']['analysis'][:300]}...")


async def demo_text_file():
    """演示读取文本文件（不受影响）"""
    print("\n" + "="*70)
    print("演示5：读取文本文件（保持原有功能）")
    print("="*70)

    tool = ReadFileTool()

    # 读取 README 文件
    print(f"\n读取文本文件: README.md")
    print("预期行为：返回文本内容，不触发图片分析\n")

    result = await tool.execute(path="README.md")

    print(f"状态: {result['status']}")
    print(f"摘要: {result['summary']}")
    print(f"文件类型: {result['data']['type']}")
    print(f"内容预览: {result['data']['content'][:200]}...")


async def demo_comparison():
    """对比传统方式 vs 新方式"""
    print("\n" + "="*70)
    print("演示6：传统方式 vs 新方式对比")
    print("="*70)

    print("\n【传统方式】（需要 LLM 多次调用）")
    print("""
步骤1: read_file(path="chart.png")
       → 返回 base64 数据

步骤2: LLM 看到 base64，判断是图片
       → 调用 analyze_image(path="chart.png")

步骤3: analyze_image 返回分析结果
       → LLM 整合回复用户

总调用次数: 2-3 次
    """)

    print("\n【新方式】（自动分析）")
    print("""
步骤1: read_file(path="chart.png")
       → 自动检测到图片
       → 自动调用 analyze_image
       → 返回图片数据 + 分析结果

步骤2: LLM 直接使用分析结果回复用户

总调用次数: 1 次 ✅
    """)

    print("\n【优势】")
    print("✅ 减少调用次数")
    print("✅ 简化 LLM 决策逻辑")
    print("✅ 提升交互效率")
    print("✅ 保持工具职责清晰（ReadFile 调用 AnalyzeImage）")


async def main():
    """运行所有演示"""
    print("\n" + "="*70)
    print("智能 ReadFile 工具演示")
    print("="*70)

    await demo_auto_analyze()
    await demo_ocr_mode()
    await demo_no_auto_analyze()
    await demo_chart_analysis()
    await demo_text_file()
    await demo_comparison()

    print("\n" + "="*70)
    print("演示完成")
    print("="*70)

    print("\n使用建议:")
    print("1. 默认使用 read_file(path='xxx.png') 自动分析")
    print("2. 需要特定分析类型时指定: analysis_type='ocr'")
    print("3. 只读取图片不分析时: auto_analyze=False")
    print("4. 文本文件使用不受影响，行为保持不变")


if __name__ == "__main__":
    asyncio.run(main())
