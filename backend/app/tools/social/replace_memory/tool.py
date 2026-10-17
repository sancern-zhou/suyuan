"""
记忆替换工具（replace_memory）

后台记忆整合器专用：更新事实层（facts/*.md）中的既有事实。
常驻长期记忆（MEMORY.md）由会话 Agent 通过 edit_file 直接维护。
"""

from pathlib import Path
from typing import Dict, Any
from contextvars import ContextVar
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.memory.curated_facts import CuratedFactStore

logger = structlog.get_logger(__name__)
_memory_context: ContextVar[tuple[str | None, str | None]] = ContextVar(
    "replace_memory_context", default=(None, None)
)


class ReplaceMemoryTool(LLMTool):
    """
    记忆替换工具（后台整合器专用，写事实层 facts/*.md）

    使用场景：
    - 事实层中的信息已过时或被修正
    - 事实描述需要更新但不改变其身份
    """

    # 类变量：用于存储当前的模式和用户信息（由记忆整合Agent设置）
    _current_mode = None
    _current_user_id = None

    def __init__(self):
        super().__init__(
            name="replace_memory",
            description="更新事实层记忆（facts/*.md）中的既有事实（后台整合专用）",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema=self._build_schema(),  # ✅ 传递 schema
            version="1.0.0",
            requires_context=False
        )

    @classmethod
    def set_memory_context(cls, mode: str, user_id: str = None):
        """设置当前的记忆上下文（由记忆整合Agent调用）"""
        cls._current_mode = mode
        cls._current_user_id = user_id
        _memory_context.set((mode, user_id))

    @classmethod
    def clear_memory_context(cls):
        """清除记忆上下文"""
        cls._current_mode = None
        cls._current_user_id = None
        _memory_context.set((None, None))

    def _build_schema(self) -> Dict[str, Any]:
        """构建工具schema"""
        return {
            "name": "replace_memory",
            "description": "更新事实层记忆（facts/*.md）中的既有事实（后台整合专用）",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_text": {
                        "type": "string",
                        "description": "要替换的旧内容（子串匹配）"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "新的内容"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["用户偏好", "领域知识", "模式方法论", "环境信息"],
                        "description": "事实类别（可选，用于精确匹配）"
                    }
                },
                "required": ["old_text", "new_text"]
            }
        }

    async def execute(self, old_text: str, new_text: str, category: str = None, **kwargs) -> Dict[str, Any]:
        """
        执行记忆替换

        Args:
            old_text: 要替换的旧内容
            new_text: 新的内容
            category: 事实类别（可选）

        Returns:
            执行结果
        """
        # 获取当前用户的记忆文件路径
        memory_file_path = self._get_memory_file_path()

        if not memory_file_path:
            return {
                "success": False,
                "error": "无法获取记忆文件路径",
                "summary": "记忆替换失败：无法找到记忆文件"
            }

        try:
            current_mode, current_user_id = _memory_context.get()
            current_mode = current_mode or self._current_mode
            current_user_id = current_user_id or self._current_user_id
            if not current_mode or current_mode == "memory_consolidator":
                # memory_consolidator 目录不承载业务记忆；解析到该模式说明
                # 整合目标模式上下文缺失，拒绝写入以免事实进入不可见目录。
                logger.warning(
                    "memory_write_rejected_for_consolidator_mode",
                    tool="replace_memory",
                )
                return {
                    "success": False,
                    "error": "记忆写入目标模式缺失（memory_consolidator 不承载业务记忆），已拒绝替换",
                    "summary": "记忆替换失败：整合目标模式未知",
                }
            # 事实层唯一写入路径：后台整合器按来源模式更新 facts/*.md
            store = CuratedFactStore(Path(self._get_memory_file_path()).parent)
            result = store.replace(old_text, new_text, category)
            return {
                "success": result == "replaced",
                "status": result,
                "summary": f"共享事实更新结果：{result}",
            }

        except Exception as e:
            logger.error(
                "failed_to_replace_memory",
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": str(e),
                "summary": "记忆替换失败"
            }

    def _get_memory_file_path(self) -> str:
        """
        获取当前用户的记忆文件路径

        路径规则（与 social/memory_store.py 对齐）：
        - 社交模式用户隔离：backend_data_registry/social/memory/{safe_user_id}/MEMORY.md
        - 非社交模式：backend_data_registry/memory/{mode}/MEMORY.md
        """
        try:
            # 使用类变量中存储的上下文
            current_mode, current_user_id = _memory_context.get()
            mode = current_mode or self._current_mode or 'social'
            user_id = current_user_id or self._current_user_id

            # 社交模式：使用与 social/memory_store.py 一致的用户隔离路径
            if mode == 'social':
                from app.utils.path_config import get_social_memory_dir
                base_path = get_social_memory_dir()
                if user_id and user_id != 'global':
                    safe_user_id = user_id.replace(":", "_")
                    memory_dir = base_path / safe_user_id
                else:
                    memory_dir = base_path / "social"
            else:
                from app.utils.path_config import get_memory_dir
                base_path = get_memory_dir()
                memory_dir = base_path / mode

            memory_dir.mkdir(parents=True, exist_ok=True)

            memory_file = memory_dir / "MEMORY.md"

            logger.debug(
                "memory_file_path_resolved",
                mode=mode,
                user_id=user_id,
                path=str(memory_file)
            )

            return str(memory_file)

        except Exception as e:
            logger.error(
                "failed_to_get_memory_file_path",
                error=str(e)
            )
            return None
