"""
知识库API路由

提供知识库管理、文档上传、检索等REST API。
"""

import json
import os
import shutil
import tempfile
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.database import get_db
from app.knowledge_base.service import KnowledgeBaseService
from app.knowledge_base.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseResponse,
    KnowledgeBaseListResponse,
    DocumentResponse,
    DocumentListResponse,
    SearchRequest,
    SearchResult,
    SearchResultItem,
    KnowledgeBaseStats,
    ChunkingStrategiesResponse,
    ChunkingStrategyInfo,
    DocumentChunksResponse,
    DocumentChunk
)
from app.knowledge_base.chunking_strategies import get_all_strategies
from app.knowledge_base.models import KnowledgeBaseStatus, DocumentStatus

logger = structlog.get_logger()
router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"])


def _build_content_disposition(filename: str) -> str:
    """
    安全构造 Content-Disposition 头，避免 latin-1 编码错误。
    - 优先使用简单的 filename=
    - 如果包含非 latin-1 字符（如中文引号等），回退到 RFC 5987 的 filename* 写法
    """
    from urllib.parse import quote

    safe_name = filename or "download"
    try:
        # FastAPI/Starlette 会用 latin-1 编码 header，先预检测
        header_value = f'attachment; filename="{safe_name}"'
        header_value.encode("latin-1")
        return header_value
    except UnicodeEncodeError:
        # 使用 RFC 5987 格式，保证 header 只包含 ASCII
        encoded = quote(safe_name, safe="")
        return f"attachment; filename*=UTF-8''{encoded}"


def get_user_id(x_user_id: Optional[str] = Header(None)) -> Optional[str]:
    """从请求头获取用户ID"""
    return x_user_id


def get_is_admin(x_is_admin: Optional[str] = Header(None)) -> bool:
    """从请求头获取管理员标识"""
    return x_is_admin == "true"


# ============ 知识库管理 ============

