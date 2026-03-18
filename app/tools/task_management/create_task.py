"""
create_task 工具

允许LLM在ReAct循环中动态创建新任务到任务清单。
"""
import structlog
import uuid
from typing import Dict, Any, Optional, List

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()


class CreateTaskTool(LLMTool):
    """创建任务工具"""

    def __init__(self):
        function_schema = {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": (
                    "创建新任务到任务清单。用于复杂任务的拆解和管理。\n\n"
                    "使用场景：\n"
                    "- 当你意识到需要多个步骤完成用户请求时\n"
                    "- 需要按顺序或并行执行多个子任务时\n"
                    "- 需要跟踪长期任务的进度时\n\n"
                    "示例：\n"
                    "用户: '综合分析广州O3污染溯源'\n"
                    "你可以创建任务清单：\n"
                    "1. create_task(subject='获取气象数据', description='获取广州近期气象数据')\n"
                    "2. create_task(subject='分析VOCs组分', description='分析VOCs组分特征', depends_on=['task_001'])\n"
                    "3. create_task(subject='生成溯源报告', description='综合分析结果生成报告', depends_on=['task_001', 'task_002'])"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {
                            "type": "string",
                            "description": "任务标题（简短，10字以内），如'获取气象数据'"
                        },
                        "description": {
                            "type": "string",
                            "description": "任务详细描述（包含具体要求和参数），如'获取广州2024年1月的气象数据，包括温度、风速、风向'"
                        },
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "依赖的任务ID列表（这些任务必须先完成），如['task_001', 'task_002']。如果没有依赖则不传此参数。"
                        }
                    },
                    "required": ["subject", "description"]
                }
            }
        }

        super().__init__(
            name="create_task",
            description="创建新任务到任务清单",
            function_schema=function_schema,
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True  # ✅ 需要 ExecutionContext（用于获取 task_list）
        )
        # ✅ 标记需要 TaskList（不需要 DataContextManager）
        self.requires_task_list = True

    async def execute(
        self,
        context: ExecutionContext,
        subject: str,
        description: str,
        depends_on: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        执行任务创建

        Args:
            context: 执行上下文
            subject: 任务标题
            description: 任务描述
            depends_on: 依赖的任务ID列表

        Returns:
            创建结果
        """
        try:
            # 从context获取task_list
            task_list = context.get_task_list()
            session_id = context.session_id

            # 生成任务ID
            task_id = f"task_{uuid.uuid4().hex[:8]}"

            # 创建任务
            task = task_list.create_task(
                session_id=session_id,
                task_id=task_id,
                subject=subject,
                description=description,
                depends_on=depends_on or [],
                expert_type=None,  # 任务清单模式不使用专家类型
                metadata={
                    "created_by": "llm",
                    "auto_generated": False
                }
            )

            logger.info(
                f"Task created by LLM: task_id={task_id}, "
                f"subject={subject}, depends_on={depends_on}"
            )

            return {
                "status": "success",
                "success": True,
                "data": {
                    "task_id": task.id,
                    "subject": task.subject,
                    "description": task.description,
                    "status": task.status.value,
                    "depends_on": task.depends_on
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "create_task",
                    "field_mapping_applied": False
                },
                "summary": f"已创建任务: {subject} (ID: {task_id})"
            }

        except Exception as e:
            logger.error(f"Failed to create task: {e}", exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "create_task"
                },
                "summary": f"创建任务失败: {str(e)}"
            }


# 创建工具实例
create_task_tool = CreateTaskTool()
