"""
搜索历史对话工具

核心功能：
- 搜索HISTORY.md历史对话
- 支持关键词搜索
- 返回匹配的历史条目
"""

from typing import Dict, Any, Optional, List
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class SearchHistoryTool(LLMTool):
    """
    搜索历史对话工具

    用途：
    - 查找之前的对话内容
    - 回溯历史结论
    - 检索用户偏好设置
    """

    def __init__(self, memory_store=None):
        # 定义 function_schema
        function_schema = {
            "name": "search_history",
            "description": "搜索历史对话（从HISTORY.md中查找相关内容）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50
                    }
                },
                "required": ["query"]
            }
        }

        # 初始化基类
        super().__init__(
            name="search_history",
            description="搜索历史对话（从HISTORY.md中查找相关内容）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        self.memory_store = memory_store

    async def execute(
        self,
        query: str = None,
        limit: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行搜索历史

        Args:
            query: 搜索关键词
            limit: 返回结果数量限制

        Returns:
            {
                "status": "success" | "failed",
                "success": true|false,
                "results": [...],
                "count": 5,
                "summary": "简要总结"
            }
        """
        # 参数验证
        if not query:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少搜索关键词"
            }

        try:
            # ✅ 获取当前用户ID
            from app.social.message_bus_singleton import get_current_chat_id, get_current_channel

            channel = get_current_channel()
            chat_id = get_current_chat_id()

            if not channel or not chat_id:
                # 如果无法获取用户信息，使用传入的 memory_store（向后兼容）
                if self.memory_store:
                    results = self.memory_store.search_history(
                        query=query,
                        limit=limit
                    )
                else:
                    logger.warning(
                        "no_memory_store_available",
                        query=query
                    )
                    results = []
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
                results = memory_store.search_history(query=query, limit=limit)

            logger.info(
                "history_searched",
                query=query,
                results_found=len(results)
            )

            # 格式化结果
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "match": result.get("match", ""),
                    "context": result.get("context", ""),
                    "line_number": result.get("line_number", 0)
                })

            return {
                "status": "success",
                "success": True,
                "results": formatted_results,
                "count": len(formatted_results),
                "summary": f"找到 {len(formatted_results)} 条相关记录"
            }

        except Exception as e:
            logger.error(
                "failed_to_search_history",
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "summary": f"搜索历史失败：{str(e)}"
            }
