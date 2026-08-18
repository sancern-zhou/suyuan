"""
知识文档分块阅读工具。

按知识库文档的chunk序列读取命中块相邻上下文或完整文档文本视图。
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog

from app.agent.resources.resource_service import SessionResourceService
from app.tools.resource_declarations import primary_file
from app.utils.path_config import format_agent_path

from .workflow_tool import WorkflowTool
from .enforcement_exam_knowledge import (
    ENFORCEMENT_EXAM_KNOWLEDGE_BASE_NAME,
    is_enforcement_exam_context,
)

logger = structlog.get_logger()


class KnowledgeDocumentReader(WorkflowTool):
    """读取知识库文档文本并发布可预览、可下载的原文资源。"""

    name = "knowledge_document_reader"
    description = (
        "读取知识库文档 chunks，并将数据库中的原文物化到当前会话资源目录；"
        "一次调用即可获得文本上下文和可预览、可下载的原文资源。"
    )
    version = "2.0.0"
    category = "knowledge_qa"
    requires_context = True
    DEFAULT_MAX_CONTENT_CHARS = 20_000

    def __init__(self, *, resource_service=None):
        super().__init__()
        self.resource_service = resource_service or SessionResourceService.database()

    async def execute(
        self,
        context=None,
        knowledge_base_id: Optional[str] = None,
        document_id: Optional[str] = None,
        chunk_index: Optional[int] = None,
        chunk_indices: Optional[List[int]] = None,
        mode: str = "neighbor_chunks",
        window: int = 2,
        max_chunks: int = 30,
        max_content_chars: int = DEFAULT_MAX_CONTENT_CHARS,
        **_: Any,
    ) -> Dict[str, Any]:
        self._start_timer()

        if not knowledge_base_id or not document_id:
            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={"error": "缺少必需参数：knowledge_base_id 或 document_id"},
                summary="读取知识文档失败：缺少参数"
            )
        session_id = getattr(context, "session_id", None)
        if not session_id:
            return self._build_udf_v2_result(
                status="failed",
                success=False,
                data={"error": "缺少当前会话上下文，无法注册原文资源"},
                summary="读取知识文档失败：缺少会话上下文",
            )

        try:
            from app.db.knowledge_database import knowledge_async_session
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

            async with knowledge_async_session() as db:
                service = KnowledgeBaseService(db=db)
                user_id = getattr(context, "user_identifier", None)
                if is_enforcement_exam_context(context):
                    knowledge_base = await service.get_knowledge_base(knowledge_base_id)
                    if (
                        knowledge_base is None
                        or str(knowledge_base.name or "").strip()
                        != ENFORCEMENT_EXAM_KNOWLEDGE_BASE_NAME
                    ):
                        return self._build_udf_v2_result(
                            status="failed",
                            success=False,
                            data={"error": "enforcement_exam_knowledge_base_required"},
                            summary=(
                                "执法备考模式只能读取“"
                                f"{ENFORCEMENT_EXAM_KNOWLEDGE_BASE_NAME}”知识库"
                            ),
                        )
                result = await service.get_document_chunks(
                    kb_id=knowledge_base_id,
                    doc_id=document_id,
                    user_id=user_id,
                )
                original = await service.get_document_original(
                    kb_id=knowledge_base_id,
                    doc_id=document_id,
                    user_id=user_id,
                )

            group_key = (
                f"knowledge-document:{knowledge_base_id}:{document_id}:"
                f"{original['checksum']}"
            )
            resource_key = f"primary:{Path(original['filename']).suffix.lstrip('.').lower() or 'file'}"
            materialized_path = self.resource_service.materialize_file_bytes(
                session_id=session_id,
                group_key=group_key,
                resource_key=resource_key,
                filename=original["filename"],
                content=original["content"],
                checksum=original["checksum"],
            )
            renderer = self._renderer_for(materialized_path)
            resources = [
                primary_file(
                    materialized_path,
                    group_key=group_key,
                    tool_name=self.name,
                    role="output",
                    renderer=renderer,
                    capabilities=("preview", "download"),
                    label=original["filename"],
                    metadata={
                        "knowledge_base_id": knowledge_base_id,
                        "document_id": document_id,
                        "checksum": original["checksum"],
                        "mime_type": original["mime_type"],
                        "size": original["size"],
                        "source": "knowledge_base_original",
                    },
                )
            ]

            all_chunks = result.get("chunks", [])
            selected_chunks = self._select_chunks(
                chunks=all_chunks,
                chunk_index=chunk_index,
                chunk_indices=chunk_indices,
                mode=mode,
                window=max(0, int(window or 0)),
                max_chunks=max(1, int(max_chunks or 1))
            )
            bounded_chunks, content_stats = self._bound_chunk_content(
                selected_chunks,
                max_chars=min(
                    100_000,
                    max(1_000, int(max_content_chars or self.DEFAULT_MAX_CONTENT_CHARS)),
                ),
            )

            self._record_step("document_chunks_read_complete", "success", {
                "selected_count": len(bounded_chunks),
                "total_chunks": len(all_chunks)
            })

            file_path = format_agent_path(materialized_path)
            content_preview = "\n\n".join(
                str(chunk.get("content") or "")
                for chunk in bounded_chunks
                if isinstance(chunk, dict)
            )[:2_000]
            content_truncated = bool(content_stats["content_truncated"])
            document_scope_partial = not (
                mode == "all_chunks" and len(selected_chunks) == len(all_chunks)
            )

            data = {
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "filename": result.get("filename", ""),
                "original_resource": {
                    "file_path": file_path,
                    "checksum": original["checksum"],
                    "size": original["size"],
                    "mime_type": original["mime_type"],
                    "presentation": renderer,
                },
                "mode": mode,
                "window": window,
                "total_chunks": len(all_chunks),
                "returned_chunks": len(bounded_chunks),
                "chunks": bounded_chunks,
                "content_truncated": content_truncated,
                "document_scope_partial": document_scope_partial,
                "total_selected_chars": content_stats["total_chars"],
                "returned_chars": content_stats["returned_chars"],
                "reading_scope": {
                    "chunk_indices": [chunk.get("chunk_index") for chunk in bounded_chunks],
                    "is_full_document": (
                        mode == "all_chunks"
                        and len(bounded_chunks) == len(all_chunks)
                        and not content_stats["content_truncated"]
                    ),
                }
            }

            response = self._build_udf_v2_result(
                status="success",
                success=True,
                data=data,
                summary=(
                    f"已读取文档并登记原文资源：返回"
                    f"{len(bounded_chunks)}/{len(all_chunks)}个chunks"
                ),
                extra_metadata={
                    "retrieval_only": True,
                    "document_id": document_id,
                    "returned_chunks": len(bounded_chunks)
                }
            )
            response.update({
                "file_path": file_path,
                "content_preview": content_preview,
                "content_truncated": content_truncated,
                "document_scope_partial": document_scope_partial,
                "total_chars": content_stats["total_chars"],
                "returned_chars": content_stats["returned_chars"],
                "llm_resume": {
                    "file_path": file_path,
                    "content_preview": content_preview,
                    "content_truncated": content_truncated,
                    "chunk_indices": data["reading_scope"]["chunk_indices"],
                    "tool_hint": (
                        "Call knowledge_document_reader again with narrower chunk_indices "
                        "when more extracted text is required."
                        if content_truncated or document_scope_partial else None
                    ),
                },
            })
            response["resources"] = resources
            return response

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

    @staticmethod
    def _bound_chunk_content(
        chunks: List[Dict[str, Any]],
        *,
        max_chars: int,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Bound extracted text while preserving chunk metadata and the source file."""
        total_chars = sum(
            len(str(chunk.get("content") or ""))
            for chunk in chunks
            if isinstance(chunk, dict)
        )
        returned_chars = 0
        bounded: List[Dict[str, Any]] = []
        content_truncated = False

        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            remaining = max_chars - returned_chars
            if remaining <= 0:
                content_truncated = True
                break

            item = dict(chunk)
            content = str(item.get("content") or "")
            if len(content) > remaining:
                item["content"] = content[:remaining]
                item["content_truncated"] = True
                item["original_content_chars"] = len(content)
                returned_chars += remaining
                bounded.append(item)
                content_truncated = True
                break

            returned_chars += len(content)
            bounded.append(item)

        if len(bounded) < len(chunks):
            content_truncated = True

        return bounded, {
            "total_chars": total_chars,
            "returned_chars": returned_chars,
            "content_truncated": content_truncated,
        }

    @staticmethod
    def _renderer_for(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return "pdf"
        if suffix in {".md", ".markdown"}:
            return "markdown"
        if suffix in {".html", ".htm"}:
            return "html"
        if suffix in {".xlsx", ".xls", ".csv"}:
            return "spreadsheet"
        if suffix in {".pptx", ".ppt"}:
            return "presentation"
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            return "image"
        return "file"

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
                    },
                    "max_content_chars": {
                        "type": "integer",
                        "description": (
                            "本次返回给模型的chunk文本字符预算；原文始终完整物化到"
                            "original_resource.file_path，不受此预算影响"
                        ),
                        "default": 20000,
                        "minimum": 1000,
                        "maximum": 100000
                    }
                },
                "required": ["knowledge_base_id", "document_id"]
            }
        }
