"""
测试 Word search_and_replace 的 wdReplaceAll 优化

验证：
1. 替换功能正常工作
2. 执行速度提升
3. 无无限循环风险
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.tools.office.word_win32_tool import WordWin32Tool
import structlog

logger = structlog.get_logger()


async def test_search_and_replace():
    """测试 search_and_replace 功能"""
    import time

    word = WordWin32Tool(visible=False)

    # 测试文件路径（请确保文件存在）
    test_file = r"D:\溯源\报告模板\2025年11月2日臭氧垂直.docx"

    print(f"\n{'='*60}")
    print(f"测试文件: {test_file}")
    print(f"{'='*60}\n")

    # 测试1: 简单替换
    print("测试1: 简单文本替换")
    print("-" * 40)

    start_time = time.time()

    result = word.search_and_replace(
        file_path=test_file,
        search_text="数据特征分析：",
        replace_text="数据特征分析：11月2日成都市城区空气质量监测数据显示，SO2浓度为4 μg/m³。",
        match_case=False,
        match_whole_word=False,
        use_wildcards=False
    )

    elapsed = time.time() - start_time

    print(f"状态: {result['status']}")
    print(f"替换次数: {result.get('replacements', 0)}")
    print(f"执行时间: {elapsed:.2f} 秒")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result['status'] == 'failed':
        print(f"错误: {result.get('error', 'Unknown')}")

    # 测试2: 通配符替换
    print("\n" + "="*60)
    print("测试2: 通配符替换（如果需要）")
    print("-" * 40)

    start_time = time.time()

    result = word.search_and_replace(
        file_path=test_file,
        search_text="*臭氧*",
        replace_text="O3",
        use_wildcards=True
    )

    elapsed = time.time() - start_time

    print(f"状态: {result['status']}")
    print(f"替换次数: {result.get('replacements', 0)}")
    print(f"执行时间: {elapsed:.2f} 秒")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result['status'] == 'failed':
        print(f"错误: {result.get('error', 'Unknown')}")

    print("\n" + "="*60)
    print("测试完成！")
    print("="*60 + "\n")

    # 关闭 Word 应用
    word.close_app()


if __name__ == "__main__":
    asyncio.run(test_search_and_replace())
