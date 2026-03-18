"""
知识问答工作流 (KnowledgeQAWorkflow)

基于知识库的专业问答系统，使用RAG（检索增强生成）技术。

流程：
1. HyDE（Hypothetical Document Embeddings）：生成假设性答案
2. 检索：基于假设性答案从知识库检索相关文档
3. 生成：基于检索结果生成最终回答

适用场景：
- 大气环境专业知识问答
- 标准规范查询
- 技术文档问答
- 政策法规咨询

参数：
- query: 用户问题
- session_id: 会话ID（可选，用于连续对话）
- top_k: 检索文档数量（默认3）

返回：
标准UDF v2.0格式，包含：
- answer: 生成的回答
- sources: 参考文档列表
"""

from typing import Dict, Any, List, Optional
import structlog

from .workflow_tool import WorkflowTool

logger = structlog.get_logger()


class KnowledgeQAWorkflow(WorkflowTool):
    """
    知识问答工作流

    基于知识库的专业问答系统，使用RAG技术。
    """

    name = "knowledge_qa_workflow"
    description = """知识问答工作流 - 基于知识库的专业问答

基于知识库的专业问答系统，使用RAG（检索增强生成）技术提供准确、专业的回答：

技术特点：
- HyDE技术：生成假设性答案，提高检索准确性
- 语义检索：基于向量相似度的智能检索
- 多源融合：综合多个文档的信息生成回答
- 连续对话：支持上下文理解的连续对话

知识库内容：
- 大气环境标准规范
- 污染防治技术指南
- 监测分析方法
- 政策法规文件
- 学术文献资料

适用场景：
- 大气环境专业知识问答
- 标准规范查询
- 技术文档问答
- 政策法规咨询
- 分析方法查询

参数：
- query: 用户问题（自然语言描述）
- session_id: 会话ID（可选，用于连续对话）
- top_k: 检索文档数量（默认3，最多10）

返回：专业回答 + 参考文档列表
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
        top_k: int = 3
    ) -> Dict[str, Any]:
        """
        执行知识问答

        Args:
            query: 用户问题
            question: 用户问题（别名，兼容 LLM 调用）
            session_id: 会话ID（可选）
            top_k: 检索文档数量

        Returns:
            标准UDF v2.0格式
        """
        self._start_timer()

        # 参数别名处理：LLM 可能传递 question 而不是 query
        actual_query = query or question
        if not actual_query:
            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={
                    "answer": "缺少必需参数：query 或 question",
                    "sources": []
                },
                summary="知识问答失败：缺少查询参数"
            )

        try:
            self._record_step("knowledge_qa_start", "running", {
                "query": actual_query[:100] if actual_query else "",
                "session_id": session_id,
                "top_k": top_k
            })

            # 导入RAG相关函数
            from app.routers.knowledge_qa import (
                search_knowledge_bases,
                build_rag_prompt
            )
            from app.services.llm_service import llm_service

            # 1. 检索相关文档（使用HyDE，关闭重排序以提高速度）
            self._record_step("knowledge_retrieval", "running")
            search_results = await search_knowledge_bases(
                query=actual_query,
                knowledge_base_ids=knowledge_base_ids,  # 传递知识库ID列表
                use_hyde=True,  # 使用HyDE检索，会自动生成假设答案
                use_reranker=False,  # 关闭重排序以提高速度
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
                        "answer": "抱歉，未在知识库中找到相关内容。可能原因：1) 未选择知识库 2) 知识库中没有相关内容。请先选择相关知识库，或尝试更换关键词。",
                        "sources": []
                    },
                    summary="未检索到相关文档"
                )

            # 3. 生成最终回答
            self._record_step("answer_generation", "running")
            prompt = build_rag_prompt(actual_query, documents)

            # ✅ 知识库问答LLM调用上下文日志
            logger.info(
                "knowledge_qa_llm_call",
                query=actual_query[:100] if len(actual_query) > 100 else actual_query,
                documents_count=len(documents),
                prompt_length=len(prompt),
            )

            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # 较低温度，更确定性
                max_tokens=2048
            )

            self._record_step("answer_generation", "success", {
                "answer_length": len(response) if response else 0
            })

            # 构建来源信息（用于data字段）
            sources = []
            for doc in documents[:5]:  # 最多返回5篇参考文档
                # 获取完整内容，不再截断
                content = doc.get("content", "")
                sources.append({
                    "title": doc.get("document_name", "未知标题"),
                    "source": doc.get("knowledge_base_name", "未知来源"),
                    "relevance": doc.get("score", 0.0),
                    "document_id": doc.get("document_id"),
                    "knowledge_base_id": doc.get("knowledge_base_id"),
                    "chunk_index": doc.get("chunk_index"),
                    "content": content  # 返回完整内容
                })

            self._record_step("knowledge_qa_complete", "success", {
                "sources_count": len(sources),
                "total_retrieved": len(documents)
            })

            # 构建数据
            data = {
                "answer": response.strip(),
                "sources": sources,
                "total_retrieved": len(documents)
            }

            return self._build_udf_v2_result(
                status="success",
                success=True,
                data=data,
                summary=f"知识问答完成，基于{len(documents)}篇文档",
                extra_metadata={
                    "can_be_final_answer": True,  # ✅ 标记：可直接作为final answer
                    "final_answer_field": "answer"  # ✅ 指定final answer字段
                }
            )

        except Exception as e:
            logger.error(
                "knowledge_qa_workflow_failed",
                query=actual_query[:100] if actual_query else "",
                error=str(e),
                exc_info=True
            )

            self._record_step("knowledge_qa_failed", "failed", {
                "error": str(e)
            })

            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={
                    "answer": f"知识问答失败: {str(e)}",
                    "sources": []
                },
                summary=f"知识问答失败: {str(e)}"
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
                        "description": "用户问题，自然语言描述，如 'PM2.5的日均值标准是多少？' 或 'VOCs的主要来源有哪些？'"
                    },
                    "question": {
                        "type": "string",
                        "description": "用户问题（别名，与query二选一）"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话ID，用于连续对话（可选）"
                    },
                    "knowledge_base_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "知识库ID列表（可选）"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "检索文档数量，默认3，最多10",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 10
                    }
                },
                "required": []  # query 和 question 都可选，因为有一个即可
            }
        }
