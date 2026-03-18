"""
Office Win32 工具快速测试

自动测试现有的 Office 文件
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

    # 测试文件路径
    test_file = r"D:\溯源\报告模板\2025年臭氧垂直报告7-ok - 副本.docx"

    print(f"测试文件: {test_file}")

    if not os.path.exists(test_file):
        print(f"\n❌ 文件不存在: {test_file}")
        print("\n当前目录下的 .docx 文件:")

        # 列出报告模板目录下的文件
        template_dir = r"D:\溯源\报告模板"
        if os.path.exists(template_dir):
            files = [f for f in os.listdir(template_dir) if f.endswith('.docx')]
            for f in files[:5]:  # 只显示前5个
                print(f"  - {f}")
        return

    print("✅ 文件存在，开始测试...\n")

    word = WordWin32Tool(visible=False)

    try:
        # 测试1: 读取文档统计
        print("[测试1] 读取文档统计信息...")
        result = word.get_document_stats(test_file)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
            stats = result['stats']
            print(f"   页数: {stats['pages']}")
            print(f"   字数: {stats['words']}")
            print(f"   段落数: {stats['paragraphs']}")
            print(f"   表格数: {stats['tables']}")
        else:
            print(f"❌ 失败: {result.get('error')}")

        # 测试2: 读取所有文本
        print("\n[测试2] 读取文档内容...")
        result = word.read_all_text(test_file)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
            paragraphs = result.get('paragraphs', [])
            print(f"   前3段内容:")
            for i, para in enumerate(paragraphs[:3]):
                preview = para[:80].replace('\n', ' ')
                print(f"   {i+1}. {preview}...")
        else:
            print(f"❌ 失败: {result.get('error')}")

        # 测试3: 读取表格
        print("\n[测试3] 读取文档表格...")
        result = word.read_tables(test_file)
        if result["status"] == "success":
            print(f"✅ 成功: {result['summary']}")
            tables = result.get('tables', [])
            if tables:
                for i, table in enumerate(tables[:2]):  # 只显示前2个表格
                    print(f"   表格{i+1}: {table['rows']}行 x {table['cols']}列")
            else:
                print("   文档中没有表格")
        else:
            print(f"❌ 失败: {result.get('error')}")

        print("\n" + "=" * 60)
        print("✅ Word 测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        word.close_app()


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("Office Win32 工具快速测试")
    print("=" * 60)

    test_word()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n测试已中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
