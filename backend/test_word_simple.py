"""
测试Word替换功能的简化调试脚本
"""

import sys
import os
import shutil
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.tools.office.word_win32_tool import WordWin32Tool


def create_test_doc():
    """创建测试文档"""
    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    doc = word.Documents.Add()
    doc.Content.Text = """测试文档

空气质量数据：
- O3_8h浓度为41 μg/m³
- PM2.5浓度为35 μg/m³
- 臭氧小时峰值56 μg/m³

其他信息：
- 41微克/立方米的浓度值
- 第二个41微克/立方米
- 第三个41微克/立方米
"""
    test_file = r"D:\溯源\backend\test_word.docx"
    doc.SaveAs(test_file)
    doc.Close()
    word.Quit()

    print(f"✅ 创建测试文档: {test_file}")
    return test_file


def read_doc_text(file_path):
    """读取文档内容"""
    tool = WordWin32Tool(visible=False)
    result = tool.read_all_text(file_path)

    if result.get("status") == "success":
        return result.get("text", "")
    else:
        print(f"❌ 读取失败: {result.get('error')}")
        return None


def main():
    print("=" * 80)
    print("Word搜索替换功能测试")
    print("=" * 80)

    # 1. 创建测试文档
    print("\n[步骤1] 创建测试文档...")
    test_file = create_test_doc()

    # 2. 读取原始内容
    print("\n[步骤2] 读取原始内容...")
    original_text = read_doc_text(test_file)
    if not original_text:
        return False

    print(f"原始内容（前300字符）:\n{original_text[:300]}")

    search_text = "41微克/立方米"
    original_count = original_text.count(search_text)
    print(f"\n📊 原始文档中 '{search_text}' 出现次数: {original_count}")

    # 3. 执行搜索替换
    print(f"\n[步骤3] 执行搜索替换...")
    print(f"搜索: '{search_text}' -> 替换为: ''")

    tool = WordWin32Tool(visible=False)
    result = tool.search_and_replace(
        file_path=test_file,
        search_text=search_text,
        replace_text="",
        match_case=False,
        match_whole_word=False,
        use_wildcards=False
    )

    print(f"\n替换结果:")
    print(f"  状态: {result.get('status')}")
    print(f"  replacements: {result.get('replacements')} (类型: {type(result.get('replacements')).__name__})")
    print(f"  output_file: {result.get('output_file')}")
    print(f"  summary: {result.get('summary')}")

    # 4. 等待Word保存
    import time
    print("\n[步骤4] 等待Word进程退出...")
    time.sleep(3)

    # 5. 读取替换后内容
    print("\n[步骤5] 读取替换后内容...")
    new_text = read_doc_text(test_file)
    if not new_text:
        return False

    print(f"替换后内容（前300字符）:\n{new_text[:300]}")

    new_count = new_text.count(search_text)
    print(f"\n📊 替换后文档中 '{search_text}' 出现次数: {new_count}")

    # 6. 对比结果
    print("\n[步骤6] 结果分析...")
    print("=" * 80)

    if new_count == 0:
        print("✅✅✅ 成功！所有目标文本已被删除")
        print(f"   {original_count} -> {new_count}")
        success = True
    elif new_count < original_count:
        print(f"⚠️  部分删除: {original_count - new_count}/{original_count}")
        success = False
    else:
        print("❌❌❌ 文档未被修改！")
        print(f"   {original_count} -> {new_count}")

        # 详细检查
        if original_text == new_text:
            print("\n⚠️  警告: 文档内容完全相同！")
            print(f"   原始长度: {len(original_text)}")
            print(f"   新长度: {len(new_text)}")
            print(f"   差异: {len(original_text) - len(new_text)} 字符")

            # 检查文件是否被修改
            import time
            original_mtime = os.path.getmtime(test_file)
            print(f"   文件修改时间: {time.ctime(original_mtime)}")

        success = False

    # 7. 清理
    print("\n[步骤7] 清理...")
    try:
        if os.path.exists(test_file):
            os.remove(test_file)
        print("✅ 清理完成")
    except Exception as e:
        print(f"⚠️  清理失败: {e}")

    print("=" * 80)
    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
