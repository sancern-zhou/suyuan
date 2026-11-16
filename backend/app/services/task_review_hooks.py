"""审核生命周期项目钩子注册表。

共享 task_review 引擎经本注册表把项目域的提交校验与决策后处理解耦到项目侧
模块（如 jiangsu_work_order_review）；项目在进程启动时注册（lifecycle/
scheduled.py 的项目门控块，web 与 worker 都执行）。共享层不写死任何项目服务。

语义约定（与历史内联钩子一致）：
- submission validator：fn(submission) 校验失败直接抛异常，阻断提交；
- decision listener：fn(record, decision, actor)，异常尽力而为（逐个隔离、
  仅告警），绝不影响决策主流程。
"""
from typing import Callable, List

import structlog

logger = structlog.get_logger()

_submission_validators: List[Callable[[dict], None]] = []
_decision_listeners: List[Callable[..., None]] = []


def register_submission_validator(fn: Callable[[dict], None]) -> None:
    if fn not in _submission_validators:
        _submission_validators.append(fn)


def register_decision_listener(fn: Callable[..., None]) -> None:
    if fn not in _decision_listeners:
        _decision_listeners.append(fn)


def run_submission_validators(submission: dict) -> None:
    """依次执行注册的提交校验器；校验失败原样抛出（阻断提交）。"""
    for fn in list(_submission_validators):
        fn(submission)


def notify_review_decision(record: dict, decision: dict | None = None, actor: dict | None = None) -> None:
    """通知所有注册的决策监听器；单个监听器失败仅告警，不阻断决策主流程。"""
    for fn in list(_decision_listeners):
        try:
            fn(record, decision, actor)
        except Exception as exc:
            logger.warning(
                "task_review_decision_listener_failed",
                listener=getattr(fn, "__name__", repr(fn)),
                error=str(exc),
                review_id=record.get("review_id"),
            )
