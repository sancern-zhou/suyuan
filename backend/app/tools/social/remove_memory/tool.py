"""
记忆删除工具（remove_memory）

从MEMORY.md中删除过时或错误的条目
"""

from pathlib import Path
from typing import Dict, Any
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class RemoveMemoryTool(LLMTool):
    """
    记忆删除工具

    从MEMORY.md中删除过时或错误的条目

    使用场景：
    - 删除临时环境信息（如"用户今天在公司"）
    - 删除过时结论
    - 删除错误记忆
    """

    # 类变量：用于存储当前的模式和用户信息（由记忆整合Agent设置）
    _current_mode = None
    _current_user_id = None

    def __init__(self):
        super().__init__(
            name="remove_memory",
            description="从MEMORY.md中删除条目",
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
                "text": {
                    "type": "string",
                    "description": "要删除的内容（子串匹配）"
                },
                "category": {
                    "type": "string",
                    "enum": ["用户偏好", "领域知识", "历史结论", "环境信息"],
                    "description": "事实类别（可选，用于精确匹配）"
                }
            },
            "required": ["text"]
        }

    async def execute(self, text: str, category: str = None, **kwargs) -> Dict[str, Any]:
        """
        执行记忆删除

        Args:
            text: 要删除的内容
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
                "summary": "记忆删除失败：无法找到记忆文件"
            }

        try:
            memory_file = Path(memory_file_path)

            if not memory_file.exists():
                return {
                    "success": False,
                    "error": "记忆文件不存在",
                    "summary": "记忆删除失败：记忆文件不存在"
                }

            # 读取当前内容
            content = memory_file.read_text(encoding="utf-8")

            # 执行删除
            success = self._remove_fact(memory_file, content, text, category)

            if success:
                logger.info(
                    "memory_fact_removed",
                    category=category,
                    text_length=len(text),
                    memory_path=str(memory_file)
                )

                return {
                    "success": True,
                    "summary": f"已删除记忆：{text[:50]}{'...' if len(text) > 50 else ''}"
                }
            else:
                return {
                    "success": False,
                    "error": f"未找到要删除的内容：{text[:50]}",
                    "summary": "记忆删除失败：未找到匹配内容"
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

    def _remove_fact(
        self,
        memory_file: Path,
        content: str,
        text: str,
        category: str = None
    ) -> bool:
        """
        删除记忆条目

        Args:
            memory_file: 记忆文件路径
            content: 当前文件内容
            text: 要删除的内容
            category: 事实类别（可选）

        Returns:
            是否成功删除
        """
        lines = content.split('\n')

        if category:
            # 只在指定章节内删除
            section_header = f"## {category}"
            in_section = False
            filtered_lines = []

            for line in lines:
                if line.startswith(section_header):
                    in_section = True
                    filtered_lines.append(line)
                elif line.startswith("## ") and in_section:
                    in_section = False
                    filtered_lines.append(line)
                elif in_section and text in line:
                    # 跳过包含text的行
                    logger.debug(
                        "removing_memory_line",
                        line=line[:50]
                    )
                    continue
                else:
                    filtered_lines.append(line)
        else:
            # 全文删除
            filtered_lines = [line for line in lines if text not in line]

        # 检查是否有变化
        if len(filtered_lines) == len(lines):
            return False

        # 重新构建内容
        new_content = '\n'.join(filtered_lines)

        # 原子写入
        memory_file.write_text(new_content, encoding="utf-8")
        return True
