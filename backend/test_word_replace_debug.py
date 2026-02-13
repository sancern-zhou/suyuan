"""
测试Word替换功能的调试脚本

目的：验证word_processor工具的搜索替换功能是否真正保存了文档
"""

import sys
import os
import shutil
from pathlib import Path
import structlog

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.tools.office.word_win32_tool import WordWin32Tool
from app.tools.office.word_tool import WordWin32LLMTool
import asyncio

logger = structlog.get_logger()


def create_test_document():
    """创建测试Word文档"""
    try:
        import win32com.client

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False

        doc = word.Documents.Add()

        # 添加测试内容
        content = """
测试文档 - 原始数据

空气质量状况：
- O3_8h浓度为41 μg/m³
- PM2.5浓度为35 μg/m³
- 臭氧小时峰值达56 μg/m³

其他信息：
- 41微克/立方米的浓度值需要关注
- 第二个41微克/立方米出现在第5段
- 第三个41微克/立方米在表格中
"""
        doc.Content.Text = content

        test_file = r"D:\溯源\backend\test_replace_original.docx"
        doc.SaveAs(test_file)
        doc.Close()
        word.Quit()

        logger.info("test_document_created", file=test_file)
        return test_file

    except Exception as e:
        logger.error("create_test_document_failed", error=str(e), exc_info=True)
        return None


def read_document_text(file_path):
    """读取文档文本内容"""
    try:
        word_tool = WordWin32Tool(visible=False)
        result = word_tool.read_all_text(file_path)

        if result.get("status") == "success":
            return result.get("text", "")
        else:
            logger.error("read_document_failed", error=result.get("error"))
            return None

    except Exception as e:
        logger.error("read_document_exception", error=str(e), exc_info=True)
        return None


def test_search_and_replace():
    """测试搜索替换功能"""
    print("=" * 80)
    print("开始测试Word搜索替换功能")
    print("=" * 80)

    # 1. 创建测试文档
    print("\n[步骤1] 创建测试文档...")
    test_file = create_test_document()
    if not test_file:
        print("❌ 创建测试文档失败")
        return False

    # 2. 创建备份
    backup_file = test_file.replace(".docx", "_backup.docx")
    shutil.copy(test_file, backup_file)
    print(f"✅ 创建备份: {backup_file}")

    # 3. 读取原始内容
    print(f"\n[步骤2] 读取原始文档内容...")
    original_text = read_document_text(test_file)
    if original_text is None:
        print("❌ 读取原始文档失败")
        return False

    print(f"✅ 原始文档内容（前500字符）:")
    print("-" * 80)
    print(original_text[:500])
    print("-" * 80)

    # 统计目标文本出现次数
    search_text = "41微克/立方米"
    count = original_text.count(search_text)
    print(f"\n📊 原始文档中 '{search_text}' 出现次数: {count}")

    # 4. 执行搜索替换
    print(f"\n[步骤3] 执行搜索替换操作...")
    print(f"搜索文本: '{search_text}'")
    print(f"替换为: '' (删除)")

    word_tool = WordWin32Tool(visible=False)

    try:
        result = word_tool.search_and_replace(
            file_path=test_file,
            search_text=search_text,
            replace_text="",
            match_case=False,
            match_whole_word=False,
            use_wildcards=False
        )

        print(f"\n📋 替换结果:")
        print(f"  - 状态: {result.get('status')}")
        print(f"  - 返回的替换次数(replacements): {result.get('replacements')}")
        print(f"  - 返回值类型: {type(result.get('replacements'))}")
        print(f"  - 匹配项: {result.get('matches')}")
        print(f"  - 输出文件: {result.get('output_file')}")
        print(f"  - 摘要: {result.get('summary')}")

    except Exception as e:
        logger.error("search_and_replace_exception", error=str(e), exc_info=True)
        print(f"❌ 搜索替换异常: {e}")
        return False

    # 5. 等待Word进程完全退出
    print("\n[步骤4] 等待Word进程退出...")
    import time
    time.sleep(2)

    # 6. 读取替换后的内容
    print(f"\n[步骤5] 读取替换后的文档内容...")
    new_text = read_document_text(test_file)
    if new_text is None:
        print("❌ 读取替换后文档失败")
        return False

    print(f"✅ 替换后文档内容（前500字符）:")
    print("-" * 80)
    print(new_text[:500])
    print("-" * 80)

    # 统计替换后的出现次数
    new_count = new_text.count(search_text)
    print(f"\n📊 替换后文档中 '{search_text}' 出现次数: {new_count}")

    # 7. 对比结果
    print(f"\n[步骤6] 对比分析...")
    print("=" * 80)

    if new_count == 0:
        print("✅✅✅ 成功！所有 '{search_text}' 已被删除")
        print(f"   原始次数: {count} → 替换后次数: {new_count}")
        success = True
    elif new_count < count:
        print(f"⚠️  部分成功: {count - new_count}/{count} 处被删除")
        print(f"   原始次数: {count} → 替换后次数: {new_count}")
        success = False
    else:
        print("❌❌❌ 失败！文档未被修改")
        print(f"   原始次数: {count} → 替换后次数: {new_count}")
        success = False

    # 8. 详细对比
    if original_text != new_text:
        print("\n📝 文档内容发生了变化:")
        print(f"   原始长度: {len(original_text)} 字符")
        print(f"   新长度: {len(new_text)} 字符")
        print(f"   差异: {len(original_text) - len(new_text)} 字符")
    else:
        print("\n⚠️  警告: 文档内容完全相同，可能未真正保存！")

    # 9. 测试LLMTool包装器
    print(f"\n[步骤7] 测试LLMTool包装器...")

    async def test_llm_tool():
        llm_tool = WordWin32LLMTool()

        try:
            # 恢复备份
            shutil.copy(backup_file, test_file)

            llm_result = await llm_tool.execute(
                file_path=test_file,
                operation="search_and_replace",
                search_text=search_text,
                replace_text=""
            )

        print(f"📋 LLMTool结果:")
        print(f"  - 状态: {llm_result.get('status')}")
        print(f"  - 成功: {llm_result.get('success')}")
        print(f"  - 摘要: {llm_result.get('summary')}")

        # 读取LLMTool操作后的内容
        llm_text = read_document_text(test_file)
        if llm_text:
            llm_count = llm_text.count(search_text)
            print(f"  - LLMTool操作后 '{search_text}' 出现次数: {llm_count}")

        except Exception as e:
            logger.error("llm_tool_test_failed", error=str(e), exc_info=True)
            print(f"❌ LLMTool测试失败: {e}")

    # 运行异步测试
    import asyncio
    asyncio.run(test_llm_tool())

    # 10. 清理
    print(f"\n[步骤8] 清理测试文件...")
    try:
        if os.path.exists(test_file):
            os.remove(test_file)
        if os.path.exists(backup_file):
            os.remove(backup_file)
        print("✅ 清理完成")
    except Exception as e:
        print(f"⚠️  清理失败: {e}")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

    return success


if __name__ == "__main__":
    try:
        success = test_search_and_replace()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error("test_failed", error=str(e), exc_info=True)
        print(f"\n❌ 测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
