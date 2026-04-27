"""
Notebook 编辑工具（专家模式 - 数据分析专用）

核心价值：
- 自动生成污染溯源分析报告
- 插入 PMF/OBM 分析代码和可视化
- 与数据分析工具链完美集成
- 支持 Context 和任务管理

使用场景：
1. 自动生成污染溯源分析报告
   - 创建分析 Notebook
   - 插入数据加载代码
   - 插入 PMF/OBM 分析
   - 插入可视化代码
   - 插入分析结论(Markdown)

2. 更新分析模板
   - 批量更新城市分析
   - 修正分析代码
   - 更新数据源

3. 交互式分析
   - Agent 自动调试代码
   - 增量构建分析流程
   - 添加分析步骤

典型工作流：
```python
# 1. 创建 Notebook
notebook_edit(notebook_path="analysis.ipynb", cell_id="cell-0", edit_mode="insert", cell_type="markdown", new_source="# 污染溯源分析报告")

# 2. 插入数据加载代码
notebook_edit(notebook_path="analysis.ipynb", cell_id="cell-0", edit_mode="insert", cell_type="code", new_source="import pandas as pd")

# 3. 插入 PMF 分析
notebook_edit(notebook_path="analysis.ipynb", cell_id="cell-1", edit_mode="insert", cell_type="code", new_source="from app.tools.analysis.calculate_pm_pmf import pmf_source_apportionment")

# 4. 插入分析结论
notebook_edit(notebook_path="analysis.ipynb", cell_id="cell-5", edit_mode="insert", cell_type="markdown", new_source="## 分析结论\\n\\n根据 PMF 模型...")
```

安全机制：
- Read-Before-Edit：必须先读取文件才能编辑
- 文件修改时间检测：防止外部修改冲突
- JSON 格式验证：确保 Notebook 结构完整
"""

from typing import TYPE_CHECKING, Any, Dict, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.notebook_edit_tool import get_notebook_edit_tool

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger(__name__)


