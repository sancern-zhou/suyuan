#!/usr/bin/env python3
"""
迁移脚本：为所有现有社交模式用户创建 USER.md 文件

执行时机：后端服务启动时自动执行（在 agent_bridge.py 中）
"""
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)


def migrate_user_md_files():
    """
    为所有现有用户创建 USER.md（如果不存在）

    USER.md 模板参考 OpenClaw 设计：
    - 由 Agent 通过对话主动维护
    - 包含用户基本信息、上下文、偏好等
    - Agent 使用 edit_file/read_file 工具管理
    """
    memory_dir = Path("backend_data_registry/social/memory")

    if not memory_dir.exists():
        logger.info("memory_dir_not_found", path=str(memory_dir))
        return

    # USER.md 模板（OpenClaw 风格）
    user_md_template = """# USER.md - About Your Human

*Learn about the person you're helping. Update this as you go.*

- **Name:**
- **What to call them:** You
- **Pronouns:** *(optional)*
- **Timezone:** UTC+8
- **Notes:**

## Context

*(What do they care about? What projects are they working on? What annoys them? What makes them laugh? Build this over time.)*

---

The more you know, the better you can help. But remember — you're learning about a person, not building a dossier. Respect the difference.
"""

    created_count = 0
    skipped_count = 0
    error_count = 0

    for user_dir in memory_dir.iterdir():
        if not user_dir.is_dir():
            continue

        user_file = user_dir / "USER.md"

        if user_file.exists():
            skipped_count += 1
            continue

        try:
            user_file.write_text(user_md_template, encoding="utf-8")
            created_count += 1
            logger.info("user_md_created", user_id=user_dir.name)
        except Exception as e:
            error_count += 1
            logger.error("user_md_creation_failed",
                        user_id=user_dir.name,
                        error=str(e))

    logger.info(
        "user_md_migration_completed",
        created=created_count,
        skipped=skipped_count,
        errors=error_count
    )

    return created_count > 0  # 返回是否创建了新文件


if __name__ == "__main__":
    """直接执行此脚本进行迁移"""
    result = migrate_user_md_files()
    if result:
        print("✅ 迁移完成：已为现有用户创建 USER.md 文件")
    else:
        print("ℹ️  无需迁移：所有用户已存在 USER.md 文件")
