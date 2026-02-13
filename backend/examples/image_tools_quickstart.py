"""
图片处理工具 - 快速开始示例

演示如何使用 read_file 和 analyze_image 工具
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.utility.read_file_tool import ReadFileTool
from app.tools.utility.analyze_image_tool import AnalyzeImageTool


async def example_1_read_text_file():
    """示例1：读取文本文件"""
    print("\n" + "="*60)
    print("示例1：读取文本文件")
    print("="*60)

    tool = ReadFileTool()

    # 读取README文件
    result = await tool.execute(
        path="README.md",
        encoding="utf-8"
    )

    if result['success']:
        print("✅ 成功读取文件")
        print(f"文件类型: {result['data']['type']}")
        print(f"文件大小: {result['data']['size']} bytes")
        print(f"内容预览: {result['data']['content'][:200]}...")
    else:
        print(f"❌ 读取失败: {result.get('error')}")


async def example_2_read_image_file():
    """示例2：读取图片文件"""
    print("\n" + "="*60)
    print("示例2：读取图片文件")
    print("="*60)

    tool = ReadFileTool()

    # 假设有一张测试图片
    test_image = "backend_data_registry/test_image.png"

    # 检查文件是否存在
    if not Path(test_image).exists():
        print(f"⚠️ 测试图片不存在: {test_image}")
        print("提示：可以放置图片到该位置进行测试")
        return

    result = await tool.execute(path=test_image)

    if result['success']:
        print("✅ 成功读取图片")
        print(f"图片格式: {result['data']['format']}")
        print(f"文件大小: {result['data']['size']} bytes")
        print(f"Base64长度: {len(result['data']['content'])} chars")
    else:
        print(f"❌ 读取失败: {result.get('error')}")


async def example_3_analyze_image_ocr():
    """示例3：OCR文字识别"""
    print("\n" + "="*60)
    print("示例3：OCR文字识别")
    print("="*60)

    tool = AnalyzeImageTool()

    # 假设有一张包含文字的图片
    test_image = "backend_data_registry/test_document.png"

    if not Path(test_image).exists():
        print(f"⚠️ 测试图片不存在: {test_image}")
        print("提示：可以放置图片到该位置进行测试")
        return

    result = await tool.execute(
        path=test_image,
        operation="ocr"
    )

    if result['success']:
        print("✅ OCR识别成功")
        print(f"识别结果: {result['data']['analysis'][:200]}...")
    else:
        print(f"❌ 识别失败: {result.get('error')}")


async def example_4_analyze_chart():
    """示例4：分析图表"""
    print("\n" + "="*60)
    print("示例4：分析数据图表")
    print("="*60)

    tool = AnalyzeImageTool()

    # 假设有一张数据图表
    test_image = "backend_data_registry/test_chart.png"

    if not Path(test_image).exists():
        print(f"⚠️ 测试图片不存在: {test_image}")
        print("提示：可以放置图片到该位置进行测试")
        return

    result = await tool.execute(
        path=test_image,
        operation="chart"
    )

    if result['success']:
        print("✅ 图表分析成功")
        print(f"分析结果: {result['data']['analysis'][:200]}...")
    else:
        print(f"❌ 分析失败: {result.get('error')}")


async def example_5_custom_prompt():
    """示例5：自定义分析提示词"""
    print("\n" + "="*60)
    print("示例5：自定义分析提示词")
    print("="*60)

    tool = AnalyzeImageTool()

    test_image = "backend_data_registry/test_image.png"

    if not Path(test_image).exists():
        print(f"⚠️ 测试图片不存在: {test_image}")
        print("提示：可以放置图片到该位置进行测试")
        return

    result = await tool.execute(
        path=test_image,
        operation="analyze",
        prompt="请详细描述这张图片中的颜色、布局、主要对象，并给出你的理解。"
    )

    if result['success']:
        print("✅ 自定义分析成功")
        print(f"分析结果: {result['data']['analysis'][:200]}...")
    else:
        print(f"❌ 分析失败: {result.get('error')}")


async def example_6_list_images():
    """示例6：列出工作目录中的图片文件"""
    print("\n" + "="*60)
    print("示例6：列出工作目录中的图片文件")
    print("="*60)

    from app.tools.utility.bash_tool import BashTool

    tool = BashTool()

    # 列出所有PNG图片
    result = await tool.execute(
        command="dir D:\\溯源\\backend_data_registry\\*.png /b"
    )

    if result['success']:
        print("✅ 找到以下图片文件:")
        files = result['data']['stdout'].strip()
        if files:
            for line in files.split('\n')[:10]:  # 只显示前10个
                print(f"  - {line}")
            if len(files.split('\n')) > 10:
                print(f"  ... 还有 {len(files.split('\n')) - 10} 个文件")
        else:
            print("  (没有找到PNG图片)")
    else:
        print(f"❌ 列出文件失败: {result.get('error')}")


async def main():
    """运行所有示例"""
    print("\n" + "="*60)
    print("图片处理工具 - 快速开始示例")
    print("="*60)

    # 运行示例
    await example_1_read_text_file()
    await example_2_read_image_file()
    await example_3_analyze_image_ocr()
    await example_4_analyze_chart()
    await example_5_custom_prompt()
    await example_6_list_images()

    print("\n" + "="*60)
    print("示例运行完成")
    print("="*60)
    print("\n提示：")
    print("1. 将测试图片放置到 backend_data_registry/ 目录")
    print("2. 运行此脚本查看效果")
    print("3. 查看 backend/docs/image_tools_guide.md 了解更多用法")


if __name__ == "__main__":
    asyncio.run(main())
