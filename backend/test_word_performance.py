"""
测试 Word 操作性能优化

验证：
1. read_all_text 使用 Content.Text + Split()
2. search_and_replace 使用 wdReplaceAll + ScreenUpdating
3. insert_text 使用 ScreenUpdating 保护
"""
import asyncio
import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.tools.office.word_win32_tool import WordWin32Tool
import structlog

logger = structlog.get_logger()


async def test_read_performance():
    """测试 read_all_text 性能"""
    word = WordWin32Tool(visible=False)
    test_file = r"D:\溯源\报告模板\2025年11月2日臭氧垂直.docx"

    print(f"\n{'='*60}")
    print(f"测试 read_all_text 性能优化")
    print(f"测试文件: {test_file}")
    print(f"{'='*60}\n")

    start_time = time.time()
    result = word.read_all_text(test_file)
    elapsed = time.time() - start_time

    print(f"状态: {result['status']}")
    print(f"执行时间: {elapsed:.2f} 秒")
    if result['status'] == 'success':
        print(f"段落数: {result['stats']['paragraph_count']}")
        print(f"字符数: {result['stats']['char_count']}")
        print(f"方法: {result.get('metadata', {}).get('method', 'N/A')}")
    else:
        print(f"错误: {result.get('error', 'Unknown')}")

    word.close_app()


async def test_search_and_replace_performance():
    """测试 search_and_replace 性能"""
    word = WordWin32Tool(visible=False)
    test_file = r"D:\溯源\报告模板\2025年11月2日臭氧垂直.docx"

    print(f"\n{'='*60}")
    print(f"测试 search_and_replace 性能优化")
    print(f"测试文件: {test_file}")
    print(f"{'='*60}\n")

    start_time = time.time()
    result = word.search_and_replace(
        file_path=test_file,
        search_text="数据特征分析：",
        replace_text="数据特征分析：（已优化）",
        match_case=False
    )
    elapsed = time.time() - start_time

    print(f"状态: {result['status']}")
    print(f"执行时间: {elapsed:.2f} 秒")
    print(f"替换次数: {result.get('replacements', 0)}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result['status'] == 'failed':
        print(f"错误: {result.get('error', 'Unknown')}")

    word.close_app()


async def test_insert_performance():
    """测试 insert_text 性能"""
    word = WordWin32Tool(visible=False)
    test_file = r"D:\溯源\报告模板\2025年11月2日臭氧垂直.docx"

    print(f"\n{'='*60}")
    print(f"测试 insert_text 性能优化")
    print(f"测试文件: {test_file}")
    print(f"{'='*60}\n")

    start_time = time.time()
    result = word.insert_text(
        file_path=test_file,
        content="这是测试插入的内容，用于验证 ScreenUpdating 优化效果。",
        position="end"
    )
    elapsed = time.time() - start_time

    print(f"状态: {result['status']}")
    print(f"执行时间: {elapsed:.2f} 秒")
    print(f"插入位置: {result.get('insert_position', 'N/A')}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result['status'] == 'failed':
        print(f"错误: {result.get('error', 'Unknown')}")

    word.close_app()


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("Word 操作性能优化测试套件")
    print("="*60)

    await test_read_performance()
    await test_search_and_replace_performance()
    await test_insert_performance()

    print("\n" + "="*60)
    print("所有测试完成！")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
