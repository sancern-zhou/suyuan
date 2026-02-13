"""
测试 Word search_and_replace 修复

验证修复：设置 Replacement.Text 后，替换是否真正生效
"""
import asyncio
import shutil
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.tools.office.word_win32_tool import WordWin32Tool
import structlog

logger = structlog.get_logger()


async def test_search_and_replace_fix():
    """测试 search_and_replace 修复"""
    word = WordWin32Tool(visible=False)

    # 原始文件
    original_file = r"D:\溯源\报告模板\2025年11月2日臭氧垂直.docx"
    # 创建测试副本
    test_file = r"D:\溯源\报告模板\test_replace_fix.docx"

    # 复制文件
    shutil.copy2(original_file, test_file)
    print(f"✅ 创建测试副本: {test_file}")

    # 读取原始内容
    result_before = word.read_all_text(test_file)
    if result_before['status'] == 'success':
        text_before = result_before['text']
        print(f"\n原始文本片段（前200字符）:")
        print(text_before[:200])
    else:
        print(f"❌ 读取失败: {result_before.get('error')}")
        word.close_app()
        return

    # 执行替换
    print(f"\n{'='*60}")
    print("执行替换操作...")
    print(f"{'='*60}\n")

    result = word.search_and_replace(
        file_path=test_file,
        search_text="数据特征分析：",
        replace_text="【已替换】数据特征分析：",
        match_case=False
    )

    print(f"替换状态: {result['status']}")
    print(f"替换次数: {result.get('replacements', 0)}")
    print(f"摘要: {result.get('summary', 'N/A')}")

    if result['status'] == 'failed':
        print(f"错误: {result.get('error', 'Unknown')}")
        word.close_app()
        return

    # 读取替换后的内容
    result_after = word.read_all_text(test_file)
    if result_after['status'] == 'success':
        text_after = result_after['text']
        print(f"\n替换后文本片段（前200字符）:")
        print(text_after[:200])

        # 验证替换是否生效
        if "【已替换】数据特征分析：" in text_after:
            print(f"\n✅ 替换成功！文本已修改")
        else:
            print(f"\n❌ 替换失败！文本未修改")
            print(f"原始文本包含'数据特征分析：': {'数据特征分析：' in text_before}")
            print(f"替换后文本包含'【已替换】': {'【已替换】' in text_after}")
    else:
        print(f"❌ 读取失败: {result_after.get('error')}")

    word.close_app()

    # 清理测试文件
    try:
        Path(test_file).unlink()
        print(f"\n✅ 清理测试文件: {test_file}")
    except:
        print(f"\n⚠️ 无法清理测试文件: {test_file}")


if __name__ == "__main__":
    asyncio.run(test_search_and_replace_fix())