@router.post("", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    request: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id),
    is_admin: bool = Depends(get_is_admin)
):
    """
    创建知识库

    - **公共知识库**: 需要管理员权限
    - **个人知识库**: 任何用户都可创建
    """
    # 公共知识库需要管理员权限
    if request.kb_type == "public" and not is_admin:
        raise HTTPException(status_code=403, detail="Only admin can create public knowledge base")

    # 个人知识库需要user_id
    if request.kb_type == "private" and not user_id:
        raise HTTPException(status_code=400, detail="User ID required for private knowledge base")

    service = KnowledgeBaseService(db=db)

    try:
        kb = await service.create_knowledge_base(
            name=request.name,
            description=request.description,
            kb_type=request.kb_type.value,
            owner_id=user_id if request.kb_type == "private" else None,
            chunking_strategy=request.chunking_strategy.value,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
            is_default=request.is_default
        )

        return _kb_to_response(kb, user_id)

    except Exception as e:
        logger.error("create_knowledge_base_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    列出所有可访问的知识库

    - 公共知识库: 所有用户可见
    - 个人知识库: 仅创建者可见
    """
    service = KnowledgeBaseService(db=db)

    try:
        kbs = await service.list_knowledge_bases(user_id=user_id)

        public_kbs = [_kb_to_response(kb, user_id) for kb in kbs if kb.is_public]
        private_kbs = [_kb_to_response(kb, user_id) for kb in kbs if kb.is_private]

        return KnowledgeBaseListResponse(
            public=public_kbs,
            private=private_kbs,
            total=len(kbs)
        )

    except Exception as e:
        logger.error("list_knowledge_bases_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=KnowledgeBaseStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id)
):
    """获取知识库统计信息"""
    service = KnowledgeBaseService(db=db)

    try:
        stats = await service.get_stats(user_id=user_id)
        return KnowledgeBaseStats(**stats)
    except Exception as e:
        logger.error("get_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies", response_model=ChunkingStrategiesResponse)
async def get_chunking_strategies():
    """获取可用的分块策略列表"""
    strategies = get_all_strategies()
    return ChunkingStrategiesResponse(
        strategies=[ChunkingStrategyInfo(**s) for s in strategies]
    )


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id)
):
    """获取知识库详情"""
    service = KnowledgeBaseService(db=db)

    kb = await service.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # 权限检查
    if kb.is_private and kb.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return _kb_to_response(kb, user_id)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: str,
    request: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id),
    is_admin: bool = Depends(get_is_admin)
):
    """更新知识库配置"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    service = KnowledgeBaseService(db=db)

    try:
        updates = request.dict(exclude_unset=True)
        if "chunking_strategy" in updates and updates["chunking_strategy"]:
            updates["chunking_strategy"] = updates["chunking_strategy"].value

        kb = await service.update_knowledge_base(
            kb_id=kb_id,
            user_id=user_id,
            is_admin=is_admin,
            **updates
        )
        return _kb_to_response(kb, user_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("update_knowledge_base_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id),
    is_admin: bool = Depends(get_is_admin)
):
    """删除知识库"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    service = KnowledgeBaseService(db=db)

    try:
        await service.delete_knowledge_base(
            kb_id=kb_id,
            user_id=user_id,
            is_admin=is_admin
        )
        return {"status": "success", "message": "Knowledge base deleted"}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("delete_knowledge_base_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============ 文档管理 ============

@router.post("/{kb_id}/documents", response_model=DocumentResponse)
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    metadata: str = Form(default="{}"),
    chunking_strategy: str = Form(default="llm"),
    chunk_size: int = Form(default=800),
    chunk_overlap: int = Form(default=100),
    llm_mode: str = Form(default="online"),  # 优先使用线上API（更快）
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id),
    is_admin: bool = Depends(get_is_admin)
):
    """
    上传文档到知识库

    支持格式: PDF, DOCX, XLSX, PPTX, HTML, TXT, MD, CSV, JSON
    
    分块策略 (chunking_strategy):
    - llm: LLM智能分块（默认，质量最高）
    - sentence: 句子分块（速度快）
    - semantic: 语义分块（基于Embedding）
    - markdown: Markdown分块
    - hybrid: 混合分块

    LLM模式 (llm_mode，仅chunking_strategy=llm时有效):
    - local: 本地千问3（默认，25000字符分段阈值）
    - online: 线上API（60000字符分段阈值，使用DeepSeek/MiniMax/Mimo等，根据LLM_PROVIDER环境变量自动选择）

    注意：上传文档到公共知识库不需要管理员权限
    """
    # 个人知识库需要user_id，公共知识库允许匿名上传

    # 检查文件大小
    max_size = int(os.getenv("KNOWLEDGE_BASE_MAX_FILE_SIZE", "50")) * 1024 * 1024
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {max_size // 1024 // 1024}MB"
        )

    # 保存上传的文件
    storage_dir = os.getenv("KNOWLEDGE_BASE_STORAGE_DIR", "data/knowledge_base")
    os.makedirs(storage_dir, exist_ok=True)

    tmp_path = os.path.join(storage_dir, f"{kb_id}_{file.filename}")
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    service = KnowledgeBaseService(db=db)

    # 验证分块策略
    valid_strategies = ["sentence", "semantic", "markdown", "hybrid", "llm"]
    if chunking_strategy not in valid_strategies:
        os.remove(tmp_path)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid chunking strategy. Must be one of: {valid_strategies}"
        )
    
    # 验证LLM模式
    valid_llm_modes = ["local", "online"]
    if llm_mode not in valid_llm_modes:
        os.remove(tmp_path)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid LLM mode. Must be one of: {valid_llm_modes}"
        )

    try:
        doc = await service.upload_document(
            kb_id=kb_id,
            file_path=tmp_path,
            filename=file.filename,
            user_id=user_id,
            is_admin=is_admin,
            metadata=json.loads(metadata),
            chunking_strategy=chunking_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            llm_mode=llm_mode
        )

        return _doc_to_response(doc)

    except ValueError as e:
        os.remove(tmp_path)
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        os.remove(tmp_path)
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        os.remove(tmp_path)
        logger.error("upload_document_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id)
):
    """列出知识库中的文档"""
    service = KnowledgeBaseService(db=db)

    # 检查知识库访问权限
    kb = await service.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if kb.is_private and kb.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        docs = await service.list_documents(kb_id)

        processing = sum(1 for d in docs if d.status == DocumentStatus.PROCESSING)
        failed = sum(1 for d in docs if d.status == DocumentStatus.FAILED)

        return DocumentListResponse(
            documents=[_doc_to_response(d) for d in docs],
            total=len(docs),
            processing=processing,
            failed=failed
        )

    except Exception as e:
        logger.error("list_documents_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id),
    is_admin: bool = Depends(get_is_admin)
):
    """删除文档"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    service = KnowledgeBaseService(db=db)

    try:
        await service.delete_document(
            kb_id=kb_id,
            doc_id=doc_id,
            user_id=user_id,
            is_admin=is_admin
        )
        return {"status": "success", "message": "Document deleted"}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("delete_document_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_id}/documents/{doc_id}/retry", response_model=DocumentResponse)
async def retry_document(
    kb_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id),
    is_admin: bool = Depends(get_is_admin)
):
    """重试处理失败的文档"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    service = KnowledgeBaseService(db=db)

    try:
        doc = await service.retry_document(
            kb_id=kb_id,
            doc_id=doc_id,
            user_id=user_id,
            is_admin=is_admin
        )
        return _doc_to_response(doc)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("retry_document_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/documents/{doc_id}/chunks", response_model=DocumentChunksResponse)
async def get_document_chunks(
    kb_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    获取文档的所有分段

    返回文档在向量库中的所有分块内容，用于查看分段效果。
    """
    service = KnowledgeBaseService(db=db)

    try:
        result = await service.get_document_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            user_id=user_id
        )

        return DocumentChunksResponse(
            document_id=result["document_id"],
            filename=result["filename"],
            chunks=[DocumentChunk(**chunk) for chunk in result["chunks"]],
            total=result["total"]
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("get_document_chunks_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============ 检索 ============

@router.post("/search", response_model=SearchResult)
async def search_knowledge_base(
    request: SearchRequest,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    检索知识库

    - 支持多知识库联合检索
    - 可选Reranker精排
    - 自动权限过滤
    - 返回文档溯源链接

    注意：检索API使用独立数据库会话，避免长时间Reranker推理导致连接超时
    """
    from app.db.database import async_session
    from sqlalchemy import select
    from app.knowledge_base.models import Document

    start_time = time.time()

    try:
        # 使用独立会话，检索完成后立即关闭（不需要commit）
        async with async_session() as db:
            service = KnowledgeBaseService(db=db)
            results = await service.search(
                query=request.query,
                user_id=user_id,
                knowledge_base_ids=request.knowledge_base_ids,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
                filters=request.filters,
                use_reranker=request.use_reranker if request.use_reranker is not None else request.rerank_mode
            )

            # 为每个结果添加溯源链接
            doc_ids = list(set(r.get("document_id") for r in results if r.get("document_id")))
            if doc_ids:
                # 批量查询文档存储信息
                doc_result = await db.execute(
                    select(Document).where(Document.id.in_(doc_ids))
                )
                docs_map = {doc.id: doc for doc in doc_result.scalars().all()}

                for r in results:
                    doc_id = r.get("document_id")
                    kb_info = r.get("knowledge_base", {})
                    kb_id = kb_info.get("id")

                    if doc_id and kb_id:
                        doc = docs_map.get(doc_id)
                        if doc:
                            has_file = bool(
                                doc.original_file_oid or
                                (doc.file_storage_type == "local" and doc.file_path)
                            )
                            r["has_original_file"] = has_file
                            if has_file:
                                r["download_url"] = f"/api/knowledge-base/{kb_id}/documents/{doc_id}/download"
                                r["preview_url"] = f"/api/knowledge-base/{kb_id}/documents/{doc_id}/preview"

        elapsed_ms = (time.time() - start_time) * 1000

        return SearchResult(
            status="success",
            results=[SearchResultItem(**r) for r in results],
            total=len(results),
            query=request.query,
            knowledge_base_ids=request.knowledge_base_ids,
            elapsed_ms=round(elapsed_ms, 2)
        )

    except Exception as e:
        logger.error("search_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============ 辅助函数 ============

def _kb_to_response(kb, user_id: Optional[str]) -> KnowledgeBaseResponse:
    """转换KnowledgeBase为响应模型"""
    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description or "",
        kb_type=kb.kb_type.value,
        status=kb.status.value,
        document_count=kb.document_count,
        chunk_count=kb.chunk_count,
        total_size=kb.total_size,
        is_owner=kb.owner_id == user_id if user_id else False,
        is_default=kb.is_default,
        chunking_strategy=kb.chunking_strategy.value,
        chunk_size=kb.chunk_size,
        chunk_overlap=kb.chunk_overlap,
        created_at=kb.created_at,
        updated_at=kb.updated_at
    )


def _doc_to_response(doc) -> DocumentResponse:
    """转换Document为响应模型"""
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status.value,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        metadata=doc.metadata or {},
        created_at=doc.created_at,
        processed_at=doc.processed_at,
        # 新增溯源相关字段
        file_storage_type=getattr(doc, 'file_storage_type', None),
        file_mime_type=getattr(doc, 'file_mime_type', None),
        has_original_file=bool(getattr(doc, 'original_file_oid', None) or
                               (getattr(doc, 'file_storage_type', None) == 'local' and getattr(doc, 'file_path', None))),
        preview_text=getattr(doc, 'file_preview_text', None)
    )


# ============ 文件溯源API ============

@router.get("/{kb_id}/documents/{doc_id}/download")
async def download_document(
    kb_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    下载文档原文件

    支持从PostgreSQL Large Object或本地文件系统获取原文件。
    用于文档溯源功能，让用户可以查看原始上传的文件。
    """
    from fastapi.responses import StreamingResponse
    from sqlalchemy import select
    from app.knowledge_base.models import Document
    from app.knowledge_base.file_storage import DatabaseFileStorageService, LocalFileStorageService
    import io

    service = KnowledgeBaseService(db=db)

    # 检查知识库访问权限
    kb = await service.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if kb.is_private and kb.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # 获取文档
    result = await db.execute(
        select(Document).where(
            Document.id == doc_id,
            Document.knowledge_base_id == kb_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        file_bytes = None
        mime_type = doc.file_mime_type or "application/octet-stream"

        if doc.file_storage_type == "database" and doc.original_file_oid:
            # 从PostgreSQL Large Object读取
            db_storage = DatabaseFileStorageService(db)
            file_bytes, _ = await db_storage.retrieve_file(doc.original_file_oid)
        elif doc.file_storage_type == "local" and doc.file_path:
            # 从本地文件系统读取
            local_storage = LocalFileStorageService()
            file_bytes, mime_type = await local_storage.retrieve_file(doc.file_path)
        else:
            raise HTTPException(
                status_code=404,
                detail="Original file not available. File may not have been stored."
            )

        # 返回文件流（使用安全的 Content-Disposition，避免中文文件名导致 latin-1 编码错误）
        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type=mime_type,
            headers={
                "Content-Disposition": _build_content_disposition(doc.filename),
                "Content-Length": str(len(file_bytes))
            }
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("download_document_failed", doc_id=doc_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file: {str(e)}")


@router.get("/{kb_id}/documents/{doc_id}/preview")
async def preview_document(
    kb_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    获取文档预览信息

    返回文档的预览文本和元数据，用于在检索结果中快速预览文档内容。
    """
    from sqlalchemy import select
    from app.knowledge_base.models import Document

    service = KnowledgeBaseService(db=db)

    # 检查知识库访问权限
    kb = await service.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if kb.is_private and kb.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # 获取文档
    result = await db.execute(
        select(Document).where(
            Document.id == doc_id,
            Document.knowledge_base_id == kb_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "mime_type": doc.file_mime_type,
        "storage_type": doc.file_storage_type,
        "has_original_file": bool(doc.original_file_oid or
                                   (doc.file_storage_type == "local" and doc.file_path)),
        "preview_text": doc.file_preview_text,
        "chunk_count": doc.chunk_count,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
        "download_url": f"/api/knowledge-base/{kb_id}/documents/{doc_id}/download"
    }
