"""
知识库检索工具

作为ReAct Agent的工具节点，支持：
- 多知识库联合检索（公共+个人）
- 语义相似度搜索 + 按需Reranker精排
- 元数据过滤
- UDF v2.0格式输出
"""

from typing import Dict, Any, List, Optional, TYPE_CHECKING
import structlog
import re

from app.tools.base.tool_interface import LLMTool, ToolCategory

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class SearchKnowledgeBaseTool(LLMTool):
    """
    知识库检索工具

    作为ReAct Agent的工具节点，支持：
    - 多知识库联合检索（公共+个人）
    - 语义相似度搜索 + 按需Reranker精排
    - 元数据过滤
    - 混合检索（向量+关键词）
    """

    def __init__(self, db_session_factory=None):
        """
        初始化知识库检索工具

        Args:
            db_session_factory: 数据库会话工厂（可选）
        """
        function_schema = {
            "name": "search_knowledge_base",
            "description": """在用户的私有知识库和公共知识库中检索相关信息。

**何时使用此工具**：
- 用户询问政策法规、排放标准、技术规范
- 需要历史案例、分析报告作为参考
- 涉及企业信息、工艺流程等背景知识
- 用户明确提到"根据知识库"、"查阅资料"

**何时不使用**：
- 实时数据查询（天气、空气质量）-> 使用专用数据工具
- 计算分析任务（PMF、OBM）-> 使用分析工具

参数：
- query: 检索查询（自然语言）
- knowledge_base_ids: 要检索的知识库ID列表（可选，不指定则检索所有可用知识库）
- top_k: 返回结果数量（默认5）
- score_threshold: 相似度阈值（0-1，默认0.5）
- filters: 元数据过滤条件（可选）
- reranker: Reranker精排模式，auto/always/never

返回：
- 相关文档片段列表，包含内容、来源、相似度分数""".strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索查询内容"
                    },
                    "knowledge_base_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "知识库ID列表，不指定则检索所有可访问的知识库"
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "返回结果数量（1-20）"
                    },
                    "score_threshold": {
                        "type": "number",
                        "default": 0.5,
                        "description": "相似度阈值（0-1）"
                    },
                    "filters": {
                        "type": "object",
                        "description": "元数据过滤条件"
                    },
                    "reranker": {
                        "type": "string",
                        "enum": ["auto", "always", "never"],
                        "default": "auto",
                        "description": "Reranker精排模式"
                    },
                    "use_reranker": {
                        "type": "boolean",
                        "description": "兼容旧参数：是否强制使用Reranker精排"
                    }
                },
                "required": ["query"]
            }
        }

        super().__init__(
            name="search_knowledge_base",
            description="Search knowledge base for relevant information",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False  # 不需要ExecutionContext
        )

        self.db_session_factory = db_session_factory

    async def _get_service_with_session(self):
        """
        获取知识库服务（带独立数据库会话）

        Returns:
            (service, db_session) 元组，调用方需要负责关闭会话
        """
        from app.knowledge_base.service import KnowledgeBaseService
        from app.db.database import async_session

        # 使用传入的工厂或默认工厂
        factory = self.db_session_factory or async_session
        db = factory()
        service = KnowledgeBaseService(db=db)

        return service, db

    async def execute(
        self,
        query: str,
        knowledge_base_ids: Optional[List[str]] = None,
        top_k: int = 5,
        score_threshold: float = 0.5,
        filters: Optional[Dict[str, Any]] = None,
        use_reranker: Optional[bool] = None,
        reranker: str = "auto",
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行知识库检索

        Args:
            query: 检索查询
            knowledge_base_ids: 知识库ID列表
            top_k: 返回数量
            score_threshold: 相似度阈值
            filters: 元数据过滤
            use_reranker: 兼容旧参数：是否强制使用Reranker
            reranker: Reranker精排模式，auto/always/never
            user_id: 用户ID（用于权限检查）

        Returns:
            UDF v2.0格式的检索结果
        """
        logger.info(
            "knowledge_base_search_started",
            query=query[:100],
            knowledge_base_ids=knowledge_base_ids,
            top_k=top_k,
            reranker=reranker,
            use_reranker=use_reranker
        )

        # 限制召回数量，避免返回过多结果
        top_k = min(top_k or 3, 3)

        # 获取服务和数据库会话
        service, db = await self._get_service_with_session()

        try:
            # 执行检索
            results = await service.search(
                query=query,
                user_id=user_id,
                knowledge_base_ids=knowledge_base_ids,
                top_k=top_k,
                score_threshold=score_threshold,
                filters=filters,
                use_reranker=use_reranker if use_reranker is not None else reranker
            )

            logger.info(
                "knowledge_base_search_completed",
                query=query[:50],
                result_count=len(results),
                knowledge_bases=knowledge_base_ids
            )

            # 构建摘要，附带可溯源信息（文档名 + 下载/预览链接）
            summary = self._generate_summary(query, results)
            # 补充简要条目，方便LLM直接引用
            preview_items = []
            for r in results[:3]:
                doc = r.get("document", {})
                kb = r.get("knowledge_base", {})
                title = doc.get("filename") or kb.get("name") or "未命名文档"
                download_url = doc.get("download_url")
                preview_items.append(
                    {
                        "title": title,
                        "kb": kb.get("name"),
                        "download_url": download_url,
                        "preview_url": doc.get("preview_url"),
                        "score": r.get("score"),
                    }
                )

            # 在summary中直接追加Top3引用，鼓励前端/LLM显式引用与溯源
            if preview_items:
                lines = []
                for i, item in enumerate(preview_items, 1):
                    line = f"{i}) {item['title']}（{item.get('kb') or '知识库'}）"
                    if item.get("download_url"):
                        line += f" 下载: {item['download_url']}"
                    if item.get("preview_url"):
                        line += f" 预览: {item['preview_url']}"
                    lines.append(line)
                summary = summary + "\nTop3参考:\n" + "\n".join(lines)

            # 生成 display_summary（精简正文片段，去元数据和标题，截断）
            display_summary = self._build_display_summary(results)
            # 生成去重的链接列表（优先 download/preview 成对出现）
            links = self._build_links(preview_items)

            return {
                "status": "success",
                "success": True,
                "data": results,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "search_knowledge_base",
                    "query": query,
                    "knowledge_base_ids": knowledge_base_ids,
                    "result_count": len(results),
                    "top_k": top_k,
                    "score_threshold": score_threshold,
                    "reranker": reranker,
                    "use_reranker": use_reranker,
                    "preview_items": preview_items,  # 供前端/LLM直接引用的简表
                    "display_summary": display_summary,  # 简洁正文片段
                    "links": links,  # 已去重的下载/预览链接
                },
                "summary": summary
            }

        except Exception as e:
            logger.error(
                "knowledge_base_search_failed",
                query=query[:50],
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "error": str(e),
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "search_knowledge_base",
                    "query": query
                },
                "summary": f"知识库检索失败: {str(e)}"
            }

        finally:
            # 确保关闭数据库会话（兼容已被远端关闭的连接）
            try:
                await db.close()
            except Exception as close_err:
                logger.warning(
                    "db_close_failed_safe_ignore",
                    error=str(close_err)
                )

    def _generate_summary(self, query: str, results: List[Dict[str, Any]]) -> str:
        """生成检索结果摘要"""
        if not results:
            return f"未找到与「{query[:30]}」相关的知识库内容"

        # 统计来源
        kb_names = set()
        for r in results:
            kb_info = r.get("knowledge_base", {})
            if kb_info.get("name"):
                kb_names.add(kb_info["name"])

        kb_summary = "、".join(list(kb_names)[:3])
        if len(kb_names) > 3:
            kb_summary += f"等{len(kb_names)}个知识库"

        return f"从{kb_summary}中检索到 {len(results)} 条相关信息"

    def _build_display_summary(self, results: List[Dict[str, Any]], max_len: int = 400) -> str:
        """提取首条 content，移除前缀元数据/标题，并截断"""
        if not results:
            return ""
        content = results[0].get("content") or ""
        if not content:
            return ""
        # 去掉方括号元数据开头
        content = re.sub(r"^\[[^\]]*?\]\s*", "", content, count=1)
        # 去掉开头 Markdown 标题行（如 #### xxx）
        content = re.sub(r"^(#+[^\n]*\n)+", "", content, count=1)
        content = content.lstrip()
        if len(content) > max_len:
            content = content[:max_len] + "…"
        return content

    def _build_links(self, preview_items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """生成去重的链接列表，每条包含 download / preview（若存在）"""
        links = []
        seen = set()
        for item in preview_items:
            dl = item.get("download_url")
            pv = item.get("preview_url")
            title = item.get("title")
            kb = item.get("kb")
            key = f"{dl}|{pv}"
            if key in seen:
                continue
            seen.add(key)
            entry: Dict[str, str] = {
                "title": title,
                "kb": kb,
            }
            if dl:
                entry["download_url"] = dl
            if pv:
                entry["preview_url"] = pv
            links.append(entry)
        return links
