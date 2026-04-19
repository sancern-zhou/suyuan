"""
记忆替换工具（replace_memory）

替换MEMORY.md中的现有条目
"""

from pathlib import Path
from typing import Dict, Any
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class ReplaceMemoryTool(LLMTool):
    """
    记忆替换工具

    替换MEMORY.md中的现有条目

    使用场景：
    - 用户纠正之前的错误信息
    - 更新过时的偏好设置
    - 修正不再准确的结论
    """

    # 类变量：用于存储当前的模式和用户信息（由记忆整合Agent设置）
    _current_mode = None
    _current_user_id = None

    def __init__(self):
        super().__init__(
            name="replace_memory",
            description="替换MEMORY.md中的现有条目",
            category=ToolCategory.TASK_MANAGEMENT,
            version="1.0.0",
            requires_context=False
        )

    @classmethod
    def set_memory_context(cls, mode: str, user_id: str = None):
        """设置当前的记忆上下文（由记忆整合Agent调用）"""
        cls._current_mode = mode
        cls._current_user_id = user_id

    @classmethod
    def clear_memory_context(cls):
        """清除记忆上下文"""
        cls._current_mode = None
        cls._current_user_id = None

    def _build_schema(self) -> Dict[str, Any]:
        """构建工具schema"""
        return {
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
                    "enum": ["用户偏好", "领域知识", "历史结论", "环境信息"],
                    "description": "事实类别（可选，用于精确匹配）"
                }
            },
            "required": ["old_text", "new_text"]
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
            memory_file = Path(memory_file_path)

            if not memory_file.exists():
                return {
                    "success": False,
                    "error": "记忆文件不存在",
                    "summary": "记忆替换失败：记忆文件不存在"
                }

            # 读取当前内容
            content = memory_file.read_text(encoding="utf-8")

            # 执行替换
            success = self._replace_fact(memory_file, content, old_text, new_text, category)

            if success:
                logger.info(
                    "memory_fact_replaced",
                    category=category,
                    old_text_length=len(old_text),
                    new_text_length=len(new_text),
                    memory_path=str(memory_file)
                )

                return {
                    "success": True,
                    "summary": f"已替换记忆：{old_text[:30]}... → {new_text[:30]}..."
                }
            else:
                return {
                    "success": False,
                    "error": f"未找到要替换的内容：{old_text[:50]}",
                    "summary": "记忆替换失败：未找到匹配内容"
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
            mode = self._current_mode or 'social'
            user_id = self._current_user_id

            # 社交模式：使用与 social/memory_store.py 一致的用户隔离路径
            if mode == 'social':
                base_path = Path("/home/xckj/suyuan/backend_data_registry/social/memory")
                if user_id and user_id != 'global':
                    safe_user_id = user_id.replace(":", "_")
                    memory_dir = base_path / safe_user_id
                else:
                    memory_dir = base_path / "social"
            else:
                base_path = Path("/home/xckj/suyuan/backend_data_registry/memory")
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

    def _replace_fact(
        self,
        memory_file: Path,
        content: str,
        old_text: str,
        new_text: str,
        category: str = None
    ) -> bool:
        """
        替换记忆条目

        Args:
            memory_file: 记忆文件路径
            content: 当前文件内容
            old_text: 要替换的旧内容
            new_text: 新的内容
            category: 事实类别（可选）

        Returns:
            是否成功替换
        """
        # 如果指定category，只在该章节内搜索
        if category:
            section_header = f"## {category}"

            if section_header not in content:
                return False

            section_start = content.index(section_header)
            section_end = content.find("\n##", section_start + 1)

            if section_end == -1:
                section_end = len(content)

            section_content = content[section_start:section_end]

            if old_text in section_content:
                new_section_content = section_content.replace(old_text, new_text)
                new_content = content[:section_start] + new_section_content + content[section_end:]

                # 原子写入
                memory_file.write_text(new_content, encoding="utf-8")
                return True

            return False
        else:
            # 全文搜索
            if old_text in content:
                new_content = content.replace(old_text, new_text)

                # 原子写入
                memory_file.write_text(new_content, encoding="utf-8")
                return True

            return False
