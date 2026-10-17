"""
记忆添加工具（remember_fact）

后台记忆整合器专用：把蒸馏出的稳定事实写入事实层（facts/*.md，带来源、
适用条件与可选失效日期，过期自动遗忘）。常驻长期记忆（MEMORY.md）由
会话 Agent 通过 edit_file 直接维护，不经过本工具。
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
    "remember_fact_memory_context", default=(None, None)
)


class RememberFactTool(LLMTool):
    """
    记忆添加工具（后台整合器专用，写事实层 facts/*.md）

    使用场景：
    - 整合器从 dreaming 候选中筛出稳定、可长期复用的信息
    - 时间敏感信息必须携带 valid_until
    """

    def __init__(self):
        super().__init__(
            name="remember_fact",
            description="写入事实层记忆（facts/*.md，后台整合专用；带来源与适用条件，可选失效日期）",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema=self._build_schema(),  # ✅ 传递 schema
            version="1.0.0",
            requires_context=False
        )

    @classmethod
    def set_memory_context(cls, mode: str, user_id: str = None):
        """
        设置当前的记忆上下文（由记忆整合Agent调用）

        Args:
            mode: 模式标识（如 'social', 'assistant', 'expert'）
            user_id: 用户标识（用于社交模式的用户隔离）
        """
        _memory_context.set((mode, user_id))

    @classmethod
    def clear_memory_context(cls):
        """清除记忆上下文"""
        _memory_context.set((None, None))

    def _build_schema(self) -> Dict[str, Any]:
        """构建工具schema"""
        return {
            "name": "remember_fact",
            "description": "写入事实层记忆（facts/*.md，后台整合专用；带来源与适用条件，可选失效日期）",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "要记住的事实（简洁明确，一句话）"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["用户偏好", "领域知识", "模式方法论", "环境信息"],
                        "description": "事实类别"
                    },
                    "source_ref": {"type": "string", "description": "来源消息或会话引用，必须可核验。"},
                    "applies_when": {"type": "string", "description": "该事实适用的模式、任务或条件。"},
                    "valid_until": {"type": "string", "description": "可选失效日期，格式 YYYY-MM-DD；时间敏感信息必填。"}
                },
                "required": ["fact", "category", "source_ref", "applies_when"]
            }
        }

    async def execute(
        self, fact: str, category: str,
        source_ref: str = "", applies_when: str = "", valid_until: str = "", **kwargs
    ) -> Dict[str, Any]:
        """
        执行记忆添加

        Args:
            fact: 要记住的事实
            category: 事实类别
            source_ref: 来源消息或会话引用
            applies_when: 适用的模式、任务或条件
            valid_until: 可选失效日期（YYYY-MM-DD）

        Returns:
            执行结果
        """
        try:
            current_mode, current_user_id = _memory_context.get()
            if not current_mode or current_mode == "memory_consolidator":
                # memory_consolidator 目录不承载业务记忆；解析到该模式说明
                # 整合目标模式上下文缺失，拒绝写入以免事实进入不可见目录。
                logger.warning(
                    "memory_write_rejected_for_consolidator_mode",
                    tool="remember_fact",
                )
                return {
                    "success": False,
                    "error": "记忆写入目标模式缺失（memory_consolidator 不承载业务记忆），已拒绝写入",
                    "summary": "记忆添加失败：整合目标模式未知",
                }
            if current_mode == "social" and (not current_user_id or current_user_id == "global"):
                # 社交记忆按用户隔离；缺用户身份时拒绝写入，
                # 绝不降级到共享目录（其内容不属于任何用户，永远不会被注入）。
                logger.warning(
                    "memory_write_rejected_for_missing_social_user",
                    tool="remember_fact",
                )
                return {
                    "success": False,
                    "error": "社交记忆写入缺少用户身份（用户隔离目录），已拒绝写入",
                    "summary": "记忆添加失败：社交用户身份未知",
                }
            # 事实层唯一写入路径：后台整合器按来源模式写入 facts/*.md
            memory_file_path = self._get_memory_file_path()
            if not memory_file_path:
                return {
                    "success": False,
                    "error": "无法获取记忆文件路径",
                    "summary": "记忆添加失败：无法找到记忆文件"
                }
            store = CuratedFactStore(Path(memory_file_path).parent)
            result = store.add(
                fact=fact, category=category, source_ref=source_ref,
                applies_when=applies_when, valid_until=valid_until,
            )
            return {"success": True, "summary": f"记忆事实{result['status']}: {fact[:50]}", **result}

        except Exception as e:
            logger.error(
                "failed_to_remember_fact",
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": str(e),
                "summary": "记忆添加失败"
            }

    def _get_memory_file_path(self) -> str | None:
        """Resolve the task-local target through the shared storage policy."""
        mode, user_id = _memory_context.get()
        try:
            return str(memory_workspace(mode, user_id) / "MEMORY.md")
        except (ValueError, OSError) as exc:
            logger.warning("invalid_memory_target", error=str(exc))
            return None
