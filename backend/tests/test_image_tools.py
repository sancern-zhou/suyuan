"""
测试图片处理工具

测试内容：
1. ReadFileTool - 读取图片文件
2. AnalyzeImageTool - 分析图片内容
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.utility.read_file_tool import ReadFileTool
from app.tools.utility.analyze_image_tool import AnalyzeImageTool
import structlog

# 配置日志
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()


async def test_read_file_tool():
    """测试 ReadFile 工具"""
    print("\n" + "="*60)
    print("测试 1: ReadFile 工具")
    print("="*60)

    tool = ReadFileTool()

    # 测试1：读取文本文件
    print("\n[测试 1.1] 读取文本文件")
    result = await tool.execute(
        path="README.md",
        encoding="utf-8"
    )
    print(f"状态: {result['status']}")
    print(f"摘要: {result.get('summary', 'N/A')}")
    if result.get('success'):
        data = result['data']
        print(f"文件类型: {data['type']}")
        print(f"文件大小: {data['size']} bytes")
        if data['type'] == 'text':
            print(f"内容预览: {data['content'][:200]}...")

    # 测试2：读取不存在的文件
    print("\n[测试 1.2] 读取不存在的文件")
    result = await tool.execute(
        path="nonexistent_file.txt"
    )
    print(f"状态: {result['status']}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    # 测试3：检查工具 schema
    print("\n[测试 1.3] 工具 Function Schema")
    schema = tool.get_function_schema()
    print(f"工具名称: {schema['name']}")
    print(f"必需参数: {schema['parameters']['required']}")
    print(f"可选参数: {list(schema['parameters']['properties'].keys())}")


async def test_analyze_image_tool():
    """测试 AnalyzeImage 工具"""
    print("\n" + "="*60)
    print("测试 2: AnalyzeImage 工具")
    print("="*60)

    tool = AnalyzeImageTool()

    # 测试1：检查工具 schema
    print("\n[测试 2.1] 工具 Function Schema")
    schema = tool.get_function_schema()
    print(f"工具名称: {schema['name']}")
    print(f"必需参数: {schema['parameters']['required']}")
    print(f"可选参数: {list(schema['parameters']['properties'].keys())}")

    # 测试2：分析不存在的图片
    print("\n[测试 2.2] 分析不存在的图片")
    result = await tool.execute(
        path="nonexistent_image.png"
    )
    print(f"状态: {result['status']}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    # 测试3：创建测试图片并分析（如果有测试图片）
    test_image_path = Path("backend_data_registry/test_image.png")
    if test_image_path.exists():
        print(f"\n[测试 2.3] 分析测试图片: {test_image_path}")
        result = await tool.execute(
            path=str(test_image_path),
            operation="describe"
        )
        print(f"状态: {result['status']}")
        print(f"摘要: {result.get('summary', 'N/A')}")
        if result.get('success'):
            print(f"分析结果: {result['data']['analysis'][:200]}...")
    else:
        print(f"\n[测试 2.3] 跳过（测试图片不存在）")
        print(f"提示：可以放置图片到 {test_image_path} 进行测试")


async def test_integration():
    """集成测试：ReadFile + AnalyzeImage"""
    print("\n" + "="*60)
    print("测试 3: 集成测试（ReadFile + AnalyzeImage）")
    print("="*60)

    read_tool = ReadFileTool()
    analyze_tool = AnalyzeImageTool()

    # 检查是否有测试图片
    test_image_path = Path("backend_data_registry/test_image.png")
    if not test_image_path.exists():
        print(f"测试图片不存在: {test_image_path}")
        print("跳过集成测试")
        return

    print(f"\n[步骤 1] 使用 ReadFile 读取图片")
    result = await read_tool.execute(path=str(test_image_path))
    print(f"状态: {result['status']}")
    if result.get('success'):
        print(f"文件类型: {result['data']['type']}")
        print(f"图片格式: {result['data']['format']}")
        print(f"文件大小: {result['data']['size']} bytes")
        print(f"Base64 长度: {len(result['data']['content'])} chars")

    print(f"\n[步骤 2] 使用 AnalyzeImage 分析图片")
    result = await analyze_tool.execute(
        path=str(test_image_path),
        operation="analyze"
    )
    print(f"状态: {result['status']}")
    if result.get('success'):
        print(f"操作类型: {result['data']['operation']}")
        print(f"分析结果: {result['data']['analysis'][:200]}...")


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("图片处理工具测试套件")
    print("="*60)

    try:
        # 测试1：ReadFile 工具
        await test_read_file_tool()

        # 测试2：AnalyzeImage 工具
        await test_analyze_image_tool()

        # 测试3：集成测试
        await test_integration()

        print("\n" + "="*60)
        print("测试完成")
        print("="*60)

    except Exception as e:
        logger.error("test_failed", error=str(e))
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
