"""
知识库服务层

提供知识库CRUD、文档处理、检索等核心业务逻辑。
"""

import os
import hashlib
import asyncio
import time
from uuid import uuid4
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from .models import (
    KnowledgeBase, Document,
    KnowledgeBaseStatus, KnowledgeBaseType,
    DocumentStatus, ChunkingStrategy
)
from .permissions import KnowledgeBasePermissions
from . import get_vector_store, get_document_processor
from .file_storage import SmartFileStorage

logger = structlog.get_logger()

# 在模块加载时设置PyTorch线程数（必须在任何PyTorch操作之前）
try:
    import torch
    _num_threads = os.cpu_count() or 4
    torch.set_num_threads(_num_threads)
    # 只在首次设置interop threads，避免重复调用报错
    if not hasattr(torch, '_interop_threads_set'):
        torch.set_num_interop_threads(min(4, _num_threads))
        torch._interop_threads_set = True
    logger.info("pytorch_threads_configured", num_threads=_num_threads)
except Exception as e:
    logger.warning("pytorch_threads_config_failed", error=str(e))

# 全局Reranker单例（避免重复加载）
_global_reranker = None
_reranker_initialized = False


def get_reranker():
    """获取全局Reranker单例"""
    global _global_reranker, _reranker_initialized

    if not _reranker_initialized:
        try:
            import torch
            from sentence_transformers import CrossEncoder

            # 获取当前PyTorch线程配置
            num_threads = torch.get_num_threads()

            # 优先使用环境变量，其次使用项目内默认路径
            local_path = os.getenv("BGE_RERANKER_MODEL_PATH")
            if not local_path:
                # 使用项目内 models 目录（相对于本文件的路径）
                backend_dir = Path(__file__).parent.parent.parent  # backend/app/knowledge_base -> backend
                local_path = str(backend_dir / "models" / "bge-reranker-model")

            if local_path and os.path.exists(local_path):
                _global_reranker = CrossEncoder(local_path)
                logger.info("reranker_singleton_loaded", path=local_path, cpu_threads=num_threads)
            else:
                model_name = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
                _global_reranker = CrossEncoder(model_name)
                logger.info("reranker_singleton_loaded_from_hub", model=model_name, cpu_threads=num_threads)
        except Exception as e:
            logger.warning("reranker_singleton_load_failed", error=str(e))
            _global_reranker = None
        _reranker_initialized = True

    return _global_reranker


