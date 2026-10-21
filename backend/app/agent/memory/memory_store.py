"""
通用分层记忆系统

从 app/social/memory_store.py 迁移，支持多种模式（社交、助手、专家、问数、编程、报告、图表、运维）

核心功能：
- MEMORY.md：常驻长期记忆（会话 Agent 经 edit_file 维护，每次会话全文注入）
- memory/YYYY-MM-DD.md：日志型/观察型长期记忆库（社交链路）
- memory/.dreams/：待晋升候选目录（社交链路）
- 事实层 facts/*.md 见 curated_facts.CuratedFactStore（后台整合器维护）
- 提供记忆上下文给 LLM

改进版（参考 nanobot）：
- 快照隔离机制（会话内注入快照，后台更新不影响当前对话）
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class MemoryStore:
    """
    通用分层记忆系统（支持所有模式）

    MEMORY.md：
    - 长期事实（用户偏好、模式方法论、重要数据）
    - 持久化存储
    - 自动整合到上下文

    memory/YYYY-MM-DD.md：
    - 可搜索日志型 daily notes
    - 用于回溯、检索和长期记忆晋升
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        mode: str = "expert",  # ✅ 新增：模式标识（social/assistant/expert/query/code/report/chart/ops）
        workspace: Optional[Path] = None,
        max_history_size: int = 50000  # daily note 单文件最大字符数（保留参数名兼容旧调用）
    ):
        """
        初始化记忆存储

        Args:
            user_id: 用户ID（格式：{mode}:{user_identifier}:{shared|unique}）
            mode: 模式标识（social/assistant/expert/query/code/report/chart/ops）
            workspace: 工作空间目录，默认 backend_data_registry/memory
            max_history_size: daily note 单文件最大字符数
        """
        self.user_id = user_id or "global"  # 默认全局记忆（向后兼容）
        self.mode = mode
        self.max_history_size = max_history_size

        # ✅ 模式专属工作空间
        self.workspace = self._init_workspace(workspace, user_id, mode)
        self.memory_file = self.workspace / "MEMORY.md"
        self.daily_memory_dir = self.workspace / "memory"
        self.dreams_dir = self.daily_memory_dir / ".dreams"

        # 初始化文件
        self._init_files()

        logger.debug(
            "memory_store_initialized",
            user_id=self.user_id,
            mode=self.mode,
            workspace=str(self.workspace)
        )

    def _init_workspace(self, workspace: Path, user_id: str, mode: str) -> Path:
        """
        初始化模式专属工作空间

        Args:
            workspace: 基础工作空间
            user_id: 社交模式用户ID，非社交模式忽略此值
            mode: 模式标识

        Returns:
            模式专属工作空间路径
        """
        from .memory_paths import memory_workspace
        return memory_workspace(mode, user_id, workspace)

    def _init_files(self) -> None:
        """初始化 MEMORY.md、USER.md 和 OpenClaw 风格 memory/ 分层目录"""
        self.daily_memory_dir.mkdir(parents=True, exist_ok=True)
        self.dreams_dir.mkdir(parents=True, exist_ok=True)

        # 创建 MEMORY.md
        if not self.memory_file.exists():
            initial_memory = """# 长期记忆 (MEMORY.md)

此文件存储用户的偏好、领域知识和模式方法论。

## 用户偏好

## 领域知识

## 模式方法论
"""
            self.memory_file.write_text(initial_memory, encoding="utf-8")
            logger.info("memory_file_created", path=str(self.memory_file))

        # 创建 USER.md（用户档案，由 Agent 通过对话主动维护）
        user_file = self.workspace / "USER.md"
        if not user_file.exists():
            initial_user_profile = """# USER.md - About Your Human

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
            user_file.write_text(initial_user_profile, encoding="utf-8")
            logger.info("user_file_created", path=str(user_file))

    def get_memory_context(self) -> str:
        """
        获取记忆上下文（用于LLM）

        Returns:
            MEMORY.md的内容（如果为空则返回空字符串）
        """
        try:
            memory_content = self.memory_file.read_text(encoding="utf-8")

            # 过滤掉空内容
            if memory_content.strip() in ["", "# 长期记忆 (MEMORY.md)", "# 长期记忆 (MEMORY.md)\n"]:
                return ""

            return f"## 长期记忆\n{memory_content}"

        except Exception as e:
            logger.error(
                "failed_to_read_memory",
                error=str(e),
                exc_info=True
            )
            return ""

    def append_daily_note(self, entry: str, note_date: Optional[str] = None) -> Path:
        """追加条目到 memory/YYYY-MM-DD.md。"""
        note_date = note_date or datetime.now().strftime("%Y-%m-%d")
        note_file = self.daily_memory_dir / f"{note_date}.md"

        if not note_file.exists():
            note_file.write_text(
                f"# Daily Memory {note_date}\n\n此文件记录当天对话摘要、观察和可检索上下文。\n",
                encoding="utf-8",
            )

        current_content = note_file.read_text(encoding="utf-8")
        normalized_entry = entry.rstrip() + "\n\n"

        if len(current_content) + len(normalized_entry) > self.max_history_size:
            keep_size = int(self.max_history_size * 0.8)
            current_content = current_content[-keep_size:]
            if not current_content.startswith("#"):
                current_content = f"# Daily Memory {note_date}\n\n... (older entries truncated)\n\n{current_content}"

        note_file.write_text(current_content + normalized_entry, encoding="utf-8")
        logger.debug("daily_note_updated", path=str(note_file), entry_length=len(normalized_entry))
        return note_file

    def list_daily_notes(self) -> List[Path]:
        """列出 daily note 文件，按日期倒序。"""
        if not self.daily_memory_dir.exists():
            return []
        return sorted(
            [
                path for path in self.daily_memory_dir.glob("*.md")
                if path.is_file() and path.parent == self.daily_memory_dir
            ],
            reverse=True,
        )

    def append_dream_candidate(self, entry: str, note_date: Optional[str] = None) -> Path:
        """追加候选记忆到 memory/.dreams/YYYY-MM-DD.md。"""
        note_date = note_date or datetime.now().strftime("%Y-%m-%d")
        dream_file = self.dreams_dir / f"{note_date}.md"

        if not dream_file.exists():
            dream_file.write_text(
                f"# Dream Candidates {note_date}\n\n此文件记录待观察、待晋升的候选长期记忆，不直接作为事实注入普通对话。\n",
                encoding="utf-8",
            )

        current_content = dream_file.read_text(encoding="utf-8")
        normalized_entry = entry.rstrip() + "\n\n"

        if len(current_content) + len(normalized_entry) > self.max_history_size:
            keep_size = int(self.max_history_size * 0.8)
            current_content = current_content[-keep_size:]
            if not current_content.startswith("#"):
                current_content = f"# Dream Candidates {note_date}\n\n... (older candidates truncated)\n\n{current_content}"

        dream_file.write_text(current_content + normalized_entry, encoding="utf-8")
        logger.debug("dream_candidate_updated", path=str(dream_file), entry_length=len(normalized_entry))
        return dream_file

    def list_dream_candidates(self) -> List[Path]:
        """列出 dream candidate 文件，按日期倒序。"""
        if not self.dreams_dir.exists():
            return []
        return sorted(
            [
                path for path in self.dreams_dir.glob("*.md")
                if path.is_file() and path.parent == self.dreams_dir
            ],
            reverse=True,
        )

    def read_recent_dreams(self, max_files: int = 5, max_chars: int = 6000) -> str:
        """读取最近的 dreaming 候选，供 consolidator 晋升判断使用。"""
        chunks = []
        remaining = max_chars

        for dream_file in self.list_dream_candidates()[:max_files]:
            if remaining <= 0:
                break

            content = dream_file.read_text(encoding="utf-8").strip()
            if not content:
                continue

            chunk = f"## {dream_file.name}\n{content}"
            if len(chunk) > remaining:
                chunk = chunk[:remaining].rstrip() + "\n...[truncated]"

            chunks.append(chunk)
            remaining -= len(chunk)

        return "\n\n".join(chunks)

    def search_daily_notes(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索 memory/YYYY-MM-DD.md daily notes。"""
        try:
            results = []
            lowered_query = query.lower()

            for note_file in self.list_daily_notes():
                note_content = note_file.read_text(encoding="utf-8")
                lines = note_content.split("\n")

                for i, line in enumerate(lines):
                    if lowered_query in line.lower():
                        context_start = max(0, i - 2)
                        context_end = min(len(lines), i + 3)
                        context = "\n".join(lines[context_start:context_end])

                        results.append({
                            "match": line.strip(),
                            "context": context,
                            "line_number": i + 1,
                            "source": f"memory/{note_file.name}"
                        })

                        if len(results) >= limit:
                            logger.info(
                                "daily_notes_searched",
                                mode=self.mode,
                                query=query,
                                results_found=len(results)
                            )
                            return results

            logger.info(
                "daily_notes_searched",
                mode=self.mode,
                query=query,
                results_found=len(results)
            )
            return results

        except Exception as e:
            logger.error(
                "failed_to_search_daily_notes",
                error=str(e),
                exc_info=True
            )
            return []


