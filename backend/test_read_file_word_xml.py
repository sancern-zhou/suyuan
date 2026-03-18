"""
测试 read_file 工具的 Word XML 智能分层功能

使用方法：
1. 确保 defusedxml 已安装：pip install defusedxml
2. 运行测试：python test_read_file_word_xml.py
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.tools.utility.read_file_tool import ReadFileTool


async def test_word_xml_detection():
    """测试 Word XML 检测"""
    print("=" * 60)
    print("测试 1: Word XML 检测")
    print("=" * 60)

    tool = ReadFileTool()

    # 测试用例
    test_cases = [
        ("D:/溯源/unpacked_2025年7月17日臭氧垂直/word/document.xml", True, "有效的 Word XML"),
        ("D:/溯源/test.xml", False, "普通 XML 文件"),
        ("D:/溯源/README.md", False, "Markdown 文件"),
    ]

    for path, expected, description in test_cases:
        result = tool._is_word_xml(Path(path))
        status = "✅" if result == expected else "❌"
        print(f"{status} {description}: {path}")
        print(f"   预期: {expected}, 实际: {result}")
        print()


async def test_word_xml_read_modes():
    """测试 Word XML 三种读取模式"""
    print("=" * 60)
    print("测试 2: Word XML 三种读取模式")
    print("=" * 60)

    tool = ReadFileTool()

    # 测试文件路径（需要实际存在）
    test_file = "D:/溯源/unpacked_2025年7月17日臭氧垂直/word/document.xml"

    if not Path(test_file).exists():
        print(f"⚠️  测试文件不存在: {test_file}")
        print("请先解包一个 Word 文档到上述路径")
        return

    # 模式 1: text 模式（纯文本）
    print("\n--- 模式 1: text（纯文本提取）---")
    result = await tool._extract_text_from_word_xml(
        Path(test_file),
        Path(test_file).stat().st_size,
        max_paragraphs=10  # 限制读取数量以节省输出
    )

    if result['success']:
        data = result['data']
        print(f"✅ 提取成功")
        print(f"   原始大小: {data['original_size']} bytes")
        print(f"   提取大小: {data['extracted_size']} bytes")
        print(f"   压缩率: {data['compression_ratio']}")
        print(f"   段落数: {result['metadata']['paragraph_count']}")
        print(f"\n   内容预览（前200字符）:")
        print(f"   {data['content'][:200]}...")
    else:
        print(f"❌ 提取失败: {result.get('error')}")

    # 模式 2: structured 模式（结构化）
    print("\n--- 模式 2: structured（结构化提取）---")
    result = await tool._extract_structured_from_word_xml(
        Path(test_file),
        Path(test_file).stat().st_size,
        max_paragraphs=10
    )

    if result['success']:
        data = result['data']
        print(f"✅ 提取成功")
        print(f"   原始大小: {data['original_size']} bytes")
        print(f"   提取大小: {data['extracted_size']} bytes")
        print(f"   压缩率: {data['compression_ratio']}")
        print(f"   段落数: {result['metadata']['paragraph_count']}")
        print(f"\n   内容预览（前300字符）:")
        print(f"   {data['content'][:300]}...")
    else:
        print(f"❌ 提取失败: {result.get('error')}")

    # 模式 3: raw 模式（原始 XML）
    print("\n--- 模式 3: raw（原始 XML）---")
    result = await tool._read_raw_word_xml(
        Path(test_file),
        Path(test_file).stat().st_size
    )

    if result['success']:
        data = result['data']
        print(f"✅ 读取成功")
        print(f"   原始大小: {data['size']} bytes")
        print(f"   读取大小: {len(data['content'].encode('utf-8'))} bytes")
        print(f"\n   内容预览（前300字符）:")
        print(f"   {data['content'][:300]}...")
    else:
        print(f"❌ 读取失败: {result.get('error')}")


async def test_auto_mode_selection():
    """测试自动模式选择"""
    print("\n" + "=" * 60)
    print("测试 3: 自动模式选择")
    print("=" * 60)

    tool = ReadFileTool()

    test_file = "D:/溯源/unpacked_2025年7月17日臭氧垂直/word/document.xml"

    if not Path(test_file).exists():
        print(f"⚠️  测试文件不存在: {test_file}")
        return

    # 获取文件大小
    file_size = Path(test_file).stat().st_size
    print(f"\n测试文件大小: {file_size} bytes ({file_size / 1024:.1f} KB)")

    # 测试自动选择（默认参数）
    print("\n--- 自动模式选择（基于文件大小）---")
    result = await tool._read_word_xml(
        Path(test_file),
        file_size
        # 不指定 raw_mode, include_formatting, max_paragraphs
    )

    if result['success']:
        data = result['data']
        print(f"✅ 自动选择成功")
        print(f"   选择模式: {data['mode']}")
        print(f"   内容大小: {data.get('extracted_size', data.get('size'))} bytes")
        print(f"   压缩率: {data.get('compression_ratio', 'N/A')}")
        print(f"\n   选择理由:")
        if file_size < 100_000:
            print(f"   → 文件较小（<100KB），使用 structured 模式保留结构")
        else:
            print(f"   → 文件较大（≥100KB），使用 text 模式节省 tokens")
    else:
        print(f"❌ 自动选择失败: {result.get('error')}")


async def test_parameter_override():
    """测试参数覆盖"""
    print("\n" + "=" * 60)
    print("测试 4: 参数覆盖")
    print("=" * 60)

    tool = ReadFileTool()

    test_file = "D:/溯源/unpacked_2025年7月17日臭氧垂直/word/document.xml"

    if not Path(test_file).exists():
        print(f"⚠️  测试文件不存在: {test_file}")
        return

    # 测试 raw_mode 覆盖
    print("\n--- 覆盖: raw_mode=True ---")
    result = await tool._read_word_xml(
        Path(test_file),
        Path(test_file).stat().st_size,
        raw_mode=True  # 强制使用 raw 模式
    )

    if result['success']:
        data = result['data']
        print(f"✅ 模式覆盖成功: {data['mode']}")
        print(f"   大小: {data['size']} bytes")
    else:
        print(f"❌ 模式覆盖失败: {result.get('error')}")

    # 测试 max_paragraphs 限制
    print("\n--- 覆盖: max_paragraphs=5 ---")
    result = await tool._read_word_xml(
        Path(test_file),
        Path(test_file).stat().st_size,
        include_formatting=True,
        max_paragraphs=5  # 只读取 5 个段落
    )

    if result['success']:
        data = result['data']
        metadata = result['metadata']
        print(f"✅ 段落限制成功")
        print(f"   模式: {data['mode']}")
        print(f"   读取段落数: {metadata['paragraph_count']}")
    else:
        print(f"❌ 段落限制失败: {result.get('error')}")


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("ReadFile 工具 - Word XML 智能分层功能测试")
    print("=" * 60)

    # 检查依赖
    try:
        import defusedxml
        print("✅ defusedxml 已安装")
    except ImportError:
        print("❌ defusedxml 未安装")
        print("请运行: pip install defusedxml")
        return

    await test_word_xml_detection()
    await test_word_xml_read_modes()
    await test_auto_mode_selection()
    await test_parameter_override()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
