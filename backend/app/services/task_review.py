"""One validated hand-off and human-review lifecycle for all scheduled tasks."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import structlog
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.path_config import get_data_registry

logger = structlog.get_logger()


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Check(ReviewModel):
    name: str = Field(min_length=1)
    status: Literal["pass", "fail", "uncertain", "not_applicable"]
    basis: str = Field(min_length=1)
    scope: Literal["core", "supporting", "rebuttal"] = "core"
    missing_evidence: list[str] = Field(default_factory=list)


class DataImpact(ReviewModel):
    pollutant: str = Field(min_length=1)
    decision: Literal["keep", "partial_exclude", "exclude", "missing_no_delete", "not_applicable", "needs_evidence"]
    granularity: str = "hour"
    station_code: str | None = None
    device_id: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    basis: str = Field(min_length=1)
    boundary_sources: list[str] = Field(default_factory=list)
    reasonableness_status: Literal["pass", "uncertain", "fail"] | None = None
    reasonableness_basis: str | None = None

    @model_validator(mode="after")
    def validate_interval(self):
        if bool(self.start) != bool(self.end):
            raise ValueError("时间区间必须同时提供 start/end")
        if self.start and self.end:
            if self.start.tzinfo is None or self.end.tzinfo is None:
                raise ValueError("时间区间必须包含时区")
            if self.start > self.end:
                raise ValueError("start 不能晚于 end")
        if self.decision in {"partial_exclude", "exclude"} and not (
            self.start and self.end and self.boundary_sources
            and self.reasonableness_status and self.reasonableness_basis
        ):
            raise ValueError("建议剔除必须包含时间区间、边界来源和合理性判断")
        return self


class Evidence(ReviewModel):
    label: str = Field(min_length=1)
    path: str = Field(min_length=1, description="项目根相对路径或数据目录中的绝对路径")


class DetailField(ReviewModel):
    key: str | None = Field(default=None, description="可选稳定业务字段标识，供来源页面读取")
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class DetailSection(ReviewModel):
    title: str = Field(min_length=1)
    fields: list[DetailField] = Field(min_length=1)


class ReviewSubmission(ReviewModel):
    subject_id: str = Field(min_length=1, max_length=240, description="稳定业务编号，用于同一任务内去重")
    event_id: str | None = None
    category: str = Field(min_length=1, max_length=60, description="任务分类，例如工单审核、智能事件、故障诊断")
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=4000)
    decision: Literal["approve", "reject", "needs_evidence", "needs_action"]
    comment: str = Field(min_length=1, max_length=12000)
    review_basis: list[str] = Field(default_factory=list, description="审核依据，例如 SOP 编号")
    checks: list[Check] = Field(min_length=1)
    data_impact: list[DataImpact] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    sections: list[DetailSection] = Field(default_factory=list, description="站点、故障事实、处置、恢复、复测、传输、事件类型与等级等通用键值区块")


class HumanDecision(ReviewModel):
    version: int = Field(ge=1)
    action: Literal["confirm", "reject", "start_disposal", "complete"]
    decision: Literal["approve", "reject", "needs_evidence", "needs_action"]
    comment: str = Field(min_length=1, max_length=4000)
    data_impact: list[DataImpact]
    intervals_confirmed: bool = False


def _storage_mode() -> str:
    configured = os.getenv("TASK_REVIEW_STORAGE")
    if configured:
        return configured.strip().lower()
    return "db" if os.getenv("DATABASE_URL") else "file"


def _use_db() -> bool:
    return _storage_mode() != "file"


def reviews_dir() -> Path:
    path = get_data_registry() / "task_reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def review_path(review_id: str) -> Path:
    if not review_id.startswith("review_") or len(review_id) != 39 or any(c not in "0123456789abcdef" for c in review_id[7:]):
        raise ValueError("invalid_review_id")
    return reviews_dir() / f"{review_id}.json"


@contextmanager
def review_lock(review_id):
    with review_path(review_id).with_suffix(".lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def _parse_db_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _db_record_to_dict(row) -> dict:
    from datetime import datetime as _datetime

    data = {}
    for col in row.__table__.columns:
        value = getattr(row, col.name)
        data[col.name] = value.isoformat() if isinstance(value, _datetime) else value
    return data


async def _db_load_review(review_id: str) -> dict | None:
    from sqlalchemy import select

    from app.db.models.task_review_db import TaskReviewDB
    from app.db.sync_bridge import bridge_session

    async with bridge_session() as session:
        row = (await session.execute(
            select(TaskReviewDB).where(TaskReviewDB.review_id == review_id)
        )).scalar_one_or_none()
        return _db_record_to_dict(row) if row else None


async def _db_save_review(review: dict) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.db.models.task_review_db import TaskReviewDB
    from app.db.sync_bridge import bridge_session

    values = {
        "review_id": review["review_id"],
        "subject_id": review.get("subject_id", ""),
        "event_id": review.get("event_id"),
        "category": review.get("category", ""),
        "title": review.get("title", ""),
        "summary": review.get("summary", ""),
        "decision": review.get("decision"),
        "comment": review.get("comment"),
        "status": review.get("status", "pending_review"),
        "task_id": review.get("task_id", ""),
        "task_name": review.get("task_name", ""),
        "execution_id": review.get("execution_id", ""),
        "version": review.get("version", 1),
        "created_at": _parse_db_datetime(review.get("created_at")),
        "updated_at": _parse_db_datetime(review.get("updated_at")),
        "allow_archived_review_reopen": review.get("allow_archived_review_reopen", True),
        "submission": review.get("submission", {}),
        "checks": review.get("checks", []),
        "data_impact": review.get("data_impact", []),
        "evidence": review.get("evidence", []),
        "actions": review.get("actions", []),
        "sections": review.get("sections", []),
        "review_basis": review.get("review_basis", []),
        "human_decision": review.get("human_decision"),
        "human_feedback": review.get("human_feedback"),
        "operations": review.get("operations", []),
        "history": review.get("history", []),
    }
    async with bridge_session() as session:
        stmt = pg_insert(TaskReviewDB).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["review_id"],
            set_={key: value for key, value in values.items() if key != "review_id"},
        )
        await session.execute(stmt)
        await session.commit()


def _db_filters(pending_only: bool, category: str | None, task_id: str | None):
    from sqlalchemy import and_

    from app.db.models.task_review_db import TaskReviewDB

    clauses = []
    if pending_only:
        clauses.append(TaskReviewDB.status.in_(["pending_review", "in_disposal"]))
    if category is not None:
        clauses.append(TaskReviewDB.category == category)
    if task_id is not None:
        clauses.append(TaskReviewDB.task_id == task_id)
    return and_(*clauses) if clauses else None


async def _db_list_reviews(*, pending_only=True, category=None, task_id=None, limit=None, offset=0) -> list[dict]:
    from sqlalchemy import select

    from app.db.models.task_review_db import TaskReviewDB
    from app.db.sync_bridge import bridge_session

    async with bridge_session() as session:
        stmt = select(TaskReviewDB).where(_db_filters(pending_only, category, task_id))
        stmt = stmt.order_by(TaskReviewDB.updated_at.desc())
        if limit is not None:
            stmt = stmt.offset(offset).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [_db_record_to_dict(row) for row in rows]


async def _db_list_categories() -> list[str]:
    from sqlalchemy import distinct, select

    from app.db.models.task_review_db import TaskReviewDB
    from app.db.sync_bridge import bridge_session

    async with bridge_session() as session:
        rows = await session.execute(select(distinct(TaskReviewDB.category)))
        return sorted({row[0] for row in rows if row[0]})


async def _db_has_active_review(task_id: str, subject_id: str) -> bool:
    from sqlalchemy import func, select

    from app.db.models.task_review_db import TaskReviewDB
    from app.db.sync_bridge import bridge_session

    async with bridge_session() as session:
        stmt = select(func.count(TaskReviewDB.review_id)).where(
            TaskReviewDB.task_id == task_id,
            TaskReviewDB.subject_id == subject_id,
            TaskReviewDB.status.in_(["pending_review", "in_disposal"]),
        )
        return (await session.execute(stmt)).scalar_one() > 0


async def _db_pending_feedback_reviews() -> list[dict]:
    from sqlalchemy import String, cast, or_, select

    from app.db.models.task_review_db import TaskReviewDB
    from app.db.sync_bridge import bridge_session

    async with bridge_session() as session:
        clause = or_(
            TaskReviewDB.human_feedback["status"].astext.in_(["pending", "failed"]),
            cast(TaskReviewDB.history, String).like('%"status": "pending"%'),
            cast(TaskReviewDB.history, String).like('%"status": "failed"%'),
        )
        stmt = select(TaskReviewDB).where(clause).order_by(TaskReviewDB.updated_at.asc()).limit(200)
        rows = (await session.execute(stmt)).scalars().all()
        return [_db_record_to_dict(row) for row in rows]


async def _db_list_reviews_payload(*, pending_only=True, category=None, limit=100, offset=0) -> dict:
    from sqlalchemy import distinct, func, select

    from app.db.models.task_review_db import TaskReviewDB
    from app.db.sync_bridge import bridge_session

    async with bridge_session() as session:
        where = _db_filters(pending_only, category, None)
        total = (await session.execute(
            select(func.count(TaskReviewDB.review_id)).where(where)
        )).scalar_one()
        stmt = select(TaskReviewDB).where(where).order_by(TaskReviewDB.updated_at.desc())
        stmt = stmt.offset(offset).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        categories = sorted({row[0] for row in (await session.execute(
            select(distinct(TaskReviewDB.category))
        )).all() if row[0]})
    return {"records": [_db_record_to_dict(row) for row in rows],
            "total": total, "categories": categories}


def load_review(review_id):
    if _use_db():
        from app.db.sync_bridge import run_db

        return run_db(_db_load_review(review_id))
    path = review_path(review_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


async def _db_load_reviews(review_ids: list[str]) -> dict[str, dict]:
    from sqlalchemy import select

    from app.db.models.task_review_db import TaskReviewDB
    from app.db.sync_bridge import bridge_session

    if not review_ids:
        return {}
    async with bridge_session() as session:
        rows = (await session.execute(
            select(TaskReviewDB).where(TaskReviewDB.review_id.in_(review_ids))
        )).scalars().all()
        return {row.review_id: _db_record_to_dict(row) for row in rows}


def load_reviews(review_ids) -> dict:
    """Batch load review records by ID; missing IDs are absent from the result."""
    ids = [rid for rid in review_ids if rid]
    if not ids:
        return {}
    if _use_db():
        from app.db.sync_bridge import run_db

        return run_db(_db_load_reviews(ids))
    result = {}
    for rid in ids:
        try:
            record = load_review(rid)
        except ValueError:
            continue
        if record is not None:
            result[rid] = record
    return result


def save_review(review):
    if _use_db():
        from app.db.sync_bridge import run_db

        run_db(_db_save_review(review))
        return
    path = review_path(review["review_id"])
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(review, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def list_reviews(*, pending_only=True, category=None, task_id=None, limit=None, offset=0):
    if _use_db():
        from app.db.sync_bridge import run_db

        return run_db(_db_list_reviews(pending_only=pending_only, category=category,
                                       task_id=task_id, limit=limit, offset=offset))
    records = [json.loads(path.read_text(encoding="utf-8")) for path in reviews_dir().glob("*.json")]
    filtered = sorted((record for record in records
                       if (not pending_only or record["status"] in {"pending_review", "in_disposal"})
                       and (category is None or record["category"] == category)
                       and (task_id is None or record["task_id"] == task_id)),
                      key=lambda item: item["updated_at"], reverse=True)
    return filtered if limit is None else filtered[offset:offset + limit]


def count_reviews(*, pending_only=True, category=None, task_id=None) -> int:
    return len(list_reviews(pending_only=pending_only, category=category, task_id=task_id))


def list_categories() -> list[str]:
    if _use_db():
        from app.db.sync_bridge import run_db

        return run_db(_db_list_categories())
    return sorted({record["category"] for record in list_reviews(pending_only=False)})


def list_reviews_payload(*, pending_only=True, category=None, limit=100, offset=0) -> dict:
    if _use_db():
        from app.db.sync_bridge import run_db

        return run_db(_db_list_reviews_payload(pending_only=pending_only, category=category,
                                               limit=limit, offset=offset))
    records = list_reviews(pending_only=pending_only, category=category)
    return {"records": records[offset:offset + limit], "total": len(records), "categories": list_categories()}


def has_active_review(task_id, subject_id):
    if _use_db():
        from app.db.sync_bridge import run_db

        return run_db(_db_has_active_review(task_id, subject_id))
    return any(record["subject_id"] == subject_id for record in list_reviews(task_id=task_id))


def pending_feedback_reviews() -> list[dict]:
    if _use_db():
        from app.db.sync_bridge import run_db

        return run_db(_db_pending_feedback_reviews())
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(reviews_dir().glob("*.json"))]


def submit_review(payload, source):
    submission = ReviewSubmission.model_validate(payload).model_dump(mode="json")
    if not source.get("task_id") or not source.get("execution_id"):
        raise ValueError("提交审核结果需要真实任务执行上下文")
    if source.get("review_subject_bound"):
        expected = source.get("expected_subject_id")
        if not expected or submission["subject_id"] != expected or submission.get("event_id") != expected:
            raise ValueError("subject_id 和 event_id 必须匹配本次任务绑定的业务编号")
    from app.scheduled_tasks.models.review_requirements import validate_review_result
    validate_review_result(submission, source.get("result_requirements", []))
    from app.utils.path_config import format_agent_path, is_path_within, resolve_agent_path
    for evidence in submission["evidence"]:
        path = resolve_agent_path(evidence["path"])
        if not is_path_within(path, [get_data_registry()]) or not path.is_file():
            raise ValueError("证据文件必须存在于当前项目数据目录")
        evidence["path"] = format_agent_path(path)
    review_id = "review_" + hashlib.sha256(json.dumps(
        [source["task_id"], submission["subject_id"]], ensure_ascii=False).encode()).hexdigest()[:32]
    with review_lock(review_id):
        previous = load_review(review_id)
        if previous and previous["execution_id"] == source["execution_id"]:
            if previous["submission"] == submission:
                return previous
            raise ValueError("本轮已提交；修改结论须启动新一轮任务，禁止覆盖人工审核依据")
        allow_reopen = source.get("allow_archived_review_reopen", True) and (
            previous.get("allow_archived_review_reopen", True) if previous else True
        )
        if previous and previous["status"] == "archived" and not allow_reopen:
            raise ValueError("已归档审核记录不允许 AI 重新提交")
        now = datetime.now().astimezone().isoformat()
        history = previous["history"] if previous else []
        if previous:
            history = [*history, {key: value for key, value in previous.items() if key != "history"}]
        record = {
            **submission, "submission": submission, "review_id": review_id,
            "task_id": source["task_id"], "task_name": source.get("task_name", source["task_id"]),
            "execution_id": source["execution_id"], "status": "pending_review",
            "version": previous["version"] + 1 if previous else 1,
            "created_at": previous["created_at"] if previous else now,
            "updated_at": now, "history": history,
            "allow_archived_review_reopen": allow_reopen,
        }
        save_review(record)
        return record


def decide_review(review_id, payload, actor):
    decision = HumanDecision.model_validate(payload).model_dump(mode="json")
    with review_lock(review_id):
        record = load_review(review_id)
        if record is None:
            raise KeyError(review_id)
        if record["version"] != decision["version"]:
            raise ValueError("结果已更新，请刷新后审核")
        allowed = {"pending_review": {"confirm", "reject", "start_disposal"}, "in_disposal": {"complete", "reject"}}
        if decision["action"] not in allowed.get(record["status"], set()):
            raise ValueError("当前状态不允许此操作")
        if decision["action"] in {"confirm", "complete"}:
            exclusions = any(item["decision"] in {"exclude", "partial_exclude"}
                             for item in [*record["data_impact"], *decision["data_impact"]])
            if exclusions and not decision["intervals_confirmed"]:
                raise ValueError("涉及数据剔除，必须人工核验时间区间与合理性")
        now = datetime.now().astimezone().isoformat()
        record["status"] = {"confirm": "archived", "reject": "rejected", "start_disposal": "in_disposal", "complete": "archived"}[decision["action"]]
        record["human_decision"] = {**decision, "actor": actor, "occurred_at": now}
        record.setdefault("operations", []).append(record["human_decision"])
        record["updated_at"] = now
        record["version"] += 1
        if decision["action"] != "start_disposal":
            record["human_feedback"] = {
                "feedback_id": f"human_{review_id}_{record['version']}", "task_id": record["task_id"],
                "review_id": review_id, "event_id": record.get("event_id"),
                "subject_id": record["subject_id"], "occurred_at": now, "actor": actor,
                "comment": decision["comment"], "ai": record["submission"], "human": decision,
                "status": "pending", "attempts": 0,
            }
        save_review(record)
        if decision["action"] == "reject":
            # 智能事件人工退回后自动触发以审核意见为基准的增量 AI 研判；
            # 钩子内部自行隔离异常，退回动作本身永不因此失败。
            try:
                from app.services.jiangsu_smart_event import queue_review_reject_rerun

                queue_review_reject_rerun(record, decision, actor)
            except Exception as exc:
                logger.warning("smart_event_review_reject_rerun_hook_failed", error=str(exc))
            # 故障工单审核退回后同样排队一次以人工意见为基准的增量复审，
            # 由 worker 侧 jiangsu_fault_work_order_review_rerun 抓取器派发。
            try:
                from app.services.jiangsu_fault_work_order_review_rerun import (
                    queue_fault_work_order_review_rerun,
                )

                queue_fault_work_order_review_rerun(record, decision, actor)
            except Exception as exc:
                logger.warning(
                    "fault_work_order_review_reject_rerun_hook_failed", error=str(exc),
                )
        return record


def review_visual(record):
    return {"id": f"task_review_{record['review_id']}", "type": "task_review",
            "title": record["title"], "data": {"review_id": record["review_id"]},
            "meta": {"generator": "submit_task_review", "review_id": record["review_id"], "visual_behavior": "task_review"}}
