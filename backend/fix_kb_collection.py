#!/usr/bin/env python3
"""
修复知识库Collection向量配置问题

删除并重建Collection，使用单一向量配置（兼容旧版）。
"""
import asyncio
from qdrant_client import QdrantClient
from app.db.database import async_session
from sqlalchemy import select
from app.knowledge_base.models import KnowledgeBase


async def fix_collection(kb_id: str = None):
    """
    修复知识库Collection

    Args:
        kb_id: 知识库ID，如果为None则修复所有问题Collection
    """
    # 连接Qdrant
    client = QdrantClient(url='http://localhost:6333', timeout=60)

    async with async_session() as db:
        if kb_id:
            result = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
            kbs = [result.scalar_one_or_none()]
        else:
            result = await db.execute(select(KnowledgeBase))
            kbs = result.scalars().all()

        for kb in kbs:
            if not kb:
                continue

            print(f"\n知识库: {kb.name}")
            print(f"ID: {kb.id}")
            print(f"Collection: {kb.qdrant_collection}")

            try:
                # 获取Collection信息
                info = client.get_collection(kb.qdrant_collection)
                vectors_config = info.config.params.vectors_config
                sparse_config = info.config.params.sparse_vectors_config

                # 检查配置类型
                is_named = isinstance(vectors_config, dict)
                has_sparse = sparse_config is not None

                print(f"当前配置:")
                print(f"  - 命名向量: {is_named}")
                print(f"  - 稀疏向量: {has_sparse}")
                print(f"  - 向量配置类型: {type(vectors_config).__name__}")

                # 判断是否需要修复
                needs_fix = is_named and not has_sparse

                if needs_fix:
                    print(f"\n⚠️  检测到问题：使用命名向量但没有稀疏向量配置")
                    print(f"正在修复...")

                    # 删除旧Collection
                    client.delete_collection(kb.qdrant_collection)
                    print(f"✓ 已删除旧Collection")

                    # 重建（单一向量模式）
                    from qdrant_client.models import Distance, VectorParams
                    client.create_collection(
                        collection_name=kb.qdrant_collection,
                        vectors_config=VectorParams(
                            size=1024,
                            distance=Distance.COSINE
                        )
                    )
                    print(f"✓ 已重建Collection（单一向量模式）")

                    # 重置文档统计
                    kb.document_count = 0
                    kb.chunk_count = 0
                    kb.total_size = 0
                    await db.commit()
                    print(f"✓ 已重置文档统计")

                    print(f"\n✅ 修复完成！请重新上传文档")
                else:
                    print(f"\n✓ Collection配置正常，无需修复")

            except Exception as e:
                print(f"\n❌ 处理失败: {e}")


if __name__ == "__main__":
    import sys

    # 从命令行参数获取知识库ID
    kb_id = sys.argv[1] if len(sys.argv) > 1 else "c8e8e83f-3ec1-46c4-8504-c898d004fbb5"

    print("=" * 60)
    print("知识库Collection修复工具")
    print("=" * 60)

    asyncio.run(fix_collection(kb_id))