class KnowledgeBaseService:
    """知识库服务"""

    def __init__(
        self,
        db: AsyncSession = None,
        vector_store = None
    ):
        self.db = db
        self.processor = get_document_processor()
        self.vector_store = vector_store or get_vector_store()
        self._reranker = None

    def _get_reranker(self):
        """获取Reranker模型（使用全局单例）"""
        if self._reranker is None:
            self._reranker = get_reranker()
        return self._reranker

    # ============ 知识库CRUD ============

    async def create_knowledge_base(
        self,
        name: str,
        description: str = "",
        kb_type: str = "private",
        owner_id: Optional[str] = None,
        chunking_strategy: str = "llm",
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        is_default: bool = False
    ) -> KnowledgeBase:
        """
        创建知识库

        Args:
            name: 知识库名称
            description: 描述
            kb_type: 类型 (public/private)
            owner_id: 所有者ID（个人知识库必须）
            chunking_strategy: 分块策略
            chunk_size: 分块大小
            chunk_overlap: 分块重叠
            is_default: 是否默认启用

        Returns:
            创建的知识库对象
        """
        kb_id = str(uuid4())
        collection_name = f"kb_{kb_id.replace('-', '_')}"

        # 类型转换
        kb_type_enum = KnowledgeBaseType(kb_type)
        strategy_enum = ChunkingStrategy(chunking_strategy)

        # 公共知识库不需要owner_id
        if kb_type_enum == KnowledgeBaseType.PUBLIC:
            owner_id = None
        elif not owner_id:
            raise ValueError("Private knowledge base requires owner_id")

        # 创建Qdrant Collection。新建知识库必须使用 hybrid 结构，避免后续静默降级。
        await self.vector_store.create_collection(collection_name, enable_hybrid=True)
        if not self.vector_store._collection_supports_hybrid(collection_name):
            raise RuntimeError(f"Failed to create hybrid collection: {collection_name}")

        # 创建数据库记录
        kb = KnowledgeBase(
            id=kb_id,
            name=name,
            description=description,
            kb_type=kb_type_enum,
            owner_id=owner_id,
            chunking_strategy=strategy_enum,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            qdrant_collection=collection_name,
            is_default=is_default
        )

        self.db.add(kb)
        await self.db.commit()
        await self.db.refresh(kb)

        logger.info(
            "knowledge_base_created",
            kb_id=kb_id,
            name=name,
            kb_type=kb_type,
            owner_id=owner_id
        )

        return kb

    async def get_knowledge_base(self, kb_id: str) -> Optional[KnowledgeBase]:
        """获取知识库"""
        result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        return result.scalar_one_or_none()

    async def list_knowledge_bases(
        self,
        user_id: Optional[str] = None,
        include_public: bool = True,
        status: Optional[KnowledgeBaseStatus] = None
    ) -> List[KnowledgeBase]:
        """
        列出用户可访问的知识库

        Args:
            user_id: 用户ID
            include_public: 是否包含公共知识库
            status: 状态过滤

        Returns:
            知识库列表
        """
        return await KnowledgeBasePermissions.get_accessible_knowledge_bases(
            db=self.db,
            user_id=user_id,
            include_public=include_public,
            status=status
        )

    async def update_knowledge_base(
        self,
        kb_id: str,
        user_id: str,
        is_admin: bool = False,
        **updates
    ) -> KnowledgeBase:
        """更新知识库配置"""
        kb = await self.get_knowledge_base(kb_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        if not KnowledgeBasePermissions.can_manage(kb, user_id, is_admin):
            raise PermissionError("No permission to update this knowledge base")

        # 允许更新的字段
        allowed_fields = {
            "name", "description", "is_default",
            "chunking_strategy", "chunk_size", "chunk_overlap"
        }

        for key, value in updates.items():
            if key in allowed_fields and value is not None:
                if key == "chunking_strategy":
                    value = ChunkingStrategy(value)
                setattr(kb, key, value)

        kb.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(kb)

        logger.info("knowledge_base_updated", kb_id=kb_id, updates=list(updates.keys()))
        return kb

    async def delete_knowledge_base(
        self,
        kb_id: str,
        user_id: str,
        is_admin: bool = False
    ) -> bool:
        """删除知识库"""
        kb = await self.get_knowledge_base(kb_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        if not KnowledgeBasePermissions.can_manage(kb, user_id, is_admin):
            raise PermissionError("No permission to delete this knowledge base")

        # 删除Qdrant Collection
        await self.vector_store.delete_collection(kb.qdrant_collection)

        # 删除数据库记录（级联删除文档）
        await self.db.delete(kb)
        await self.db.commit()

        logger.info("knowledge_base_deleted", kb_id=kb_id)
        return True

    # ============ 文档处理 ============

    async def upload_document(
        self,
        kb_id: str,
        file_path: str,
        filename: str,
        user_id: Optional[str] = None,
        is_admin: bool = False,
        metadata: Dict[str, Any] = None,
        chunking_strategy: str = "llm",
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        llm_mode: str = "online"  # 优先使用线上API（更快）
    ) -> Document:
        """
        上传并处理文档

        Args:
            kb_id: 知识库ID
            file_path: 文件路径
            filename: 文件名
            user_id: 用户ID
            is_admin: 是否管理员
            metadata: 自定义元数据
            chunking_strategy: 分块策略 (llm/sentence/semantic/markdown/hybrid)
            chunk_size: 分块大小
            chunk_overlap: 分块重叠
            llm_mode: LLM模式 - "local"(本地千问3) / "online"(线上API)

        Returns:
            文档对象
        """
        kb = await self.get_knowledge_base(kb_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        if not KnowledgeBasePermissions.can_upload(kb, user_id, is_admin):
            raise PermissionError("No permission to upload to this knowledge base")

        # 获取文件信息
        file_size = os.path.getsize(file_path)
        file_type = self.processor.get_file_type(file_path)
        file_hash = self._calculate_file_hash(file_path)

        # 创建文档记录
        doc_id = str(uuid4())
        doc = Document(
            id=doc_id,
            knowledge_base_id=kb_id,
            filename=filename,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            file_hash=file_hash,
            status=DocumentStatus.PROCESSING,
            extra_metadata=metadata or {}
        )

        self.db.add(doc)
        await self.db.commit()
        await self.db.refresh(doc)

        # 异步处理文档（传入分块参数）
        try:
            await self._process_document(
                doc, kb,
                chunking_strategy=chunking_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                llm_mode=llm_mode
            )
        except Exception as e:
            # 使用新session更新失败状态（原有连接可能已超时）
            try:
                from app.db.database import async_session
                async with async_session() as fresh_db:
                    doc_result = await fresh_db.execute(
                        select(Document).where(Document.id == doc_id)
                    )
                    doc_fresh = doc_result.scalar_one_or_none()
                    if doc_fresh:
                        doc_fresh.status = DocumentStatus.FAILED
                        doc_fresh.error_message = str(e)[:500]
                        await fresh_db.commit()
            except Exception as update_err:
                logger.error("failed_to_update_status", doc_id=doc_id, error=str(update_err))
            logger.error("document_processing_failed", doc_id=doc_id, error=str(e))
            raise

        # 返回最新状态的文档
        from app.db.database import async_session
        async with async_session() as fresh_db:
            doc_result = await fresh_db.execute(
                select(Document).where(Document.id == doc_id)
            )
            return doc_result.scalar_one()

    async def _process_document(
        self,
        doc: Document,
        kb: KnowledgeBase,
        chunking_strategy: str = "llm",
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        llm_mode: str = "local"
    ):
        """处理文档：解析、分块、向量化、存储原文件（支持LLM模式选择）"""
        # 先提取所有需要的值（避免在线程中访问 SQLAlchemy 对象）
        doc_id = doc.id
        doc_file_path = doc.file_path
        doc_filename = doc.filename
        doc_file_size = doc.file_size
        doc_extra_metadata = dict(doc.extra_metadata) if doc.extra_metadata else {}

        kb_id = kb.id
        kb_collection = kb.qdrant_collection

        try:
            # 1. 解析文档（在线程池中执行）
            content = await self.processor.parse(doc_file_path)

            # 2. 分块（使用传入的分块策略参数和LLM模式）
            chunks = await self.processor.chunk(
                content=content,
                strategy=chunking_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                filename=doc_filename,
                llm_mode=llm_mode
            )

            # 3. 向量化并存储（在线程池中执行）
            chunk_count = await self.vector_store.add_chunks(
                collection_name=kb_collection,
                chunks=chunks,
                metadata={
                    "document_id": doc_id,
                    "filename": doc_filename,
                    "knowledge_base_id": kb_id,
                    **doc_extra_metadata
                }
            )

            # 4. 存储原文件到数据库（使用智能存储策略）
            storage_info = None
            try:
                from app.db.database import async_session
                async with async_session() as storage_db:
                    file_storage = SmartFileStorage(storage_db)
                    storage_info = await file_storage.store_file(
                        temp_file_path=doc_file_path,
                        original_filename=doc_filename,
                        document_id=doc_id,
                        knowledge_base_id=kb_id
                    )
                    await storage_db.commit()
                    logger.info(
                        "original_file_stored",
                        doc_id=doc_id,
                        storage_type=storage_info.get("storage_type"),
                        size=storage_info.get("size")
                    )
            except Exception as storage_err:
                # 文件存储失败不应阻止文档处理完成
                logger.warning(
                    "original_file_storage_failed",
                    doc_id=doc_id,
                    error=str(storage_err)
                )

            # 5. 生成文件预览文本（取前500字符）
            preview_text = content[:500] if content else None

            # 6. 使用新的数据库会话更新状态（避免长时间操作导致连接超时）
            from app.db.database import async_session
            async with async_session() as fresh_db:
                doc_result = await fresh_db.execute(
                    select(Document).where(Document.id == doc_id)
                )
                doc_fresh = doc_result.scalar_one()
                doc_fresh.status = DocumentStatus.COMPLETED
                doc_fresh.chunk_count = chunk_count
                doc_fresh.processed_at = datetime.utcnow()
                doc_fresh.file_preview_text = preview_text

                # 更新文件存储信息
                if storage_info:
                    doc_fresh.file_storage_type = storage_info.get("storage_type", "none")
                    doc_fresh.file_mime_type = storage_info.get("mime_type")
                    doc_fresh.file_checksum = storage_info.get("checksum")
                    doc_fresh.storage_size = storage_info.get("size", 0)
                    if storage_info.get("storage_type") == "database":
                        loid = storage_info.get("loid")
                        if loid:
                            doc_fresh.original_file_oid = int(loid)
                    elif storage_info.get("storage_type") == "local":
                        doc_fresh.file_path = storage_info.get("storage_path", doc_file_path)

                kb_result = await fresh_db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
                )
                kb_fresh = kb_result.scalar_one()
                kb_fresh.document_count += 1
                kb_fresh.chunk_count += chunk_count
                kb_fresh.total_size += doc_file_size

                await fresh_db.commit()

            logger.info(
                "document_processed",
                doc_id=doc_id,
                filename=doc_filename,
                chunk_count=chunk_count,
                storage_type=storage_info.get("storage_type") if storage_info else "none"
            )

        except Exception as e:
            # 使用新的数据库会话更新失败状态（避免连接超时问题）
            try:
                from app.db.database import async_session
                async with async_session() as fresh_db:
                    doc_result = await fresh_db.execute(
                        select(Document).where(Document.id == doc_id)
                    )
                    doc_fresh = doc_result.scalar_one_or_none()
                    if doc_fresh:
                        doc_fresh.status = DocumentStatus.FAILED
                        doc_fresh.error_message = str(e)[:500]  # 限制错误信息长度
                        doc_fresh.retry_count += 1
                        await fresh_db.commit()
            except Exception as update_error:
                logger.error(
                    "failed_to_update_document_status",
                    doc_id=doc_id,
                    error=str(update_error)
                )

            logger.error(
                "document_process_failed",
                doc_id=doc_id,
                error=str(e)
            )
            raise

    async def delete_document(
        self,
        kb_id: str,
        doc_id: str,
        user_id: str,
        is_admin: bool = False
    ) -> bool:
        """删除文档"""
        kb = await self.get_knowledge_base(kb_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        if not KnowledgeBasePermissions.can_manage(kb, user_id, is_admin):
            raise PermissionError("No permission to delete document")

        # 获取文档
        result = await self.db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.knowledge_base_id == kb_id
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")

        # 删除向量
        await self.vector_store.delete_by_document(kb.qdrant_collection, doc_id)

        # 更新知识库统计
        kb.document_count = max(0, kb.document_count - 1)
        kb.chunk_count = max(0, kb.chunk_count - doc.chunk_count)
        kb.total_size = max(0, kb.total_size - doc.file_size)

        # 删除数据库记录
        await self.db.delete(doc)
        await self.db.commit()

        logger.info("document_deleted", kb_id=kb_id, doc_id=doc_id)
        return True

    async def list_documents(self, kb_id: str) -> List[Document]:
        """列出知识库中的文档"""
        result = await self.db.execute(
            select(Document)
            .where(Document.knowledge_base_id == kb_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def retry_document(
        self,
        kb_id: str,
        doc_id: str,
        user_id: str,
        is_admin: bool = False
    ) -> Document:
        """重试处理失败的文档"""
        kb = await self.get_knowledge_base(kb_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        if not KnowledgeBasePermissions.can_manage(kb, user_id, is_admin):
            raise PermissionError("No permission to retry document")

        result = await self.db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.knowledge_base_id == kb_id
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")

        if doc.status != DocumentStatus.FAILED:
            raise ValueError("Only failed documents can be retried")

        doc.status = DocumentStatus.PROCESSING
        doc.error_message = None
        await self.db.commit()

        try:
            await self._process_document(doc, kb)
        except Exception as e:
            logger.error("document_retry_failed", doc_id=doc_id, error=str(e))

        await self.db.refresh(doc)
        return doc

    # ============ 检索 ============

    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        knowledge_base_ids: Optional[List[str]] = None,
        top_k: int = 5,
        score_threshold: float = 0.25,
        filters: Optional[Dict[str, Any]] = None,
        use_reranker: bool | str = True,
        use_hybrid: bool = True,
        alpha: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        检索知识库（支持混合检索）

        Args:
            query: 查询文本
            user_id: 用户ID（用于权限检查）
            knowledge_base_ids: 指定知识库ID列表
            top_k: 返回数量
            score_threshold: 相似度阈值
            filters: 元数据过滤
            use_reranker: 是否使用Reranker精排，支持 bool 或 auto/always/never
            use_hybrid: 是否使用混合检索（Dense+Sparse BM25）
            alpha: Dense权重（0-1），1=纯语义，0=纯关键词

        Returns:
            检索结果列表
        """
        if score_threshold is None:
            score_threshold = 0.25

        # 获取要检索的知识库
        if knowledge_base_ids:
            # 过滤出可访问的
            accessible_ids = await KnowledgeBasePermissions.filter_accessible_ids(
                db=self.db,
                knowledge_base_ids=knowledge_base_ids,
                user_id=user_id
            )
            kbs = [
                await self.get_knowledge_base(kb_id)
                for kb_id in accessible_ids
            ]
            kbs = [kb for kb in kbs if kb]
        else:
            # 检索所有可访问的活跃知识库
            kbs = await self.list_knowledge_bases(
                user_id=user_id,
                status=KnowledgeBaseStatus.ACTIVE
            )

        if not kbs:
            return []

        search_started_at = time.time()

        rerank_mode = self._normalize_rerank_mode(use_reranker)
        recall_for_rerank = rerank_mode in {"auto", "always"}

        # 根据是否可能使用重排序决定召回策略。每库召回不能过小，否则多知识库场景下
        # 相关片段很容易在粗召回阶段被截断；也不能无限放大，否则精排成本会线性增加。
        if recall_for_rerank:
            recall_per_kb = min(max(top_k * 4, 8), 20)
            rerank_candidate_limit = min(max(top_k * 8, 20), 60)
        else:
            recall_per_kb = min(max(top_k * 3, 8), 15)
            rerank_candidate_limit = top_k

        logger.info(
            "knowledge_search_recall_plan",
            query_preview=query[:100],
            kb_count=len(kbs),
            top_k=top_k,
            recall_per_kb=recall_per_kb,
            rerank_candidate_limit=rerank_candidate_limit,
            use_hybrid=use_hybrid,
            use_reranker=rerank_mode,
            score_threshold=score_threshold
        )

        async def search_single_kb(kb: KnowledgeBase):
            if use_hybrid:
                # 使用混合检索（Dense + Sparse BM25）
                kb_results = await self.vector_store.hybrid_search(
                    collection_name=kb.qdrant_collection,
                    query=query,
                    top_k=recall_per_kb,
                    score_threshold=score_threshold,
                    alpha=alpha,
                    filters=filters
                )
            else:
                # 纯向量检索
                kb_results = await self.vector_store.search(
                    collection_name=kb.qdrant_collection,
                    query=query,
                    top_k=recall_per_kb,
                    score_threshold=score_threshold,
                    filters=filters
                )
            for result in kb_results:
                result["knowledge_base"] = {
                    "id": kb.id,
                    "name": kb.name,
                    "type": kb.kb_type.value
                }
            return kb_results

        recall_started_at = time.time()
        all_results = await asyncio.gather(*[search_single_kb(kb) for kb in kbs])
        recall_elapsed_ms = (time.time() - recall_started_at) * 1000
        results = []
        for kb_results in all_results:
            results.extend(kb_results)

        logger.info(
            "knowledge_search_candidates_collected",
            query_preview=query[:100],
            candidate_count=len(results),
            kb_count=len(kbs),
            use_reranker=rerank_mode,
            recall_elapsed_ms=round(recall_elapsed_ms, 2)
        )

        # 根据是否使用重排序决定后续逻辑
        should_rerank = self._should_rerank(query, results, top_k, rerank_mode)
        if should_rerank and len(results) > top_k:
            before_limit_count = len(results)
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:rerank_candidate_limit]
            if before_limit_count > len(results):
                logger.info(
                    "knowledge_search_candidates_limited_before_rerank",
                    query_preview=query[:100],
                    before_count=before_limit_count,
                    after_count=len(results),
                    limit=rerank_candidate_limit
                )
            # 开启重排序：从多个候选中精选top_k
            results = await self._rerank(query, results, top_k)
        else:
            # 关闭重排序或候选数量不足，直接排序返回
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:top_k]

        # 为每个结果添加原文档信息（用于溯源比对）
        await self._enrich_results_with_document_info(results)
        self._attach_chunk_source_fields(results)
        self._log_search_top_results(query, results)

        logger.info(
            "knowledge_search_finished",
            query_preview=query[:100],
            result_count=len(results),
            elapsed_ms=round((time.time() - search_started_at) * 1000, 2)
        )

        return results

    def _normalize_rerank_mode(self, use_reranker: bool | str) -> str:
        """兼容旧的 bool 参数，同时支持 auto/always/never。"""
        if isinstance(use_reranker, bool):
            return "always" if use_reranker else "never"
        mode = str(use_reranker or "auto").strip().lower()
        aliases = {
            "true": "always",
            "false": "never",
            "yes": "always",
            "no": "never",
            "on": "always",
            "off": "never",
        }
        mode = aliases.get(mode, mode)
        return mode if mode in {"auto", "always", "never"} else "auto"

    def _should_rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int,
        rerank_mode: str
    ) -> bool:
        """auto 模式只在粗召回不够确定时启用 CrossEncoder。"""
        if rerank_mode == "always":
            return True
        if rerank_mode == "never" or len(results) <= top_k:
            return False

        sorted_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
        top1 = float(sorted_results[0].get("score") or 0) if sorted_results else 0.0
        top2 = float(sorted_results[1].get("score") or 0) if len(sorted_results) > 1 else 0.0
        score_gap = top1 - top2
        relative_gap = score_gap / max(abs(top1), 1e-6)

        top_docs = [
            item.get("document_id")
            for item in sorted_results[:max(3, min(5, len(sorted_results)))]
            if item.get("document_id")
        ]
        dominant_doc_hits = max((top_docs.count(doc_id) for doc_id in set(top_docs)), default=0)
        document_concentrated = bool(top_docs) and (
            dominant_doc_hits >= 3 or len(set(top_docs[:3])) == 1
        )

        obvious_score_gap = score_gap >= 0.08 or relative_gap >= 0.20
        should_rerank = not (obvious_score_gap or document_concentrated)
        logger.info(
            "rerank_auto_decision",
            query_preview=query[:100],
            candidate_count=len(results),
            top_k=top_k,
            top1_score=top1,
            top2_score=top2,
            score_gap=round(score_gap, 6),
            relative_gap=round(relative_gap, 6),
            document_concentrated=document_concentrated,
            should_rerank=should_rerank
        )
        return should_rerank

    def _attach_chunk_source_fields(self, results: List[Dict[str, Any]]) -> None:
        """把常用chunk元数据提升到顶层，方便API和工具直接溯源。"""
        for item in results:
            metadata = item.get("metadata", {}) or {}
            chunk_metadata = metadata.get("chunk_metadata", {}) or {}
            item["section"] = chunk_metadata.get("section") or metadata.get("section")
            item["topic"] = chunk_metadata.get("topic") or metadata.get("topic")

    def _log_search_top_results(self, query: str, results: List[Dict[str, Any]]) -> None:
        """记录检索最终Top结果摘要，便于判断召回、精排和分块质量。"""
        try:
            diagnostics = []
            for rank, item in enumerate(results[:5], 1):
                metadata = item.get("metadata", {}) or {}
                chunk_metadata = metadata.get("chunk_metadata", {}) or {}
                document = item.get("document", {}) or {}
                diagnostics.append({
                    "rank": rank,
                    "score": item.get("score"),
                    "original_score": item.get("original_score"),
                    "rerank_score": item.get("rerank_score"),
                    "document": document.get("filename") or item.get("filename"),
                    "kb": (item.get("knowledge_base") or {}).get("name"),
                    "chunk_index": item.get("chunk_index"),
                    "section": chunk_metadata.get("section") or metadata.get("section"),
                    "topic": chunk_metadata.get("topic") or metadata.get("topic"),
                    "preview": (item.get("content") or "")[:120]
                })
            logger.info(
                "knowledge_search_top_results",
                query_preview=query[:100],
                result_count=len(results),
                results=diagnostics
            )
        except Exception as e:
            logger.warning("knowledge_search_top_results_log_failed", error=str(e))

    async def _rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """使用BGE-Reranker重排序"""
        reranker = self._get_reranker()
        
        # 如果reranker不可用，回退到向量相似度排序
        if reranker is None:
            logger.warning("reranker_unavailable_fallback_to_vector_score")
            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[:top_k]

        try:
            rerank_started_at = time.time()
            pairs = [
                (
                    query,
                    (c.get("embedding_text") or c.get("metadata", {}).get("embedding_text") or c.get("content", ""))[:1200]
                )
                for c in candidates
            ]
            scores = reranker.predict(pairs)

            for i, score in enumerate(scores):
                candidates[i]["rerank_score"] = float(score)
                candidates[i]["original_score"] = candidates[i]["score"]
                candidates[i]["score"] = float(score)

            candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
            logger.info(
                "rerank_completed",
                candidate_count=len(candidates),
                top_k=top_k,
                elapsed_ms=round((time.time() - rerank_started_at) * 1000, 2)
            )
            return candidates[:top_k]
        except Exception as e:
            logger.warning("rerank_failed_fallback_to_vector_score", error=str(e))
            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[:top_k]

    async def _enrich_results_with_document_info(self, results: List[Dict[str, Any]]) -> None:
        """
        为检索结果添加原文档信息（用于溯源比对）
        
        Args:
            results: 检索结果列表（原地修改）
        """
        if not results or not self.db:
            return

        # 收集所有唯一的document_id
        doc_ids = list(set(
            r.get("document_id") 
            for r in results 
            if r.get("document_id")
        ))

        if not doc_ids:
            return

        try:
            # 批量查询文档信息
            from sqlalchemy import select
            doc_result = await self.db.execute(
                select(Document).where(Document.id.in_(doc_ids))
            )
            docs_map = {doc.id: doc for doc in doc_result.scalars().all()}

            # 为每个结果添加原文档信息
            for r in results:
                doc_id = r.get("document_id")
                if not doc_id:
                    continue

                doc = docs_map.get(doc_id)
                if doc:
                    # 检查是否有原文件
                    has_original_file = bool(
                        doc.original_file_oid or
                        (doc.file_storage_type == "local" and doc.file_path)
                    )

                    # 添加原文档信息
                    r["document"] = {
                        "id": doc.id,
                        "filename": doc.filename,
                        "file_type": doc.file_type,
                        "file_size": doc.file_size,
                        "file_storage_type": doc.file_storage_type,
                        "file_mime_type": doc.file_mime_type,
                        "has_original_file": has_original_file,
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                        "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
                    }

                    # 如果有原文件，添加知识库ID（用于生成下载链接）
                    if has_original_file:
                        kb_info = r.get("knowledge_base", {})
                        kb_id = kb_info.get("id")
                        if kb_id:
                            r["document"]["download_url"] = f"/api/knowledge-base/{kb_id}/documents/{doc_id}/download"
                            r["document"]["preview_url"] = f"/api/knowledge-base/{kb_id}/documents/{doc_id}/preview"

        except Exception as e:
            logger.warning(
                "enrich_document_info_failed",
                error=str(e),
                doc_count=len(doc_ids)
            )
            # 失败不影响主流程，继续返回结果

    # ============ 统计 ============

    async def get_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息"""
        kbs = await self.list_knowledge_bases(user_id=user_id)

        total_docs = sum(kb.document_count for kb in kbs)
        total_chunks = sum(kb.chunk_count for kb in kbs)
        total_size = sum(kb.total_size for kb in kbs)
        public_count = sum(1 for kb in kbs if kb.is_public)
        private_count = len(kbs) - public_count

        # 统计处理中和失败的文档
        processing = 0
        failed = 0
        for kb in kbs:
            docs = await self.list_documents(kb.id)
            processing += sum(1 for d in docs if d.status == DocumentStatus.PROCESSING)
            failed += sum(1 for d in docs if d.status == DocumentStatus.FAILED)

        return {
            "total_knowledge_bases": len(kbs),
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "total_size": total_size,
            "public_count": public_count,
            "private_count": private_count,
            "processing_documents": processing,
            "failed_documents": failed
        }

    # ============ 文档分段 ============

    async def get_document_chunks(
        self,
        kb_id: str,
        doc_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取文档的所有分段

        Args:
            kb_id: 知识库ID
            doc_id: 文档ID
            user_id: 用户ID（用于权限检查）

        Returns:
            文档分段信息
        """
        kb = await self.get_knowledge_base(kb_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        # 权限检查
        if kb.is_private and kb.owner_id != user_id:
            raise PermissionError("No permission to access this knowledge base")

        # 获取文档信息
        result = await self.db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.knowledge_base_id == kb_id
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")

        # 从Qdrant获取分段
        chunks = await self._get_chunks_from_qdrant(kb.qdrant_collection, doc_id)

        return {
            "document_id": doc_id,
            "filename": doc.filename,
            "chunks": chunks,
            "total": len(chunks)
        }

    async def _get_chunks_from_qdrant(
        self,
        collection_name: str,
        document_id: str
    ) -> List[Dict[str, Any]]:
        """从Qdrant获取文档的所有分段"""
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # 使用scroll获取所有匹配的点
            results = self.vector_store.qdrant_client.scroll(
                collection_name=collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id)
                    )]
                ),
                limit=1000,  # 最多1000个分块
                with_payload=True,
                with_vectors=False
            )

            chunks = []
            for point in results[0]:
                payload = point.payload
                chunks.append({
                    "chunk_index": payload.get("chunk_index", 0),
                    "content": payload.get("content", ""),
                    "original_content": payload.get("original_content") or payload.get("content", ""),
                    "context_prefix": payload.get("context_prefix", ""),
                    "embedding_text": payload.get("embedding_text", ""),
                    "chunk_id": payload.get("chunk_id"),
                    "start_char": payload.get("start_char"),
                    "end_char": payload.get("end_char"),
                    "metadata": payload.get("chunk_metadata", {})
                })

            # 按chunk_index排序
            chunks.sort(key=lambda x: x["chunk_index"])
            return chunks

        except Exception as e:
            logger.error(
                "get_chunks_from_qdrant_failed",
                collection=collection_name,
                document_id=document_id,
                error=str(e)
            )
            raise

    # ============ 辅助方法 ============

    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件MD5哈希"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
