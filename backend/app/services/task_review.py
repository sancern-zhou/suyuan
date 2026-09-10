"""One validated hand-off and human-review lifecycle for all scheduled tasks."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.utils.path_config import get_data_registry


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
            if self.start >= self.end:
                raise ValueError("start 必须早于 end")
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


def reviews_dir() -> Path:
    path = get_data_registry() / "task_reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def review_path(review_id: str) -> Path:
    if not review_id.startswith("review_") or len(review_id) != 39 or any(c not in "0123456789abcdef" for c in review_id[7:]):
        raise ValueError("invalid_review_id")
    return reviews_dir() / f"{review_id}.json"


def load_review(review_id):
    path = review_path(review_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_review(review):
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


@contextmanager
def review_lock(review_id):
    with review_path(review_id).with_suffix(".lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def list_reviews(*, pending_only=True, category=None, task_id=None):
    records = [json.loads(path.read_text(encoding="utf-8")) for path in reviews_dir().glob("*.json")]
    return sorted((record for record in records
                   if (not pending_only or record["status"] in {"pending_review", "in_disposal"})
                   and (category is None or record["category"] == category)
                   and (task_id is None or record["task_id"] == task_id)),
                  key=lambda item: item["updated_at"], reverse=True)


def has_active_review(task_id, subject_id):
    return any(record["subject_id"] == subject_id for record in list_reviews(task_id=task_id))


def submit_review(payload, source):
    submission = ReviewSubmission.model_validate(payload).model_dump(mode="json")
    if not source.get("task_id") or not source.get("execution_id"):
        raise ValueError("提交审核结果需要真实任务执行上下文")
    from app.utils.path_config import resolve_agent_path, is_path_within, format_agent_path
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
        return record


def review_visual(record):
    return {"id": f"task_review_{record['review_id']}", "type": "task_review",
            "title": record["title"], "data": {"review_id": record["review_id"]},
            "meta": {"generator": "submit_task_review", "review_id": record["review_id"], "visual_behavior": "task_review"}}
