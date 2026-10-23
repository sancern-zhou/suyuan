"""
记忆删除工具（remove_memory）

后台记忆整合器专用：从事实层（facts/*.md）删除过时或错误的事实。
常驻长期记忆（MEMORY.md）由会话 Agent 通过 edit_file 直接维护。
"""

from pathlib import Path
from typing import Dict, Any
from contextvars import ContextVar
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.memory.curated_facts import CuratedFactStore
from app.agent.memory.memory_paths import memory_workspace

logger = structlog.get_logger(__name__)
_memory_context: ContextVar[tuple[str | None, str | None]] = ContextVar(
    "remove_memory_context", default=(None, None)
)


class RemoveMemoryTool(LLMTool):
    """
    记忆删除工具（后台整合器专用，写事实层 facts/*.md）

    使用场景：
    - 删除已失效或被证伪的事实
    - 清理重复条目
    """

    def __init__(self):
        super().__init__(
            name="remove_memory",
            description="从事实层记忆（facts/*.md）删除事实（后台整合专用）",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema=self._build_schema(),  # ✅ 传递 schema
            version="1.0.0",
            requires_context=False
        )

    @classmethod
    def set_memory_context(cls, mode: str, user_id: str = None):
        """设置当前的记忆上下文（由记忆整合Agent调用）"""
        _memory_context.set((mode, user_id))

    @classmethod
    def clear_memory_context(cls):
        """清除记忆上下文"""
        _memory_context.set((None, None))

    def _build_schema(self) -> Dict[str, Any]:
        """构建工具schema"""
        return {
            "name": "remove_memory",
            "description": "从事实层记忆（facts/*.md）删除事实（后台整合专用）",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_text": {
                        "type": "string",
                        "description": "要删除的内容（子串匹配）"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["用户偏好", "领域知识", "模式方法论", "环境信息"],
                        "description": "事实类别（可选，用于精确匹配）"
                    }
                },
                "required": ["old_text"]
            }
        }

    async def execute(self, old_text: str, category: str = None, **kwargs) -> Dict[str, Any]:
        """
        执行记忆删除

        Args:
            old_text: 要删除的内容（参数名改为 old_text，与 replace_memory 保持一致）
            category: 事实类别（可选）

        Returns:
            执行结果
        """
        try:
            current_mode, current_user_id = _memory_context.get()
            if not current_mode or current_mode == "memory_consolidator":
                # memory_consolidator 目录不承载业务记忆；解析到该模式说明
                # 整合目标模式上下文缺失，拒绝删除以免误操作不可见目录。
                logger.warning(
                    "memory_write_rejected_for_consolidator_mode",
                    tool="remove_memory",
                )
                return {
                    "success": False,
                    "error": "记忆写入目标模式缺失（memory_consolidator 不承载业务记忆），已拒绝删除",
                    "summary": "记忆删除失败：整合目标模式未知",
                }
            if current_mode == "assistant" and (not current_user_id or current_user_id == "global"):
                # 社交记忆按用户隔离；缺用户身份时拒绝写入，
                # 绝不降级到共享目录（其内容不属于任何用户，永远不会被注入）。
                logger.warning(
                    "memory_write_rejected_for_missing_social_user",
                    tool="remove_memory",
                )
                return {
                    "success": False,
                    "error": "社交记忆写入缺少用户身份（用户隔离目录），已拒绝删除",
                    "summary": "记忆删除失败：社交用户身份未知",
                }
            # 事实层唯一写入路径：后台整合器按来源模式删除 facts/*.md 中的事实
            memory_file_path = self._get_memory_file_path()
            if not memory_file_path:
                return {
                    "success": False,
                    "error": "无法获取记忆文件路径",
                    "summary": "记忆删除失败：无法找到记忆文件"
                }
            store = CuratedFactStore(Path(memory_file_path).parent)
            result = store.remove(old_text, category)
            return {
                "success": result == "removed",
                "status": result,
                "summary": f"共享事实删除结果：{result}",
            }

        except Exception as e:
            logger.error(
                "failed_to_remove_memory",
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": str(e),
                "summary": "记忆删除失败"
            }

    def _get_memory_file_path(self) -> str | None:
        """Resolve the task-local target through the shared storage policy."""
        mode, user_id = _memory_context.get()
        try:
            return str(memory_workspace(mode, user_id) / "MEMORY.md")
        except (ValueError, OSError) as exc:
            logger.warning("invalid_memory_target", error=str(exc))
            return None
