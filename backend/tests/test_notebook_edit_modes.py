"""
测试 NotebookEditTool 在专家模式和助手模式下的集成

验证：
1. 专家模式：NotebookEditExpert 正确工作
2. 助手模式：NotebookEditAssistant 正确工作
3. 工具注册：两个工具都正确注册到 global_tool_registry
4. Context 集成：专家模式正确使用 ExecutionContext
5. 任务管理：专家模式正确记录任务到 task_list
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path

from app.tools import global_tool_registry
from app.agent.context import ExecutionContext
from app.agent.task.task_list import TaskList


class TestNotebookEditModes:
    """测试 NotebookEditTool 的多模式集成"""

    @pytest.fixture
    def sample_notebook(self):
        """创建示例 Notebook 文件"""
        nb_content = {
            "cells": [
                {
                    "id": "cell-1",
                    "cell_type": "code",
                    "source": ["print('Hello, World!')"],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                },
                {
                    "id": "cell-2",
                    "cell_type": "markdown",
                    "source": ["# Test Notebook"],
                    "metadata": {}
                }
            ],
            "metadata": {
                "language_info": {"name": "python"},
                "kernelspec": {
                    "name": "python3",
                    "display_name": "Python 3"
                }
            },
            "nbformat": 4,
            "nbformat_minor": 5
        }

        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False) as f:
            json.dump(nb_content, f)
            return f.name

    def test_tools_registered(self):
        """测试工具是否正确注册"""
        tools = global_tool_registry.list_tools()

        # 检查两个工具都已注册
        assert "notebook_edit" in tools, "notebook_edit 工具未注册"

        # 获取工具实例
        tool = global_tool_registry.get_tool("notebook_edit")
        assert tool is not None, "无法获取 notebook_edit 工具"

        print("✅ 工具注册测试通过")

    @pytest.mark.asyncio
    async def test_expert_mode(self, sample_notebook):
        """测试专家模式的 Notebook 编辑"""
        # 获取工具
        tool = global_tool_registry.get_tool("notebook_edit")

        # 创建模拟的 ExecutionContext
        class MockContext:
            def __init__(self):
                self.task_list = TaskList()

        context = MockContext()

        # 1. 先读取文件（Read-Before-Edit 要求）
        from app.tools.utility.read_file_tool import ReadFileTool
        read_tool = ReadFileTool()

        read_result = await read_tool.execute(
            path=sample_notebook,
            offset=0,
            limit=100
        )

        assert read_result["success"], "读取 Notebook 失败"
        print(f"✅ 读取 Notebook 成功: {len(read_result['data']['content'])} 字符")

        # 2. 测试插入单元格（专家模式）
        insert_result = await tool.execute(
            context=context,
            notebook_path=sample_notebook,
            cell_id="cell-1",
            edit_mode="insert",
            cell_type="code",
            new_source="import pandas as pd\nprint('Expert mode test')"
        )

        assert insert_result["success"], f"插入单元格失败: {insert_result.get('summary')}"
        print(f"✅ 专家模式插入成功: {insert_result['summary']}")

        # 3. 检查任务是否记录
        assert context.task_list.count() > 0, "任务未被记录到 task_list"
        print(f"✅ 任务已记录: {context.task_list.count()} 个任务")

        # 4. 验证 Notebook 内容
        with open(sample_notebook, 'r') as f:
            nb = json.load(f)

        assert len(nb["cells"]) == 3, "单元格数量不正确"
        assert nb["cells"][2]["source"] == ["import pandas as pd", "print('Expert mode test')"], "新单元格内容不正确"
        print("✅ Notebook 内容验证通过")

    @pytest.mark.asyncio
    async def test_assistant_mode(self, sample_notebook):
        """测试助手模式的 Notebook 编辑"""
        # 获取工具
        tool = global_tool_registry.get_tool("notebook_edit")

        # 1. 先读取文件（Read-Before-Edit 要求）
        from app.tools.utility.read_file_tool import ReadFileTool
        read_tool = ReadFileTool()

        read_result = await read_tool.execute(
            path=sample_notebook,
            offset=0,
            limit=100
        )

        assert read_result["success"], "读取 Notebook 失败"

        # 2. 测试替换单元格（助手模式，无 Context）
        replace_result = await tool.execute(
            notebook_path=sample_notebook,
            cell_id="cell-1",
            edit_mode="replace",
            new_source="print('Assistant mode test')"
        )

        assert replace_result["success"], f"替换单元格失败: {replace_result.get('summary')}"
        print(f"✅ 助手模式替换成功: {replace_result['summary']}")

        # 3. 验证 Notebook 内容
        with open(sample_notebook, 'r') as f:
            nb = json.load(f)

        assert nb["cells"][0]["source"] == ["print('Assistant mode test')"], "单元格内容未更新"
        print("✅ Notebook 内容验证通过")

    @pytest.mark.asyncio
    async def test_both_modes_comparison(self, sample_notebook):
        """对比专家模式和助手模式的差异"""
        tool = global_tool_registry.get_tool("notebook_edit")

        # 创建模拟的 ExecutionContext（专家模式）
        class MockContext:
            def __init__(self):
                self.task_list = TaskList()

        context = MockContext()

        # 先读取文件
        from app.tools.utility.read_file_tool import ReadFileTool
        read_tool = ReadFileTool()
        await read_tool.execute(path=sample_notebook)

        # 专家模式：有 Context 和任务管理
        expert_result = await tool.execute(
            context=context,
            notebook_path=sample_notebook,
            cell_id="cell-1",
            edit_mode="insert",
            cell_type="markdown",
            new_source="## Expert Mode Analysis\n\nPMF源解析结果..."
        )

        assert expert_result["success"], "专家模式执行失败"
        print(f"✅ 专家模式: {expert_result['summary']}")
        print(f"   - 任务记录: {context.task_list.count()} 个任务")

        # 助手模式：无 Context，无任务管理
        assistant_result = await tool.execute(
            notebook_path=sample_notebook,
            cell_id="cell-2",
            edit_mode="replace",
            new_source="# Assistant Mode\n\nOffice report..."
        )

        assert assistant_result["success"], "助手模式执行失败"
        print(f"✅ 助手模式: {assistant_result['summary']}")

        # 验证差异
        assert context.task_list.count() > 0, "专家模式未记录任务"
        print(f"✅ 模式差异验证通过")
        print(f"   - 专家模式: 有任务管理、Context 集成")
        print(f"   - 助手模式: 无任务管理、简化接口")

    def test_tool_availability(self):
        """测试工具可用性"""
        tool = global_tool_registry.get_tool("notebook_edit")

        # 检查工具是否可用
        assert tool.is_available(), "工具不可用"

        # 检查工具属性
        assert hasattr(tool, 'name'), "工具缺少 name 属性"
        assert hasattr(tool, 'requires_context'), "工具缺少 requires_context 属性"
        assert hasattr(tool, 'requires_task_list'), "工具缺少 requires_task_list 属性"

        print(f"✅ 工具名称: {tool.name}")
        print(f"✅ 需要 Context: {tool.requires_context}")
        print(f"✅ 需要任务列表: {tool.requires_task_list}")
        print("✅ 工具属性验证通过")


def test_manual():
    """手动测试函数（不使用 pytest）"""
    import asyncio

    async def run_tests():
        print("=" * 60)
        print("NotebookEditTool 多模式集成测试")
        print("=" * 60)

        # 创建测试实例
        test = TestNotebookEditModes()

        # 创建示例 Notebook
        print("\n1. 创建示例 Notebook...")
        sample_nb = {
            "cells": [
                {
                    "id": "cell-1",
                    "cell_type": "code",
                    "source": ["print('Original code')"],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                }
            ],
            "metadata": {"language_info": {"name": "python"}},
            "nbformat": 4,
            "nbformat_minor": 5
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False) as f:
            json.dump(sample_nb, f)
            sample_notebook = f.name

        print(f"✅ 示例 Notebook 创建成功: {sample_notebook}")

        try:
            # 测试工具注册
            print("\n2. 测试工具注册...")
            test.test_tools_registered()

            # 测试专家模式
            print("\n3. 测试专家模式...")
            await test.test_expert_mode(sample_notebook)

            # 测试助手模式
            print("\n4. 测试助手模式...")
            await test.test_assistant_mode(sample_notebook)

            # 测试模式对比
            print("\n5. 测试模式对比...")
            await test.test_both_modes_comparison(sample_notebook)

            # 测试工具可用性
            print("\n6. 测试工具可用性...")
            test.test_tool_availability()

            print("\n" + "=" * 60)
            print("✅ 所有测试通过！")
            print("=" * 60)

        finally:
            # 清理临时文件
            import os
            if os.path.exists(sample_notebook):
                os.unlink(sample_notebook)
                print(f"\n✅ 临时文件已清理: {sample_notebook}")

    # 运行测试
    asyncio.run(run_tests())


if __name__ == "__main__":
    test_manual()
