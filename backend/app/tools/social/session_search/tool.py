"""
Session Search Tool

Search agent_runs logs using FTS5 full-text index.
Supports Chinese CJK search with trigram tokenizer.
"""

from typing import Dict, Any, List
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class SessionSearchTool(LLMTool):
    """
    Session Search Tool

    Search historical agent runs from logs/agent_runs/ directory.

    Use cases:
    - Find previous analyses on the same topic
    - Retrieve past query results
    - Review conversation history
    - Check if similar questions were asked before
    """

    def __init__(self):
        function_schema = {
            "name": "session_search",
            "description": "搜索历史会话（从 logs/agent_runs/ 的Agent运行日志中查找相关内容）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（支持中文和英文）"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20
                    },
                    "rebuild": {
                        "type": "boolean",
                        "description": "是否重建索引（首次使用或索引过期时设为true）",
                        "default": False
                    }
                },
                "required": ["query"]
            }
        }

        super().__init__(
            name="session_search",
            description="搜索历史会话（从 logs/agent_runs/ 的Agent运行日志中查找相关内容）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

        self._fts_index = None

    def _get_fts_index(self):
        """Get FTS index instance"""
        if self._fts_index is None:
            from app.tools.social.session_search.fts_index import get_fts_index
            self._fts_index = get_fts_index()
        return self._fts_index

    async def execute(
        self,
        query: str = None,
        limit: int = 5,
        rebuild: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute session search

        Args:
            query: Search keyword
            limit: Maximum results to return
            rebuild: Whether to rebuild the index

        Returns:
            {
                "status": "success" | "failed",
                "success": true|false,
                "results": [...],
                "count": 5,
                "summary": "简要总结"
            }
        """
        # Parameter validation
        if not query:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少搜索关键词"
            }

        limit = min(max(1, limit), 20)

        try:
            fts_index = self._get_fts_index()

            # Rebuild index if requested
            if rebuild:
                logger.info("rebuilding_fts_index")
                indexed_count = fts_index.build_index()
                logger.info("fts_index_rebuilt", count=indexed_count)

            # Ensure index is initialized
            if not fts_index._initialized:
                logger.info("initializing_fts_index")
                indexed_count = fts_index.build_index()
                if indexed_count == 0:
                    return {
                        "status": "empty",
                        "success": True,
                        "results": [],
                        "count": 0,
                        "summary": "索引为空，没有找到历史会话记录"
                    }

            # Execute search
            results = fts_index.search(query, limit)

            logger.info(
                "session_searched",
                query=query,
                results_found=len(results),
                cjk_detected=fts_index._count_cjk(query) > 0
            )

            # Format results
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "run_id": result.get("run_id", ""),
                    "session_id": result.get("session_id", ""),
                    "query_preview": self._truncate_text(result.get("query", ""), 200),
                    "response_preview": self._truncate_text(result.get("response_preview", ""), 300),
                    "start_time": result.get("start_time", ""),
                    "duration_ms": result.get("duration_ms", 0),
                    "status": result.get("status", "")
                })

            return {
                "status": "success",
                "success": True,
                "results": formatted_results,
                "count": len(formatted_results),
                "summary": f"找到 {len(formatted_results)} 条相关会话记录"
            }

        except Exception as e:
            logger.error(
                "failed_to_search_sessions",
                query=query,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "summary": f"搜索会话失败：{str(e)}"
            }

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to max length"""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."
