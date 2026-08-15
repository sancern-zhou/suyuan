"""
数据库迁移脚本：添加文档存储相关字段

为Document表添加原文件存储所需的字段：
- original_file_oid: PostgreSQL Large Object ID
- file_storage_type: 存储类型 (database/local/oss)
- file_mime_type: MIME类型
- file_checksum: SHA256校验和
- storage_size: 实际存储大小
- file_preview_text: 文件预览文本

使用方法：
    cd backend
    python scripts/migrate_document_storage.py
"""

import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def run_migration():
    """执行数据库迁移"""

    # 从环境变量获取数据库URL
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("Error: DATABASE_URL environment variable is not set.")
        print("Please configure it in your .env file.")
        return

    print(f"Connecting to database...")
    print(f"URL: {database_url[:50]}...")

    engine = create_async_engine(database_url, echo=True)

    async with engine.begin() as conn:
        # 检查数据库类型
        is_postgres = "postgresql" in database_url.lower()

        print(f"Database type: {'PostgreSQL' if is_postgres else 'Other'}")

        if not is_postgres:
            print("Warning: This migration is designed for PostgreSQL. Other databases may not support Large Objects.")

        # 定义要添加的字段
        columns_to_add = [
            ("original_file_oid", "BIGINT"),
            ("file_storage_type", "VARCHAR(20) DEFAULT 'database'"),
            ("file_mime_type", "VARCHAR(100)"),
            ("file_checksum", "VARCHAR(64)"),
            ("storage_size", "BIGINT DEFAULT 0"),
            ("file_preview_text", "TEXT"),
        ]

        for col_name, col_type in columns_to_add:
            try:
                # PostgreSQL语法：ADD COLUMN IF NOT EXISTS
                await conn.execute(text(
                    f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                print(f"Added column: {col_name}")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"Column {col_name} already exists, skipping...")
                else:
                    print(f"Warning: Could not add column {col_name}: {e}")

        # 创建索引
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_documents_storage_type ON documents(file_storage_type)"
            ))
            print("Created index: idx_documents_storage_type")
        except Exception as e:
            print(f"Warning: Could not create index: {e}")

        print("\nMigration completed successfully!")

        # 显示当前表结构
        try:
            result = await conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'documents'
                ORDER BY ordinal_position
            """))
            print("\nCurrent documents table structure:")
            for row in result:
                print(f"  - {row[0]}: {row[1]} (nullable: {row[2]})")
        except Exception as e:
            print(f"Could not retrieve table structure: {e}")

    await engine.dispose()


if __name__ == "__main__":
    print("=" * 60)
    print("Document Storage Migration Script")
    print("=" * 60)

    asyncio.run(run_migration())
