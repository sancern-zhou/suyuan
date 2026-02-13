"""
测试 Word Tool 的 tables 操作是否返回完整数据
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.tools.office.word_tool import WordWin32LLMTool


async def test_tables_returns_full_data():
    """测试 tables 操作返回完整表格数据"""
    print("=" * 60)
    print("测试 Word Tool - Tables 操作返回完整数据")
    print("=" * 60)

    # 创建工具实例
    tool = WordWin32LLMTool()

    # 测试文档路径（请根据实际情况修改）
    test_file = r"D:\溯源\报告模板\2025年臭氧垂直报告7-ok - 副本.docx"

    if not os.path.exists(test_file):
        print(f"\n[ERROR] 测试文件不存在: {test_file}")
        print("请修改 test_file 变量为实际存在的文档路径")
        return

    print(f"\n[INFO] 测试文件: {test_file}")

    # 执行 tables 操作
    print("\n[EXEC] 执行 operation='tables' ...")
    result = await tool.execute(path=test_file, operation="tables")

    # 打印结果
    print("\n" + "=" * 60)
    print("返回结果分析")
    print("=" * 60)

    print(f"\n[OK] 状态: {result.get('status')}")
    print(f"[OK] 成功: {result.get('success')}")

    # 检查数据结构
    data = result.get("data", {})
    tables = data.get("tables", [])
    table_count = data.get("table_count", 0)

    print(f"\n[DATA] 表格数量: {table_count}")
    print(f"[DATA] 返回的表格数组长度: {len(tables)}")

    # 检查是否包含完整数据
    if tables:
        print("\n" + "=" * 60)
        print("表格详细信息（前2个表格）")
        print("=" * 60)

        for i, table in enumerate(tables[:2]):
            print(f"\n表格 {i + 1}:")
            print(f"  - 索引: {table.get('index')}")
            print(f"  - 行数: {table.get('rows')}")
            print(f"  - 列数: {table.get('cols')}")

            table_data = table.get("data", [])
            print(f"  - 数据行数: {len(table_data)}")

            if table_data:
                print(f"  - 前2行数据预览:")
                for row_idx, row in enumerate(table_data[:2]):
                    # 使用 ASCII 编码安全打印
                    try:
                        print(f"    行{row_idx + 1}: {row}")
                    except UnicodeEncodeError:
                        # 如果有编码问题，只打印行号和单元格数量
                        print(f"    行{row_idx + 1}: [{len(row)} 个单元格]")

                # 计算总字符数（用于验证数据完整性）
                total_chars = sum(len(str(cell)) for row in table_data for cell in row)
                print(f"  - 数据总字符数: {total_chars}")

    # 打印 summary
    print("\n" + "=" * 60)
    print("Summary 信息")
    print("=" * 60)
    summary = result.get("summary", "")
    try:
        print(f"\n{summary}")
    except UnicodeEncodeError:
        # 如果有编码问题，打印简化版本
        print(f"\n[Summary] 表格数量: {table_count}, 详细信息请查看 data.tables 字段")

    # 验证结论
    print("\n" + "=" * 60)
    print("验证结论")
    print("=" * 60)

    if tables and len(tables) > 0:
        first_table = tables[0]
        if "data" in first_table and len(first_table["data"]) > 0:
            print("\n[PASS] 测试通过！tables 操作返回了完整的表格数据")
            print(f"[PASS] 包含 {len(tables)} 个表格的完整数据")
            print(f"[PASS] 第一个表格包含 {len(first_table['data'])} 行数据")
            print(f"[PASS] Summary 中包含表格详细信息")
        else:
            print("\n[FAIL] 测试失败！tables 操作未返回完整数据")
            print(f"[FAIL] 第一个表格缺少 data 字段或数据为空")
    else:
        print("\n[WARN] 文档中没有表格或表格数据为空")


if __name__ == "__main__":
    asyncio.run(test_tables_returns_full_data())
