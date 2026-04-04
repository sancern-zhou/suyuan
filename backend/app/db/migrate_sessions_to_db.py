"""
会话迁移工具

将文件存储的会话迁移到数据库
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
import structlog

from app.db.session_repository import get_session_repository
from app.db.models_session import SessionState as DBSessionState
from app.agent.session.models import SessionState

logger = structlog.get_logger()


async def migrate_sessions_to_db(
    storage_path: str = "backend_data_registry/sessions",
    pattern: str = "*.json"
):
    """
    迁移文件会话到数据库

    Args:
        storage_path: 会话文件存储路径
        pattern: 文件匹配模式
    """
    repository = get_session_repository()
    storage_dir = Path(storage_path)

    if not storage_dir.exists():
        logger.warning("storage_path_not_found", path=storage_path)
        return

    # 查找所有会话文件
    session_files = list(storage_dir.glob(pattern))
    total_files = len(session_files)

    if total_files == 0:
        logger.info("no_session_files_found", path=storage_path)
        return

    logger.info("starting_migration", total_files=total_files)

    success_count = 0
    error_count = 0
    skip_count = 0

    for idx, session_file in enumerate(session_files, 1):
        try:
            logger.info(
                "migrating_session",
                index=idx,
                total=total_files,
                file=session_file.name
            )

            # 读取会话文件
            session_data = json.loads(session_file.read_text(encoding='utf-8'))
            session_id = session_data.get("session_id")

            if not session_id:
                logger.warning("session_missing_id", file=session_file.name)
                error_count += 1
                continue

            # 检查会话是否已存在
            existing = await repository.get_session(session_id)
            if existing:
                logger.info("session_already_exists", session_id=session_id, action="skip")
                skip_count += 1
                continue

            # 创建会话
            state_str = session_data.get("state", "active")
            try:
                state = DBSessionState(state_str)
            except ValueError:
                state = DBSessionState.ACTIVE

            await repository.create_session(
                session_id=session_id,
                query=session_data.get("query", ""),
                state=state,
                mode=session_data.get("metadata", {}).get("mode"),
                metadata=session_data.get("metadata", {})
            )

            # 更新会话的其他字段
            update_data = {}

            if session_data.get("created_at"):
                try:
                    update_data["created_at"] = datetime.fromisoformat(session_data["created_at"])
                except:
                    pass

            if session_data.get("updated_at"):
                try:
                    update_data["updated_at"] = datetime.fromisoformat(session_data["updated_at"])
                except:
                    pass

            if session_data.get("completed_at"):
                try:
                    update_data["completed_at"] = datetime.fromisoformat(session_data["completed_at"])
                except:
                    pass

            if session_data.get("current_step"):
                update_data["current_step"] = session_data["current_step"]

            if session_data.get("current_expert"):
                update_data["current_expert"] = session_data["current_expert"]

            if session_data.get("data_ids"):
                update_data["data_ids"] = session_data["data_ids"]

            if session_data.get("visual_ids"):
                update_data["visual_ids"] = session_data["visual_ids"]

            if session_data.get("error"):
                update_data["error"] = session_data["error"]

            if update_data:
                await repository.update_session(session_id, **update_data)

            # 迁移对话历史
            conversation_history = session_data.get("conversation_history", [])
            if conversation_history:
                await repository.save_conversation_history(
                    session_id,
                    conversation_history
                )

            logger.info(
                "session_migrated",
                session_id=session_id,
                message_count=len(conversation_history)
            )
            success_count += 1

        except Exception as e:
            logger.error(
                "migration_failed",
                file=session_file.name,
                error=str(e)
            )
            error_count += 1

    # 输出迁移结果
    logger.info(
        "migration_completed",
        total=total_files,
        success=success_count,
        skipped=skip_count,
        errors=error_count
    )

    return {
        "total": total_files,
        "success": success_count,
        "skipped": skip_count,
        "errors": error_count
    }


async def main():
    """主函数"""
    print("=" * 60)
    print("会话迁移工具")
    print("将文件存储的会话迁移到 PostgreSQL 数据库")
    print("=" * 60)
    print()

    result = await migrate_sessions_to_db()

    print()
    print("=" * 60)
    print("迁移结果：")
    print(f"  总计：{result['total']} 个文件")
    print(f"  成功：{result['success']} 个")
    print(f"  跳过：{result['skipped']} 个")
    print(f"  失败：{result['errors']} 个")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
