"""
PDF解析工具测试脚本

测试parse_pdf工具的各种功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.utility.parse_pdf_tool import create_parse_pdf_tool


async def test_parse_pdf():
    """测试PDF解析工具"""

    # 创建工具实例
    tool = create_parse_pdf_tool()

    print("=" * 60)
    print("PDF解析工具测试")
    print("=" * 60)

    # 测试1: 检查工具是否可用
    print("\n[测试1] 检查工具可用性...")
    if tool.is_available():
        print("✓ 工具可用")
    else:
        print("✗ 工具不可用")
        return

    # 测试2: 获取工具schema
    print("\n[测试2] 获取工具schema...")
    schema = tool.get_function_schema()
    print(f"✓ 工具名称: {schema['name']}")
    print(f"✓ 参数: {', '.join(schema['parameters']['properties'].keys())}")

    # 测试3: 解析PDF（需要提供实际PDF文件路径）
    print("\n[测试3] 解析PDF文件...")
    print("请提供PDF文件路径进行测试（或按Enter跳过）")

    pdf_path = input("PDF文件路径: ").strip()

    if pdf_path and Path(pdf_path).exists():
        # 测试自动检测模式
        print("\n--- 测试自动检测模式 ---")
        result = await tool.execute(path=pdf_path, mode="auto")

        if result["success"]:
            print(f"✓ 解析成功")
            print(f"  摘要: {result['summary']}")
            print(f"  数据类型: {result['data']['type']}")
            if "content_length" in result["data"]:
                print(f"  内容长度: {result['data']['content_length']} 字符")
        else:
            print(f"✗ 解析失败: {result['data'].get('error', '未知错误')}")

        # 测试文本提取
        print("\n--- 测试文本提取模式 ---")
        result = await tool.execute(path=pdf_path, mode="text")

        if result["success"]:
            print(f"✓ 文本提取成功")
            print(f"  总页数: {result['data']['total_pages']}")
            print(f"  处理页数: {result['data']['pages_processed']}")

            # 显示前200个字符
            content = result["data"]["content"]
            preview = content[:200] + "..." if len(content) > 200 else content
            print(f"  内容预览: {preview}")
        else:
            print(f"✗ 文本提取失败: {result['data'].get('error', '未知错误')}")

        # 测试元数据提取
        print("\n--- 测试元数据提取 ---")
        result = await tool.execute(path=pdf_path, mode="meta")

        if result["success"]:
            print(f"✓ 元数据提取成功")
            data = result["data"]
            if "title" in data and data["title"]:
                print(f"  标题: {data['title']}")
            if "author" in data and data["author"]:
                print(f"  作者: {data['author']}")
            print(f"  页数: {data['page_count']}")
            print(f"  是否加密: {data['is_encrypted']}")
        else:
            print(f"✗ 元数据提取失败: {result['data'].get('error', '未知错误')}")

        # 测试分页读取
        if result["success"] and result["data"]["page_count"] > 1:
            print("\n--- 测试分页读取（第1-2页） ---")
            result = await tool.execute(path=pdf_path, mode="text", pages="1-2")

            if result["success"]:
                print(f"✓ 分页读取成功")
                print(f"  处理页数: {result['data']['pages_processed']}")
            else:
                print(f"✗ 分页读取失败: {result['data'].get('error', '未知错误')}")

        # 测试表格提取
        print("\n--- 测试表格提取 ---")
        result = await tool.execute(path=pdf_path, mode="table")

        if result["success"]:
            table_count = result["data"]["table_count"]
            print(f"✓ 表格提取成功")
            print(f"  表格数量: {table_count}")
            if table_count > 0:
                first_table = result["data"]["tables"][0]
                print(f"  第一个表格: {first_table['rows']}行 x {first_table['cols']}列")
        else:
            print(f"✗ 表格提取失败: {result['data'].get('error', '未知错误')}")

        # 测试OCR（如果是扫描版PDF）
        print("\n--- 测试OCR检测 ---")
        print("提示: 如果是扫描版PDF，可以使用 mode='ocr' 进行OCR识别")

    else:
        print("跳过PDF文件测试")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_parse_pdf())
