"""
社交模式记忆管理工具测试

测试remember_fact、replace_memory、remove_memory三个工具
"""

import asyncio
import pytest
from pathlib import Path
import tempfile
import shutil

from app.tools.social.remember_fact.tool import RememberFactTool
from app.tools.social.replace_memory.tool import ReplaceMemoryTool
from app.tools.social.remove_memory.tool import RemoveMemoryTool


@pytest.fixture
def temp_memory_dir():
    """创建临时记忆目录"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.mark.asyncio
async def test_remember_fact(temp_memory_dir):
    """测试记忆添加"""
    # 创建临时记忆文件
    memory_file = Path(temp_memory_dir) / "MEMORY.md"
    memory_file.write_text("""# 长期记忆 (MEMORY.md)

## 用户偏好

## 领域知识

## 历史结论

## 环境信息
""", encoding="utf-8")

    # 创建工具实例
    tool = RememberFactTool()

    # Mock _get_memory_file_path
    original_get_path = tool._get_memory_file_path
    tool._get_memory_file_path = lambda: str(memory_file)

    # 执行添加
    result = await tool.execute(
        fact="用户喜欢简洁的回答",
        category="用户偏好",
        priority=4
    )

    # 验证结果
    assert result["success"] == True
    assert "已记住" in result["summary"]

    # 验证文件内容
    content = memory_file.read_text(encoding="utf-8")
    assert "用户喜欢简洁的回答" in content

    # 恢复原方法
    tool._get_memory_file_path = original_get_path


@pytest.mark.asyncio
async def test_replace_memory(temp_memory_dir):
    """测试记忆替换"""
    # 创建临时记忆文件
    memory_file = Path(temp_memory_dir) / "MEMORY.md"
    memory_file.write_text("""# 长期记忆 (MEMORY.md)

## 用户偏好

- 用户喜欢详细的回答

## 领域知识

## 历史结论

## 环境信息
""", encoding="utf-8")

    # 创建工具实例
    tool = ReplaceMemoryTool()

    # Mock _get_memory_file_path
    tool._get_memory_file_path = lambda: str(memory_file)

    # 执行替换
    result = await tool.execute(
        old_text="用户喜欢详细的回答",
        new_text="用户喜欢简洁的回答",
        category="用户偏好"
    )

    # 验证结果
    assert result["success"] == True
    assert "已替换" in result["summary"]

    # 验证文件内容
    content = memory_file.read_text(encoding="utf-8")
    assert "用户喜欢简洁的回答" in content
    assert "用户喜欢详细的回答" not in content


@pytest.mark.asyncio
async def test_remove_memory(temp_memory_dir):
    """测试记忆删除"""
    # 创建临时记忆文件
    memory_file = Path(temp_memory_dir) / "MEMORY.md"
    memory_file.write_text("""# 长期记忆 (MEMORY.md)

## 用户偏好

- 用户喜欢简洁的回答

## 领域知识

## 历史结论

## 环境信息

- 用户今天在公司
""", encoding="utf-8")

    # 创建工具实例
    tool = RemoveMemoryTool()

    # Mock _get_memory_file_path
    tool._get_memory_file_path = lambda: str(memory_file)

    # 执行删除
    result = await tool.execute(
        text="用户今天在公司",
        category="环境信息"
    )

    # 验证结果
    assert result["success"] == True
    assert "已删除" in result["summary"]

    # 验证文件内容
    content = memory_file.read_text(encoding="utf-8")
    assert "用户今天在公司" not in content
    assert "用户喜欢简洁的回答" in content  # 其他条目保持不变


@pytest.mark.asyncio
async def test_memory_limit(temp_memory_dir):
    """测试字符限制"""
    # 创建接近限制的MEMORY.md
    memory_file = Path(temp_memory_dir) / "MEMORY.md"
    large_content = "# 长期记忆\n\n" + "x" * 3000  # 已满
    memory_file.write_text(large_content, encoding="utf-8")

    # 创建工具实例
    tool = RememberFactTool()

    # Mock _get_memory_file_path
    tool._get_memory_file_path = lambda: str(memory_file)

    # 执行添加（应该被拒绝）
    result = await tool.execute(
        fact="用户喜欢简洁的回答",
        category="用户偏好"
    )

    # 验证结果
    assert result["success"] == False
    assert "已满" in result["error"]


@pytest.mark.asyncio
async def test_memory_management_flow(temp_memory_dir):
    """测试完整的记忆管理流程"""
    # 创建临时记忆文件
    memory_file = Path(temp_memory_dir) / "MEMORY.md"
    memory_file.write_text("""# 长期记忆 (MEMORY.md)

## 用户偏好

## 领域知识

## 历史结论

## 环境信息
""", encoding="utf-8")

    # 创建工具实例
    remember_tool = RememberFactTool()
    replace_tool = ReplaceMemoryTool()
    remove_tool = RemoveMemoryTool()

    # Mock _get_memory_file_path
    remember_tool._get_memory_file_path = lambda: str(memory_file)
    replace_tool._get_memory_file_path = lambda: str(memory_file)
    remove_tool._get_memory_file_path = lambda: str(memory_file)

    # 1. 添加用户偏好
    result1 = await remember_tool.execute(
        fact="用户喜欢详细的回答",
        category="用户偏好"
    )
    assert result1["success"] == True

    # 2. 添加环境信息
    result2 = await remember_tool.execute(
        fact="用户今天在公司",
        category="环境信息"
    )
    assert result2["success"] == True

    # 3. 验证内容
    content = memory_file.read_text(encoding="utf-8")
    assert "用户喜欢详细的回答" in content
    assert "用户今天在公司" in content

    # 4. 替换偏好
    result3 = await replace_tool.execute(
        old_text="用户喜欢详细的回答",
        new_text="用户喜欢简洁的回答",
        category="用户偏好"
    )
    assert result3["success"] == True

    # 5. 删除临时信息
    result4 = await remove_tool.execute(
        text="用户今天在公司",
        category="环境信息"
    )
    assert result4["success"] == True

    # 6. 验证最终状态
    final_content = memory_file.read_text(encoding="utf-8")
    assert "用户喜欢简洁的回答" in final_content
    assert "用户今天在公司" not in final_content


if __name__ == "__main__":
    # 快速测试
    import sys
    temp_dir = tempfile.mkdtemp()
    try:
        print("Testing remember_fact...")
        asyncio.run(test_remember_fact(temp_dir))
        print("✓ remember_fact passed")

        print("Testing replace_memory...")
        asyncio.run(test_replace_memory(temp_dir))
        print("✓ replace_memory passed")

        print("Testing remove_memory...")
        asyncio.run(test_remove_memory(temp_dir))
        print("✓ remove_memory passed")

        print("Testing memory_limit...")
        asyncio.run(test_memory_limit(temp_dir))
        print("✓ memory_limit passed")

        print("Testing memory_management_flow...")
        asyncio.run(test_memory_management_flow(temp_dir))
        print("✓ memory_management_flow passed")

        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        shutil.rmtree(temp_dir)
