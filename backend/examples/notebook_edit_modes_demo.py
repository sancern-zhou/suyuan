"""
NotebookEditTool 多模式使用示例

演示如何在专家模式和助手模式下使用 NotebookEditTool。
"""

import asyncio
import tempfile
import json
from pathlib import Path


async def expert_mode_example():
    """专家模式示例：数据分析报告"""
    print("=" * 60)
    print("专家模式示例：自动生成污染溯源分析报告")
    print("=" * 60)

    # 1. 创建示例 Notebook
    nb_content = {
        "cells": [
            {
                "id": "cell-1",
                "cell_type": "code",
                "source": ["# 数据加载代码将在下一步插入"],
                "execution_count": None,
                "outputs": [],
                "metadata": {}
            }
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False, dir='/tmp') as f:
        json.dump(nb_content, f)
        notebook_path = f.name

    print(f"\n✅ 创建示例 Notebook: {notebook_path}")

    try:
        # 模拟专家模式调用
        from app.tools import global_tool_registry
        from app.tools.utility.read_file_tool import ReadFileTool

        # 1. 先读取 Notebook（Read-Before-Edit）
        read_tool = ReadFileTool()
        read_result = await read_tool.execute(
            path=notebook_path,
            offset=0,
            limit=100
        )

        if not read_result["success"]:
            print(f"❌ 读取失败: {read_result.get('summary')}")
            return

        print(f"✅ 读取 Notebook 成功")

        # 2. 获取工具（专家模式）
        tool = global_tool_registry.get_tool("notebook_edit")

        # 3. 创建模拟的 Context
        class MockContext:
            def __init__(self):
                from app.agent.task.task_list import TaskList
                self.task_list = TaskList()

        context = MockContext()

        # 4. 插入标题单元格
        result = await tool.execute(
            context=context,
            notebook_path=notebook_path,
            cell_id="cell-0",
            edit_mode="insert",
            cell_type="markdown",
            new_source="# 广州O3污染溯源分析报告\n\n时间范围：2026年1月"
        )

        if result["success"]:
            print(f"✅ 标题插入成功: {result['summary']}")
            print(f"   - 总单元格数: {result['data']['total_cells']}")
        else:
            print(f"❌ 插入失败: {result.get('summary')}")
            return

        # 5. 插入数据加载代码
        result = await tool.execute(
            context=context,
            notebook_path=notebook_path,
            cell_id="cell-0",
            edit_mode="insert",
            cell_type="code",
            new_source="""
import sys
sys.path.append('/home/xckj/suyuan/backend')

from app.tools.query.query_standard_report.tool import get_standard_report_data

# 加载数据
data = get_standard_report_data(
    city='广州',
    start_date='2026-01-01',
    end_date='2026-01-31'
)
print(f"数据加载完成: {len(data)} 个字段")
"""
        )

        if result["success"]:
            print(f"✅ 代码插入成功: {result['summary']}")
        else:
            print(f"❌ 插入失败: {result.get('summary')}")
            return

        # 6. 插入分析结论
        result = await tool.execute(
            context=context,
            notebook_path=notebook_path,
            cell_id="cell-2",
            edit_mode="insert",
            cell_type="markdown",
            new_source="""
## 分析结论

根据 PMF 模型分析，O3 主要来源为：
1. 机动车排放（40%）
2. 工业排放（25%）
3. 挥发排放（15%）

**政策建议**：
- 加强机动车尾气排放控制
- 推进工业 VOCs 深度治理
"""
        )

        if result["success"]:
            print(f"✅ 结论插入成功: {result['summary']}")
        else:
            print(f"❌ 插入失败: {result.get('summary')}")
            return

        # 7. 检查任务记录
        print(f"\n✅ 任务记录: {context.task_list.count()} 个任务")
        for task in context.task_list.get_all_tasks():
            print(f"   - {task.content}")

        # 8. 显示最终 Notebook 结构
        with open(notebook_path, 'r') as f:
            nb = json.load(f)

        print(f"\n✅ 最终 Notebook 结构:")
        print(f"   - 总单元格数: {len(nb['cells'])}")
        for i, cell in enumerate(nb['cells']):
            cell_type = cell.get('cell_type', 'unknown')
            source_preview = ''.join(cell.get('source', [])[:50])
            print(f"   - cell-{i}: {cell_type} - {source_preview}...")

    finally:
        # 清理临时文件
        import os
        if os.path.exists(notebook_path):
            os.unlink(notebook_path)
            print(f"\n✅ 临时文件已清理: {notebook_path}")


async def assistant_mode_example():
    """助手模式示例：办公报告生成"""
    print("\n" + "=" * 60)
    print("助手模式示例：办公报告生成")
    print("=" * 60)

    # 1. 创建示例 Notebook
    nb_content = {
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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False, dir='/tmp') as f:
        json.dump(nb_content, f)
        notebook_path = f.name

    print(f"\n✅ 创建示例 Notebook: {notebook_path}")

    try:
        # 模拟助手模式调用
        from app.tools import global_tool_registry
        from app.tools.utility.read_file_tool import ReadFileTool

        # 1. 先读取 Notebook（Read-Before-Edit）
        read_tool = ReadFileTool()
        read_result = await read_tool.execute(
            path=notebook_path,
            offset=0,
            limit=100
        )

        if not read_result["success"]:
            print(f"❌ 读取失败: {read_result.get('summary')}")
            return

        print(f"✅ 读取 Notebook 成功")

        # 2. 获取工具（助手模式）
        tool = global_tool_registry.get_tool("notebook_edit")

        # 3. 替换代码单元格（助手模式，无需 Context）
        result = await tool.execute(
            notebook_path=notebook_path,
            cell_id="cell-1",
            edit_mode="replace",
            new_source="print('Assistant mode: Monthly business report')"
        )

        if result["success"]:
            print(f"✅ 代码替换成功: {result['summary']}")
        else:
            print(f"❌ 替换失败: {result.get('summary')}")
            return

        # 4. 插入业务分析标题
        result = await tool.execute(
            notebook_path=notebook_path,
            cell_id="cell-0",
            edit_mode="insert",
            cell_type="markdown",
            new_source="# 月度业务分析报告\n\n报告期间：2026年3月"
        )

        if result["success"]:
            print(f"✅ 标题插入成功: {result['summary']}")
        else:
            print(f"❌ 插入失败: {result.get('summary')}")
            return

        # 5. 插入业务结论
        result = await tool.execute(
            notebook_path=notebook_path,
            cell_id="cell-2",
            edit_mode="insert",
            cell_type="markdown",
            new_source="""
## 业务分析结论

1. **收入增长**：本月收入同比增长 15%
2. **成本控制**：运营成本下降 8%
3. **客户满意度**：提升至 92%

**下月计划**：
- 继续优化运营流程
- 加强客户服务培训
"""
        )

        if result["success"]:
            print(f"✅ 结论插入成功: {result['summary']}")
        else:
            print(f"❌ 插入失败: {result.get('summary')}")
            return

        # 6. 显示最终 Notebook 结构
        with open(notebook_path, 'r') as f:
            nb = json.load(f)

        print(f"\n✅ 最终 Notebook 结构:")
        print(f"   - 总单元格数: {len(nb['cells'])}")
        for i, cell in enumerate(nb['cells']):
            cell_type = cell.get('cell_type', 'unknown')
            source_preview = ''.join(cell.get('source', [])[:50])
            print(f"   - cell-{i}: {cell_type} - {source_preview}...")

    finally:
        # 清理临时文件
        import os
        if os.path.exists(notebook_path):
            os.unlink(notebook_path)
            print(f"\n✅ 临时文件已清理: {notebook_path}")


async def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("NotebookEditTool 多模式使用示例")
    print("=" * 60)

    # 专家模式示例
    await expert_mode_example()

    # 助手模式示例
    await assistant_mode_example()

    print("\n" + "=" * 60)
    print("✅ 所有示例运行完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
