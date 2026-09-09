"""Jiangsu smart-event domain adapter.

The upstream smart-event and rule APIs are still evolving.  This module keeps
the application contract stable and currently builds pending events from the
already available Jiangsu alarm API.  A future platform adapter can replace
the source without changing route or frontend payloads.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config.config_manager import config_manager
from app.tools.jiangsu.alarm_records import JiangsuAlarmRecordsTool
from app.utils.path_config import get_data_registry
from app.scheduled_tasks.models import ExecutionStatus, TaskEvent


AI_EVENT_TYPES = (
    "疑似雾炮喷淋",
    "疑似人员进入采样区干扰操作",
    "疑似仪器故障",
    "疑似外界环境影响",
    "疑似站房停电",
    "疑似公共系统异常",
    "疑似站房环境影响",
    "合规运维核查",
    "数据异常待研判",
    "其他待人工复核",
)

SMART_EVENT_TRIGGER_TYPES = {
    "供电报警": "jiangsu.smart_event.alarm.power",
    "数采网络报警": "jiangsu.smart_event.alarm.network",
    "站房环境报警": "jiangsu.smart_event.alarm.environment",
    "仪器报警": "jiangsu.smart_event.alarm.instrument",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "event_merge_window_minutes": 60,
    "event_before_extend_minutes": 30,
    "event_after_extend_minutes": 30,
    "video_tag_confidence_threshold": 0.7,
    "station_missing_factor_threshold": 2,
    "station_missing_duration_minutes": 5,
    "multi_instrument_threshold": 2,
    "single_instrument_missing_duration_minutes": 5,
    "initial_naming_priority": [
        "人员进入采样区",
        "雾炮喷淋",
        "供电断数",
        "公共系统报警",
        "站房环境",
        "仪器报警",
        "超限报警",
        "数据异常",
    ],
    "ai_event_type_dictionary": list(AI_EVENT_TYPES),
    "data_anomaly_threshold_pct": 20,
    "pm_rise_threshold_pct": 20,
}


class SmartEventUpstreamError(RuntimeError):
    """Raised when the current upstream alarm source cannot be queried."""


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%m/%d/%Y %I:%M:%S %p",
        ):
            try:
                parsed = datetime.strptime(str(value).strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _format_time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _stable_id(record: dict[str, Any]) -> str:
    raw = _first(record, "id", "alarmId", "callId", "uniqueCode")
    if raw not in (None, ""):
        return f"alarm:{raw}"
    material = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return f"alarm:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"


def _alarm_label(record: dict[str, Any]) -> tuple[str, str]:
    text = str(_first(record, "content", "alarmContent", "description") or "平台告警")
    classification_text = " ".join(
        str(record.get(key) or "") for key in ("content", "alarmContent", "description", "ddRuleType", "callType")
    )
    lower = classification_text.lower()
    if "ups" in lower or "电源" in classification_text or "供电" in classification_text:
        return "供电报警", "供电/UPS"
    if any(word in classification_text for word in ("网络", "通讯", "通信", "数采", "断数", "离线", "上传")):
        return "数采网络报警", "数采/网络"
    if any(word in classification_text for word in ("温度", "湿度", "空调", "除湿", "通风")):
        return "站房环境报警", "站房环境"
    return "仪器报警", str(_first(record, "deviceName", "device", "objectName") or text[:80] or "告警对象")


def normalize_alarm_event(record: dict[str, Any]) -> dict[str, Any]:
    """Map one platform alarm row to the V3 pending-event contract."""

    event_id = _stable_id(record)
    site_id = str(_first(record, "code", "stacode", "stationCode", "station_code", "uniqueCode") or "").strip()
    site_name = str(_first(record, "stationName", "positionName", "name", "siteName") or site_id or "未知站点").strip()
    occurred = _parse_time(_first(record, "alarmtime", "alarmTime", "timePoint", "createTime", "occurredAt"))
    ended = _parse_time(_first(record, "alarmendtime", "alarmEndTime", "endTime", "resolvedAt")) or occurred
    start = _format_time(occurred)
    end = _format_time(ended)
    label, obj = _alarm_label(record)
    tag = {
        "tag_id": f"{event_id}:alarm",
        "tag_source": "子站报警",
        "tag_category": "报警",
        "tag_name": label,
        "tag_object": obj,
        "tag_start_time": start,
        "tag_end_time": start,
        "tag_confidence": None,
        "clue_id": str(_first(record, "id", "alarmId", "callId") or event_id),
        "tag_display_text": f"报警：{label}",
    }
    initial_name = f"{site_name}{label}线索待研判事件"
    return {
        "event_id": event_id,
        "site_id": site_id,
        "site_name": site_name,
        "city_name": _first(record, "cityName", "city", "city_name"),
        "district_name": _first(record, "districtName", "district", "district_name"),
        "event_start_time": start,
        "event_end_time": end,
        "initial_event_name": initial_name,
        "event_name": initial_name,
        "event_status": "未研判",
        "event_type": "待 AI 研判",
        "source_alarm_state": _first(record, "ddalarmstateName", "ddalarmstate", "alarmState"),
        "event_trigger_type": SMART_EVENT_TRIGGER_TYPES[label],
        "clue_tags": [tag],
        "primary_clue_tag": label,
        "clue_count": 1,
        "ai_event_type": None,
        "ai_event_name": None,
        "ai_data_impact": "待确认",
        "ai_suggested_level": None,
        "ai_diagnosis_note": None,
        "manual_final_event_type": None,
        "manual_final_level": None,
        "archived": False,
        "operation_records": [],
        "evidence": {"alarm": record},
        "source": "alarm_adapter",
    }


class JiangsuSmartEventService:
    """Application service for the staged smart-event integration."""

    def __init__(self, alarm_tool: JiangsuAlarmRecordsTool | None = None, *, data_root: Path | None = None):
        self.alarm_tool = alarm_tool or JiangsuAlarmRecordsTool()
        self.data_root = data_root or get_data_registry()

    @property
    def config_path(self) -> Path:
        return self.data_root / "jiangsu_smart_events" / "config.json"

    @property
    def store_path(self) -> Path:
        return self.data_root / "jiangsu_smart_events" / "store.json"

    def _load_store(self) -> dict[str, Any]:
        if self.store_path.is_file():
            try:
                value = json.loads(self.store_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    value.setdefault("events", [])
                    value.setdefault("tasks", [])
                    return value
            except (OSError, ValueError):
                pass
        return {"schema_version": "jiangsu_smart_events/v1", "events": [], "tasks": []}

    def _save_store(self, store: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.store_path.name}.", suffix=".tmp", dir=self.store_path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(store, handle, ensure_ascii=False, indent=2, default=str)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.store_path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _filter_events(
        events: list[dict[str, Any]], *, status: str | None, keyword: str | None, limit: int
    ) -> list[dict[str, Any]]:
        filtered = events
        if status:
            filtered = [item for item in filtered if item.get("event_status") == status]
        if keyword:
            needle = keyword.strip().lower()
            filtered = [item for item in filtered if needle in json.dumps(item, ensure_ascii=False).lower()]
        return filtered[:limit]

    async def _fetch_alarm_events(
        self,
        *,
        start_time: str,
        end_time: str,
        station_codes: list[str] | None,
        limit: int,
    ) -> dict[str, Any]:
        result = await self.alarm_tool.execute(
            station_codes=station_codes,
            station_type="省控" if not station_codes else None,
            start_time=start_time,
            end_time=end_time,
            max_result_count=min(limit, 100),
            sorting="timePoint",
        )
        if not result.get("success"):
            raise SmartEventUpstreamError(str(result.get("summary") or "告警接口查询失败"))
        events = [normalize_alarm_event(row) for row in result.get("data", []) if isinstance(row, dict)]
        if not station_codes:
            for event in events:
                event["station_type"] = "省控"
        return {
            "events": events,
            "source_metadata": result.get("metadata") or {},
        }

    def _create_ai_task(self, event: dict[str, Any], *, actor: dict[str, Any] | None = None) -> dict[str, Any]:
        now = datetime.now().astimezone().isoformat()
        task_id = f"task:{uuid4().hex}"
        return {
            "task_id": task_id,
            "event_id": event["event_id"],
            "task_type": "ai_judgment",
            "scheduled_task_id": f"jiangsu_smart_event_{self._task_suffix(event)}_alarm",
            "event_type": event.get("primary_clue_tag"),
            "event_trigger_type": event.get("event_trigger_type"),
            "title": f"AI研判：{event.get('event_name') or event.get('initial_event_name')}",
            "status": "待执行",
            "conversation_id": f"conversation:{uuid4().hex}",
            "created_at": now,
            "updated_at": now,
            "created_by": actor or {"user_id": "system", "username": "system"},
            "context": {
                "event_id": event["event_id"],
                "event_name": event.get("event_name"),
                "clue_tags": event.get("clue_tags", []),
            },
        }

    @staticmethod
    def _task_suffix(event: dict[str, Any]) -> str:
        trigger = str(event.get("event_trigger_type") or "").rsplit(".", 1)[-1]
        return {"power": "power", "network": "network", "environment": "environment"}.get(
            trigger, "instrument"
        )

    def _upsert_events(
        self, incoming: list[dict[str, Any]], *, actor: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        store = self._load_store()
        existing = {str(item.get("event_id")): item for item in store.get("events", []) if isinstance(item, dict)}
        tasks = [item for item in store.get("tasks", []) if isinstance(item, dict)]
        created_tasks: list[dict[str, Any]] = []
        now = datetime.now().astimezone().isoformat()
        for candidate in incoming:
            event_id = str(candidate["event_id"])
            current = existing.get(event_id)
            if current is None:
                candidate["created_at"] = now
                candidate["updated_at"] = now
                current = candidate
                existing[event_id] = current
            else:
                for field in (
                    "site_id", "site_name", "event_start_time", "event_end_time",
                    "source_alarm_state", "primary_clue_tag", "event_trigger_type",
                ):
                    if candidate.get(field) not in (None, ""):
                        current[field] = candidate[field]
                current["event_end_time"] = candidate.get("event_end_time") or current.get("event_end_time")
                current["evidence"] = candidate.get("evidence") or current.get("evidence", {})
                current["updated_at"] = now
                old_tags = {item.get("tag_id"): item for item in current.get("clue_tags", [])}
                old_tags.update({item.get("tag_id"): item for item in candidate.get("clue_tags", [])})
                current["clue_tags"] = list(old_tags.values())
                current["clue_count"] = len(current["clue_tags"])
            has_ai_task = any(
                item.get("event_id") == event_id
                and item.get("task_type") == "ai_judgment"
                for item in tasks
            )
            if not has_ai_task:
                task = self._create_ai_task(current, actor=actor)
                tasks.append(task)
                created_tasks.append(task)
        store["events"] = list(existing.values())
        store["tasks"] = tasks
        store["updated_at"] = now
        self._save_store(store)
        return store, created_tasks

    async def _dispatch_pending_tasks(
        self, store: dict[str, Any], *, wait: bool = False
    ) -> list[dict[str, Any]]:
        """Publish smart events to the real event-triggered task service."""

        try:
            from app.scheduled_tasks import get_scheduled_task_service

            task_service = get_scheduled_task_service()
        except (RuntimeError, ImportError) as exc:
            return [{"status": "not_dispatched", "reason": str(exc)}]

        events = {item.get("event_id"): item for item in store.get("events", [])}
        outcomes: list[dict[str, Any]] = []
        changed = False
        for card in store.get("tasks", []):
            if card.get("task_type") != "ai_judgment" or card.get("status") not in {"待执行", "待调度"}:
                continue
            event = events.get(card.get("event_id"))
            if not event or not event.get("event_trigger_type"):
                continue
            task_event = TaskEvent(
                event_id=str(event["event_id"]),
                event_type=str(event["event_trigger_type"]),
                occurred_at=_parse_time(event.get("event_start_time")) or datetime.now().astimezone(),
                attributes={
                    "smart_event_id": event["event_id"],
                    "smart_event_type": event.get("primary_clue_tag"),
                    "site_id": event.get("site_id"),
                    "site_name": event.get("site_name"),
                },
                payload={"smart_event": event},
            )
            try:
                dispatch = await task_service.publish_event(task_event, wait=wait)
                if wait and dispatch.execution_ids:
                    # The completion hook may already have written a terminal
                    # status and final reply while publish_event was awaited.
                    latest = self._load_store()
                    latest_card = next(
                        (item for item in latest.get("tasks", []) if item.get("task_id") == card.get("task_id")),
                        None,
                    )
                    if latest_card:
                        card.clear()
                        card.update(latest_card)
                else:
                    card["status"] = "执行中" if dispatch.accepted_task_ids else card.get("status", "待执行")
                card["dispatch_status"] = "accepted" if dispatch.accepted_task_ids else "duplicate_or_unmatched"
                card["scheduled_task_ids"] = list(dispatch.accepted_task_ids or dispatch.matched_task_ids)
                card["execution_ids"] = list(dispatch.execution_ids)
                card["updated_at"] = datetime.now().astimezone().isoformat()
                changed = True
                outcomes.append({"event_id": event["event_id"], **dispatch.model_dump(mode="json")})
            except Exception as exc:  # noqa: BLE001 - keep the event visible for retry
                card["dispatch_status"] = "failed"
                card["dispatch_error"] = str(exc)
                card["updated_at"] = datetime.now().astimezone().isoformat()
                changed = True
                outcomes.append({"event_id": event["event_id"], "status": "failed", "error": str(exc)})
        if changed:
            store["updated_at"] = datetime.now().astimezone().isoformat()
            self._save_store(store)
        return outcomes

    async def sync_alarm_events(
        self,
        *,
        start_time: str,
        end_time: str,
        station_codes: list[str] | None = None,
        actor: dict[str, Any] | None = None,
        limit: int = 100,
        wait_for_ai: bool = False,
        dispatch_ai: bool = True,
    ) -> dict[str, Any]:
        fetched = await self._fetch_alarm_events(
            start_time=start_time, end_time=end_time, station_codes=station_codes, limit=limit
        )
        store, created_tasks = self._upsert_events(fetched["events"], actor=actor)
        dispatches = await self._dispatch_pending_tasks(store, wait=wait_for_ai) if dispatch_ai else []
        store["last_sync"] = {
            "source": "alarm_adapter",
            "station_type": "省控" if not station_codes else None,
            "event_count": len(fetched["events"]),
            "source_metadata": fetched["source_metadata"],
            "synced_at": datetime.now().astimezone().isoformat(),
        }
        self._save_store(store)
        return {
            "events": fetched["events"],
            "stored_event_count": len(store.get("events", [])),
            "created_tasks": created_tasks,
            "dispatches": dispatches,
            "ai_dispatch_skipped": not dispatch_ai,
            "source_metadata": fetched["source_metadata"],
        }

    async def list_events(
        self,
        *,
        start_time: str,
        end_time: str,
        station_codes: list[str] | None = None,
        status: str | None = None,
        keyword: str | None = None,
        limit: int = 100,
        refresh: bool = True,
    ) -> dict[str, Any]:
        upstream_error: str | None = None
        if refresh:
            try:
                await self.sync_alarm_events(
                    start_time=start_time,
                    end_time=end_time,
                    station_codes=station_codes,
                    limit=limit,
                    dispatch_ai=False,
                )
            except SmartEventUpstreamError as exc:
                upstream_error = str(exc)
        store = self._load_store()
        if upstream_error and not store.get("events"):
            raise SmartEventUpstreamError(upstream_error)
        events = self._filter_events(
            [item for item in store.get("events", []) if isinstance(item, dict)],
            status=status,
            keyword=keyword,
            limit=limit,
        )
        return {
            "events": events,
            "total": len(events),
            "source": "alarm_adapter_store_stale" if upstream_error else "alarm_adapter_store",
            "source_metadata": {
                "store_path": str(self.store_path),
                "upstream_error": upstream_error,
                "last_sync": store.get("last_sync"),
            },
            "capabilities": {
                "platform_event_api": False,
                "alarm_adapter": True,
                "event_store": True,
                "task_cards": True,
                "upstream_available": upstream_error is None,
                "ai_judgment": True,
                "event_driven_tasks": True,
                "task_history_learning": True,
                "alarm_scope": "省控",
                "unscoped_upstream_query": True,
                "operations": True,
                "manual_confirmation": True,
                "archive_lock": True,
            },
        }

    async def get_event(self, event_id: str, **query: Any) -> dict[str, Any] | None:
        payload = await self.list_events(**query)
        return next((item for item in payload["events"] if item["event_id"] == event_id), None)

    def list_tasks(self, *, event_id: str | None = None, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        tasks = [item for item in self._load_store().get("tasks", []) if isinstance(item, dict)]
        if event_id:
            tasks = [item for item in tasks if item.get("event_id") == event_id]
        if status:
            tasks = [item for item in tasks if item.get("status") == status]
        return tasks[:limit]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list_tasks(limit=1000) if item.get("task_id") == task_id), None)

    @staticmethod
    def _stored_event(store: dict[str, Any], event_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in store.get("events", []) if isinstance(item, dict) and item.get("event_id") == event_id),
            None,
        )

    @staticmethod
    def _append_operation(
        event: dict[str, Any], *, action: str, actor: dict[str, Any], summary: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "operation_id": f"operation:{uuid4().hex}",
            "action": action,
            "summary": summary,
            "actor": actor,
            "created_at": datetime.now().astimezone().isoformat(),
            "details": details or {},
        }
        event.setdefault("operation_records", []).append(record)
        return record

    @staticmethod
    def _ensure_not_archived(event: dict[str, Any]) -> None:
        if event.get("archived") is True or event.get("event_status") == "已归档":
            raise ValueError("smart_event_archived")

    def submit_ai_judgment(
        self, event_id: str, payload: dict[str, Any], *, actor: dict[str, Any]
    ) -> dict[str, Any]:
        """Save a structured human confirmation of the Agent judgment."""

        store = self._load_store()
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        event_type = str(payload.get("event_type") or payload.get("ai_event_type") or "").strip()
        if not event_type:
            raise ValueError("event_type_required")
        confirmed = bool(payload.get("confirmed", False))
        now = datetime.now().astimezone().isoformat()
        manual = {
            "event_type": event_type,
            "event_name": str(payload.get("event_name") or "").strip() or None,
            "level": str(payload.get("level") or payload.get("suggested_level") or "").strip() or None,
            "data_impact": payload.get("data_impact"),
            "diagnosis_note": str(payload.get("diagnosis_note") or "").strip() or None,
            "confirmed": confirmed,
            "confirmed_at": now if confirmed else None,
            "confirmed_by": actor if confirmed else None,
        }
        event["manual_final_event_type"] = event_type if confirmed else None
        event["manual_final_level"] = manual["level"] if confirmed else None
        event["manual_confirmation"] = manual
        event["ai_event_type"] = event_type
        event["ai_suggested_level"] = manual["level"]
        if manual["event_name"] and confirmed:
            event["event_name"] = manual["event_name"]
        if manual["data_impact"] is not None:
            event["ai_data_impact"] = manual["data_impact"]
        if manual["diagnosis_note"]:
            event["ai_diagnosis_note"] = manual["diagnosis_note"]
        event["event_status"] = "已确认" if confirmed else "待人工确认"
        event["updated_at"] = now
        self._append_operation(
            event,
            action="confirm_ai_judgment" if confirmed else "save_ai_judgment_draft",
            actor=actor,
            summary="人工确认 AI 研判结果" if confirmed else "保存 AI 研判确认草稿",
            details={"event_type": event_type, "level": manual["level"]},
        )
        store["updated_at"] = now
        self._save_store(store)
        return event

    def record_operation(
        self, event_id: str, *, action: str, summary: str, actor: dict[str, Any],
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        store = self._load_store()
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        record = self._append_operation(event, action=action, actor=actor, summary=summary, details=details)
        now = datetime.now().astimezone().isoformat()
        event["updated_at"] = now
        store["updated_at"] = now
        self._save_store(store)
        return record

    def archive_event(self, event_id: str, *, actor: dict[str, Any], comment: str | None = None) -> dict[str, Any]:
        store = self._load_store()
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        if not (event.get("manual_confirmation") or {}).get("confirmed"):
            raise ValueError("smart_event_judgment_not_confirmed")
        now = datetime.now().astimezone().isoformat()
        event["archived"] = True
        event["event_status"] = "已归档"
        event["archived_at"] = now
        event["archived_by"] = actor
        event["archive_comment"] = str(comment or "").strip() or None
        self._append_operation(
            event,
            action="archive_event",
            actor=actor,
            summary="人工归档智能事件",
            details={"comment": event["archive_comment"]},
        )
        event["updated_at"] = now
        store["updated_at"] = now
        self._save_store(store)
        return event

    def create_task(self, event_id: str, *, actor: dict[str, Any] | None = None) -> dict[str, Any]:
        store = self._load_store()
        event = next((item for item in store.get("events", []) if item.get("event_id") == event_id), None)
        if event is None:
            raise KeyError(event_id)
        task = self._create_ai_task(event, actor=actor)
        store.setdefault("tasks", []).append(task)
        store["updated_at"] = datetime.now().astimezone().isoformat()
        self._save_store(store)
        return task

    def apply_task_execution(self, event_id: str, task: Any, execution: Any) -> None:
        """Persist the Agent's final reply back into the fixed event detail."""

        store = self._load_store()
        event = next((item for item in store.get("events", []) if item.get("event_id") == event_id), None)
        if event is None:
            return
        final_response = ""
        if getattr(execution, "steps", None):
            final_response = str(getattr(execution.steps[-1], "agent_response", "") or "")
        status = getattr(getattr(execution, "status", None), "value", getattr(execution, "status", ""))
        result = {
            "task_id": getattr(task, "task_id", None),
            "execution_id": getattr(execution, "execution_id", None),
            "task_name": getattr(task, "name", None),
            "status": status,
            "final_response": final_response,
            "completed_at": _format_time(getattr(execution, "completed_at", None)),
            "updated_at": datetime.now().astimezone().isoformat(),
        }
        event["ai_judgment"] = result
        event["ai_diagnosis_note"] = final_response or event.get("ai_diagnosis_note")
        event["event_status"] = "AI 已研判" if status == ExecutionStatus.SUCCESS.value else "AI 研判失败"
        event["updated_at"] = result["updated_at"]
        for card in store.get("tasks", []):
            if card.get("event_id") != event_id or card.get("task_type") != "ai_judgment":
                continue
            card["status"] = "已完成" if status == ExecutionStatus.SUCCESS.value else "执行失败"
            card["execution_id"] = result["execution_id"]
            card["final_response"] = final_response
            card["updated_at"] = result["updated_at"]
        store["updated_at"] = result["updated_at"]
        self._save_store(store)

    def load_config(self) -> dict[str, Any]:
        path = self.config_path
        if path.is_file():
            try:
                stored = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    return {**DEFAULT_CONFIG, **stored}
            except (OSError, ValueError):
                pass
        # Keep config-manager visible as a compatibility source for deployments
        # that already provision a matching section.
        section = config_manager.get_section("jiangsu_smart_event")
        if isinstance(section, dict):
            return {**DEFAULT_CONFIG, **section}
        return dict(DEFAULT_CONFIG)

    def save_config(self, values: dict[str, Any]) -> dict[str, Any]:
        config = {**DEFAULT_CONFIG, **values}
        config["version"] = int(config.get("version") or 1)
        config["ai_event_type_dictionary"] = [
            item for item in config["ai_event_type_dictionary"] if item in AI_EVENT_TYPES
        ] or list(AI_EVENT_TYPES)
        path = self.config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return config


async def persist_scheduled_task_result(task: Any, event: Any, execution: Any) -> None:
    """Scheduled-task result hook used by both the web process and worker."""

    if not str(getattr(event, "event_type", "")).startswith("jiangsu.smart_event."):
        return
    smart_event_id = getattr(event, "event_id", None) or getattr(event, "attributes", {}).get("smart_event_id")
    if not smart_event_id:
        return
    JiangsuSmartEventService().apply_task_execution(str(smart_event_id), task, execution)
