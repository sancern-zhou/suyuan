"""
记忆添加工具（remember_fact）

让LLM主动添加重要信息到长期记忆（MEMORY.md）
"""

from pathlib import Path
from typing import Dict, Any
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class RememberFactTool(LLMTool):
    """
    记忆添加工具

    让LLM主动添加重要信息到长期记忆（MEMORY.md）

    使用场景：
    - 用户明确说"记住这个"或"记住"
    - 用户分享个人偏好（如"我喜欢简洁的回答"）
    - 用户纠正错误（如"不对，我想要详细版本"）
    - 发现环境信息（如"用户在使用手机"、"用户在广州"）
    - 学习到API特性或约定
    - 识别稳定的、将来会有用的事实
    """

    # 类变量：用于存储当前的模式和用户信息（由记忆整合Agent设置）
    _current_mode = None
    _current_user_id = None

    def __init__(self):
        super().__init__(
            name="remember_fact",
            description="记住重要事实到长期记忆（MEMORY.md）",
            category=ToolCategory.TASK_MANAGEMENT,
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
                "fact": {
                    "type": "string",
                    "description": "要记住的事实（简洁明确，一句话）"
                },
                "category": {
                    "type": "string",
                    "enum": ["用户偏好", "领域知识", "历史结论", "环境信息"],
                    "description": "事实类别"
                },
                "priority": {
                    "type": "integer",
                    "description": "优先级（1-5，5最高）",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 5
                }
            },
            "required": ["fact", "category"]
        }

    async def execute(self, fact: str, category: str, priority: int = 3, **kwargs) -> Dict[str, Any]:
        """
        执行记忆添加

        Args:
            fact: 要记住的事实
            category: 事实类别
            priority: 优先级（1-5）

        Returns:
            执行结果
        """
        # 获取当前用户的记忆文件路径
        memory_file_path = self._get_memory_file_path()

        if not memory_file_path:
            return {
                "success": False,
                "error": "无法获取记忆文件路径",
                "summary": "记忆添加失败：无法找到记忆文件"
            }

        try:
            # 获取当前MEMORY.md大小
            memory_file = Path(memory_file_path)
            if memory_file.exists():
                current_size = len(memory_file.read_text(encoding="utf-8"))
                max_size = 3000

                if current_size >= max_size:
                    return {
                        "success": False,
                        "error": f"MEMORY.md已满（{current_size}/{max_size}字符），请先使用remove_memory清理旧内容",
                        "summary": "记忆添加失败：记忆文件已满"
                    }

            # 添加记忆
            self._append_fact(memory_file, category, fact)

            logger.info(
                "memory_fact_added",
                category=category,
                priority=priority,
                fact_length=len(fact),
                memory_path=str(memory_file)
            )

            return {
                "success": True,
                "summary": f"已记住：{fact[:50]}{'...' if len(fact) > 50 else ''}"
            }

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

    def _get_memory_file_path(self) -> str:
        """
        获取当前用户的记忆文件路径

        路径规则：
        - 社交模式用户隔离：backend_data_registry/social/memory/{safe_user_id}/MEMORY.md
        - 非社交模式：backend_data_registry/memory/{mode}/MEMORY.md

        优先级：
        1. 使用类变量中存储的上下文（由记忆整合Agent设置）
        2. 降级到默认模式（social）
        """
        try:
            # 1. 优先使用类变量中存储的上下文
            mode = self._current_mode or 'social'
            user_id = self._current_user_id

            # 2. 社交模式：使用与 social/memory_store.py 一致的用户隔离路径
            if mode == 'social':
                base_path = Path("/home/xckj/suyuan/backend_data_registry/social/memory")
                if user_id and user_id != 'global':
                    # 与 social/memory_store.py 的路径对齐：user_id中的:替换为_
                    safe_user_id = user_id.replace(":", "_")
                    memory_dir = base_path / safe_user_id
                else:
                    # 无user_id时降级到 social 子目录
                    memory_dir = base_path / "social"
            else:
                # 非社交模式：使用通用记忆路径
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

    def _append_fact(self, memory_file: Path, category: str, fact: str) -> None:
        """
        快速追加事实到对应章节

        Args:
            memory_file: 记忆文件路径
            category: 事实类别
            fact: 事实内容
        """
        # 确保文件存在
        if not memory_file.exists():
            initial_content = """# 长期记忆 (MEMORY.md)

此文件存储用户的偏好、领域知识和重要结论。

## 用户偏好

## 领域知识

## 历史结论

## 环境信息
"""
            memory_file.write_text(initial_content, encoding="utf-8")

        content = memory_file.read_text(encoding="utf-8")

        # 查找章节位置
        section_header = f"## {category}"

        if section_header in content:
            # 在章节末尾追加
            section_start = content.index(section_header)
            section_end = content.find("\n##", section_start + 1)

            if section_end == -1:
                section_end = len(content)

            before = content[:section_end]
            after = content[section_end:]

            # 检查章节内是否已有内容
            section_content = content[section_start:section_end]
            if section_content.strip().endswith(section_header):
                # 章节为空，直接添加
                new_content = f"{before}\n- {fact}{after}"
            else:
                # 章节已有内容，追加
                new_content = f"{before}\n- {fact}{after}"
        else:
            # 章节不存在，创建新章节
            new_content = f"{content}\n## {category}\n\n- {fact}\n"

        # 原子写入
        memory_file.write_text(new_content, encoding="utf-8")
