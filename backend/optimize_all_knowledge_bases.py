#!/usr/bin/env python3
"""
批量优化知识库Collection索引配置

自动检测并重建所有未优化的知识库：
1. 查询所有知识库的Collection配置
2. 找出 full_scan_threshold > 100 的（未优化）
3. 批量重建Collection（应用新配置）
4. 重置文档统计（需要重新上传）

使用方法：
    cd backend && python optimize_all_knowledge_bases.py [--dry-run] [--force]

参数：
    --dry-run: 仅检测，不实际重建
    --force: 跳过确认，直接执行
"""
import asyncio
import sys
import argparse
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.db.database import async_session
from sqlalchemy import select
from app.knowledge_base.models import KnowledgeBase
from app.knowledge_base import get_vector_store
import structlog

logger = structlog.get_logger()


async def check_collection_optimization(qdrant_client, collection_name: str) -> dict:
    """
    检查Collection是否已优化

    Returns:
        {
            "optimized": bool,
            "full_scan_threshold": int,
            "points_count": int,
            "indexed_vectors": int
        }
    """
    try:
        collection_info = qdrant_client.get_collection(collection_name)
        hnsw_config = collection_info.config.params.hnsw_config if hasattr(collection_info.config.params, 'hnsw_config') else None
        full_scan_threshold = hnsw_config.full_scan_threshold if hnsw_config else 10000
        points_count = collection_info.points_count
        indexed_vectors = collection_info.indexed_vectors_count

        # 判断是否已优化
        is_optimized = full_scan_threshold <= 100

        return {
            "optimized": is_optimized,
            "full_scan_threshold": full_scan_threshold,
            "points_count": points_count,
            "indexed_vectors": indexed_vectors,
            "exists": True
        }
    except Exception as e:
        logger.warning("check_collection_failed", collection=collection_name, error=str(e))
        return {"exists": False, "error": str(e)}


async def rebuild_collection(qb, kb, vector_store) -> bool:
    """
    重建单个知识库的Collection

    Returns:
        是否成功
    """
    try:
        collection_name = kb.qdrant_collection

        logger.info(
            "rebuilding_collection",
            kb_name=kb.name,
            kb_id=kb.id,
            collection=collection_name,
            doc_count=kb.document_count,
            chunk_count=kb.chunk_count
        )

        # 1. 删除旧Collection
        try:
            vector_store.qdrant_client.delete_collection(collection_name)
            logger.info("collection_deleted", collection=collection_name)
        except Exception as e:
            logger.warning("delete_collection_failed", collection=collection_name, error=str(e))

        # 2. 创建新Collection（应用新的索引配置）
        await vector_store.create_collection(collection_name, enable_hybrid=False)
        logger.info("collection_created", collection=collection_name)

        # 3. 验证新配置
        new_config = await check_collection_optimization(
            vector_store.qdrant_client,
            collection_name
        )
        if new_config.get("optimized"):
            logger.info(
                "collection_optimized",
                collection=collection_name,
                full_scan_threshold=new_config.get("full_scan_threshold")
            )
        else:
            logger.error(
                "collection_optimization_failed",
                collection=collection_name,
                full_scan_threshold=new_config.get("full_scan_threshold")
            )
            return False

        # 4. 重置统计信息
        kb.document_count = 0
        kb.chunk_count = 0
        kb.total_size = 0
        await qb.commit()

        logger.info(
            "collection_rebuild_success",
            kb_name=kb.name,
            collection=collection_name
        )
        return True

    except Exception as e:
        logger.error(
            "rebuild_collection_failed",
            kb_name=kb.name,
            kb_id=kb.id,
            error=str(e)
        )
        return False