class NotebookEditExpert(LLMTool):
    """
    Notebook 编辑工具（专家模式 - 数据分析专用）

    核心价值：
    - 数据分析报告自动化的关键工具
    - 与专家模式工具链完美集成
    - 支持 Context 和任务管理
    """

    def __init__(self):
        function_schema = {
            "name": "notebook_edit",
            "description": """编辑 Jupyter Notebook (专家模式专用)

⭐ 数据分析报告自动化的核心工具

支持操作：
- replace: 替换单元格内容（默认）
- insert: 在指定单元格后插入新单元格
- delete: 删除指定单元格

单元格类型：
- code: 代码单元格（可执行）
- markdown: 文档单元格（说明文字）

使用场景：
1. 自动生成污染溯源分析报告
   - 插入数据加载代码
   - 插入 PMF/OBM 分析代码
   - 插入可视化代码
   - 插入分析结论(Markdown)

2. 更新分析模板
   - 批量更新城市分析
   - 修正分析代码
   - 更新数据源

3. 交互式分析
   - Agent 自动调试代码
   - 增量构建分析流程

典型工作流：
```python
# 创建报告
notebook_edit(notebook_path="guangzhou_analysis.ipynb", cell_id="cell-0", edit_mode="insert", cell_type="markdown", new_source="# 广州O3污染溯源分析")

# 插入数据加载
notebook_edit(notebook_path="guangzhou_analysis.ipynb", cell_id="cell-0", edit_mode="insert", cell_type="code", new_source="import sys\\nsys.path.append('/home/xckj/suyuan/backend')\\nfrom app.tools.query.query_standard_report.tool import get_standard_report_data")

# 插入 PMF 分析
notebook_edit(notebook_path="guangzhou_analysis.ipynb", cell_id="cell-1", edit_mode="insert", cell_type="code", new_source="from app.tools.analysis.calculate_pm_pmf.tool import pmf_source_apportionment")

# 插入分析结论
notebook_edit(notebook_path="guangzhou_analysis.ipynb", cell_id="cell-10", edit_mode="insert", cell_type="markdown", new_source="## 分析结论\\n\\n根据 PMF 模型分析，O3 主要来源为...")
```

重要：
- 必须先用 read_file 读取 notebook 文件
- insert 模式必须指定 cell_type (code/markdown)
- 与 execute_python_tool 配合使用
- 与数据分析工具链(PMF/OBM/可视化)配合使用
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "notebook_path": {
                        "type": "string",
                        "description": "Jupyter Notebook 文件的绝对路径（.ipynb 文件）。示例：'D:/溯源/reports/guangzhou_analysis.ipynb' 或 'reports/guangzhou_analysis.ipynb'"
                    },
                    "cell_id": {
                        "type": "string",
                        "description": "目标单元格ID或索引（如 'cell-0'、'cell-1'）。insert模式可选（默认在开头插入）。示例：'cell-0'（第一个单元格）、'cell-5'（第六个单元格）"
                    },
                    "new_source": {
                        "type": "string",
                        "description": "新的单元格内容。replace/delete模式可选。支持多行代码，换行符使用 \\\\n。示例：'import pandas as pd\\\\ndf = pd.read_csv(\\\"data.csv\\\")'"
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
            description="编辑 Jupyter Notebook (.ipynb) 文件的单元格（专家模式 - 数据分析专用）",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="2.0.0",
            requires_context=True  # ✅ 专家模式需要 Context
        )

        # 复用核心实现
        self.core_tool = get_notebook_edit_tool()

    async def execute(
        self,
        context: Optional['ExecutionContext'] = None,
        notebook_path: str = None,
        new_source: str = None,
        cell_id: str = None,
        cell_type: str = "code",
        edit_mode: str = "replace",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 Notebook 编辑操作（专家模式）

        专家模式增强功能：
        1. 自动记录到任务列表（如果可用）
        2. 支持 Context 数据引用
        3. 与数据分析工具链集成

        Args:
            context: ExecutionContext（专家模式提供）
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
            # 1. 记录任务到任务列表（如果可用）
            if context and hasattr(context, 'task_list') and context.task_list:
                task_list = context.task_list
                task_content = f"编辑 Notebook: {notebook_path} ({edit_mode})"
                if cell_id:
                    task_content += f" - 单元格 {cell_id}"

                task_id = task_list.add_task(
                    content=task_content,
                    metadata={
                        "tool": "notebook_edit",
                        "mode": edit_mode,
                        "cell_type": cell_type,
                        "notebook_path": notebook_path
                    }
                )

                logger.info(
                    "notebook_edit_task_created",
                    task_id=task_id,
                    notebook_path=notebook_path,
                    edit_mode=edit_mode
                )

            # 2. 调用核心工具
            result = await self.core_tool.execute(
                notebook_path=notebook_path,
                new_source=new_source,
                cell_id=cell_id,
                cell_type=cell_type,
                edit_mode=edit_mode,
                **kwargs
            )

            # 3. 如果成功，更新任务状态
            if result.get("success") and context and hasattr(context, 'task_list') and context.task_list:
                task_list.update_task_status(
                    task_id=task_id,
                    status="completed"
                )
            elif not result.get("success") and context and hasattr(context, 'task_list') and context.task_list:
                task_list.update_task_status(
                    task_id=task_id,
                    status="failed",
                    error_message=result.get("summary", "Unknown error")
                )

            # 4. 返回结果
            return result

        except Exception as e:
            logger.error(
                "notebook_edit_expert_failed",
                notebook_path=notebook_path,
                error=str(e),
                exc_info=True
            )

            # 更新任务状态为失败
            if context and hasattr(context, 'task_list') and context.task_list:
                try:
                    task_list.update_task_status(
                        task_id=task_id,
                        status="failed",
                        error_message=str(e)
                    )
                except:
                    pass

            return {
                "success": False,
                "error": str(e),
                "summary": f"编辑 Notebook 失败（专家模式）: {str(e)}"
            }

    def is_available(self) -> bool:
        """检查工具是否可用"""
        return self.core_tool.is_available()
