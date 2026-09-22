"""故障工单审核证据包持久化。

参照智能事件证据包的存储模式（jiangsu_smart_event_store）：每个工单一个内容寻址
证据目录（index.json + sources/<name>.json），manifest 只保存轻量索引行，避免把
全部证据塞进单个大 JSON。AI 研判结论（task_reviews）与人工操作（反馈/归档/退回）
回写到证据包并更新状态。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from app.utils.path_config import format_agent_path, resolve_agent_path

SCHEMA = "jiangsu_work_order_reviews/v1"
EVIDENCE_INDEX_NAME = "index.json"
SOURCE_NAME_PATTERN = re.compile(r"^[0-9A-Za-z_.-]{1,64}$")

_SOURCE_ORDER = ("work_order", "station_hour", "band", "weather", "alarms", "env_power", "qc")

_DECISION_STATUS = {
    "pass": "待归档",
    "approve": "待归档",
    "confirm": "待归档",
    "needs_evidence": "待补证",
    "reject": "已退回",
}
_HUMAN_ACTION_STATUS = {
    "confirm": "已归档",
    "complete": "已归档",
    "reject": "已退回",
    "start_disposal": "处置中",
    "archive": "已归档",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _orders_root():
    from app.utils.path_config import get_data_registry

    return (get_data_registry() / "jiangsu_work_order_reviews").resolve()


def _order_hash(code: str) -> str:
    return hashlib.sha256(str(code).encode("utf-8")).hexdigest()[:24]


def _store_path() -> Any:
    return _orders_root() / "store.json"


@contextmanager
def _store_lock():
    root = _orders_root()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".store.lock"
    with open(lock_path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"schema_version": SCHEMA, "orders": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema_version": SCHEMA, "orders": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("orders"), dict):
        return {"schema_version": SCHEMA, "orders": {}}
    return payload


def _save_store(store: dict[str, Any]) -> None:
    from app.services.jiangsu_smart_event_store import atomic_json

    atomic_json(_store_path(), store)


def _normalise_sources(sources: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    normalised: dict[str, dict[str, Any]] = {}
    for name, payload in (sources or {}).items():
        key = str(name or "").strip()
        if not key or not SOURCE_NAME_PATTERN.match(key) or not isinstance(payload, dict):
            continue
        entry = {k: v for k, v in payload.items() if k != "data"}
        entry["record_count"] = int(payload.get("record_count") or 0)
        if "data" in payload:
            entry["data"] = payload["data"]
        normalised[key] = entry
    for name in _SOURCE_ORDER:
        normalised.setdefault(name, {"status": "skipped", "record_count": 0, "summary": "未采集"})
    return normalised


def _entry_from_package(package: dict[str, Any], index_path: Any) -> dict[str, Any]:
    sources = package.get("sources") if isinstance(package.get("sources"), dict) else {}
    return {
        "working_order_code": package.get("working_order_code"),
        "title": package.get("title"),
        "site_name": package.get("site_name"),
        "site_id": package.get("site_id"),
        "pollutant": package.get("pollutant"),
        "window_start": package.get("window", {}).get("start_time") if isinstance(package.get("window"), dict) else None,
        "window_end": package.get("window", {}).get("end_time") if isinstance(package.get("window"), dict) else None,
        "status": package.get("status") or "待审核",
        "decision": package.get("judgment", {}).get("decision") if isinstance(package.get("judgment"), dict) else None,
        "review_id": package.get("judgment", {}).get("review_id") if isinstance(package.get("judgment"), dict) else None,
        "collected_at": package.get("collected_at"),
        "updated_at": package.get("updated_at") or _now(),
        "source_counts": {
            name: int((source or {}).get("record_count") or 0)
            for name, source in sources.items()
        },
        "operations_count": len(package.get("operations") or []),
        "index_path": format_agent_path(index_path),
    }


def _write_package(package: dict[str, Any]) -> dict[str, Any]:
    """内容寻址落盘证据包，返回 (manifest 行, index 路径, 各 source 文件路径)。"""
    from app.services.jiangsu_smart_event_store import write_package_dir

    folder = _orders_root() / "orders" / _order_hash(str(package.get("working_order_code")))
    index_path = write_package_dir(folder, package)
    sources_dir = index_path.parent / "sources"
    source_files = {
        name: format_agent_path(sources_dir / f"{name}.json")
        for name in (package.get("sources") or {})
        if (sources_dir / f"{name}.json").exists()
    }
    entry = _entry_from_package(package, index_path)
    entry["source_files"] = source_files
    return entry


def _read_package(entry: dict[str, Any]) -> dict[str, Any]:
    from app.services.jiangsu_smart_event_store import read_package_file

    index_path = resolve_agent_path(entry.get("index_path"))
    if not index_path.exists():
        return {}
    return read_package_file(index_path)


def save_evidence(package: dict[str, Any]) -> dict[str, Any]:
    """采集完成后保存证据包；已有人工状态时不回退状态。"""
    code = str(package.get("working_order_code") or "").strip()
    if not code:
        raise ValueError("证据包缺少 working_order_code")
    package = dict(package)
    package["working_order_code"] = code
    package["schema_version"] = SCHEMA
    package["sources"] = _normalise_sources(package.get("sources"))
    package.setdefault("collected_at", _now())
    package.setdefault("operations", [])
    with _store_lock():
        store = _load_store()
        previous = store["orders"].get(code) or {}
        previous_package = _read_package(previous) if previous else {}
        # 重新采集保留既有 AI/人工状态与操作记录（存于上一个证据包），只刷新证据数据。
        if previous_package:
            for key in ("judgment", "operations"):
                if previous_package.get(key) is not None:
                    package[key] = previous_package[key]
        previous_status = previous.get("status")
        if previous_status:
            package["status"] = previous_status
        if not package.get("status"):
            package["status"] = "待审核"
        package["updated_at"] = _now()
        entry = _write_package(package)
        store["orders"][code] = entry
        _save_store(store)
    return entry


def _persist_package_update(code: str, mutate) -> dict[str, Any]:
    with _store_lock():
        store = _load_store()
        entry = store["orders"].get(code)
        if not entry:
            raise KeyError(code)
        package = _read_package(entry)
        if not package:
            raise KeyError(code)
        mutate(package)
        package["updated_at"] = _now()
        new_entry = _write_package(package)
        store["orders"][code] = new_entry
        _save_store(store)
        return new_entry


def attach_judgment(code: str, review: dict[str, Any]) -> dict[str, Any]:
    """AI 研判提交（submit_task_review）后回写证据包。"""

    def mutate(package: dict[str, Any]) -> None:
        submission = review.get("submission") if isinstance(review.get("submission"), dict) else review
        package["judgment"] = {
            "review_id": review.get("review_id"),
            "version": review.get("version"),
            "decision": submission.get("decision"),
            "decision_label": submission.get("decision_label"),
            "comment": submission.get("comment"),
            "data_impact": submission.get("data_impact") or [],
            "checks": submission.get("checks") or [],
            "title": review.get("title"),
            "summary": review.get("summary"),
            "judged_at": review.get("updated_at") or _now(),
        }
        decision = str(submission.get("decision") or "").lower()
        package["status"] = _DECISION_STATUS.get(decision, "待归档")

    return _persist_package_update(code, mutate)


def apply_human_decision(review: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """人工审核决策（task_reviews.decide_review）后回写证据包。"""
    code = str(review.get("subject_id") or "").strip()
    action = str(decision.get("action") or "").lower()

    def mutate(package: dict[str, Any]) -> None:
        package["status"] = _HUMAN_ACTION_STATUS.get(action, package.get("status") or "待审核")
        package.setdefault("operations", []).append({
            "action": action,
            "label": {"confirm": "归档", "complete": "处置完成", "reject": "退回",
                      "start_disposal": "转入处置"}.get(action, action),
            "comment": decision.get("comment") or "",
            "actor": decision.get("actor"),
            "at": _now(),
            "source": "task_review_decision",
        })

    return _persist_package_update(code, mutate) if code else {}


def record_operation(code: str, action: str, comment: str = "", actor: dict[str, Any] | None = None,
                     *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """记录用户在审核工作台执行的操作（反馈/归档/退回等）。"""
    action = str(action or "").strip().lower()
    if action not in {"feedback", "archive", "reject", "reopen"}:
        raise ValueError(f"不支持的操作：{action}")

    def mutate(package: dict[str, Any]) -> None:
        package.setdefault("operations", []).append({
            "action": action,
            "label": {"feedback": "反馈", "archive": "归档", "reject": "退回", "reopen": "重新打开"}[action],
            "comment": str(comment or "")[:2000],
            "actor": actor or {},
            "at": _now(),
            "source": "review_workspace",
            **(extra or {}),
        })
        if action in _HUMAN_ACTION_STATUS:
            package["status"] = _HUMAN_ACTION_STATUS[action]
        elif action == "feedback" and not package.get("judgment"):
            package["status"] = "待审核"

    return _persist_package_update(code, mutate)


def list_orders(limit: int = 50, offset: int = 0, status: str | None = None,
                keyword: str | None = None) -> dict[str, Any]:
    with _store_lock():
        store = _load_store()
        entries = list(store["orders"].values())
    keyword_text = str(keyword or "").strip().casefold()
    rows = []
    for entry in entries:
        if status and entry.get("status") != status:
            continue
        if keyword_text:
            haystack = " ".join(str(entry.get(key) or "") for key in
                                ("working_order_code", "title", "site_name", "pollutant")).casefold()
            if keyword_text not in haystack:
                continue
        rows.append(entry)
    rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    total = len(rows)
    return {"orders": rows[offset:offset + limit], "total": total,
            "statuses": sorted({str(entry.get("status") or "") for entry in entries if entry.get("status")})}


def get_order(code: str) -> dict[str, Any]:
    with _store_lock():
        store = _load_store()
        entry = store["orders"].get(str(code or "").strip())
    if not entry:
        raise KeyError(code)
    package = _read_package(entry)
    index = {k: v for k, v in package.items() if k != "sources"}
    index["sources"] = {
        name: {k: v for k, v in (source or {}).items() if k != "data"}
        for name, source in (package.get("sources") or {}).items()
    }
    return {"entry": {k: v for k, v in entry.items() if k != "source_files"}, "index": index}


def get_order_source(code: str, name: str) -> dict[str, Any]:
    name = str(name or "").strip()
    if not SOURCE_NAME_PATTERN.match(name):
        raise ValueError("无效的来源名称")
    with _store_lock():
        store = _load_store()
        entry = store["orders"].get(str(code or "").strip())
    if not entry:
        raise KeyError(code)
    source_path = resolve_agent_path(entry.get("index_path")).parent / "sources" / f"{name}.json"
    if not source_path.exists():
        raise KeyError(f"{code}/{name}")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    return {"source": name, "data": payload.get("data"),
            "meta": {k: v for k, v in payload.items() if k != "data"}}


def sync_review_record(review: dict[str, Any], decision: dict[str, Any] | None = None) -> None:
    """task_review 生命周期钩子：AI 提交或人工决策后同步审核包。

    由 task_review.submit_review / decide_review 调用；异常由调用方隔离，
    不阻断审核主流程。
    """
    code = str(review.get("subject_id") or "").strip()
    if not code:
        return
    if decision is None:
        attach_judgment(code, review)
    else:
        apply_human_decision(review, decision)
