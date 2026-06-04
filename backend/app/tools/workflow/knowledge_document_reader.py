"""
知识文档分块阅读工具。

按知识库文档的chunk序列读取命中块相邻上下文或完整文档文本视图。
"""

from typing import Dict, Any, List, Optional
import structlog

from .workflow_tool import WorkflowTool

logger = structlog.get_logger()


class KnowledgeDocumentReader(WorkflowTool):
    """读取知识库文档的chunk文本视图。"""

    name = "knowledge_document_reader"
    description = (
        "按 knowledge_qa_workflow 返回的 document_read_targets 读取文档 chunks；"
        "可读命中块邻近上下文或全文 chunks。"
    )
    version = "1.0.0"
    category = "knowledge_qa"
    requires_context = False

    async def execute(
        self,
        knowledge_base_id: Optional[str] = None,
        document_id: Optional[str] = None,
        chunk_index: Optional[int] = None,
        chunk_indices: Optional[List[int]] = None,
        mode: str = "neighbor_chunks",
        window: int = 2,
        max_chunks: int = 30
    ) -> Dict[str, Any]:
        self._start_timer()

        if not knowledge_base_id or not document_id:
            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={"error": "缺少必需参数：knowledge_base_id 或 document_id"},
                summary="读取知识文档失败：缺少参数"
            )

        try:
            from app.db.database import async_session
            from app.knowledge_base.service import KnowledgeBaseService

            self._record_step("document_chunks_read_start", "running", {
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "chunk_index": chunk_index,
                "chunk_indices": chunk_indices,
                "mode": mode,
                "window": window,
                "max_chunks": max_chunks
            })

            async with async_session() as db:
                service = KnowledgeBaseService(db=db)
                result = await service.get_document_chunks(
                    kb_id=knowledge_base_id,
                    doc_id=document_id,
                    user_id=None
                )

            all_chunks = result.get("chunks", [])
            selected_chunks = self._select_chunks(
                chunks=all_chunks,
                chunk_index=chunk_index,
                chunk_indices=chunk_indices,
                mode=mode,
                window=max(0, int(window or 0)),
                max_chunks=max(1, int(max_chunks or 1))
            )

            self._record_step("document_chunks_read_complete", "success", {
                "selected_count": len(selected_chunks),
                "total_chunks": len(all_chunks)
            })

            data = {
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "filename": result.get("filename", ""),
                "mode": mode,
                "window": window,
                "total_chunks": len(all_chunks),
                "returned_chunks": len(selected_chunks),
                "chunks": selected_chunks,
                "reading_scope": {
                    "chunk_indices": [chunk.get("chunk_index") for chunk in selected_chunks],
                    "is_full_document": mode == "all_chunks" and len(selected_chunks) == len(all_chunks)
                }
            }

            return self._build_udf_v2_result(
                status="success",
                success=True,
                data=data,
                summary=f"已读取文档chunk文本视图：返回{len(selected_chunks)}/{len(all_chunks)}个chunks",
                extra_metadata={
                    "retrieval_only": True,
                    "document_id": document_id,
                    "returned_chunks": len(selected_chunks)
                }
            )

        except Exception as e:
            logger.error(
                "knowledge_document_reader_failed",
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                error=str(e),
                exc_info=True
            )
            self._record_step("document_chunks_read_failed", "failed", {"error": str(e)})
            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={
                    "knowledge_base_id": knowledge_base_id,
                    "document_id": document_id,
                    "error": str(e)
                },
                summary=f"读取知识文档失败: {str(e)}"
            )

    def _select_chunks(
        self,
        chunks: List[Dict[str, Any]],
        chunk_index: Optional[int],
        chunk_indices: Optional[List[int]],
        mode: str,
        window: int,
        max_chunks: int
    ) -> List[Dict[str, Any]]:
        if mode == "all_chunks":
            return chunks[:max_chunks]

        requested = []
        if chunk_indices:
            requested.extend(int(index) for index in chunk_indices if index is not None)
        elif chunk_index is not None:
            requested.append(int(chunk_index))

        if not requested:
            return chunks[:max_chunks]

        selected_indices = set()
        for index in requested:
            start = max(0, index - window)
            end = index + window
            selected_indices.update(range(start, end + 1))

        selected = [
            chunk for chunk in chunks
            if int(chunk.get("chunk_index", -1)) in selected_indices
        ]
        return selected[:max_chunks]

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "knowledge_base_id": {
                        "type": "string",
                        "description": "知识库ID"
                    },
                    "document_id": {
                        "type": "string",
                        "description": "文档ID"
                    },
                    "chunk_index": {
                        "type": "integer",
                        "description": "单个命中chunk索引"
                    },
                    "chunk_indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "命中的多个chunk索引"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["neighbor_chunks", "all_chunks"],
                        "description": "读取模式",
                        "default": "neighbor_chunks"
                    },
                    "window": {
                        "type": "integer",
                        "description": "邻近窗口",
                        "default": 2,
                        "minimum": 0,
                        "maximum": 10
                    },
                    "max_chunks": {
                        "type": "integer",
                        "description": "返回chunk上限",
                        "default": 30,
                        "minimum": 1,
                        "maximum": 200
                    }
                },
                "required": ["knowledge_base_id", "document_id"]
            }
        }
