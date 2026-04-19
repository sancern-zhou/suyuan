"""
记忆恢复工具

从备份恢复被清空的记忆文件
"""

from typing import Optional, Dict, Any
import structlog

from app.agent.memory.memory_store import ImprovedMemoryStore
from app.schemas.common import ToolResult

logger = structlog.get_logger(__name__)


class Tool:
    """记忆恢复工具"""

    name = "restore_memory"
    description = """
    从备份恢复被清空的记忆文件（MEMORY.md）。

    当记忆文件被意外清空时，使用此工具从自动备份恢复记忆内容。

    使用场景：
    - 记忆文件被清空或只有初始模板
    - 需要恢复之前的记忆内容

    注意事项：
    - 此工具会覆盖当前的 MEMORY.md 文件
    - 恢复前会检查备份文件是否存在和有效
    - 建议先查看备份信息再决定是否恢复
    """

    parameters = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "description": "模式标识（social/assistant/expert/query/code/report/chart）",
                "enum": ["social", "assistant", "expert", "query", "code", "report", "chart"],
                "default": "query"
            },
            "action": {
                "type": "string",
                "description": "操作类型：info（查看备份信息）或 restore（执行恢复）",
                "enum": ["info", "restore"],
                "default": "info"
            }
        },
        "required": []
    }

    requires_context = False
    requires_task_list = False

    async def execute(self, mode: str = "query", action: str = "info") -> ToolResult:
        """
        执行记忆恢复操作

        Args:
            mode: 模式标识
            action: 操作类型（info/restore）

        Returns:
            操作结果
        """
        try:
            # 创建记忆存储实例
            memory_store = ImprovedMemoryStore(user_id="global", mode=mode)

            if action == "info":
                # 查看备份信息
                backup_info = memory_store.get_backup_info()

                if not backup_info["exists"]:
                    return ToolResult.success(
                        data={
                            "has_backup": False,
                            "message": f"模式 [{mode}] 没有找到备份文件。"
                        },
                        summary=f"模式 [{mode}] 没有备份文件"
                    )

                # 读取当前记忆内容
                current_content = memory_store.read_long_term()
                current_size = len(current_content) if current_content else 0

                return ToolResult.success(
                    data={
                        "has_backup": True,
                        "backup_size": backup_info["size"],
                        "backup_preview": backup_info["preview"],
                        "current_size": current_size,
                        "current_preview": current_content[:200] + "..." if current_content and len(current_content) > 200 else current_content,
                        "backup_path": backup_info["path"],
                        "recommendation": "建议执行恢复" if current_size < 100 else "当前记忆内容正常，无需恢复"
                    },
                    summary=f"模式 [{mode}] 备份信息：备份大小 {backup_info['size']} 字符，当前记忆 {current_size} 字符"
                )

            elif action == "restore":
                # 执行恢复
                success = memory_store.restore_from_backup()

                if not success:
                    return ToolResult.failed(
                        error=f"模式 [{mode}] 恢复失败：备份文件不存在或无效"
                    )

                # 恢复后读取内容确认
                restored_content = memory_store.read_long_term()
                restored_size = len(restored_content) if restored_content else 0

                return ToolResult.success(
                    data={
                        "restored": True,
                        "restored_size": restored_size,
                        "preview": restored_content[:300] + "..." if restored_content and len(restored_content) > 300 else restored_content
                    },
                    summary=f"模式 [{mode}] 记忆已恢复：{restored_size} 字符"
                )

            else:
                return ToolResult.failed(
                    error=f"不支持的操作类型：{action}，请使用 info 或 restore"
                )

        except Exception as e:
            logger.error(
                "restore_memory_tool_error",
                mode=mode,
                action=action,
                error=str(e),
                exc_info=True
            )
            return ToolResult.failed(
                error=f"记忆恢复失败：{str(e)}"
            )