# ============================================================================
# 会话级常驻记忆快照
# ============================================================================

class ImprovedMemoryStore(MemoryStore):
    """Unified store with task-local resident-memory snapshots.

    Each run captures its own immutable string; cached stores can be reused by
    concurrent runs without sharing snapshots or creating temporary files.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from contextvars import ContextVar
        self._snapshot = ContextVar("resident_memory_snapshot", default=None)

    def create_snapshot(self) -> None:
        self._snapshot.set(self.read_long_term())

    def get_memory_context(self) -> str:
        snapshot = self._snapshot.get()
        if snapshot is None:
            return super().get_memory_context()
        return f"## 长期记忆\n{snapshot}" if snapshot.strip() else ""

    def cleanup_snapshot(self) -> None:
        self._snapshot.set(None)

    def read_long_term(self) -> str:
        """读取长期记忆内容"""
        try:
            if not self.memory_file.exists():
                return ""

            content = self.memory_file.read_text(encoding="utf-8")

            # 过滤掉空内容或只有标题的情况
            if content.strip() in ["", "# 长期记忆 (MEMORY.md)", "# 长期记忆 (MEMORY.md)\n"]:
                return ""

            return content

        except Exception as e:
            logger.error(
                "failed_to_read_long_term_memory",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e)
            )
            return ""
