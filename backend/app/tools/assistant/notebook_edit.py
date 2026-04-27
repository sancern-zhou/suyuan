"""
Notebook 编辑工具（助手模式 - 办公任务专用）

核心价值：
- 办公报告生成
- 数据汇总文档
- 业务分析模板
- 简化 Notebook 编辑

使用场景：
1. 办公报告生成
   - 自动生成业务分析报告
   - 创建数据汇总文档
   - 生成月度/季度报告

2. 数据汇总文档
   - 汇总多个数据源
   - 生成统计图表
   - 添加分析结论

3. 业务分析模板
   - 更新分析模板
   - 修正文档内容
   - 添加新的分析章节

典型工作流：
```python
# 创建办公报告
notebook_edit(notebook_path="monthly_report.ipynb", cell_id="cell-0", edit_mode="insert", cell_type="markdown", new_source="# 月度业务分析报告")

# 插入数据汇总
notebook_edit(notebook_path="monthly_report.ipynb", cell_id="cell-0", edit_mode="insert", cell_type="code", new_source="import pandas as pd\\ndf = pd.read_excel('monthly_data.xlsx')")

# 插入分析结论
notebook_edit(notebook_path="monthly_report.ipynb", cell_id="cell-5", edit_mode="insert", cell_type="markdown", new_source="## 业务分析结论\\n\\n本月业务增长...")
```

特点：
- 简化接口，无需 Context
- 专注办公场景
- 与办公工具配合使用
"""

from typing import Any, Dict
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.notebook_edit_tool import get_notebook_edit_tool

logger = structlog.get_logger(__name__)


class NotebookEditAssistant(LLMTool):
    """
    Notebook 编辑工具（助手模式 - 办公任务专用）

    核心价值：
    - 办公报告自动化的关键工具
    - 简化接口，易于使用
    - 与办公工具配合
    """

    def __init__(self):
        function_schema = {
            "name": "notebook_edit",
            "description": """编辑 Jupyter Notebook (助手模式专用 - 办公任务)

⭐ 办公报告和数据汇总文档自动化的核心工具

支持操作：
- replace: 替换单元格内容（默认）
- insert: 在指定单元格后插入新单元格
- delete: 删除指定单元格

单元格类型：
- code: 代码单元格（可执行）
- markdown: 文档单元格（说明文字）

使用场景：
1. 办公报告生成
   - 自动生成业务分析报告
   - 创建数据汇总文档
   - 生成月度/季度报告

2. 数据汇总文档
   - 汇总多个数据源
   - 生成统计图表
   - 添加分析结论

3. 业务分析模板
   - 更新分析模板
   - 修正文档内容
   - 添加新的分析章节

典型工作流：
```python
# 创建办公报告
notebook_edit(notebook_path="monthly_report.ipynb", cell_id="cell-0", edit_mode="insert", cell_type="markdown", new_source="# 月度业务分析报告")

# 插入数据汇总代码
notebook_edit(notebook_path="monthly_report.ipynb", cell_id="cell-0", edit_mode="insert", cell_type="code", new_source="import pandas as pd\\ndf = pd.read_excel('monthly_data.xlsx')\\nprint(df.describe())")

# 插入分析结论
notebook_edit(notebook_path="monthly_report.ipynb", cell_id="cell-5", edit_mode="insert", cell_type="markdown", new_source="## 业务分析结论\\n\\n本月业务增长 15%，主要来自...")
```

重要：
- 必须先用 read_file 读取 notebook 文件
- insert 模式必须指定 cell_type (code/markdown)
- 办公场景的简化版本，无需复杂的 Context
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "notebook_path": {
                        "type": "string",
                        "description": "Jupyter Notebook 文件的绝对路径（.ipynb 文件）。示例：'D:/work/reports/monthly_report.ipynb' 或 'reports/monthly_report.ipynb'"
                    },
                    "cell_id": {
                        "type": "string",
                        "description": "目标单元格ID或索引（如 'cell-0'、'cell-1'）。insert模式可选（默认在开头插入）。示例：'cell-0'（第一个单元格）"
                    },
                    "new_source": {
                        "type": "string",
                        "description": "新的单元格内容。replace/delete模式可选。支持多行代码，换行符使用 \\\\n。示例：'import pandas as pd\\\\ndf = pd.read_excel(\\\"data.xlsx\\\")'"
                    },
                    "cell_type": {
                        "type": "string",
                        "enum": ["code", "markdown"],
                        "description": "单元格类型（insert模式必填，replace/delete模式可选）。code：可执行代码单元格；markdown：文档说明单元格"
                    },
                    "edit_mode": {
                        "type": "string",
                        "enum": ["replace", "insert", "delete"],
                        "description": "编辑模式。replace：替换单元格内容（默认）；insert：插入新单元格；delete：删除单元格"
                    }
                },
                "required": ["notebook_path"],
                "additionalProperties": False
            }
        }

        super().__init__(
            name="notebook_edit",
            description="编辑 Jupyter Notebook (.ipynb) 文件的单元格（助手模式 - 办公任务专用）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False  # ❌ 助手模式不需要 Context
        )

        # 复用核心实现
        self.core_tool = get_notebook_edit_tool()

    async def execute(
        self,
        notebook_path: str = None,
        new_source: str = None,
        cell_id: str = None,
        cell_type: str = "code",
        edit_mode: str = "replace",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 Notebook 编辑操作（助手模式）

        助手模式特点：
        - 简化接口
        - 无 Context 依赖
        - 直接调用核心工具
        - 专注办公场景

        Args:
            notebook_path: Notebook 文件路径
            new_source: 新的单元格内容
            cell_id: 目标单元格ID或索引
            cell_type: 单元格类型（code/markdown）
            edit_mode: 编辑模式（replace/insert/delete）
            **kwargs: 其他参数

        Returns:
            {
                "success": true/false,
                "data": {
                    "cell_id": "...",
                    "cell_type": "code/markdown",
                    "language": "python",
                    "edit_mode": "replace/insert/delete",
                    "new_source": "...",
                    "notebook_path": "...",
                    "total_cells": 10
                },
                "summary": "操作摘要"
            }
        """
        try:
            logger.info(
                "notebook_edit_assistant_called",
                notebook_path=notebook_path,
                edit_mode=edit_mode,
                cell_type=cell_type
            )

            # 直接调用核心工具，无额外处理
            result = await self.core_tool.execute(
                notebook_path=notebook_path,
                new_source=new_source,
                cell_id=cell_id,
                cell_type=cell_type,
                edit_mode=edit_mode,
                **kwargs
            )

            return result

        except Exception as e:
            logger.error(
                "notebook_edit_assistant_failed",
                notebook_path=notebook_path,
                error=str(e),
                exc_info=True
            )

            return {
                "success": False,
                "error": str(e),
                "summary": f"编辑 Notebook 失败（助手模式）: {str(e)}"
            }

    def is_available(self) -> bool:
        """检查工具是否可用"""
        return self.core_tool.is_available()
