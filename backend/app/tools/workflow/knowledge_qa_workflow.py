"""
知识库检索工作流 (KnowledgeQAWorkflow)

从知识库中检索相关文档，为主Agent提供参考资料。

设计理念：
- 只负责检索，不生成回答
- 主Agent根据检索结果和对话上下文生成最终回答
- 避免重复LLM调用，提高效率

流程：
1. 检索：基于原问题或主Agent补充后的关键词从知识库检索相关文档
2. 可选精排：按 reranker 参数决定是否启用 CrossEncoder
3. 返回：将检索结果返回给主Agent

适用场景：
- 需要查询专业标准、规范、技术文档
- 需要参考政策法规、学术文献
- 需要获取专业领域的权威资料

参数：
- query: 用户问题
- knowledge_base_ids: 知识库ID列表（可选，默认使用所有可用知识库）
- top_k: 检索文档数量（默认3）
- reranker: 精排模式，auto/always/never，默认auto

返回：
标准UDF v2.0格式，包含：
- query: 原始查询
- sources: 检索到的文档列表
- total_retrieved: 检索到的文档总数
- retrieval_summary: 检索结果摘要
"""

from typing import Dict, Any, List, Optional
import structlog

from .workflow_tool import WorkflowTool

logger = structlog.get_logger()


