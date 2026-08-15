"""
社交模式记忆管理工具简化测试

测试remember_fact、replace_memory、remove_memory三个工具
不加载全局工具注册表
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, Any

# 添加backend到path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class MockBaseTool:
    """模拟BaseTool"""

    def _build_schema(self):
        return {"type": "object"}


# 简化版工具实现（直接复制核心逻辑）
class RememberFactTool:
    """记忆添加工具"""

    name = "remember_fact"
    description = "记住重要事实到长期记忆（MEMORY.md）"

    def _get_memory_file_path(self) -> str:
        """获取当前用户的记忆文件路径"""
        mode = "social"
        base_path = Path("/home/xckj/suyuan/backend_data_registry/memory")
        memory_dir = base_path / mode
        memory_dir.mkdir(parents=True, exist_ok=True)

        memory_file = memory_dir / "MEMORY.md"
        return str(memory_file)

    def _append_fact(self, memory_file: Path, category: str, fact: str) -> None:
        """快速追加事实到对应章节"""
        # 确保文件存在
        if not memory_file.exists():
            initial_content = """# 长期记忆 (MEMORY.md)

此文件存储用户的偏好、领域知识和重要结论。

## 用户偏好

## 领域知识

## 历史结论

## 环境信息
"""
            memory_file.write_text(initial_content, encoding="utf-8")

        content = memory_file.read_text(encoding="utf-8")

        # 查找章节位置
        section_header = f"## {category}"

        if section_header in content:
            # 在章节末尾追加
            section_start = content.index(section_header)
            section_end = content.find("\n##", section_start + 1)

            if section_end == -1:
                section_end = len(content)

            before = content[:section_end]
            after = content[section_end:]

            # 检查章节内是否已有内容
            section_content = content[section_start:section_end]
            if section_content.strip().endswith(section_header):
                # 章节为空，直接添加
                new_content = f"{before}\n- {fact}{after}"
            else:
                # 章节已有内容，追加
                new_content = f"{before}\n- {fact}{after}"
        else:
            # 章节不存在，创建新章节
            new_content = f"{content}\n## {category}\n\n- {fact}\n"

        # 原子写入
        memory_file.write_text(new_content, encoding="utf-8")

    async def execute(self, fact: str, category: str, priority: int = 3, **kwargs) -> Dict[str, Any]:
        """执行记忆添加"""
        memory_file_path = self._get_memory_file_path()

        if not memory_file_path:
            return {
                "success": False,
                "error": "无法获取记忆文件路径",
                "summary": "记忆添加失败：无法找到记忆文件"
            }

        try:
            # 获取当前MEMORY.md大小
            memory_file = Path(memory_file_path)
            if memory_file.exists():
                current_size = len(memory_file.read_text(encoding="utf-8"))
                max_size = 3000

                if current_size >= max_size:
                    return {
                        "success": False,
                        "error": f"MEMORY.md已满（{current_size}/{max_size}字符），请先使用remove_memory清理旧内容",
                        "summary": "记忆添加失败：记忆文件已满"
                    }

            # 添加记忆
            self._append_fact(memory_file, category, fact)

            return {
                "success": True,
                "summary": f"已记住：{fact[:50]}{'...' if len(fact) > 50 else ''}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "summary": "记忆添加失败"
            }


class ReplaceMemoryTool:
    """记忆替换工具"""

    name = "replace_memory"
    description = "替换MEMORY.md中的现有条目"

    def _get_memory_file_path(self) -> str:
        """获取当前用户的记忆文件路径"""
        mode = "social"
        base_path = Path("/home/xckj/suyuan/backend_data_registry/memory")
        memory_dir = base_path / mode
        memory_dir.mkdir(parents=True, exist_ok=True)

        memory_file = memory_dir / "MEMORY.md"
        return str(memory_file)

    def _replace_fact(
        self,
        memory_file: Path,
        content: str,
        old_text: str,
        new_text: str,
        category: str = None
    ) -> bool:
        """替换记忆条目"""
        # 如果指定category，只在该章节内搜索
        if category:
            section_header = f"## {category}"

            if section_header not in content:
                return False

            section_start = content.index(section_header)
            section_end = content.find("\n##", section_start + 1)

            if section_end == -1:
                section_end = len(content)

            section_content = content[section_start:section_end]

            if old_text in section_content:
                new_section_content = section_content.replace(old_text, new_text)
                new_content = content[:section_start] + new_section_content + content[section_end:]

                # 原子写入
                memory_file.write_text(new_content, encoding="utf-8")
                return True

            return False
        else:
            # 全文搜索
            if old_text in content:
                new_content = content.replace(old_text, new_text)

                # 原子写入
                memory_file.write_text(new_content, encoding="utf-8")
                return True

            return False

    async def execute(self, old_text: str, new_text: str, category: str = None, **kwargs) -> Dict[str, Any]:
        """执行记忆替换"""
        memory_file_path = self._get_memory_file_path()

        if not memory_file_path:
            return {
                "success": False,
                "error": "无法获取记忆文件路径",
                "summary": "记忆替换失败：无法找到记忆文件"
            }

        try:
            memory_file = Path(memory_file_path)

            if not memory_file.exists():
                return {
                    "success": False,
                    "error": "记忆文件不存在",
                    "summary": "记忆替换失败：记忆文件不存在"
                }

            # 读取当前内容
            content = memory_file.read_text(encoding="utf-8")

            # 执行替换
            success = self._replace_fact(memory_file, content, old_text, new_text, category)

            if success:
                return {
                    "success": True,
                    "summary": f"已替换记忆：{old_text[:30]}... → {new_text[:30]}..."
                }
            else:
                return {
                    "success": False,
                    "error": f"未找到要替换的内容：{old_text[:50]}",
                    "summary": "记忆替换失败：未找到匹配内容"
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "summary": "记忆替换失败"
            }


class RemoveMemoryTool:
    """记忆删除工具"""

    name = "remove_memory"
    description = "从MEMORY.md中删除条目"

    def _get_memory_file_path(self) -> str:
        """获取当前用户的记忆文件路径"""
        mode = "social"
        base_path = Path("/home/xckj/suyuan/backend_data_registry/memory")
        memory_dir = base_path / mode
        memory_dir.mkdir(parents=True, exist_ok=True)

        memory_file = memory_dir / "MEMORY.md"
        return str(memory_file)

    def _remove_fact(
        self,
        memory_file: Path,
        content: str,
        text: str,
        category: str = None
    ) -> bool:
        """删除记忆条目"""
        lines = content.split('\n')

        if category:
            # 只在指定章节内删除
            section_header = f"## {category}"
            in_section = False
            filtered_lines = []

            for line in lines:
                if line.startswith(section_header):
                    in_section = True
                    filtered_lines.append(line)
                elif line.startswith("## ") and in_section:
                    in_section = False
                    filtered_lines.append(line)
                elif in_section and text in line:
                    # 跳过包含text的行
                    continue
                else:
                    filtered_lines.append(line)
        else:
            # 全文删除
            filtered_lines = [line for line in lines if text not in line]

        # 检查是否有变化
        if len(filtered_lines) == len(lines):
            return False

        # 重新构建内容
        new_content = '\n'.join(filtered_lines)

        # 原子写入
        memory_file.write_text(new_content, encoding="utf-8")
        return True

    async def execute(self, text: str, category: str = None, **kwargs) -> Dict[str, Any]:
        """执行记忆删除"""
        memory_file_path = self._get_memory_file_path()

        if not memory_file_path:
            return {
                "success": False,
                "error": "无法获取记忆文件路径",
                "summary": "记忆删除失败：无法找到记忆文件"
            }

        try:
            memory_file = Path(memory_file_path)

            if not memory_file.exists():
                return {
                    "success": False,
                    "error": "记忆文件不存在",
                    "summary": "记忆删除失败：记忆文件不存在"
                }

            # 读取当前内容
            content = memory_file.read_text(encoding="utf-8")

            # 执行删除
            success = self._remove_fact(memory_file, content, text, category)

            if success:
                return {
                    "success": True,
                    "summary": f"已删除记忆：{text[:50]}{'...' if len(text) > 50 else ''}"
                }
            else:
                return {
                    "success": False,
                    "error": f"未找到要删除的内容：{text[:50]}",
                    "summary": "记忆删除失败：未找到匹配内容"
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "summary": "记忆删除失败"
            }


async def test_all():
    """测试所有功能"""
    # 使用临时文件进行测试
    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    memory_file = Path(temp_dir) / "MEMORY.md"

    # 修改工具的路径获取方法
    original_get_path_remember = RememberFactTool._get_memory_file_path
    original_get_path_replace = ReplaceMemoryTool._get_memory_file_path
    original_get_path_remove = RemoveMemoryTool._get_memory_file_path

    def mock_get_path():
        return str(memory_file)

    RememberFactTool._get_memory_file_path = staticmethod(mock_get_path)
    ReplaceMemoryTool._get_memory_file_path = staticmethod(mock_get_path)
    RemoveMemoryTool._get_memory_file_path = staticmethod(mock_get_path)

    try:
        # 创建工具实例
        remember_tool = RememberFactTool()
        replace_tool = ReplaceMemoryTool()
        remove_tool = RemoveMemoryTool()

        print("Testing remember_fact...")
        result1 = await remember_tool.execute(
            fact="用户喜欢详细的回答",
            category="用户偏好"
        )
        assert result1["success"] == True, f"remember_fact failed: {result1}"
        print("✓ remember_fact passed")

        print("Testing remember_fact (second entry)...")
        result2 = await remember_tool.execute(
            fact="用户今天在公司",
            category="环境信息"
        )
        assert result2["success"] == True, f"remember_fact (2) failed: {result2}"
        print("✓ remember_fact (2) passed")

        # 验证内容
        content = memory_file.read_text(encoding="utf-8")
        assert "用户喜欢详细的回答" in content, "Content not found in memory"
        assert "用户今天在公司" in content, "Content not found in memory"
        print("✓ Content verification passed")

        print("Testing replace_memory...")
        result3 = await replace_tool.execute(
            old_text="用户喜欢详细的回答",
            new_text="用户喜欢简洁的回答",
            category="用户偏好"
        )
        assert result3["success"] == True, f"replace_memory failed: {result3}"
        print("✓ replace_memory passed")

        # 验证替换
        content = memory_file.read_text(encoding="utf-8")
        assert "用户喜欢简洁的回答" in content, "Replacement not found"
        assert "用户喜欢详细的回答" not in content, "Old text still present"
        print("✓ Replacement verification passed")

        print("Testing remove_memory...")
        result4 = await remove_tool.execute(
            text="用户今天在公司",
            category="环境信息"
        )
        assert result4["success"] == True, f"remove_memory failed: {result4}"
        print("✓ remove_memory passed")

        # 验证删除
        content = memory_file.read_text(encoding="utf-8")
        assert "用户今天在公司" not in content, "Deleted text still present"
        assert "用户喜欢简洁的回答" in content, "Other content was deleted"
        print("✓ Removal verification passed")

        print("\n✅ All tests passed!")

        # 显示最终内容
        print("\nFinal MEMORY.md content:")
        print(content)

    finally:
        # 恢复原始方法
        RememberFactTool._get_memory_file_path = original_get_path_remember
        ReplaceMemoryTool._get_memory_file_path = original_get_path_replace
        RemoveMemoryTool._get_memory_file_path = original_get_path_remove

        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        asyncio.run(test_all())
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
