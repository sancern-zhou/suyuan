"""
知识库导出工具

功能：
- 导出 Qdrant 向量数据（collection）
- 导出 PostgreSQL 元数据（知识库、文档信息）
- 导出原始文档文件
- 生成导入说明文件
"""

import os
import json
import asyncio
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

# 异步支持
import aiofiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Qdrant
from qdrant_client import QdrantClient

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

# 导出目录
EXPORT_DIR = os.getenv("EXPORT_DIR", "./knowledge_base_exports")


class KnowledgeBaseExporter:
    """知识库导出器"""

    def __init__(
        self,
        export_dir: str = EXPORT_DIR,
        db_url: str = DATABASE_URL,
        qdrant_host: str = QDRANT_HOST,
        qdrant_port: int = QDRANT_PORT,
        qdrant_api_key: Optional[str] = QDRANT_API_KEY
    ):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

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

        # 日期时间戳
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    async def close(self):
        """关闭连接"""
        await self.db_engine.dispose()
        logger.info("connections_closed")

    # ============= 知识库导出 =============

    async def export_knowledge_base(
        self,
        kb_id: str,
        include_documents: bool = True,
        include_vectors: bool = True,
        include_original_files: bool = True
    ) -> Dict[str, Any]:
        """
        导出单个知识库

        Args:
            kb_id: 知识库ID
            include_documents: 是否包含文档信息
            include_vectors: 是否包含向量数据
            include_original_files: 是否包含原始文档文件

        Returns:
            导出结果信息
        """
        export_kb_dir = self.export_dir / f"kb_{kb_id}_{self.timestamp}"
        export_kb_dir.mkdir(parents=True, exist_ok=True)

        result = {
            "kb_id": kb_id,
            "export_dir": str(export_kb_dir),
            "success": False,
            "errors": []
        }

        try:
            # 1. 获取知识库信息
            kb_info = await self._get_knowledge_base_info(kb_id)
            if not kb_info:
                result["errors"].append(f"Knowledge base not found: {kb_id}")
                return result

            result["kb_info"] = kb_info
            logger.info("exporting_knowledge_base", kb_id=kb_id, kb_name=kb_info["name"])

            # 2. 导出元数据
            metadata_path = export_kb_dir / "metadata.json"
            await self._export_metadata(kb_id, metadata_path)
            result["metadata_file"] = str(metadata_path)

            # 3. 导出向量数据
            if include_vectors:
                vectors_path = export_kb_dir / "vectors.jsonl"
                vector_count = await self._export_vectors(kb_info["qdrant_collection"], vectors_path)
                result["vector_count"] = vector_count
                result["vectors_file"] = str(vectors_path)
                logger.info("vectors_exported", count=vector_count)

            # 4. 导出文档信息
            if include_documents:
                docs_path = export_kb_dir / "documents.jsonl"
                doc_count = await self._export_documents(kb_id, docs_path)
                result["document_count"] = doc_count
                result["documents_file"] = str(docs_path)
                logger.info("documents_exported", count=doc_count)

            # 5. 导出原始文件
            if include_original_files:
                files_dir = export_kb_dir / "original_files"
                files_count = await self._export_original_files(kb_id, files_dir)
                result["original_files_count"] = files_count
                result["original_files_dir"] = str(files_dir)
                logger.info("original_files_exported", count=files_count)

            # 6. 生成导入说明
            readme_path = export_kb_dir / "IMPORT_GUIDE.md"
            self._generate_import_guide(kb_info, readme_path)
            result["import_guide"] = str(readme_path)

            result["success"] = True
            logger.info("knowledge_base_exported_success", kb_id=kb_id)

        except Exception as e:
            error_msg = f"Export failed: {str(e)}"
            result["errors"].append(error_msg)
            logger.error("export_failed", kb_id=kb_id, error=str(e))

        return result

    async def export_all_knowledge_bases(
        self,
        include_vectors: bool = True,
        include_original_files: bool = True
    ) -> List[Dict[str, Any]]:
        """
        导出所有知识库

        Returns:
            每个知识库的导出结果列表
        """
        results = []

        async with self.db_session() as session:
            result = await session.execute(
                text("SELECT id FROM knowledge_bases")
            )
            kb_ids = [row[0] for row in result.fetchall()]

        logger.info("exporting_all_knowledge_bases", count=len(kb_ids))

        for kb_id in kb_ids:
            export_result = await self.export_knowledge_base(
                kb_id=kb_id,
                include_vectors=include_vectors,
                include_original_files=include_original_files
            )
            results.append(export_result)

        # 生成汇总报告
        summary_path = self.export_dir / f"export_summary_{self.timestamp}.json"
        summary = {
            "export_time": self.timestamp,
            "total_knowledge_bases": len(kb_ids),
            "successful": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
            "results": results
        }
        async with aiofiles.open(summary_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(summary, ensure_ascii=False, indent=2))

        logger.info("all_knowledge_bases_exported", success=summary["successful"], failed=summary["failed"])

        return results

    # ============= 私有方法 =============

    async def _get_knowledge_base_info(self, kb_id: str) -> Optional[Dict[str, Any]]:
        """获取知识库信息"""
        async with self.db_session() as session:
            result = await session.execute(
                text(f"""
                    SELECT id, name, description, kb_type, owner_id, is_default,
                           embedding_model, chunking_strategy, chunk_size, chunk_overlap,
                           qdrant_collection, status, document_count, chunk_count,
                           total_size, created_at, updated_at
                    FROM knowledge_bases
                    WHERE id = :kb_id
                """),
                {"kb_id": kb_id}
            )
            row = result.fetchone()

            if not row:
                return None

            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "kb_type": row[3],
                "owner_id": row[4],
                "is_default": row[5],
                "embedding_model": row[6],
                "chunking_strategy": row[7],
                "chunk_size": row[8],
                "chunk_overlap": row[9],
                "qdrant_collection": row[10],
                "status": row[11],
                "document_count": row[12],
                "chunk_count": row[13],
                "total_size": row[14],
                "created_at": row[15].isoformat() if row[15] else None,
                "updated_at": row[16].isoformat() if row[16] else None
            }

    async def _export_metadata(self, kb_id: str, output_path: Path):
        """导出知识库和文档元数据"""
        async with self.db_session() as session:
            # 知识库信息
            kb_result = await session.execute(
                text("""
                    SELECT id, name, description, kb_type, owner_id, is_default,
                           embedding_model, chunking_strategy, chunk_size, chunk_overlap,
                           qdrant_collection, status, document_count, chunk_count,
                           total_size, created_at, updated_at
                    FROM knowledge_bases
                    WHERE id = :kb_id
                """),
                {"kb_id": kb_id}
            )
            kb_row = kb_result.fetchone()

            # 文档信息
            docs_result = await session.execute(
                text("""
                    SELECT id, filename, file_type, file_size, file_hash,
                           file_storage_type, file_mime_type, storage_size,
                           status, chunk_count, error_message, extra_metadata,
                           created_at, processed_at, updated_at
                    FROM documents
                    WHERE knowledge_base_id = :kb_id
                    ORDER BY created_at
                """),
                {"kb_id": kb_id}
            )
            docs_rows = docs_result.fetchall()

            metadata = {
                "export_time": datetime.now().isoformat(),
                "knowledge_base": {
                    "id": kb_row[0],
                    "name": kb_row[1],
                    "description": kb_row[2],
                    "kb_type": kb_row[3],
                    "owner_id": kb_row[4],
                    "is_default": kb_row[5],
                    "embedding_model": kb_row[6],
                    "chunking_strategy": kb_row[7],
                    "chunk_size": kb_row[8],
                    "chunk_overlap": kb_row[9],
                    "qdrant_collection": kb_row[10],
                    "status": kb_row[11],
                    "document_count": kb_row[12],
                    "chunk_count": kb_row[13],
                    "total_size": kb_row[14],
                    "created_at": kb_row[15].isoformat() if kb_row[15] else None,
                    "updated_at": kb_row[16].isoformat() if kb_row[16] else None
                },
                "documents": []
            }

            for row in docs_rows:
                metadata["documents"].append({
                    "id": row[0],
                    "filename": row[1],
                    "file_type": row[2],
                    "file_size": row[3],
                    "file_hash": row[4],
                    "file_storage_type": row[5],
                    "file_mime_type": row[6],
                    "storage_size": row[7],
                    "status": row[8],
                    "chunk_count": row[9],
                    "error_message": row[10],
                    "extra_metadata": row[11],
                    "created_at": row[12].isoformat() if row[12] else None,
                    "processed_at": row[13].isoformat() if row[13] else None,
                    "updated_at": row[14].isoformat() if row[14] else None
                })

        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(metadata, ensure_ascii=False, indent=2))

        logger.info("metadata_exported", doc_count=len(metadata["documents"]))

    async def _export_vectors(self, collection_name: str, output_path: Path) -> int:
        """导出向量数据到 JSONL 格式"""
        from qdrant_client.models import ScrollResult

        count = 0

        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            # 使用 scroll API 分批获取数据
            offset = None

            while True:
                try:
                    result: ScrollResult = self.qdrant_client.scroll(
                        collection_name=collection_name,
                        offset=offset,
                        limit=100,
                        with_payload=True,
                        with_vectors=True
                    )

                    points = result[0]
                    next_offset = result[1]

                    for point in points:
                        record = {
                            "id": point.id,
                            "vector": point.vector if point.vector else {},
                            "payload": point.payload
                        }
                        await f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        count += 1

                    if next_offset is None:
                        break
                    offset = next_offset

                except Exception as e:
                    logger.error("scroll_failed", collection=collection_name, error=str(e))
                    break

        return count

    async def _export_documents(self, kb_id: str, output_path: Path) -> int:
        """导出文档信息到 JSONL 格式"""
        async with self.db_session() as session:
            result = await session.execute(
                text("""
                    SELECT id, knowledge_base_id, filename, file_type, file_size, file_hash,
                           file_path, original_file_oid, file_storage_type, file_mime_type,
                           file_checksum, storage_size, file_preview_text,
                           status, chunk_count, error_message, retry_count,
                           extra_metadata, created_at, processed_at, updated_at
                    FROM documents
                    WHERE knowledge_base_id = :kb_id
                    ORDER BY created_at
                """),
                {"kb_id": kb_id}
            )
            rows = result.fetchall()

        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            for row in rows:
                doc = {
                    "id": row[0],
                    "knowledge_base_id": row[1],
                    "filename": row[2],
                    "file_type": row[3],
                    "file_size": row[4],
                    "file_hash": row[5],
                    "file_path": row[6],
                    "original_file_oid": row[7],
                    "file_storage_type": row[8],
                    "file_mime_type": row[9],
                    "file_checksum": row[10],
                    "storage_size": row[11],
                    "file_preview_text": row[12],
                    "status": row[13],
                    "chunk_count": row[14],
                    "error_message": row[15],
                    "retry_count": row[16],
                    "extra_metadata": row[17],
                    "created_at": row[18].isoformat() if row[18] else None,
                    "processed_at": row[19].isoformat() if row[19] else None,
                    "updated_at": row[20].isoformat() if row[20] else None
                }
                await f.write(json.dumps(doc, ensure_ascii=False) + "\n")

        return len(rows)

    async def _export_original_files(self, kb_id: str, output_dir: Path) -> int:
        """导出原始文档文件"""
        output_dir.mkdir(parents=True, exist_ok=True)
        count = 0

        async with self.db_session() as session:
            result = await session.execute(
                text("""
                    SELECT id, filename, file_storage_type, original_file_oid, file_path
                    FROM documents
                    WHERE knowledge_base_id = :kb_id
                """),
                {"kb_id": kb_id}
            )
            rows = result.fetchall()

            for row in rows:
                doc_id, filename, storage_type, loid, file_path = row

                try:
                    # 只处理已完成且有文件的文档
                    if storage_type not in ("database", "local"):
                        continue
                    if storage_type == "database" and loid:
                        # 从 PostgreSQL Large Object 导出
                        file_data = await session.execute(
                            text("SELECT lo_get(:loid)"),
                            {"loid": loid}
                        )
                        data = file_data.scalar()

                        # 保存文件
                        safe_filename = self._sanitize_filename(filename)
                        file_path_out = output_dir / safe_filename

                        async with aiofiles.open(file_path_out, "wb") as f:
                            await f.write(data)

                        count += 1
                        logger.debug("file_exported_from_db", doc_id=doc_id, filename=filename)

                    elif storage_type == "local" and file_path and os.path.exists(file_path):
                        # 从本地文件系统复制
                        safe_filename = self._sanitize_filename(filename)
                        file_path_out = output_dir / safe_filename

                        # 复制文件
                        with open(file_path, "rb") as src:
                            with open(file_path_out, "wb") as dst:
                                dst.write(src.read())

                        count += 1
                        logger.debug("file_copied_from_local", doc_id=doc_id, filename=filename)

                except Exception as e:
                    logger.warning("file_export_failed", doc_id=doc_id, filename=filename, error=str(e))

        return count

    def _generate_import_guide(self, kb_info: Dict[str, Any], output_path: Path):
        """生成导入说明文件"""
        collection = kb_info["qdrant_collection"]

        guide = f'''# 知识库导入说明

## 导出信息

- 知识库名称: {kb_info["name"]}
- 知识库ID: {kb_info["id"]}
- 导出时间: {datetime.now().isoformat()}
- Collection名称: {collection}

## 导入步骤

### 方式一：使用导入脚本（推荐）

```bash
# 进入后端目录
cd backend

# 运行导入脚本
python -m app.knowledge_base.import_knowledge_base --input-dir ./knowledge_base_exports/kb_{kb_info["id"]}_{self.timestamp}
```

### 方式二：手动导入

#### 1. 还原元数据

```bash
# 连接到数据库
psql -U postgres -d weather_db

# 导入知识库和文档信息（需要手动调整ID）
```

#### 2. 还原向量数据

```python
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)

# 导入向量
client.import_collection(
    collection_name="{collection}",
    path="./vectors.jsonl"
)
```

#### 3. 还原原始文件

将 `original_files/` 目录下的文件复制到相应的存储位置。

## 环境要求

- PostgreSQL 12+
- Qdrant 1.7+
- Python 3.9+

## 配置说明

确保目标环境配置以下环境变量：

```bash
# 数据库
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/weather_db

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=  # 可选
```

## 向量模型

当前知识库使用的嵌入模型: `{kb_info["embedding_model"]}`

导入目标环境时，需要确保使用相同或兼容的嵌入模型。

## 分块配置

- 分块策略: `{kb_info["chunking_strategy"]}`
- 分块大小: `{kb_info["chunk_size"]}`
- 重叠大小: `{kb_info["chunk_overlap"]}`

## 文件列表

- `metadata.json` - 知识库和文档元数据
- `vectors.jsonl` - 向量数据（如果导出时包含）
- `documents.jsonl` - 文档详细信息
- `original_files/` - 原始文档文件（如果导出时包含）

## 注意事项

1. 导入后可能需要重新向量化（如果目标环境的嵌入模型不同）
2. 原始文件如果存储在数据库中（Large Object），导入时需要重建
3. Collection名称在导入时会自动创建
'''

        output_path.write_text(guide, encoding="utf-8")
        logger.info("import_guide_generated", path=str(output_path))

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除非法字符"""
        import re
        # 替换非法字符
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # 限制长度
        if len(sanitized) > 200:
            name, ext = os.path.splitext(sanitized)
            sanitized = name[:190] + ext
        return sanitized


# ============= 主入口 =============

async def main():
    """主入口函数"""
    import argparse

    parser = argparse.ArgumentParser(description="知识库导出工具")
    parser.add_argument(
        "--kb-id",
        type=str,
        help="指定导出的知识库ID，不指定则导出所有"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=EXPORT_DIR,
        help=f"导出目录（默认: {EXPORT_DIR})"
    )
    parser.add_argument(
        "--skip-vectors",
        action="store_true",
        help="跳过向量数据导出（减少导出时间）"
    )
    parser.add_argument(
        "--skip-files",
        action="store_true",
        help="跳过原始文件导出（减少磁盘占用）"
    )

    args = parser.parse_args()

    exporter = KnowledgeBaseExporter(export_dir=args.output_dir)

    try:
        if args.kb_id:
            # 导出单个知识库
            result = await exporter.export_knowledge_base(
                kb_id=args.kb_id,
                include_vectors=not args.skip_vectors,
                include_original_files=not args.skip_files
            )
            print(f"\n导出结果:")
            print(f"  知识库: {result.get('kb_info', {}).get('name', 'N/A')}")
            print(f"  成功: {result['success']}")
            print(f"  向量数量: {result.get('vector_count', 0)}")
            print(f"  文档数量: {result.get('document_count', 0)}")
            print(f"  原始文件: {result.get('original_files_count', 0)}")
            print(f"  导出目录: {result['export_dir']}")
            if result['errors']:
                print(f"  错误: {result['errors']}")
        else:
            # 导出所有知识库
            results = await exporter.export_all_knowledge_bases(
                include_vectors=not args.skip_vectors,
                include_original_files=not args.skip_files
            )
            print(f"\n导出完成:")
            print(f"  总数: {len(results)}")
            print(f"  成功: {sum(1 for r in results if r['success'])}")
            print(f"  失败: {sum(1 for r in results if not r['success'])}")
            print(f"  导出目录: {args.output_dir}")

    finally:
        await exporter.close()


if __name__ == "__main__":
    import sys
    asyncio.run(main())
