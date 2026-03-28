"""Spawn tool for creating background subagent tasks.

Allows Agent to create long-running background tasks without blocking
the main conversation.
"""

from typing import Dict, Any, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class SpawnTool(LLMTool):
    """
    Spawn tool for creating background subagent tasks.

    The spawn tool allows the Agent to create a background subagent that
    executes a long-running task independently. The main conversation is
    not blocked, and the user receives a notification when the task completes.

    Example use cases:
    - PMF source analysis (10-20 minutes)
    - OBM/OFP analysis (5-10 minutes)
    - Batch data processing (30-40 minutes)
    """

    def __init__(self):
        """Initialize spawn tool."""
        # Define function schema
        function_schema = {
            "name": "spawn",
            "description": """
            创建后台子Agent执行长时间任务（不阻塞主对话，任务完成后主动通知）

            使用场景：
            - PMF源解析（预计10-20分钟）
            - OBM/OFP分析（预计5-10分钟）
            - 批量数据处理（预计30-40分钟）
            - 其他耗时超过2分钟的分析任务

            工作流程：
            1. 创建后台任务，返回任务ID
            2. 任务在后台独立执行（不阻塞主对话）
            3. 任务完成后主动通知用户（微信消息）

            注意事项：
            - 每个用户最多5个并发任务
            - 任务超时时间默认1小时（可调整60-86400秒）
            - 后台任务使用独立会话，不影响主对话记忆
            """,
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "任务描述（必填，如：对广州超级站2024-01数据进行PMF源解析）"
                    },
                    "label": {
                        "type": "string",
                        "description": "任务标签（可选，如：PMF源解析，用于通知消息标题）"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒，默认3600，范围60-86400）",
                        "minimum": 60,
                        "maximum": 86400,
                        "default": 3600
                    }
                },
                "required": ["task"]
            }
        }

        # Initialize base class
        super().__init__(
            name="spawn",
            description="创建后台子Agent执行长时间任务（不阻塞主对话）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        # SubagentManager will be injected via singleton
        self._manager = None

    @property
    def manager(self):
        """Get SubagentManager from singleton."""
        if self._manager is None:
            from app.social.subagent_singleton import get_subagent_manager
            self._manager = get_subagent_manager()
        return self._manager

    async def execute(
        self,
        task: str = None,
        label: str = None,
        timeout: int = 3600,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute the spawn tool.

        Args:
            task: Task description (required)
            label: Optional task label
            timeout: Timeout in seconds (default: 3600)

        Returns:
            Result dict with task_id and summary
        """
        # Validate required parameters
        if not task:
            return {
                "status": "error",
                "success": False,
                "error": "缺少必填参数：task（任务描述）"
            }

        # Validate timeout
        if not isinstance(timeout, int) or timeout < 60 or timeout > 86400:
            timeout = 3600

        # Get SubagentManager
        manager = self.manager
        if not manager:
            return {
                "status": "error",
                "success": False,
                "error": "SubagentManager未初始化，请检查系统配置"
            }

        # Get current context information
        from app.social.message_bus_singleton import get_current_chat_id, get_current_channel

        chat_id = get_current_chat_id()
        channel = get_current_channel()

        if not chat_id or not channel:
            return {
                "status": "error",
                "success": False,
                "error": "无法获取当前会话信息（chat_id或channel为空）"
            }

        # Build social_user_id
        # Format: {channel}:{bot_account}:{sender_id}
        # For now, we use a simplified format since we don't have bot_account here
        social_user_id = f"{channel}:default:{chat_id}"

        try:
            # Spawn the subagent
            result = await manager.spawn_subagent(
                task=task,
                social_user_id=social_user_id,
                origin_channel=channel,
                origin_chat_id=chat_id,
                origin_sender_id=chat_id,  # For weixin, chat_id = sender_id
                label=label,
                timeout=timeout
            )

            if not result.get("success"):
                return {
                    "status": "error",
                    "success": False,
                    "error": result.get("error", "创建后台任务失败")
                }

            # Format success response
            task_id = result["task_id"]
            task_label = result.get("label", "后台任务")

            summary = f"""已创建后台任务「{task_label}」

任务ID: {task_id}
状态: 执行中
超时: {timeout}秒

任务将在后台执行，完成后会主动通知您。
您可以继续提问，不会影响任务执行。"""

            return {
                "status": "success",
                "success": True,
                "task_id": task_id,
                "label": task_label,
                "summary": summary
            }

        except Exception as e:
            logger.error(
                "spawn_tool_failed",
                task=task,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "error",
                "success": False,
                "error": f"创建后台任务失败: {str(e)}"
            }
