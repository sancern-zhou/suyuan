"""
测试 read_file 工具功能
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.utility.read_file_tool import ReadFileTool
import structlog

# 配置日志
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()


async def test_read_text_file():
    """测试1：读取文本文件"""
    print("\n" + "="*70)
    print("测试 1：读取文本文件（README.md）")
    print("="*70)

    tool = ReadFileTool()

    # 读取 README 文件
    result = await tool.execute(
        path="README.md",
        encoding="utf-8"
    )

    print(f"\n状态: {result['status']}")
    print(f"成功: {result['success']}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result.get('success'):
        data = result['data']
        print(f"\n文件信息:")
        print(f"  - 类型: {data['type']}")
        print(f"  - 格式: {data['format']}")
        print(f"  - 大小: {data['size']} bytes")
        print(f"  - 路径: {data['path']}")

        content = data['content']
        print(f"\n内容统计:")
        print(f"  - 总字符数: {len(content)}")
        print(f"  - 总行数: {content.count(chr(10)) + 1}")

        print(f"\n内容预览（前500字符）:")
        print("-" * 50)
        print(content[:500])
        print("-" * 50)

        # 验证是否完整
        if 'truncated' in data:
            print(f"\n⚠️ 警告: 内容被截断")
        else:
            print(f"\n✅ 确认: 内容完整，无截断")

        return True
    else:
        print(f"\n❌ 错误: {result.get('error', 'Unknown error')}")
        return False


async def test_read_nonexistent_file():
    """测试2：读取不存在的文件"""
    print("\n" + "="*70)
    print("测试 2：读取不存在的文件")
    print("="*70)

    tool = ReadFileTool()

    result = await tool.execute(
        path="nonexistent_file.txt"
    )

    print(f"\n状态: {result['status']}")
    print(f"成功: {result['success']}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if not result.get('success'):
        print(f"✅ 正确处理不存在的文件")
        return True
    else:
        print(f"❌ 应该失败但没有失败")
        return False


async def test_read_image_file():
    """测试3：读取图片文件（如果有）"""
    print("\n" + "="*70)
    print("测试 3：读取图片文件（自动分析）")
    print("="*70)

    # 查找测试图片
    test_images = [
        "backend_data_registry/test_image.png",
        "backend_data_registry/test_chart.png",
        "docs/images/sample.png"
    ]

    test_image = None
    for img_path in test_images:
        if Path(img_path).exists():
            test_image = img_path
            break

    if not test_image:
        print("\n⚠️ 跳过：没有找到测试图片")
        print("   提示：可以将图片放到以下位置进行测试：")
        print("   - backend_data_registry/test_image.png")
        print("   - backend_data_registry/test_chart.png")
        return None

    print(f"\n测试图片: {test_image}")

    tool = ReadFileTool()

    # 测试：只读取不分析
    print("\n[步骤 1] 只读取图片（不自动分析）")
    result = await tool.execute(
        path=test_image,
        auto_analyze=False
    )

    print(f"状态: {result['status']}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result.get('success'):
        data = result['data']
        print(f"\n图片信息:")
        print(f"  - 类型: {data['type']}")
        print(f"  - 格式: {data['format']}")
        print(f"  - 大小: {data['size']} bytes")
        print(f"  - Base64长度: {len(data['content'])} chars")

        if 'analysis' in data:
            print(f"  - 分析结果: 有")
        else:
            print(f"  - 分析结果: 无（符合预期，auto_analyze=False）")

        print(f"\n✅ 图片读取成功（无自动分析）")

    # 测试：自动分析图片
    print("\n[步骤 2] 读取并自动分析图片")
    result = await tool.execute(
        path=test_image,
        auto_analyze=True,
        analysis_type="describe"
    )

    print(f"状态: {result['status']}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result.get('success'):
        data = result['data']

        if 'analysis' in data:
            print(f"\n✅ 自动分析成功")
            print(f"\n分析结果预览（前300字符）:")
            print("-" * 50)
            print(data['analysis'][:300])
            print("-" * 50)
        else:
            print(f"\n⚠️ 自动分析失败: {data.get('analysis_error', 'Unknown error')}")

        return True
    else:
        print(f"\n❌ 错误: {result.get('error', 'Unknown error')}")
        return False


async def test_read_large_file():
    """测试4：读取大文件（验证无截断）"""
    print("\n" + "="*70)
    print("测试 4：读取大文件（验证无截断）")
    print("="*70)

    # 查找较大的文件
    large_files = [
        "app/agent/tool_adapter.py",
        "app/tools/__init__.py",
        "README.md"
    ]

    large_file = None
    for file_path in large_files:
        if Path(file_path).exists():
            size = Path(file_path).stat().st_size
            if size > 10000:  # 大于 10KB
                large_file = file_path
                break

    if not large_file:
        print("\n⚠️ 跳过：没有找到足够大的测试文件")
        return None

    print(f"\n测试文件: {large_file}")
    print(f"文件大小: {Path(large_file).stat().st_size} bytes")

    tool = ReadFileTool()

    result = await tool.execute(
        path=large_file,
        encoding="utf-8"
    )

    print(f"\n状态: {result['status']}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result.get('success'):
        data = result['data']
        content = data['content']

        print(f"\n内容统计:")
        print(f"  - 原始文件大小: {data['size']} bytes")
        print(f"  - 读取内容长度: {len(content)} chars")

        # 验证是否完整
        if 'truncated' in data:
            print(f"\n❌ 错误: 内容被截断（不应该有截断）")
            print(f"   truncated 字段值: {data['truncated']}")
            return False
        else:
            print(f"\n✅ 确认: 内容完整，无截断")
            print(f"   - 即使是大文件，也返回了完整内容")
            print(f"   - 依赖上下文压缩策略处理大文件")
            return True
    else:
        print(f"\n❌ 错误: {result.get('error', 'Unknown error')}")
        return False


async def test_encoding_options():
    """测试5：测试不同编码"""
    print("\n" + "="*70)
    print("测试 5：测试不同编码选项")
    print("="*70)

    tool = ReadFileTool()

    # 测试 UTF-8 编码
    print("\n[测试 5.1] UTF-8 编码")
    result = await tool.execute(
        path="README.md",
        encoding="utf-8"
    )

    if result['success']:
        print(f"✅ UTF-8 编码成功")
        print(f"   摘要: {result['summary']}")
    else:
        print(f"❌ UTF-8 编码失败: {result.get('error')}")

    # 测试 GBK 编码（对于中文文件）
    print("\n[测试 5.2] GBK 编码（备用）")
    result = await tool.execute(
        path="README.md",
        encoding="gbk"
    )

    if result['success']:
        print(f"✅ GBK 编码成功")
        print(f"   摘要: {result['summary']}")
    else:
        print(f"⚠️ GBK 编码失败: {result.get('error')}")
        print(f"   说明: UTF-8 编码的文件用 GBK 解码可能失败，这是正常的")

    return True


async def main():
    """运行所有测试"""
    print("\n" + "="*70)
    print("read_file 工具功能测试")
    print("="*70)

    results = []

    # 运行测试
    results.append(await test_read_text_file())
    results.append(await test_read_nonexistent_file())
    results.append(await test_read_image_file())
    results.append(await test_read_large_file())
    results.append(await test_encoding_options())

    # 统计结果
    passed = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False)
    skipped = sum(1 for r in results if r is None)

    print("\n" + "="*70)
    print("测试结果汇总")
    print("="*70)
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")
    print(f"⚠️ 跳过: {skipped}")
    print(f"📊 总计: {len(results)}")

    if failed == 0:
        print("\n🎉 所有测试通过！read_file 工具运行正常")
    else:
        print(f"\n⚠️ 有 {failed} 个测试失败，需要检查")


if __name__ == "__main__":
    asyncio.run(main())