def _build_document_read_targets(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按文档聚合命中chunk，给Agent后续阅读相邻块或全文块的目标。"""
    targets_by_key: Dict[tuple, Dict[str, Any]] = {}

    for doc in documents:
        kb_id = doc.get("knowledge_base_id")
        doc_id = doc.get("document_id")
        if not kb_id or not doc_id:
            continue

        key = (kb_id, doc_id)
        chunk_index = doc.get("chunk_index")
        target = targets_by_key.setdefault(key, {
            "knowledge_base_id": kb_id,
            "knowledge_base_name": doc.get("knowledge_base_name", ""),
            "document_id": doc_id,
            "document_name": doc.get("document_name", ""),
            "matched_chunk_indices": [],
            "matched_sections": [],
            "matched_topics": [],
            "best_score": doc.get("score", 0.0),
            "suggested_reading": {
                "default_mode": "neighbor_chunks",
                "neighbor_window": 2,
                "full_document_mode": "all_chunks",
                "reader_tool": "knowledge_document_reader"
            },
            "read_reason": "命中chunk只是定位证据；严肃知识问答应按document_id和chunk_index读取相邻块后再回答。"
        })

        if chunk_index is not None and chunk_index not in target["matched_chunk_indices"]:
            target["matched_chunk_indices"].append(chunk_index)

        section = doc.get("section")
        if section and section not in target["matched_sections"]:
            target["matched_sections"].append(section)

        topic = doc.get("topic")
        if topic and topic not in target["matched_topics"]:
            target["matched_topics"].append(topic)

        target["best_score"] = max(float(target.get("best_score") or 0), float(doc.get("score") or 0))

    targets = list(targets_by_key.values())
    for target in targets:
        target["matched_chunk_indices"].sort()

    targets.sort(key=lambda item: item.get("best_score", 0), reverse=True)
    return targets


class KnowledgeQAWorkflow(WorkflowTool):
    """
    知识库检索工作流

    从知识库中检索相关文档，为主Agent提供参考资料。
    只负责检索，不生成回答。
    """

    name = "knowledge_qa_workflow"
    description = """知识库检索工具 - 从知识库中检索相关文档

从知识库中检索与用户问题相关的文档片段，为主Agent提供参考资料。

技术特点：
- 语义检索：基于向量相似度的智能检索
- 混合检索：dense+sparse融合，适合标准号和关键词查询
- 按需精排：auto模式仅在粗召回不够确定时启用Reranker
- 多源融合：从多个知识库中检索相关文档

知识库内容：
- 大气环境标准规范
- 污染防治技术指南
- 监测分析方法
- 政策法规文件
- 学术文献资料

适用场景：
- 需要查询专业标准、规范、技术文档
- 需要参考政策法规、学术文献
- 需要获取专业领域的权威资料

参数：
- query: 用户问题（自然语言描述）
- knowledge_base_ids: 知识库ID列表（可选，默认使用所有可用知识库）
- top_k: 检索文档数量（默认3，最多10）
- reranker: 精排模式，auto/always/never，默认auto。标准号、明确查询建议auto或never；法规条款、跨文档对比、低置信召回可用always。

返回：检索到的文档列表（包含文档内容、来源、相关度等信息）
注意：此工具只负责检索，不生成回答。主Agent应使用检索结果生成最终回答。
"""
    version = "1.0.0"
    category = "knowledge_qa"
    requires_context = False

    def __init__(self):
        """初始化知识问答工作流"""
        super().__init__()

    async def execute(
        self,
        query: Optional[str] = None,
        question: Optional[str] = None,  # 别名，兼容 LLM 调用
        session_id: Optional[str] = None,
        knowledge_base_ids: Optional[List[str]] = None,  # 知识库ID列表
        top_k: int = 3,
        reranker: str = "auto"
    ) -> Dict[str, Any]:
        """
        执行知识库检索

        Args:
            query: 用户问题
            question: 用户问题（别名，兼容 LLM 调用）
            session_id: 会话ID（可选，当前未使用）
            knowledge_base_ids: 知识库ID列表（可选）
            top_k: 检索文档数量
            reranker: 精排模式，auto/always/never

        Returns:
            标准UDF v2.0格式，包含检索结果
        """
        self._start_timer()

        # 参数别名处理：LLM 可能传递 question 而不是 query
        actual_query = query or question
        if not actual_query:
            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={
                    "query": None,
                    "sources": [],
                    "total_retrieved": 0,
                    "error": "缺少必需参数：query 或 question"
                },
                summary="知识检索失败：缺少查询参数"
            )

        try:
            self._record_step("knowledge_retrieval_start", "running", {
                "query": actual_query[:100] if actual_query else "",
                "session_id": session_id,
                "top_k": top_k,
                "reranker": reranker
            })

            # 导入检索函数
            from app.routers.knowledge_qa import search_knowledge_bases

            # 1. 检索相关文档。HyDE不再由workflow双路触发；需要扩展词时由主Agent拼入query。
            self._record_step("knowledge_retrieval", "running")
            search_results = await search_knowledge_bases(
                query=actual_query,
                knowledge_base_ids=knowledge_base_ids,  # 传递知识库ID列表
                use_hyde=False,
                use_reranker=reranker,
                top_k=min(top_k, 10)  # 限制最大10篇
            )

            # search_results 是一个列表，不是字典
            documents = search_results if search_results else []
            self._record_step("knowledge_retrieval", "success", {
                "retrieved_count": len(documents)
            })

            if not documents:
                # 没有检索到相关文档
                return self._build_udf_v2_result(
                    status="empty",
                    success=True,
                    data={
                        "query": actual_query,
                        "sources": [],
                        "total_retrieved": 0,
                        "retrieval_summary": "未在知识库中找到相关文档"
                    },
                    summary="未检索到相关文档",
                    extra_metadata={
                        "retrieval_only": True,
                        "documents_count": 0
                    }
                )

            # ✅ 不生成回答，只返回检索结果，让主 Agent 决定如何使用
            # 构建来源信息（用于data字段）
            sources = []
            retrieval_metadata = documents[0].get("retrieval_metadata", {}) if documents else {}
            document_read_targets = _build_document_read_targets(documents)
            for doc in documents[:5]:  # 最多返回5篇参考文档
                # 获取完整内容，不再截断
                content = doc.get("content", "")
                sources.append({
                    "title": doc.get("document_name", "未知标题"),
                    "source": doc.get("knowledge_base_name", "未知来源"),
                    "relevance": doc.get("score", 0.0),
                    "rerank_score": doc.get("rerank_score"),
                    "original_score": doc.get("original_score"),
                    "document_id": doc.get("document_id"),
                    "document": doc.get("document", {}),
                    "has_original_file": doc.get("has_original_file", False),
                    "download_url": doc.get("download_url"),
                    "preview_url": doc.get("preview_url"),
                    "knowledge_base_id": doc.get("knowledge_base_id"),
                    "chunk_index": doc.get("chunk_index"),
                    "section": doc.get("section"),
                    "topic": doc.get("topic"),
                    "retrieval_route": doc.get("retrieval_route"),
                    "retrieval_routes": doc.get("retrieval_routes", []),
                    "retrieval_metadata": doc.get("retrieval_metadata", {}),
                    "content": content  # 返回完整内容
                })

            self._record_step("knowledge_retrieval_complete", "success", {
                "sources_count": len(sources),
                "total_retrieved": len(documents)
            })

            # 构建数据：只返回检索结果，不生成回答
            data = {
                "query": actual_query,
                "sources": sources,
                "document_read_targets": document_read_targets,
                "reading_requirement": {
                    "applies_to": "严肃知识问答、标准条款解释、计算方法、表格/公式解读、跨章节总结",
                    "required_action": "按document_read_targets中的document_id和matched_chunk_indices，调用knowledge_document_reader读取相邻chunks；需要全文概括时读取all_chunks。",
                    "do_not_answer_from_chunks_only": True
                },
                "total_retrieved": len(documents),
                "retrieval_metadata": retrieval_metadata,
                "retrieval_summary": f"从知识库中检索到 {len(documents)} 篇相关文档"
            }

            # ❌ 移除 can_be_final_answer 标记，让主 Agent 决定如何使用检索结果
            return self._build_udf_v2_result(
                status="success",
                success=True,
                data=data,
                summary=f"知识检索完成，找到{len(documents)}篇相关文档",
                extra_metadata={
                    "retrieval_only": True,  # ✅ 标记：仅检索，不生成回答
                    "documents_count": len(documents),
                    "document_read_targets_count": len(document_read_targets),
                    "retrieval_metadata": retrieval_metadata
                }
            )

        except Exception as e:
            logger.error(
                "knowledge_qa_workflow_failed",
                query=actual_query[:100] if actual_query else "",
                error=str(e),
                exc_info=True
            )

            self._record_step("knowledge_retrieval_failed", "failed", {
                "error": str(e)
            })

            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={
                    "query": actual_query,
                    "sources": [],
                    "total_retrieved": 0,
                    "error": str(e)
                },
                summary=f"知识检索失败: {str(e)}"
            )

    def get_function_schema(self) -> Dict[str, Any]:
        """
        生成OpenAI Function Schema

        Returns:
            OpenAI Function Schema格式
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用户问题，自然语言描述，如 'HJ 906-2017 数据有效性是如何定义的' 或 'PM2.5的日均值标准是多少？'"
                    },
                    "question": {
                        "type": "string",
                        "description": "用户问题（别名，与query二选一）"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话ID（当前未使用，保留用于未来扩展）"
                    },
                    "knowledge_base_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "知识库ID列表（可选，不指定则使用所有可用知识库）"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "检索文档数量，默认3，最多10",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 10
                    },
                    "reranker": {
                        "type": "string",
                        "enum": ["auto", "always", "never"],
                        "description": "Reranker精排模式。auto默认按粗召回置信度决定；always强制精排；never跳过精排。",
                        "default": "auto"
                    }
                },
                "required": []  # query 和 question 都可选，因为有一个即可
            }
        }
