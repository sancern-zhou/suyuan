"""
调试 Word 替换功能

直接读取文档，执行替换，然后验证是否真的修改了文档
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


async def debug_replace():
    """调试替换功能"""
    word = WordWin32Tool(visible=False)

    # 测试文件
    test_file = r"D:\溯源\报告模板\2025年11月3日臭氧垂直.docx"

    # 先创建备份
    backup_file = test_file.replace(".docx", "_backup.docx")
    shutil.copy2(test_file, backup_file)
    print(f"✅ 创建备份: {backup_file}")

    # 读取原始内容
    print(f"\n{'='*60}")
    print("步骤1: 读取原始文档")
    print(f"{'='*60}\n")

    result_before = word.read_all_text(test_file)
    if result_before['status'] != 'success':
        print(f"❌ 读取失败: {result_before.get('error')}")
        word.close_app()
        return

    text_before = result_before['text']

    # 查找目标文本
    search_text = "数据特征分析："
    if search_text in text_before:
        print(f"✅ 找到目标文本: '{search_text}'")
        # 显示前后文
        idx = text_before.find(search_text)
        context_start = max(0, idx - 50)
        context_end = min(len(text_before), idx + 100)
        print(f"上下文: ...{text_before[context_start:context_end]}...")
    else:
        print(f"⚠️ 未找到目标文本: '{search_text}'")
        print(f"文档中包含的文本片段: {text_before[:200]}...")

    # 执行替换
    print(f"\n{'='*60}")
    print("步骤2: 执行替换操作")
    print(f"{'='*60}\n")

    replace_text = "数据特征分析：2025年11月3日，天气晴，最高气温16.0℃，平均湿度75.6%RH，风向为南偏西风，平均风速1.2 m/s。"
    print(f"查找文本: {search_text}")
    print(f"替换文本: {replace_text}")
    print(f"替换文本长度: {len(replace_text)} 字符")

    result = word.search_and_replace(
        file_path=test_file,
        search_text=search_text,
        replace_text=replace_text,
        match_case=False
    )

    print(f"\n替换结果:")
    print(f"  状态: {result['status']}")
    print(f"  次数: {result.get('replacements', 0)}")
    print(f"  摘要: {result.get('summary', 'N/A')}")

    if result['status'] == 'failed':
        print(f"  错误: {result.get('error', 'Unknown')}")

    # 关闭 Word（确保文件释放）
    word.close_app()

    # 重新打开读取内容
    print(f"\n{'='*60}")
    print("步骤3: 验证替换结果（重新打开文档）")
    print(f"{'='*60}\n")

    # 创建新的 Word 实例
    word2 = WordWin32Tool(visible=False)

    result_after = word2.read_all_text(test_file)
    if result_after['status'] != 'success':
        print(f"❌ 读取失败: {result_after.get('error')}")
        word2.close_app()
        return

    text_after = result_after['text']

    # 验证替换
    if replace_text in text_after:
        print(f"✅ 替换成功！找到替换后的文本")
        idx = text_after.find(replace_text)
        context_start = max(0, idx - 20)
        context_end = min(len(text_after), idx + 150)
        print(f"替换后内容: {text_after[context_start:context_end]}...")
    else:
        print(f"❌ 替换失败！未找到替换后的文本")

        # 检查原始文本是否还在
        if search_text in text_after:
            print(f"原始文本仍然存在: '{search_text}'")
        else:
            print(f"原始文本也不见了（可能被删除了）")

        # 显示文档前500字符
        print(f"\n文档前500字符:")
        print(text_after[:500])

    word2.close_app()

    # 恢复备份
    print(f"\n{'='*60}")
    print("步骤4: 恢复备份")
    print(f"{'='*60}\n")

    shutil.copy2(backup_file, test_file)
    Path(backup_file).unlink()
    print(f"✅ 已恢复原始文档")


if __name__ == "__main__":
    asyncio.run(debug_replace())
