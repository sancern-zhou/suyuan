"""
NotebookEditTool 测试脚本

测试 Jupyter Notebook 编辑功能：
1. 创建测试 notebook
2. 测试 replace 操作
3. 测试 insert 操作
4. 测试 delete 操作
5. 测试 Read-Before-Edit 安全机制
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path


async def create_test_notebook(path: str):
    """创建测试用的 Jupyter Notebook"""
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "name": "python",
                "version": "3.9.0"
            }
        },
        "cells": [
            {
                "id": "cell-0",
                "cell_type": "markdown",
                "source": "# 数据分析报告\n\n本报告展示了污染溯源分析结果。",
                "metadata": {}
            },
            {
                "id": "cell-1",
                "cell_type": "code",
                "source": "import pandas as pd\nimport matplotlib.pyplot as plt\n\nprint('数据加载完成')",
                "execution_count": 1,
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": "数据加载完成\n"
                    }
                ],
                "metadata": {}
            },
            {
                "id": "cell-2",
                "cell_type": "markdown",
                "source": "## 数据概览\n\n上表展示了污染物浓度数据。",
                "metadata": {}
            },
            {
                "id": "cell-3",
                "cell_type": "code",
                "source": "# 数据分析代码\ndata = pd.read_csv('data.csv')\ndata.head()",
                "execution_count": None,
                "outputs": [],
                "metadata": {}
            }
        ]
    }

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(notebook, f, indent=1, ensure_ascii=False)

    print(f"✅ 测试 Notebook 已创建: {path}")
    print(f"   包含 {len(notebook['cells'])} 个单元格")


async def test_notebook_edit():
    """测试 NotebookEditTool"""
    from app.tools.utility.notebook_edit_tool import NotebookEditTool, get_notebook_edit_tool
    from app.tools.utility.read_file_tool import ReadFileTool

    # 创建临时测试文件（在允许的工作目录中）
    test_dir = Path("/home/xckj/suyuan/backend_data_registry/tests")
    test_dir.mkdir(parents=True, exist_ok=True)
    test_path = test_dir / "test_notebook.ipynb"

    try:
        print("\n" + "="*60)
        print("NotebookEditTool 测试")
        print("="*60)

        # 1. 创建测试 notebook
        await create_test_notebook(test_path)

        # 初始化工具
        edit_tool = get_notebook_edit_tool()
        read_tool = ReadFileTool()

        # 2. 测试 Read-Before-Edit 安全机制
        print("\n📝 测试 1: Read-Before-Edit 安全机制")
        result = await edit_tool.execute(
            notebook_path=test_path,
            cell_id="cell-0",
            new_source="尝试直接编辑（未读取）"
        )
        assert not result["success"], "应该失败：文件尚未读取"
        assert "尚未读取" in result["summary"], "错误信息应该提示先读取文件"
        print("✅ Read-Before-Edit 机制正常工作")

        # 3. 读取 notebook
        print("\n📝 测试 2: 读取 Notebook")
        result = await read_tool.execute(path=test_path)
        assert result["success"], f"读取失败: {result.get('summary')}"
        print(f"✅ 成功读取 Notebook")
        print(f"   内容预览: {result['data']['content'][:100]}...")

        # 4. 测试 replace 操作
        print("\n📝 测试 3: Replace 操作（替换单元格内容）")
        result = await edit_tool.execute(
            notebook_path=test_path,
            cell_id="cell-1",
            new_source="# 更新后的代码\nprint('Hello, NotebookEditTool!')",
            edit_mode="replace"
        )
        assert result["success"], f"Replace 失败: {result.get('summary')}"
        print(f"✅ {result['summary']}")
        print(f"   单元格类型: {result['data']['cell_type']}")
        print(f"   总单元格数: {result['data']['total_cells']}")

        # 验证替换结果
        with open(test_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        assert "Hello, NotebookEditTool!" in notebook['cells'][1]['source'], "内容未正确替换"
        assert notebook['cells'][1]['execution_count'] is None, "执行状态未清空"
        assert notebook['cells'][1]['outputs'] == [], "输出未清空"
        print("✅ 替换结果验证通过（执行状态已清空）")

        # 5. 测试 insert 操作
        print("\n📝 测试 4: Insert 操作（插入新单元格）")
        result = await edit_tool.execute(
            notebook_path=test_path,
            cell_id="cell-2",
            new_source="## 新插入的章节\n\n这是动态插入的内容。",
            cell_type="markdown",
            edit_mode="insert"
        )
        assert result["success"], f"Insert 失败: {result.get('summary')}"
        print(f"✅ {result['summary']}")

        # 验证插入结果
        with open(test_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        assert len(notebook['cells']) == 5, f"单元格数应为 5，实际为 {len(notebook['cells'])}"
        assert "新插入的章节" in notebook['cells'][3]['source'], "新单元格未正确插入"
        print("✅ 插入结果验证通过")

        # 6. 测试 delete 操作
        print("\n📝 测试 5: Delete 操作（删除单元格）")
        result = await edit_tool.execute(
            notebook_path=test_path,
            cell_id="cell-4",
            edit_mode="delete"
        )
        assert result["success"], f"Delete 失败: {result.get('summary')}"
        print(f"✅ {result['summary']}")

        # 验证删除结果
        with open(test_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        assert len(notebook['cells']) == 4, f"单元格数应为 4，实际为 {len(notebook['cells'])}"
        print("✅ 删除结果验证通过")

        # 7. 测试索引格式（cell-N）
        print("\n📝 测试 6: 使用索引格式（cell-0）")
        result = await edit_tool.execute(
            notebook_path=test_path,
            cell_id="cell-0",
            new_source="# 更新后的标题\n\n数据分析报告（已更新）",
            edit_mode="replace"
        )
        assert result["success"], f"索引格式替换失败: {result.get('summary')}"
        print(f"✅ {result['summary']}")

        # 8. 显示最终结果
        print("\n📊 最终 Notebook 内容:")
        with open(test_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)

        for i, cell in enumerate(notebook['cells']):
            cell_type = cell['cell_type']
            source = cell['source'][:50].replace('\n', ' ')
            print(f"   [{i}] {cell_type.upper()}: {source}...")

        print("\n" + "="*60)
        print("✅ 所有测试通过！")
        print("="*60)

        # 9. 保存测试文件供用户查看
        output_path = Path.home() / "test_notebook_output.ipynb"
        import shutil
        shutil.copy(test_path, output_path)
        print(f"\n📁 测试结果已保存到: {output_path}")
        print("   可以用 Jupyter Notebook 打开查看。")

    finally:
        # 清理临时文件
        if os.path.exists(test_path):
            os.remove(test_path)
            # 尝试删除测试目录
            try:
                test_dir.rmdir()
            except:
                pass
            print(f"\n🧹 临时测试文件已清理")


if __name__ == "__main__":
    asyncio.run(test_notebook_edit())
