"""
详细测试 Word 替换功能，添加详细的日志和验证
"""
import asyncio
import shutil
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.tools.office.word_win32_tool import WordWin32Tool
import structlog

# 配置详细的日志
logger = structlog.get_logger()


async def test_replace_with_details():
    """详细测试替换功能"""
    word = WordWin32Tool(visible=False)

    # 测试文件
    test_file = r"D:\溯源\报告模板\2025年11月3日臭氧垂直.docx"
    backup_file = test_file.replace(".docx", "_test_backup.docx")

    # 创建备份
    shutil.copy2(test_file, backup_file)
    print(f"✅ 创建备份: {backup_file}")

    # 步骤1：读取原始内容
    print(f"\n{'='*60}")
    print("步骤1: 读取原始文档内容")
    print(f"{'='*60}\n")

    result_before = word.read_all_text(test_file)
    if result_before['status'] != 'success':
        print(f"❌ 读取失败: {result_before.get('error')}")
        word.close_app()
        return

    text_before = result_before['text']
    search_text = "数据特征分析："

    # 查找目标文本
    if search_text in text_before:
        idx = text_before.find(search_text)
        context_start = max(0, idx - 30)
        context_end = min(len(text_before), idx + 100)
        print(f"✅ 找到目标文本:")
        print(f"   位置: {idx}")
        print(f"   上下文: ...{text_before[context_start:context_end]}...")
    else:
        print(f"❌ 未找到目标文本: '{search_text}'")
        print(f"文档前200字符: {text_before[:200]}")
        word.close_app()
        return

    # 步骤2：执行替换
    print(f"\n{'='*60}")
    print("步骤2: 执行替换操作")
    print(f"{'='*60}\n")

    replace_text = "数据特征分析：2025年11月3日，天气晴，最高气温16.0℃，平均湿度75.6%，风向为南偏西风，平均风速0.8 m/s，紫外线辐射量为162.521 W/m²。空气质量监测数据显示，SO2浓度为4 μg/m³，NO2为23 μg/m³，CO为0.6 mg/m³，O3_8h为34 μg/m³，PM2.5为28 μg/m³，PM10为36 μg/m³，AQI为40，空气质量为优。各项数据均为单日观测值，时间一致，无缺失或异常值。"

    print(f"查找文本: {search_text}")
    print(f"替换文本长度: {len(replace_text)} 字符")
    print(f"替换文本预览: {replace_text[:100]}...")

    result = word.search_and_replace(
        file_path=test_file,
        search_text=search_text,
        replace_text=replace_text,
        match_case=False
    )

    print(f"\n替换结果:")
    print(f"  状态: {result['status']}")
    print(f"  次数: {result.get('replacements', 0)}")
    print(f"  方法: {result.get('metadata', {}).get('method', 'N/A')}")
    print(f"  摘要: {result.get('summary', 'N/A')}")

    if result['status'] == 'failed':
        print(f"  错误: {result.get('error', 'Unknown')}")
        word.close_app()
        return

    # 关闭 Word
    word.close_app()

    # 等待文件完全写入
    import time
    time.sleep(1)

    # 步骤3：重新打开并验证
    print(f"\n{'='*60}")
    print("步骤3: 重新打开文档验证替换结果")
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
    print(f"验证替换结果:")

    # 检查原始文本是否还在
    if search_text in text_after:
        print(f"  ❌ 原始文本仍然存在: '{search_text}'")
        idx = text_after.find(search_text)
        context_start = max(0, idx - 30)
        context_end = min(len(text_after), idx + 100)
        print(f"     上下文: ...{text_after[context_start:context_end]}...")
    else:
        print(f"  ✅ 原始文本已删除")

    # 检查新文本是否存在
    if replace_text in text_after:
        print(f"  ✅ 替换文本已插入")
        idx = text_after.find(replace_text)
        context_start = max(0, idx - 10)
        context_end = min(len(text_after), idx + 150)
        print(f"     替换后内容: {text_after[context_start:context_end]}...")
    else:
        print(f"  ❌ 替换文本未找到")
        print(f"     搜索的文本（前100字符）: {replace_text[:100]}")

        # 检查部分匹配
        partial_search = "2025年11月3日，天气晴"
        if partial_search in text_after:
            print(f"  ⚠️ 找到部分匹配: '{partial_search}'")
            idx = text_after.find(partial_search)
            context_start = max(0, idx - 20)
            context_end = min(len(text_after), idx + 100)
            print(f"     上下文: {text_after[context_start:context_end]}...")

    word2.close_app()

    # 恢复备份
    print(f"\n{'='*60}")
    print("步骤4: 恢复原始文档")
    print(f"{'='*60}\n")

    shutil.copy2(backup_file, test_file)
    Path(backup_file).unlink()
    print(f"✅ 已恢复原始文档")

    print(f"\n{'='*60}")
    print("测试完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(test_replace_with_details())
