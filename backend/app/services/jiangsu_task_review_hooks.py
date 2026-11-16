"""江苏工单/智能事件审核生命周期钩子（经 task_review_hooks 注册表挂接）。

历史内联在共享 task_review.py 中的 4 个钩子（证据包同步、剔除申报一致性
硬校验、智能事件退回重跑、决策对话反馈）迁出为项目侧实现；工单号谓词与
路由文案属江苏工单域知识，不进入共享层。web 与 worker 都执行注册点
（lifecycle/scheduled.py 的项目门控块）。
"""
import structlog

from app.services.task_review import append_review_session_record
from app.services.task_review_hooks import (
    register_decision_listener,
    register_submission_validator,
)

logger = structlog.get_logger()


def is_work_order_review(record: dict) -> bool:
    """判断审核记录是否属于故障工单审核（subject_id 为工单号或分类为工单审核）。"""
    subject = str(record.get("subject_id") or "")
    return bool(subject) and (subject.startswith("FA") or record.get("category") == "工单审核")


def _sync_evidence_listener(record, decision, actor, session_id=None) -> None:
    """把工单审核的 AI 提交/人工决策同步到证据包；失败不阻断审核主流程。"""
    if not is_work_order_review(record):
        return
    from app.services.jiangsu_work_order_review import sync_review_record

    try:
        sync_review_record(record, decision)
    except KeyError:
        # 尚未采集证据包的工单审核（例如未走 jiangsu_fetch_review_evidence）跳过同步。
        logger.debug("work_order_review_package_missing", subject_id=record.get("subject_id"))
    except Exception as exc:
        logger.warning("work_order_review_sync_failed", error=str(exc),
                       subject_id=record.get("subject_id"))


def _removal_declaration_validator(submission) -> None:
    """工单审核结论语义：通过的前提是剔除申报一致；申报无剔除而建议剔除时拒绝 approve。"""
    if not is_work_order_review(submission):
        return
    from app.services.jiangsu_work_order_review import validate_removal_declaration_consistency

    validate_removal_declaration_consistency(submission)


def _feedback_listener(record, decision, actor, session_id=None) -> None:
    """审核决策（确认归档/退回）写入原审核会话的反馈记录，并按需排队一致性确认。

    两个动作都尽力而为：失败只告警，绝不影响决策主流程。
    """
    if decision is None:
        # 提交路径（decision=None）只做证据包同步，不写会话反馈。
        return
    if not is_work_order_review(record):
        return
    from app.services.jiangsu_fault_work_order_review_feedback import (
        queue_work_order_review_feedback,
    )

    resolved_session_id = session_id
    try:
        resolved_session_id = append_review_session_record(record, decision, actor)
    except Exception as exc:
        logger.warning("work_order_review_session_record_failed", error=str(exc),
                       review_id=record.get("review_id"))
    try:
        queue_work_order_review_feedback(record, decision, actor, session_id=resolved_session_id)
    except Exception as exc:
        logger.warning("work_order_review_feedback_hook_failed", error=str(exc),
                       review_id=record.get("review_id"))


def _reject_rerun_listener(record, decision, actor, session_id=None) -> None:
    """智能事件人工退回后自动触发以审核意见为基准的增量 AI 研判（尽力而为）。"""
    if not decision or decision.get("action") != "reject":
        return
    from app.services.jiangsu_smart_event import queue_review_reject_rerun

    try:
        queue_review_reject_rerun(record, decision, actor)
    except Exception as exc:
        logger.warning("smart_event_review_reject_rerun_hook_failed", error=str(exc))


def register_task_review_hooks() -> None:
    """把江苏审核生命周期钩子注册进共享注册表（幂等）。"""
    register_submission_validator(_removal_declaration_validator)
    register_decision_listener(_sync_evidence_listener)
    register_decision_listener(_feedback_listener)
    register_decision_listener(_reject_rerun_listener)
