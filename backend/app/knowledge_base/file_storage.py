"""
数据库文件存储服务
使用PostgreSQL Large Object存储原文件，确保数据可靠性
"""

import os
import hashlib
import shutil
from typing import Optional, Tuple, Dict, Any
import mimetypes
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = structlog.get_logger()


class DatabaseFileStorageService:
    """PostgreSQL数据库文件存储服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        # 支持的存储类型
        self.supported_types = {
            ".pdf", ".docx", ".doc", ".xlsx", ".xls",
            ".pptx", ".ppt", ".html", ".htm", ".txt",
            ".md", ".csv", ".json", ".xml", ".rtf"
        }

    async def store_original_file(
        self,
        temp_file_path: str,
        original_filename: str,
        document_id: str,
        knowledge_base_id: str
    ) -> Dict[str, Any]:
        """
        将文件存储到PostgreSQL Large Object

        Returns:
            {
                "storage_type": "database",
                "loid": "Large Object ID",
                "mime_type": "MIME类型",
                "checksum": "SHA256校验和",
                "size": "文件大小"
            }
        """

        # 1. 获取文件信息
        file_ext = os.path.splitext(original_filename)[1].lower()
        mime_type, _ = mimetypes.guess_type(original_filename)

        if file_ext not in self.supported_types:
            raise ValueError(f"Unsupported file type: {file_ext}")

        # 2. 读取文件数据
        with open(temp_file_path, "rb") as f:
            file_data = f.read()

        file_size = len(file_data)

        # 3. 计算SHA256校验和
        checksum = hashlib.sha256(file_data).hexdigest()

        # 4. 存储到PostgreSQL Large Object
        loid = await self._store_to_lo(file_data)

        logger.info(
            "file_stored_to_database",
            document_id=document_id,
            loid=loid,
            mime_type=mime_type,
            size=file_size,
            checksum=checksum[:16] + "..."  # 只记录前16位用于日志
        )

        return {
            "storage_type": "database",
            "loid": str(loid),
            "mime_type": mime_type or "application/octet-stream",
            "checksum": checksum,
            "size": file_size
        }

    async def _store_to_lo(self, data: bytes) -> int:
        """存储到PostgreSQL Large Object"""
        try:
            # 使用SQLAlchemy的text()包装SQL语句
            # 创建Large Object
            result = await self.db.execute(text("SELECT lo_create(0)"))
            loid = result.scalar()

            # 使用lo_put写入数据（PostgreSQL 9.4+）
            # lo_put(loid, offset, data) - 直接写入整个数据
            await self.db.execute(
                text("SELECT lo_put(:loid, 0, :data)"),
                {"loid": loid, "data": data}
            )

            return loid

        except Exception as e:
            logger.error("lo_store_failed", error=str(e))
            raise

    async def retrieve_file(self, loid: int) -> Tuple[bytes, str]:
        """
        从数据库读取文件

        Returns:
            (file_bytes, mime_type)
        """
        try:
            # 使用lo_get读取Large Object
            result = await self.db.execute(
                text("SELECT lo_get(:loid)"),
                {"loid": loid}
            )
            file_bytes = result.scalar()

            if file_bytes is None:
                raise FileNotFoundError(f"File not found in database: OID {loid}")

            # 获取MIME类型（这里简化处理，实际应从文档记录获取）
            return file_bytes, "application/octet-stream"

        except Exception as e:
            logger.error("file_retrieval_failed", loid=loid, error=str(e))
            raise

    async def delete_file(self, loid: int) -> bool:
        """从数据库删除文件"""
        try:
            await self.db.execute(
                text("SELECT lo_unlink(:loid)"),
                {"loid": loid}
            )
            logger.info("file_deleted_from_database", loid=loid)
            return True
        except Exception as e:
            logger.error("file_delete_failed", loid=loid, error=str(e))
            return False

    async def get_file_info(self, loid: int) -> Dict[str, Any]:
        """获取文件信息（从pg_largeobject表）"""
        try:
            result = await self.db.execute(
                text("""
                SELECT
                    sum(octet_length(data)) as size
                FROM pg_largeobject
                WHERE loid = :loid
                """),
                {"loid": loid}
            )
            row = result.fetchone()
            if row and row[0]:
                return {"size": row[0]}
            return {}
        except Exception as e:
            logger.error("file_info_failed", loid=loid, error=str(e))
            return {}

# 本地文件存储（作为回退方案）
class LocalFileStorageService:
    """本地文件存储服务"""

    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.getenv(
            "KNOWLEDGE_BASE_STORAGE_DIR",
            "data/knowledge_base/files"
        )
        os.makedirs(self.storage_dir, exist_ok=True)

    async def store_original_file(
        self,
        temp_file_path: str,
        original_filename: str,
        document_id: str,
        knowledge_base_id: str
    ) -> Dict[str, Any]:
        """存储到本地文件系统"""
        import shutil

        file_ext = os.path.splitext(original_filename)[1].lower()
        kb_dir = os.path.join(self.storage_dir, knowledge_base_id)
        os.makedirs(kb_dir, exist_ok=True)

        storage_filename = f"{document_id}{file_ext}"
        storage_path = os.path.join(kb_dir, storage_filename)

        shutil.move(temp_file_path, storage_path)

        return {
            "storage_type": "local",
            "storage_path": storage_path,
            "mime_type": mimetypes.guess_type(original_filename)[0],
            "size": os.path.getsize(storage_path)
        }

    async def retrieve_file(self, storage_path: str) -> Tuple[bytes, str]:
        """从本地读取文件"""
        try:
            with open(storage_path, "rb") as f:
                file_bytes = f.read()
            mime_type, _ = mimetypes.guess_type(storage_path)
            return file_bytes, mime_type or "application/octet-stream"
        except Exception as e:
            logger.error("local_file_read_failed", path=storage_path, error=str(e))
            raise

    async def delete_file(self, storage_path: str) -> bool:
        """删除本地文件"""
        try:
            if os.path.exists(storage_path):
                os.remove(storage_path)
                logger.info("local_file_deleted", path=storage_path)
                return True
            return False
        except Exception as e:
            logger.error("local_file_delete_failed", path=storage_path, error=str(e))
            return False

# 智能存储策略（根据文件大小自动选择）
class SmartFileStorage:
    """智能文件存储服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.database_storage = DatabaseFileStorageService(db)
        self.local_storage = LocalFileStorageService()

        # 存储策略阈值
        self.db_max_size = 5 * 1024 * 1024  # 5MB
        self.local_max_size = 100 * 1024 * 1024  # 100MB

    async def store_file(
        self,
        temp_file_path: str,
        original_filename: str,
        document_id: str,
        knowledge_base_id: str
    ) -> Dict[str, Any]:
        """根据文件大小智能选择存储方式"""
        file_size = os.path.getsize(temp_file_path)

        if file_size <= self.db_max_size:
            # 小文件：数据库存储
            return await self.database_storage.store_original_file(
                temp_file_path, original_filename, document_id, knowledge_base_id
            )
        elif file_size <= self.local_max_size:
            # 中等文件：本地存储
            return await self.local_storage.store_original_file(
                temp_file_path, original_filename, document_id, knowledge_base_id
            )
        else:
            # 大文件：抛出错误（需要配置OSS）
            raise ValueError(
                f"File too large ({file_size} bytes). "
                "Please configure OSS storage for files larger than 100MB"
            )