async def main(dry_run: bool = False, force: bool = False):
    """主函数"""
    vector_store = get_vector_store()

    print("\n" + "=" * 80)
    print("知识库Collection索引优化工具")
    print("=" * 80)

    # 1. 获取所有知识库
    async with async_session() as db:
        result = await db.execute(select(KnowledgeBase))
        all_kbs = result.scalars().all()

        if not all_kbs:
            print("\n✓ 没有找到任何知识库")
            return

        print(f"\n找到 {len(all_kbs)} 个知识库")

        # 2. 检查每个知识库的优化状态
        print("\n正在检查Collection配置...")
        print("-" * 80)

        needs_optimization = []
        already_optimized = []

        for kb in all_kbs:
            collection_name = kb.qdrant_collection
            config = await check_collection_optimization(
                vector_store.qdrant_client,
                collection_name
            )

            if not config.get("exists"):
                print(f"⚠️  {kb.name} ({kb.id})")
                print(f"    Collection不存在或无法访问")
                continue

            status_icon = "✅" if config.get("optimized") else "⚠️ "
            threshold = config.get("full_scan_threshold", "未知")
            points = config.get("points_count", 0)

            print(f"{status_icon} {kb.name}")
            print(f"    ID: {kb.id}")
            print(f"    Collection: {collection_name}")
            print(f"    向量数: {points}")
            print(f"    索引阈值: {threshold}")
            print(f"    状态: {'已优化' if config.get('optimized') else '需要优化'}")
            print()

            if not config.get("optimized"):
                needs_optimization.append((kb, config))
            else:
                already_optimized.append(kb)

        # 3. 汇总
        print("=" * 80)
        print(f"检查完成：")
        print(f"  - 已优化: {len(already_optimized)} 个")
        print(f"  - 需要优化: {len(needs_optimization)} 个")
        print("=" * 80)

        if not needs_optimization:
            print("\n✅ 所有知识库都已优化，无需重建")
            return

        if dry_run:
            print("\n[DRY RUN MODE] 不会实际执行重建")
            print("\n需要优化的知识库：")
            for kb, config in needs_optimization:
                print(f"  - {kb.name} ({kb.document_count} 个文档)")
            return

        # 4. 确认
        if not force:
            print("\n以下知识库将被重建（文档需要重新上传）：")
            for kb, config in needs_optimization:
                print(f"  - {kb.name} ({kb.document_count} 个文档, {kb.chunk_count} 个分块)")

            print("\n⚠️  警告：重建将删除Collection中的所有向量数据")
            confirm = input("\n确认继续？(yes/no): ").strip().lower()
            if confirm not in ["yes", "y"]:
                print("已取消")
                return

        # 5. 执行重建
        print("\n开始重建...")
        print("-" * 80)

        success_count = 0
        failed_count = 0

        for kb, config in needs_optimization:
            success = await rebuild_collection(db, kb, vector_store)
            if success:
                success_count += 1
                print(f"✅ {kb.name} - 重建成功")
            else:
                failed_count += 1
                print(f"❌ {kb.name} - 重建失败")

        # 6. 最终报告
        print("\n" + "=" * 80)
        print("重建完成")
        print("=" * 80)
        print(f"成功: {success_count} 个")
        print(f"失败: {failed_count} 个")
        print("=" * 80)

        if success_count > 0:
            print("\n✅ 优化完成！请重新上传相关知识库的文档")
            print("\n提示：")
            print("  - 文档上传后会自动使用新的索引配置")
            print("  - 检索速度将显著提升（12秒 → <0.1秒）")
            print("  - 可以通过知识库管理页面重新上传文档")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="批量优化知识库Collection索引配置",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 检查所有知识库（不执行重建）
  python optimize_all_knowledge_bases.py --dry-run

  # 交互式重建（需要确认）
  python optimize_all_knowledge_bases.py

  # 强制重建（跳过确认）
  python optimize_all_knowledge_bases.py --force
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅检测，不实际重建"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="跳过确认，直接执行"
    )

    args = parser.parse_args()

    try:
        asyncio.run(main(dry_run=args.dry_run, force=args.force))
    except KeyboardInterrupt:
        print("\n\n已中断")
    except Exception as e:
        logger.error("script_failed", error=str(e))
        print(f"\n❌ 执行失败: {e}")
        sys.exit(1)
