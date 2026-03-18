"""
测试 Word 替换功能的返回值问题
"""

import asyncio
from app.tools.office.word_tool import WordWin32LLMTool


async def test_replace_return_value():
    """测试替换功能的返回值"""

    word_tool = WordWin32LLMTool()

    # 测试文件路径
    file_path = r"D:\溯源\报告模板\2025年臭氧垂直报告7-ok - 副本.docx"

    print("=" * 80)
    print("测试 Word 替换功能")
    print("=" * 80)

    # 1. 先读取文档，查看实际内容
    print("\n步骤1：读取文档内容")
    read_result = await word_tool.execute(
        file_path=file_path,
        operation="read",
        start_index=0,
        end_index=10
    )

    if read_result["success"]:
        content = read_result["data"]["content"]
        print(f"文档前500字符：\n{content[:500]}")

        # 检查是否包含要替换的文本
        search_text = "臭氧滑动8小时最大浓度（O3_8h）为41微克/立方米"
        if search_text in content:
            print(f"\n✅ 找到精确匹配的文本：{search_text}")
        else:
            print(f"\n❌ 未找到精确匹配的文本：{search_text}")
            print("可能的相似文本：")
            # 查找相似的文本
            if "臭氧" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if "臭氧" in line and "浓度" in line:
                        print(f"  行{i+1}: {line.strip()}")
    else:
        print("❌ 读取文档失败")
        return

    # 2. 尝试替换（使用精确文本）
    print("\n步骤2：尝试替换文本")
    replace_result = await word_tool.execute(
        file_path=file_path,
        operation="replace",
        find=search_text,
        replace=""
    )

    print(f"\n替换结果：")
    print(f"  状态: {replace_result['status']}")
    print(f"  替换次数: {replace_result['data']['replacements']}")
    print(f"  替换次数类型: {type(replace_result['data']['replacements'])}")
    print(f"  摘要: {replace_result['summary']}")

    # 3. 再次读取，验证是否真的替换了
    print("\n步骤3：验证替换结果")
    verify_result = await word_tool.execute(
        file_path=file_path,
        operation="read",
        start_index=0,
        end_index=10
    )

    if verify_result["success"]:
        content_after = verify_result["data"]["content"]
        if search_text in content_after:
            print(f"❌ 替换失败：文本仍然存在")
        else:
            print(f"✅ 替换成功：文本已被删除")


if __name__ == "__main__":
    asyncio.run(test_replace_return_value())
