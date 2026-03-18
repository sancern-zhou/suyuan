"""
知识库导入工具

功能：
- 导入 Qdrant 向量数据
- 导入 PostgreSQL 元数据
- 导入原始文档文件
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4
import hashlib

# 异步支持
import aiofiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams, SparseVectorParams, SparseIndexParams

import structlog

logger = structlog.get_logger()

# ============= 配置 =============

# 数据库配置
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_db"
)

# Qdrant配置
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# 嵌入模型配置（用于验证）
EMBEDDING_DIM = 1024  # BGE-M3 维度


class KnowledgeBaseImporter:
    """知识库导入器"""

    def __init__(
        self,
        db_url: str = DATABASE_URL,
        qdrant_host: str = QDRANT_HOST,
        qdrant_port: int = QDRANT_PORT,
        qdrant_api_key: Optional[str] = QDRANT_API_KEY,
        embedding_dim: int = EMBEDDING_DIM
    ):
        # 初始化 Qdrant 客户端
        self.qdrant_client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            api_key=qdrant_api_key
        )

        # 初始化数据库引擎（使用 asyncpg，与项目一致）
        self.db_engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300
        )
        self.db_session = async_sessionmaker(
            self.db_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        self.embedding_dim = embedding_dim

    async def close(self):
        """关闭连接"""
        await self.db_engine.dispose()
        logger.info("connections_closed")

    # ============= 导入方法 =============

    async def import_knowledge_base(
        self,
        input_dir: str,
        new_kb_id: Optional[str] = None,
        import_vectors: bool = True,
        import_files: bool = True,
        skip_on_conflict: bool = False
    ) -> Dict[str, Any]:
        """
        导入知识库

        Args:
            input_dir: 导出目录路径
            new_kb_id: 新的知识库ID（不提供则使用原ID）
            import_vectors: 是否导入向量数据
            import_files: 是否导入原始文件
            skip_on_conflict: 冲突时是否跳过

        Returns:
            导入结果信息
        """
        input_path = Path(input_dir)
        result = {
            "input_dir": str(input_path),
            "success": False,
            "errors": []
        }

        try:
            # 1. 读取元数据
            metadata_path = input_path / "metadata.json"
            if not metadata_path.exists():
                result["errors"].append(f"Metadata file not found: {metadata_path}")
                return result

            async with aiofiles.open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.loads(await f.read())

            kb_info = metadata["knowledge_base"]
            original_kb_id = kb_info["id"]

            # 使用新ID或原ID
            final_kb_id = new_kb_id or original_kb_id
            new_collection_name = f"kb_{final_kb_id.replace('-', '_')}"

            logger.info("importing_knowledge_base", original_id=original_kb_id, new_id=final_kb_id)

            # 2. 检查目标环境是否已存在
            existing_kb = await self._get_knowledge_base(final_kb_id)
            if existing_kb:
                if skip_on_conflict:
                    result["errors"].append(f"Knowledge base already exists: {final_kb_id}, skipped")
                    return result
                else:
                    result["errors"].append(f"Knowledge base already exists: {final_kb_id}")
                    return result

            # 3. 创建知识库记录
            await self._create_knowledge_base(kb_info, final_kb_id, new_collection_name)
            result["kb_id"] = final_kb_id
            result["collection_name"] = new_collection_name

            # 4. 导入文档信息
            docs_path = input_path / "documents.jsonl"
            if docs_path.exists():
                doc_count = await self._import_documents(
                    docs_path, final_kb_id, metadata.get("documents", [])
                )
                result["document_count"] = doc_count
                logger.info("documents_imported", count=doc_count)

            # 5. 创建向量 Collection
            if import_vectors:
                vectors_path = input_path / "vectors.jsonl"
                if vectors_path.exists():
                    # 检测是否使用混合向量
                    has_sparse = await self._check_sparse_vectors(vectors_path)

                    vector_count = await self._import_vectors(
                        vectors_path,
                        new_collection_name,
                        has_sparse=has_sparse
                    )
                    result["vector_count"] = vector_count
                    logger.info("vectors_imported", count=vector_count)

            # 6. 导入原始文件
            if import_files:
                files_dir = input_path / "original_files"
                if files_dir.exists():
                    files_count = await self._import_original_files(
                        files_dir, final_kb_id
                    )
                    result["original_files_count"] = files_count
                    logger.info("original_files_imported", count=files_count)

            result["success"] = True
            logger.info("knowledge_base_imported_success", kb_id=final_kb_id)

        except Exception as e:
            error_msg = f"Import failed: {str(e)}"
            result["errors"].append(error_msg)
            logger.error("import_failed", error=str(e))

        return result

    async def import_all(
        self,
        input_dir: str,
        import_vectors: bool = True,
        import_files: bool = True,
        skip_on_conflict: bool = False
    ) -> List[Dict[str, Any]]:
        """
        导入目录下所有知识库

        Args:
            input_dir: 导出目录路径
            import_vectors: 是否导入向量数据
            import_files: 是否导入原始文件
            skip_on_conflict: 冲突时是否跳过

        Returns:
            每个知识库的导入结果列表
        """
        input_path = Path(input_dir)
        results = []

        # 查找所有知识库导出目录
        kb_dirs = []
        for item in input_path.iterdir():
            if item.is_dir() and item.name.startswith("kb_"):
                kb_dirs.append(item)

        kb_dirs.sort(key=lambda x: x.name)

        logger.info("importing_all_knowledge_bases", count=len(kb_dirs))

        for kb_dir in kb_dirs:
            result = await self.import_knowledge_base(
                input_dir=str(kb_dir),
                import_vectors=import_vectors,
                import_files=import_files,
                skip_on_conflict=skip_on_conflict
            )
            results.append(result)

        # 生成汇总
        summary = {
            "import_time": datetime.now().isoformat(),
            "total": len(results),
            "successful": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
            "results": results
        }

        logger.info("all_knowledge_bases_imported", success=summary["successful"], failed=summary["failed"])

        return results

    # ============= 私有方法 =============

    async def _get_knowledge_base(self, kb_id: str) -> Optional[Dict[str, Any]]:
        """检查知识库是否存在"""
        async with self.db_session() as session:
            result = await session.execute(
                text("SELECT id, name FROM knowledge_bases WHERE id = :kb_id"),
                {"kb_id": kb_id}
            )
            row = result.fetchone()
            return {"id": row[0], "name": row[1]} if row else None

    async def _create_knowledge_base(
        self,
        kb_info: Dict[str, Any],
        new_kb_id: str,
        new_collection_name: str
    ):
        """创建知识库记录"""
        async with self.db_session() as session:
            await session.execute(
                text("""
                    INSERT INTO knowledge_bases (
                        id, name, description, kb_type, owner_id, is_default,
                        embedding_model, chunking_strategy, chunk_size, chunk_overlap,
                        qdrant_collection, status, document_count, chunk_count,
                        total_size, created_at, updated_at
                    ) VALUES (
                        :id, :name, :description, :kb_type, :owner_id, :is_default,
                        :embedding_model, :chunking_strategy, :chunk_size, :chunk_overlap,
                        :qdrant_collection, :status, :document_count, :chunk_count,
                        :total_size, :created_at, :updated_at
                    )
                """),
                {
                    "id": new_kb_id,
                    "name": kb_info["name"],
                    "description": kb_info.get("description", ""),
                    "kb_type": kb_info.get("kb_type", "private"),
                    "owner_id": kb_info.get("owner_id"),
                    "is_default": kb_info.get("is_default", False),
                    "embedding_model": kb_info.get("embedding_model", "BAAI/bge-m3"),
                    "chunking_strategy": kb_info.get("chunking_strategy", "sentence"),
                    "chunk_size": kb_info.get("chunk_size", 256),
                    "chunk_overlap": kb_info.get("chunk_overlap", 64),
                    "qdrant_collection": new_collection_name,
                    "status": "active",
                    "document_count": 0,
                    "chunk_count": 0,
                    "total_size": 0,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            await session.commit()

        logger.info("knowledge_base_record_created", kb_id=new_kb_id)

    async def _import_documents(
        self,
        docs_path: Path,
        kb_id: str,
        original_docs: List[Dict[str, Any]]
    ) -> int:
        """导入文档信息"""
        doc_map = {doc.get("original_id", doc["id"]): doc for doc in original_docs}
        count = 0

        async with aiofiles.open(docs_path, "r", encoding="utf-8") as f:
            async for line in f:
                doc_data = json.loads(line)
                original_doc_id = doc_data["id"]

                # 生成新的文档ID
                new_doc_id = str(uuid4())

                async with self.db_session() as session:
                    await session.execute(
                        text("""
                            INSERT INTO documents (
                                id, knowledge_base_id, filename, file_type, file_size,
                                file_hash, file_path, original_file_oid, file_storage_type,
                                file_mime_type, file_checksum, storage_size, file_preview_text,
                                status, chunk_count, error_message, retry_count,
                                extra_metadata, created_at, processed_at, updated_at
                            ) VALUES (
                                :id, :knowledge_base_id, :filename, :file_type, :file_size,
                                :file_hash, :file_path, :original_file_oid, :file_storage_type,
                                :file_mime_type, :file_checksum, :storage_size, :file_preview_text,
                                :status, :chunk_count, :error_message, :retry_count,
                                :extra_metadata, :created_at, :processed_at, :updated_at
                            )
                        """),
                        {
                            "id": new_doc_id,
                            "knowledge_base_id": kb_id,
                            "filename": doc_data["filename"],
                            "file_type": doc_data["file_type"],
                            "file_size": doc_data["file_size"],
                            "file_hash": doc_data["file_hash"],
                            "file_path": doc_data.get("file_path"),
                            "original_file_oid": None,  # 重新导入时需要处理
                            "file_storage_type": doc_data.get("file_storage_type", "local"),
                            "file_mime_type": doc_data.get("file_mime_type"),
                            "file_checksum": doc_data.get("file_checksum"),
                            "storage_size": doc_data.get("storage_size", 0),
                            "file_preview_text": doc_data.get("file_preview_text"),
                            "status": doc_data["status"],
                            "chunk_count": doc_data.get("chunk_count", 0),
                            "error_message": doc_data.get("error_message"),
                            "retry_count": doc_data.get("retry_count", 0),
                            "extra_metadata": json.dumps(doc_data.get("extra_metadata", {})),
                            "created_at": datetime.fromisoformat(doc_data["created_at"]) if doc_data.get("created_at") else datetime.utcnow(),
                            "processed_at": datetime.fromisoformat(doc_data["processed_at"]) if doc_data.get("processed_at") else None,
                            "updated_at": datetime.utcnow()
                        }
                    )
                    await session.commit()

                # 更新文档计数
                async with self.db_session() as session:
                    await session.execute(
                        text("""
                            UPDATE knowledge_bases
                            SET document_count = document_count + 1,
                                chunk_count = chunk_count + :chunk_count,
                                total_size = total_size + :file_size,
                                updated_at = :updated_at
                            WHERE id = :kb_id
                        """),
                        {
                            "kb_id": kb_id,
                            "chunk_count": doc_data.get("chunk_count", 0),
                            "file_size": doc_data.get("file_size", 0),
                            "updated_at": datetime.utcnow()
                        }
                    )
                    await session.commit()

                count += 1

        return count

    async def _check_sparse_vectors(self, vectors_path: Path) -> bool:
        """检查是否包含稀疏向量"""
        async with aiofiles.open(vectors_path, "r", encoding="utf-8") as f:
            async for line in f:
                record = json.loads(line)
                vector = record.get("vector", {})
                if isinstance(vector, dict) and "sparse" in vector:
                    return True
                break
        return False

    async def _import_vectors(
        self,
        vectors_path: Path,
        collection_name: str,
        has_sparse: bool = False
    ) -> int:
        """导入向量数据"""
        # 检查并创建 collection
        try:
            collections = self.qdrant_client.get_collections()
            existing_names = [c.name for c in collections.collections]
        except Exception:
            existing_names = []

        if collection_name not in existing_names:
            if has_sparse:
                self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "dense": VectorParams(
                            size=self.embedding_dim,
                            distance=Distance.COSINE
                        )
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams(
                            index=SparseIndexParams(on_disk=False)
                        )
                    }
                )
            else:
                self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
            logger.info("collection_created", collection=collection_name)

        # 批量导入
        count = 0
        batch_size = 100
        batch = []

        async with aiofiles.open(vectors_path, "r", encoding="utf-8") as f:
            async for line in f:
                record = json.loads(line)

                point = PointStruct(
                    id=record["id"],
                    vector=record["vector"],
                    payload=record["payload"]
                )
                batch.append(point)

                if len(batch) >= batch_size:
                    try:
                        self.qdrant_client.upsert(
                            collection_name=collection_name,
                            points=batch
                        )
                        count += len(batch)
                    except Exception as e:
                        logger.warning("batch_upsert_failed", error=str(e))
                    batch = []

        # 处理剩余批次
        if batch:
            try:
                self.qdrant_client.upsert(
                    collection_name=collection_name,
                    points=batch
                )
                count += len(batch)
            except Exception as e:
                logger.warning("final_batch_upsert_failed", error=str(e))

        return count

    async def _import_original_files(
        self,
        files_dir: Path,
        kb_id: str
    ) -> int:
        """导入原始文档文件到数据库存储"""
        count = 0

        # 获取所有文档信息
        async with self.db_session() as session:
            result = await session.execute(
                text("SELECT id, filename FROM documents WHERE knowledge_base_id = :kb_id"),
                {"kb_id": kb_id}
            )
            docs = {row[1]: row[0] for row in result.fetchall()}

        for file_path in files_dir.iterdir():
            if not file_path.is_file():
                continue

            filename = file_path.name
            if filename not in docs:
                logger.warning("file_no_document", filename=filename)
                continue

            doc_id = docs[filename]

            try:
                # 读取文件内容
                file_data = file_path.read_bytes()

                # 计算校验和
                checksum = hashlib.sha256(file_data).hexdigest()

                # 存储到 PostgreSQL Large Object
                async with self.db_session() as session:
                    # 导入 Large Object
                    loid = await session.execute(
                        text("SELECT lo_import(:path)"),
                        {"path": str(file_path)}
                    )
                    loid = loid.scalar()

                    # 更新文档记录
                    await session.execute(
                        text("""
                            UPDATE documents
                            SET original_file_oid = :loid,
                                file_storage_type = 'database',
                                file_checksum = :checksum,
                                storage_size = :size
                            WHERE id = :doc_id
                        """),
                        {
                            "loid": loid,
                            "checksum": checksum,
                            "size": len(file_data),
                            "doc_id": doc_id
                        }
                    )
                    await session.commit()

                count += 1
                logger.debug("file_imported", filename=filename, doc_id=doc_id)

            except Exception as e:
                logger.warning("file_import_failed", filename=filename, error=str(e))

        return count


# ============= 主入口 =============

async def main():
    """主入口函数"""
    import argparse

    parser = argparse.ArgumentParser(description="知识库导入工具")
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="导出的知识库目录路径"
    )
    parser.add_argument(
        "--new-kb-id",
        type=str,
        help="新的知识库ID（不提供则使用原ID）"
    )
    parser.add_argument(
        "--skip-vectors",
        action="store_true",
        help="跳过向量数据导入"
    )
    parser.add_argument(
        "--skip-files",
        action="store_true",
        help="跳过原始文件导入"
    )
    parser.add_argument(
        "--skip-on-conflict",
        action="store_true",
        help="知识库已存在时跳过"
    )

    args = parser.parse_args()

    importer = KnowledgeBaseImporter()

    try:
        result = await importer.import_knowledge_base(
            input_dir=args.input_dir,
            new_kb_id=args.new_kb_id,
            import_vectors=not args.skip_vectors,
            import_files=not args.skip_files,
            skip_on_conflict=args.skip_on_conflict
        )

        print(f"\n导入结果:")
        print(f"  成功: {result['success']}")
        if result.get('kb_id'):
            print(f"  知识库ID: {result['kb_id']}")
            print(f"  Collection: {result.get('collection_name', 'N/A')}")
        print(f"  文档数量: {result.get('document_count', 0)}")
        print(f"  向量数量: {result.get('vector_count', 0)}")
        print(f"  原始文件: {result.get('original_files_count', 0)}")
        if result['errors']:
            print(f"  错误: {result['errors']}")

    finally:
        await importer.close()


if __name__ == "__main__":
    import sys
    asyncio.run(main())
