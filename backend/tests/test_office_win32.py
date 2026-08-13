"""
Office Win32 工具测试脚本

用于测试 Word、Excel、PowerPoint 自动化功能
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.tools.office import WordWin32Tool, ExcelWin32Tool, PPTWin32Tool


def test_word():
    """测试 Word 工具"""
    print("\n" + "=" * 60)
    print("测试 Word Win32 工具")
    print("=" * 60)

    # 创建一个测试文件路径（请替换为实际路径）
    user_input = input("请输入 Word 文档路径（按回车使用默认）: ").strip()

    # 去除可能的引号
    if user_input:
        test_file = user_input.strip('"').strip("'")
    else:
        # 使用默认路径
        test_file = r"D:\溯源\报告模板\2025年臭氧垂直报告7-ok - 副本.docx"

    print(f"正在尝试打开: {test_file}")

    if not os.path.exists(test_file):
        print(f"\n❌ 文件不存在: {test_file}")
        print("\n提示：")
        print("1. 检查路径是否正确")
        print("2. 不要输入引号")
        print("3. 可以直接复制粘贴文件路径")
        return

    word = WordWin32Tool(visible=False)

    try:
        # 测试1: 读取文档统计
        print("\n[测试1] 读取文档统计信息...")
        result = word.get_document_stats(test_file)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
            print(f"   详细信息: {result['stats']}")
        else:
            print(f"❌ 失败: {result.get('error')}")

        # 测试2: 读取所有文本
        print("\n[测试2] 读取文档内容...")
        result = word.read_all_text(test_file)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
            print(f"   前3段内容:")
            for i, para in enumerate(result['paragraphs'][:3]):
                print(f"   {i+1}. {para[:50]}...")
        else:
            print(f"❌ 失败: {result.get('error')}")

        # 测试3: 读取表格
        print("\n[测试3] 读取文档表格...")
        result = word.read_tables(test_file)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
            if result['tables']:
                print(f"   第一个表格: {result['tables'][0]['rows']}行 x {result['tables'][0]['cols']}列")
        else:
            print(f"❌ 失败: {result.get('error')}")

        # 测试4: 替换文本
        print("\n[测试4] 替换文本...")
        old_text = input("请输入要查找的文本（按回车跳过）: ").strip()
        if old_text:
            new_text = input("请输入替换的文本: ").strip()
            result = word.replace_text(test_file, old_text, new_text, save_as=test_file.replace(".docx", "_modified.docx"))
            if result["status"] == "success":
                print(f"✅ 成功: {result['summary']}")
            else:
                print(f"❌ 失败: {result.get('error')}")
        else:
            print("⏭️  跳过测试")

    finally:
        word.close_app()


def test_excel():
    """测试 Excel 工具"""
    print("\n" + "=" * 60)
    print("测试 Excel Win32 工具")
    print("=" * 60)

    test_file = input("请输入 Excel 文件路径（按回车跳过）: ").strip() or r"D:\test.xlsx"

    if not os.path.exists(test_file):
        print(f"\n文件不存在: {test_file}")
        print("提示：请先创建一个测试文件，或输入正确的路径")
        return

    excel = ExcelWin32Tool(visible=False)

    try:
        # 测试1: 列出工作表
        print("\n[测试1] 列出所有工作表...")
        result = excel.list_sheets(test_file)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
            print(f"   工作表列表: {', '.join(result['sheets'])}")
        else:
            print(f"❌ 失败: {result.get('error')}")
            return

        # 测试2: 读取单元格
        print("\n[测试2] 读取单元格...")
        sheet_name = result['sheets'][0] if result['sheets'] else "Sheet1"
        cell = input(f"请输入要读取的单元格（如 A1，默认: {sheet_name}!A1）: ").strip() or "A1"
        result = excel.read_cell(test_file, sheet_name, cell)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
            print(f"   值: {result['value']}")
        else:
            print(f"❌ 失败: {result.get('error')}")

        # 测试3: 写入单元格
        print("\n[测试3] 写入单元格...")
        write_value = input("请输入要写入的值（按回车跳过）: ").strip()
        if write_value:
            result = excel.write_cell(test_file, sheet_name, cell, write_value, save_as=test_file.replace(".xlsx", "_modified.xlsx"))
            if result["status"] == "success":
                print(f"✅ 成功: {result['summary']}")
            else:
                print(f"❌ 失败: {result.get('error')}")
        else:
            print("⏭️  跳过测试")

    finally:
        excel.close_app()


def test_ppt():
    """测试 PowerPoint 工具"""
    print("\n" + "=" * 60)
    print("测试 PowerPoint Win32 工具")
    print("=" * 60)

    test_file = input("请输入 PowerPoint 文件路径（按回车跳过）: ").strip() or r"D:\test.pptx"

    if not os.path.exists(test_file):
        print(f"\n文件不存在: {test_file}")
        print("提示：请先创建一个测试文件，或输入正确的路径")
        return

    ppt = PPTWin32Tool(visible=False)

    try:
        # 测试1: 列出幻灯片
        print("\n[测试1] 列出所有幻灯片...")
        result = ppt.list_slides(test_file)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
            for slide in result['slides'][:3]:  # 只显示前3张
                print(f"   {slide['index']}. {slide['title']}")
        else:
            print(f"❌ 失败: {result.get('error')}")
            return

        # 测试2: 读取所有文本
        print("\n[测试2] 读取所有文本...")
        result = ppt.read_all_text(test_file)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
        else:
            print(f"❌ 失败: {result.get('error')}")

        # 测试3: 替换文本
        print("\n[测试3] 替换文本...")
        old_text = input("请输入要查找的文本（按回车跳过）: ").strip()
        if old_text:
            new_text = input("请输入替换的文本: ").strip()
            result = ppt.replace_text(test_file, old_text, new_text, save_as=test_file.replace(".pptx", "_modified.pptx"))
            if result["status"] == "success":
                print(f"✅ 成功: {result['summary']}")
            else:
                print(f"❌ 失败: {result.get('error')}")
        else:
            print("⏭️  跳过测试")

    finally:
        ppt.close_app()


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("Office Win32 自动化工具测试")
    print("=" * 60)
    print("\n请选择要测试的组件:")
    print("1. Word")
    print("2. Excel")
    print("3. PowerPoint")
    print("4. 全部测试")
    print("0. 退出")

    while True:
        choice = input("\n请输入选项 (0-4): ").strip()

        if choice == "0":
            print("退出测试")
            break
        elif choice == "1":
            test_word()
        elif choice == "2":
            test_excel()
        elif choice == "3":
            test_ppt()
        elif choice == "4":
            test_word()
            test_excel()
            test_ppt()
        else:
            print("无效选项，请重新输入")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n测试已中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
