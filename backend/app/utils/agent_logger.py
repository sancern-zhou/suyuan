"""
Agent Logger - Agent运行日志记录器

学习Mini-Agent的完整运行追踪机制，提供详细的执行日志。
与现有structlog协同工作，增加完整的运行追踪能力。

核心功能:
- 每次运行生成独立日志文件
- 记录完整的请求/响应/工具调用链
- 支持调试和问题排查
- 提供运行统计分析
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()


class AgentLogger:
    """
    Agent运行日志记录器

    功能：
    - 每次运行生成独立JSON日志文件
    - 记录LLM请求、响应、工具调用
    - 支持运行回放和调试
    - 提供性能统计
    """

    def __init__(
        self,
        log_dir: str = "./logs/agent_runs",
        enable_file_logging: bool = True,
        max_content_preview: int = 500
    ):
        """
        初始化Agent日志记录器

        Args:
            log_dir: 日志目录
            enable_file_logging: 是否启用文件日志
            max_content_preview: 内容预览最大长度
        """
        self.log_dir = Path(log_dir)
        self.enable_file_logging = enable_file_logging
        self.max_content_preview = max_content_preview

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

            # 运行记录
            "iterations": [],
            "llm_calls": [],
            "tool_calls": [],
            "errors": [],

            # 统计信息
            "stats": {
                "total_llm_calls": 0,
                "total_tool_calls": 0,
                "total_tokens_input": 0,
                "total_tokens_output": 0,
                "total_duration_ms": 0
            }
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

    def log_llm_request(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Any]] = None,
        iteration: int = 0,
        phase: str = "unknown"
    ):
        """
        记录LLM请求

        Args:
            messages: 消息列表
            tools: 可用工具列表
            iteration: 当前迭代次数
            phase: 阶段（thought/action/summary等）
        """
        if not self.current_run:
            return

        # 提取工具名称
        tool_names = []
        if tools:
            for tool in tools:
                if hasattr(tool, "name"):
                    tool_names.append(tool.name)
                elif isinstance(tool, dict):
                    tool_names.append(tool.get("name", "unknown"))

        # 计算消息摘要
        message_summary = []
        for msg in messages[-5:]:  # 只记录最近5条
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str):
                preview = content[:self.max_content_preview]
                if len(content) > self.max_content_preview:
                    preview += "..."
            else:
                preview = str(content)[:self.max_content_preview]

            message_summary.append({
                "role": role,
                "content_preview": preview,
                "content_length": len(str(content))
            })

        llm_call = {
            "call_id": len(self.current_run["llm_calls"]) + 1,
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "phase": phase,
            "message_count": len(messages),
            "message_summary": message_summary,
            "tools_available": tool_names,
            "tool_count": len(tool_names)
        }

        self.current_run["llm_calls"].append(llm_call)
        self.current_run["stats"]["total_llm_calls"] += 1

    def log_llm_response(
        self,
        content: Optional[str] = None,
        thinking: Optional[str] = None,
        tool_calls: Optional[List[Any]] = None,
        finish_reason: Optional[str] = None,
        usage: Optional[Dict[str, int]] = None,
        iteration: int = 0
    ):
        """
        记录LLM响应

        Args:
            content: 响应内容
            thinking: 思考过程
            tool_calls: 工具调用
            finish_reason: 完成原因
            usage: Token使用量
            iteration: 当前迭代次数
        """
        if not self.current_run:
            return

        # 处理工具调用
        tool_call_summary = []
        if tool_calls:
            for tc in tool_calls:
                if hasattr(tc, "function"):
                    tool_call_summary.append({
                        "id": getattr(tc, "id", "unknown"),
                        "name": tc.function.name,
                        "arguments_preview": str(tc.function.arguments)[:200]
                    })
                elif isinstance(tc, dict):
                    func = tc.get("function", {})
                    tool_call_summary.append({
                        "id": tc.get("id", "unknown"),
                        "name": func.get("name", "unknown"),
                        "arguments_preview": str(func.get("arguments", {}))[:200]
                    })

        response = {
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "has_content": bool(content),
            "content_preview": (content[:self.max_content_preview] + "...") if content and len(content) > self.max_content_preview else content,
            "content_length": len(content) if content else 0,
            "has_thinking": bool(thinking),
            "thinking_preview": (thinking[:200] + "...") if thinking and len(thinking) > 200 else thinking,
            "tool_calls": tool_call_summary,
            "tool_call_count": len(tool_call_summary),
            "finish_reason": finish_reason
        }

        # 更新Token统计
        if usage:
            response["usage"] = usage
            self.current_run["stats"]["total_tokens_input"] += usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
            self.current_run["stats"]["total_tokens_output"] += usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)

        # 更新最近的LLM调用记录
        if self.current_run["llm_calls"]:
            self.current_run["llm_calls"][-1]["response"] = response

    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        iteration: int = 0
    ):
        """
        记录工具调用开始

        Args:
            tool_name: 工具名称
            arguments: 调用参数
            iteration: 当前迭代次数
        """
        if not self.current_run:
            return

        # 参数摘要（避免过长）
        args_summary = {}
        for key, value in arguments.items():
            str_value = str(value)
            if len(str_value) > 200:
                args_summary[key] = str_value[:200] + "..."
            else:
                args_summary[key] = value

        tool_call = {
            "call_id": len(self.current_run["tool_calls"]) + 1,
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "tool_name": tool_name,
            "arguments": args_summary,
            "status": "started",
            "result": None,
            "duration_ms": None
        }

        self.current_run["tool_calls"].append(tool_call)
        self.current_run["stats"]["total_tool_calls"] += 1

    def log_tool_result(
        self,
        tool_name: str,
        success: bool,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None
    ):
        """
        记录工具执行结果

        Args:
            tool_name: 工具名称
            success: 是否成功
            result: 执行结果
            error: 错误信息
            duration_ms: 执行时长（毫秒）
        """
        if not self.current_run:
            return

        # 找到对应的工具调用记录
        for tool_call in reversed(self.current_run["tool_calls"]):
            if tool_call["tool_name"] == tool_name and tool_call["status"] == "started":
                tool_call["status"] = "success" if success else "failed"
                tool_call["duration_ms"] = duration_ms

                if success and result:
                    # 结果摘要
                    result_str = str(result)
                    tool_call["result"] = {
                        "success": True,
                        "preview": result_str[:self.max_content_preview] + "..." if len(result_str) > self.max_content_preview else result_str,
                        "length": len(result_str),
                        "has_data": "data" in result if isinstance(result, dict) else False,
                        "has_visuals": "visuals" in result if isinstance(result, dict) else False
                    }
                elif error:
                    tool_call["result"] = {
                        "success": False,
                        "error": error[:500]
                    }

                if duration_ms:
                    self.current_run["stats"]["total_duration_ms"] += duration_ms

                break

    def log_iteration(
        self,
        iteration: int,
        thought: str,
        action: Dict[str, Any],
        observation: Dict[str, Any]
    ):
        """
        记录完整的迭代

        Args:
            iteration: 迭代次数
            thought: 思考内容
            action: 行动决策
            observation: 观察结果
        """
        if not self.current_run:
            return

        iter_record = {
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "thought_preview": thought[:300] + "..." if len(thought) > 300 else thought,
            "action_type": action.get("type", "unknown"),
            "action_tool": action.get("tool"),
            "observation_success": observation.get("success", True),
            "observation_preview": str(observation.get("summary", ""))[:200]
        }

        self.current_run["iterations"].append(iter_record)

    def log_error(
        self,
        error: str,
        error_type: str = "unknown",
        iteration: int = 0,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        记录错误

        Args:
            error: 错误信息
            error_type: 错误类型
            iteration: 发生迭代
            context: 错误上下文
        """
        if not self.current_run:
            return

        error_record = {
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "error_type": error_type,
            "error": error[:1000],
            "context": context
        }

        self.current_run["errors"].append(error_record)

        logger.error(
            "agent_error_logged",
            error_type=error_type,
            iteration=iteration
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

        # 计算总时长
        start_time = datetime.fromisoformat(self.current_run["start_time"])
        total_duration = (end_time - start_time).total_seconds() * 1000
        self.current_run["stats"]["total_duration_ms"] = total_duration

        # 写入文件
        if self.enable_file_logging and self.log_file:
            self._save_to_file()

        logger.info(
            "agent_run_ended",
            run_id=self.current_run["run_id"],
            status=status,
            iterations=len(self.current_run["iterations"]),
            llm_calls=self.current_run["stats"]["total_llm_calls"],
            tool_calls=self.current_run["stats"]["total_tool_calls"],
            duration_ms=total_duration
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
        """获取当前运行统计"""
        if not self.current_run:
            return {}
        return self.current_run["stats"].copy()

    def get_run_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取运行摘要

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
            "iterations": len(self.current_run["iterations"]),
            "llm_calls": self.current_run["stats"]["total_llm_calls"],
            "tool_calls": self.current_run["stats"]["total_tool_calls"],
            "tokens_used": self.current_run["stats"]["total_tokens_input"] + self.current_run["stats"]["total_tokens_output"],
            "duration_ms": self.current_run["stats"]["total_duration_ms"],
            "errors": len(self.current_run["errors"]),
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
