"""
Agent Logger - Agent运行日志记录器（简化版）

参考 OpenClaw 设计，只保留核心指标：
- duration_ms: 运行时长
- usage: Token使用情况

移除未使用的复杂追踪：
- iterations 详细追踪
- llm_calls 详细记录
- tool_calls 详细记录
- message_summary、tool_call_summary 等

核心功能:
- 每次运行生成独立日志文件
- 记录核心统计指标（时长、token使用）
- 记录错误信息（用于调试）
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger()


class AgentLogger:
    """
    Agent运行日志记录器（简化版）

    功能：
    - 每次运行生成独立JSON日志文件
    - 只记录核心指标：duration_ms、usage
    - 记录错误信息用于调试
    """

    def __init__(
        self,
        log_dir: str = "./logs/agent_runs",
        enable_file_logging: bool = True
    ):
        """
        初始化Agent日志记录器

        Args:
            log_dir: 日志目录
            enable_file_logging: 是否启用文件日志
        """
        self.log_dir = Path(log_dir)
        self.enable_file_logging = enable_file_logging

        # 当前运行数据
        self.current_run: Optional[Dict[str, Any]] = None
        self.log_file: Optional[Path] = None

        # 确保日志目录存在
        if enable_file_logging:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def start_new_run(
        self,
        session_id: Optional[str] = None,
        query: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        开始新的运行记录

        Args:
            session_id: 会话ID
            query: 用户查询
            metadata: 额外元数据

        Returns:
            运行ID
        """
        timestamp = datetime.now()
        run_id = timestamp.strftime("%Y%m%d_%H%M%S_%f")

        self.current_run = {
            "run_id": run_id,
            "session_id": session_id,
            "start_time": timestamp.isoformat(),
            "end_time": None,
            "status": "running",
            "query": query,
            "metadata": metadata or {},

            # 核心统计指标（参考 OpenClaw）
            "stats": {
                "duration_ms": 0,
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0
                }
            },

            # 错误记录（用于调试）
            "errors": []
        }

        # 创建日志文件
        if self.enable_file_logging:
            self.log_file = self.log_dir / f"run_{run_id}.json"

        logger.info(
            "agent_run_started",
            run_id=run_id,
            session_id=session_id,
            log_file=str(self.log_file) if self.log_file else None
        )

        return run_id

    def record_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0
    ):
        """
        记录Token使用情况

        Args:
            input_tokens: 输入token数
            output_tokens: 输出token数
        """
        if not self.current_run:
            return

        self.current_run["stats"]["usage"]["input_tokens"] += input_tokens
        self.current_run["stats"]["usage"]["output_tokens"] += output_tokens
        self.current_run["stats"]["usage"]["total_tokens"] += (input_tokens + output_tokens)

    def log_error(
        self,
        error: str,
        error_type: str = "unknown",
        context: Optional[Dict[str, Any]] = None
    ):
        """
        记录错误（用于调试）

        Args:
            error: 错误信息
            error_type: 错误类型
            context: 错误上下文
        """
        if not self.current_run:
            return

        error_record = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "error": error[:1000],  # 限制长度
            "context": context
        }

        self.current_run["errors"].append(error_record)

        logger.error(
            "agent_error_logged",
            error_type=error_type,
            error_preview=error[:200]
        )

    def end_run(
        self,
        status: str = "completed",
        final_answer: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        结束运行记录

        Args:
            status: 运行状态（completed/failed/timeout）
            final_answer: 最终答案
            metadata: 额外元数据
        """
        if not self.current_run:
            return

        end_time = datetime.now()
        self.current_run["end_time"] = end_time.isoformat()
        self.current_run["status"] = status

        if final_answer:
            self.current_run["final_answer_preview"] = final_answer[:1000]

        if metadata:
            self.current_run["metadata"].update(metadata)

        # 计算总时长（核心指标）
        start_time = datetime.fromisoformat(self.current_run["start_time"])
        total_duration = (end_time - start_time).total_seconds() * 1000
        self.current_run["stats"]["duration_ms"] = total_duration

        # 写入文件
        if self.enable_file_logging and self.log_file:
            self._save_to_file()

        # 记录核心统计日志
        logger.info(
            "agent_run_ended",
            run_id=self.current_run["run_id"],
            status=status,
            duration_ms=total_duration,
            input_tokens=self.current_run["stats"]["usage"]["input_tokens"],
            output_tokens=self.current_run["stats"]["usage"]["output_tokens"],
            total_tokens=self.current_run["stats"]["usage"]["total_tokens"],
            errors_count=len(self.current_run["errors"])
        )

    def _save_to_file(self):
        """保存日志到文件"""
        if not self.log_file or not self.current_run:
            return

        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(self.current_run, f, ensure_ascii=False, indent=2, default=str)

            logger.debug("agent_log_saved", file=str(self.log_file))

        except Exception as e:
            logger.error("agent_log_save_failed", error=str(e))

    def get_log_file_path(self) -> Optional[str]:
        """获取当前日志文件路径"""
        return str(self.log_file) if self.log_file else None

    def get_current_stats(self) -> Dict[str, Any]:
        """
        获取当前运行统计（核心指标）

        Returns:
            {
                "duration_ms": 1234,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 200,
                    "total_tokens": 300
                }
            }
        """
        if not self.current_run:
            return {}
        return self.current_run["stats"].copy()

    def get_run_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取运行摘要（核心指标）

        Returns:
            运行摘要字典
        """
        if not self.current_run:
            return None

        return {
            "run_id": self.current_run["run_id"],
            "status": self.current_run["status"],
            "start_time": self.current_run["start_time"],
            "end_time": self.current_run["end_time"],
            "query_preview": self.current_run["query"][:100] if self.current_run["query"] else None,
            # 核心指标
            "duration_ms": self.current_run["stats"]["duration_ms"],
            "input_tokens": self.current_run["stats"]["usage"]["input_tokens"],
            "output_tokens": self.current_run["stats"]["usage"]["output_tokens"],
            "total_tokens": self.current_run["stats"]["usage"]["total_tokens"],
            "errors_count": len(self.current_run["errors"]),
            "log_file": str(self.log_file) if self.log_file else None
        }


class AgentLoggerMixin:
    """
    Agent日志混入类

    可添加到ReActLoop或ReActAgent，提供运行日志能力
    """

    def __init__(self, log_dir: str = "./logs/agent_runs"):
        self._agent_logger = AgentLogger(log_dir=log_dir)

    def get_agent_logger(self) -> AgentLogger:
        """获取Agent日志记录器"""
        return self._agent_logger


# 便捷函数
def create_agent_logger(
    log_dir: str = "./logs/agent_runs",
    enable_file_logging: bool = True
) -> AgentLogger:
    """
    创建Agent日志记录器

    Args:
        log_dir: 日志目录
        enable_file_logging: 是否启用文件日志

    Returns:
        AgentLogger实例
    """
    return AgentLogger(
        log_dir=log_dir,
        enable_file_logging=enable_file_logging
    )
