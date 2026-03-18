"""
LLM Context Logger - LLM请求上下文日志记录器

专门用于记录完整的LLM请求上下文到文件，避免控制台输出过长。

功能：
- 每次LLM调用生成独立的上下文日志文件
- 记录完整的system_prompt、user_conversation等
- 在控制台只显示预览和文件路径
- 支持按时间戳或session_id查询历史记录
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import structlog

logger = structlog.get_logger()


class LLMContextLogger:
    """
    LLM请求上下文日志记录器

    专门记录完整的LLM请求上下文，用于调试和分析。
    """

    def __init__(
        self,
        log_dir: str = "./logs/llm_context",
        enable_file_logging: bool = True,
        max_files: int = 100  # 最多保留多少个日志文件
    ):
        """
        初始化LLM上下文日志记录器

        Args:
            log_dir: 日志目录
            enable_file_logging: 是否启用文件日志
            max_files: 最多保留的日志文件数量（超过后自动清理旧文件）
        """
        self.log_dir = Path(log_dir)
        self.enable_file_logging = enable_file_logging
        self.max_files = max_files

        # 当前会话的上下文记录
        self.session_contexts: Dict[str, List[Dict[str, Any]]] = {}

        # 确保日志目录存在
        if enable_file_logging:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_request_context(
        self,
        session_id: str,
        iteration: int,
        mode: str,
        messages: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        记录LLM请求上下文

        Args:
            session_id: 会话ID
            iteration: 迭代次数
            mode: Agent模式
            messages: 完整的消息列表
            metadata: 额外元数据

        Returns:
            日志文件路径（如果启用文件日志）
        """
        if not self.enable_file_logging:
            return None

        try:
            timestamp = datetime.now()
            context_id = f"{session_id}_iter{iteration}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"

            # 提取system_prompt和user_conversation
            system_prompt = ""
            user_conversation = ""
            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                elif msg.get("role") == "user":
                    user_conversation = msg.get("content", "")

            # 构建上下文记录
            context_record = {
                "context_id": context_id,
                "timestamp": timestamp.isoformat(),
                "session_id": session_id,
                "iteration": iteration,
                "mode": mode,
                "metadata": metadata or {},

                # 完整的上下文内容
                "system_prompt": system_prompt,
                "system_prompt_length": len(system_prompt),

                "user_conversation": user_conversation,
                "user_conversation_length": len(user_conversation),

                "messages_count": len(messages),
                "messages": messages,  # 完整的消息列表
            }

            # 创建日志文件
            log_file = self.log_dir / f"context_{context_id}.json"

            # 写入文件
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(context_record, f, ensure_ascii=False, indent=2, default=str)

            # 添加到会话上下文列表
            if session_id not in self.session_contexts:
                self.session_contexts[session_id] = []
            self.session_contexts[session_id].append(context_record)

            # 清理旧文件
            self._cleanup_old_files()

            # 返回文件路径和预览信息
            preview = {
                "log_file": str(log_file),
                "context_id": context_id,
                "system_prompt_preview": system_prompt[:200] + "..." if len(system_prompt) > 200 else system_prompt,
                "user_conversation_preview": user_conversation[:500] + "..." if len(user_conversation) > 500 else user_conversation,
            }

            logger.info(
                "llm_context_logged",
                session_id=session_id,
                iteration=iteration,
                log_file=str(log_file),
                system_prompt_length=len(system_prompt),
                user_conversation_length=len(user_conversation),
            )

            return str(log_file)

        except Exception as e:
            logger.error("llm_context_logging_failed", error=str(e), session_id=session_id, iteration=iteration)
            return None

    def get_session_contexts(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取会话的所有上下文记录

        Args:
            session_id: 会话ID
            limit: 最多返回多少条记录

        Returns:
            上下文记录列表
        """
        contexts = self.session_contexts.get(session_id, [])
        if limit:
            contexts = contexts[-limit:]
        return contexts

    def get_latest_context(
        self,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取会话的最新上下文记录

        Args:
            session_id: 会话ID

        Returns:
            最新的上下文记录
        """
        contexts = self.session_contexts.get(session_id, [])
        if contexts:
            return contexts[-1]
        return None

    def _cleanup_old_files(self):
        """清理旧的日志文件，保留最新的max_files个文件"""
        try:
            # 获取所有日志文件
            log_files = list(self.log_dir.glob("context_*.json"))

            # 如果文件数量超过限制，删除最旧的文件
            if len(log_files) > self.max_files:
                # 按修改时间排序
                log_files.sort(key=lambda f: f.stat().st_mtime)

                # 删除最旧的文件
                files_to_delete = log_files[:len(log_files) - self.max_files]
                for file in files_to_delete:
                    file.unlink()
                    logger.debug("old_llm_context_file_deleted", file=str(file))

        except Exception as e:
            logger.error("llm_context_cleanup_failed", error=str(e))

    def get_log_file_path(self, context_id: str) -> Optional[str]:
        """
        根据context_id获取日志文件路径

        Args:
            context_id: 上下文ID

        Returns:
            日志文件路径
        """
        log_file = self.log_dir / f"context_{context_id}.json"
        if log_file.exists():
            return str(log_file)
        return None

    def clear_session(self, session_id: str):
        """
        清除会话的内存上下文记录

        Args:
            session_id: 会话ID
        """
        if session_id in self.session_contexts:
            del self.session_contexts[session_id]


# 全局实例
_llm_context_logger: Optional[LLMContextLogger] = None


def get_llm_context_logger() -> LLMContextLogger:
    """
    获取全局LLM上下文日志记录器实例

    Returns:
        LLMContextLogger实例
    """
    global _llm_context_logger
    if _llm_context_logger is None:
        _llm_context_logger = LLMContextLogger()
    return _llm_context_logger


def create_llm_context_logger(
    log_dir: str = "./logs/llm_context",
    enable_file_logging: bool = True,
    max_files: int = 100
) -> LLMContextLogger:
    """
    创建LLM上下文日志记录器

    Args:
        log_dir: 日志目录
        enable_file_logging: 是否启用文件日志
        max_files: 最多保留的日志文件数量

    Returns:
        LLMContextLogger实例
    """
    return LLMContextLogger(
        log_dir=log_dir,
        enable_file_logging=enable_file_logging,
        max_files=max_files
    )
