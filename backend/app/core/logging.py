"""Logging configuration extracted from app/main.py."""

import logging
import os
import sys

import structlog


def configure_logging() -> None:
    """Configure stdlib logging and structlog renderers."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.INFO)
    logging.getLogger("apscheduler.executors").setLevel(logging.INFO)

    use_json_logs = os.getenv("USE_JSON_LOGS", "false").lower() == "true"
    if use_json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )

    def add_process(logger, method_name, event_dict):
        # 多进程部署（uvicorn --workers N）共享同一日志文件，PID 是区分
        # 各 worker 事件的唯一线索；放在时间戳之后便于按进程切分日志。
        event_dict["process"] = os.getpid()
        return event_dict

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            add_process,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

