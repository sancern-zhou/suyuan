"""
TodoWrite Tool - Simple task management tool

Replaces the 4-tool task management system with a single complete-replacement tool.

Key improvements:
- Single tool instead of 4 (create_task, update_task, list_tasks, get_task)
- 2 fields instead of 15+ (content, status)
- Complete replacement mode instead of incremental updates
- Constraints: max 20 items, one in_progress at a time
- Simple text rendering output

Usage example:
    TodoWrite(items=[
        {"content": "读取Excel文件", "status": "completed"},
        {"content": "分析数据", "status": "in_progress"},
        {"content": "生成报告", "status": "pending"}
    ])
"""

import structlog
from typing import Dict, Any, List

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()


class TodoWriteTool(LLMTool):
    """TodoWrite tool for simple task management"""

    def __init__(self):
        function_schema = {
            "name": "TodoWrite",
            "description": (
                "更新任务清单（完整替换）。复杂任务或3步以上流程使用；最多20项，"
                "同时只能一个in_progress，每项包含content和status。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_list_file": {
                        "type": "string",
                        "description": "任务清单模板路径，可选；建议优先直接传items"
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "任务描述，简短明确"
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                    "description": "任务状态：pending/in_progress/completed"
                                }
                            },
                            "required": ["content", "status"]
                        },
                        "description": "任务列表（完整替换，不是增量更新）"
                    }
                },
                "required": ["items"]
            }
        }

        super().__init__(
            name="TodoWrite",
            description="更新任务清单（完整替换模式）",
            function_schema=function_schema,
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True
        )
        # Mark that we need todo_list from context
        self.requires_task_list = True

    async def execute(
        self,
        context: ExecutionContext,
        items: List[Dict[str, str]] = None,
        task_list_file: str = None
    ) -> Dict[str, Any]:
        """
        Execute TodoWrite tool

        Args:
            context: Execution context
            items: List of todo items (optional if task_list_file provided)
            task_list_file: Path to task list file (optional)

        Returns:
            Execution result with rendered todo list
        """
        try:
            # Import TodoList
            from app.agent.task.todo_models import TodoList

            # If task_list_file provided, parse tasks from file
            if task_list_file:
                items = await self._parse_task_list_from_file(task_list_file)

            if not items:
                raise ValueError("必须提供 items 或 task_list_file 参数")

            # Get todo_list from context
            todo_list = context.get_task_list()

            # Check if this is the old TaskList or new TodoList
            if todo_list is None:
                # Create new TodoList
                todo_list = TodoList()
            elif not isinstance(todo_list, TodoList):
                # This is the old TaskList, create new TodoList instead
                logger.info("converting_old_tasklist_to_new_todolist")
                todo_list = TodoList()

            # Update todo list
            rendered = todo_list.update(items)

            logger.info(
                "todowrite_executed",
                session_id=context.session_id,
                item_count=len(items),
                rendered_summary=rendered.split('\n')[-1] if rendered else ""
            )

            return {
                "status": "success",
                "success": True,
                "data": {
                    "rendered": rendered,
                    "items": items
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "TodoWrite",
                    "field_mapping_applied": False
                },
                "summary": f"任务清单已更新 ({len(items)} 个任务)"
            }

        except ValueError as e:
            # Validation error (e.g., too many items, multiple in_progress)
            logger.error(f"TodoWrite validation failed: {e}")
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "TodoWrite"
                },
                "summary": f"任务清单更新失败: {str(e)}"
            }
        except Exception as e:
            logger.error(f"TodoWrite execution failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "TodoWrite"
                },
                "summary": f"任务清单更新失败: {str(e)}"
            }

    async def _parse_task_list_from_file(self, file_path: str) -> List[Dict[str, str]]:
        """从Markdown文件解析任务清单（包含详细信息）"""
        import re
        import aiofiles
        import os
        from pathlib import Path

        try:
            # 尝试多个可能的路径
            possible_paths = []

            # 1. 原始路径（可能是绝对路径或相对于当前工作目录）
            possible_paths.append(file_path)

            # 2. 相对于项目根目录（假设backend目录存在）
            current_dir = Path.cwd()
            # 尝试向上查找项目根目录（包含backend目录的父目录）
            for parent in [current_dir, *current_dir.parents]:
                if (parent / "backend").exists():
                    project_root = parent
                    possible_paths.append(str(project_root / file_path))
                    break

            # 3. 尝试从backend目录内部解析
            if "backend/" in file_path or "backend\\" in file_path:
                # 如果路径包含backend/，说明是从项目根目录的相对路径
                for parent in [current_dir, *current_dir.parents]:
                    if (parent / "backend").exists():
                        project_root = parent
                        possible_paths.append(str(project_root / file_path))
                        break

            # 去重并尝试打开文件
            actual_path = None
            for path in set(possible_paths):
                if os.path.exists(path):
                    actual_path = path
                    break

            if not actual_path:
                raise FileNotFoundError(f"文件不存在，尝试的路径: {possible_paths}")

            logger.info(f"找到任务清单文件: {actual_path}")

            async with aiofiles.open(actual_path, 'r', encoding='utf-8') as f:
                content = await f.read()

            tasks = []

            # 匹配任务块（从### 任务N到下一个### 任务或文件结尾）
            task_blocks = re.split(r'### 任务\d+[：:]', content)

            for i, block in enumerate(task_blocks[1:], 1):  # 跳过第一个空块
                # 提取任务标题（第一行）
                lines = block.strip().split('\n')
                title = lines[0].strip() if lines else f"任务{i}"

                # 提取关键信息
                tools_info = ""
                target_info = ""

                # 提取目标
                target_match = re.search(r'\*\*目标\*\*[：:]\s*(.+?)(?=\n|\*\*)', block)
                if target_match:
                    target_info = target_match.group(1).strip()

                # 提取工具调用（从代码块中）
                code_blocks = re.findall(r'```python\n(.*?)```', block, re.DOTALL)
                if code_blocks:
                    # 提取工具名称
                    tool_names = []
                    for code in code_blocks:
                        # 匹配函数调用
                        func_calls = re.findall(r'(\w+)\s*\(', code)
                        tool_names.extend([name for name in func_calls if name not in ['if', 'for', 'while', 'print']])

                    if tool_names:
                        tools_info = f" | 工具: {', '.join(tool_names[:3])}"  # 只显示前3个

                # 构建详细任务描述
                tool_count = len(tool_names) if tool_names else 0
                if tool_count > 0:
                    tools_info = f" | 需调用{tool_count}个工具: {', '.join(tool_names[:3])}"
                else:
                    tools_info = ""

                if target_info:
                    content = f"{title} - {target_info}{tools_info}"
                else:
                    content = f"{title}{tools_info}"

                tasks.append({
                    "content": content,
                    "status": "pending"
                })

            logger.info(f"从文件解析到 {len(tasks)} 个任务（含详细信息）", file=actual_path)
            return tasks

        except Exception as e:
            logger.error(f"解析任务清单文件失败: {e}", file=file_path, exc_info=True)
            raise ValueError(f"无法解析任务清单文件: {str(e)}")


# Create tool instance
todo_write_tool = TodoWriteTool()
