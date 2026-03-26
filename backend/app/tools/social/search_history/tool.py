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
            # 如果有MemoryStore，使用MemoryStore
            if self.memory_store:
                results = self.memory_store.search_history(
                    query=query,
                    limit=limit
                )
            else:
                # 降级方案：返回空结果
                logger.warning(
                    "no_memory_store_available",
                    query=query
                )
                results = []

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
