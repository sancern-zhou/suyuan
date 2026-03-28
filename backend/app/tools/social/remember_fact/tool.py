"""
记住重要事实工具

核心功能：
- 记住用户偏好、重要结论到MEMORY.md
- 持久化存储，长期保留
"""

from typing import Dict, Any, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class RememberFactTool(LLMTool):
    """
    记住重要事实工具

    用途：
    - 用户偏好（如"关注PM2.5"）
    - 重要结论（如"广州O3污染主要来自VOCs"）
    - 关键数据（如"2024年AQI达标率85%"）
    """

    def __init__(self, memory_store=None):
        # 定义 function_schema
        function_schema = {
            "name": "remember_fact",
            "description": "记住重要事实到长期记忆（用户偏好、重要结论、关键数据）",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "要记住的事实内容"
                    },
                    "category": {
                        "type": "string",
                        "description": "分类（如'user_preference'=用户偏好, 'conclusion'=重要结论, 'data'=关键数据）",
                        "default": "general",
                        "enum": ["user_preference", "conclusion", "data", "general"]
                    }
                },
                "required": ["fact"]
            }
        }

        # 初始化基类
        super().__init__(
            name="remember_fact",
            description="记住重要事实到长期记忆（用户偏好、重要结论、关键数据）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        self.memory_store = memory_store

    async def execute(
        self,
        fact: str = None,
        category: str = "general",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行记住事实

        Args:
            fact: 事实内容
            category: 分类

        Returns:
            {
                "status": "success" | "failed",
                "success": true|false,
                "category": "分类",
                "summary": "简要总结"
            }
        """
        # 参数验证
        if not fact:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少事实内容"
            }

        try:
            # ✅ 获取当前用户ID
            from app.social.message_bus_singleton import get_current_chat_id, get_current_channel

            channel = get_current_channel()
            chat_id = get_current_chat_id()

            if not channel or not chat_id:
                # 如果无法获取用户信息，使用传入的 memory_store（向后兼容）
                if self.memory_store:
                    success = self.memory_store.remember_fact(
                        fact=fact,
                        category=category
                    )
                else:
                    logger.info(
                        "fact_remembered_log_only",
                        fact=fact,
                        category=category
                    )
                    success = True
            else:
                # ✅ 使用 UserMemoryManager 获取用户专属记忆
                from app.social.message_bus_singleton import get_message_bus

                message_bus = get_message_bus()

                if not message_bus or not message_bus.agent_bridge:
                    return {
                        "status": "failed",
                        "success": False,
                        "summary": "AgentBridge 未初始化"
                    }

                agent_bridge = message_bus.agent_bridge

                if not agent_bridge.user_memory_manager:
                    return {
                        "status": "failed",
                        "success": False,
                        "summary": "用户记忆管理器未初始化"
                    }

                # 获取机器人账号并构建用户ID
                bot_account = await agent_bridge._get_bot_account(channel)
                user_id = f"{channel}:{bot_account}:{chat_id}"

                # 获取用户专属 MemoryStore
                memory_store = await agent_bridge.user_memory_manager.get_user_memory(user_id)
                success = memory_store.remember_fact(fact=fact, category=category)

            logger.info(
                "fact_remembered",
                category=category,
                fact_length=len(fact)
            )

            return {
                "status": "success",
                "success": True,
                "category": category,
                "summary": f"已记住：{fact[:50]}..."
            }

        except Exception as e:
            logger.error(
                "failed_to_remember_fact",
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "summary": f"记住事实失败：{str(e)}"
            }
