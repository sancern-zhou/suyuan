"""Durable Jiangsu event assessment, priority dispatch and delayed-clue polling."""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

AUTOMATION_DEFAULTS = {
    "auto_ai_enabled": True,
    "schedule_interval_minutes": 60,
    "rescan_lookback_hours": 24,
    "evidence_refresh_minutes": 60,
    "evidence_batch_size": 30,
    "ai_max_concurrency": 2,
    "ai_max_retries": 3,
    "ai_retry_delay_minutes": 5,
}


def parse_time(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else result.astimezone()
    except ValueError:
        return None


def is_human_review_continuation(card: dict) -> bool:
    """人工反馈/审核退回产生的增量卡：即使自动派发关闭也必须执行。

    ``_record_feedback`` 会把反馈写入 ``continuity.feedback``，这类卡代表
    明确的人工动作，不应被 ``auto_ai_enabled`` 阻塞。
    """
    continuity = card.get("continuity") if isinstance(card.get("continuity"), dict) else {}
    return bool(continuity.get("feedback"))


def evidence_signature(package):
    """Ignore collection timestamps; only changed evidence should start a new round."""
    def substantive(value):
        if isinstance(value, dict):
            return {key: substantive(item) for key, item in value.items()
                    if key not in {"metadata", "summary", "collected_at", "queried_at", "persisted_path"}}
        if isinstance(value, list):
            return [substantive(item) for item in value]
        return value
    sources = package.get("sources") or {}
    material = {key: {"status": value.get("status"), "data": substantive(value.get("data")),
                      "regional_deltas": value.get("regional_deltas")}
                for key, value in sources.items() if isinstance(value, dict)}
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def update_initial_assessment(event, package, detected_tags=None):
    tags = [tag for tag in event.get("clue_tags", []) if not tag.get("detected")]
    tags.extend(detected_tags or [])
    impact_tags = [tag for tag in tags if tag.get("tag_category") in {"数据", "断数"}
                   or tag.get("tag_source") in {"异常数据识别", "断数报警", "数据有效性异常"}
                   or any(word in str(tag.get("tag_name") or "")
                          for word in ("断数", "恒值", "负值", "无效值", "突升", "突降", "逻辑异常", "倒挂", "离群"))]
    monitoring = (package.get("sources") or {}).get("monitoring") or {}
    hour = (monitoring.get("data") or {}).get("station_hour") or {}
    query_ok = (hour.get("success") is True or hour.get("status") == "success") and bool(hour.get("data"))
    impact = "有数据影响" if impact_tags else ("无数据影响" if query_ok else "待确认")
    event["system_data_impact"] = impact
    event["data_impact"] = impact
    event["ai_task_priority"] = "urgent" if impact == "有数据影响" else "normal"
    event["data_impact_basis"] = {
        "clue_ids": [tag.get("tag_id") for tag in impact_tags],
        "monitoring_available": query_ok,
        "note": "命中数据异常或断数线索" if impact_tags else (
            "监测查询成功，未命中数据异常；超限本身不计为数据影响" if query_ok else "监测证据不足，数据影响待确认"),
    }
    update_impact_conflict(event)
    package["system_assessment"] = {key: event[key] for key in (
        "system_data_impact", "ai_task_priority", "data_impact_basis")}


def update_impact_conflict(event):
    system, ai = event.get("system_data_impact"), event.get("ai_data_impact")
    definitive = {"有数据影响", "无数据影响"}
    conflict = system in definitive and ai in definitive and system != ai
    event["data_impact_conflict"] = conflict
    event["data_impact_conflict_note"] = (
        f"系统初判为{system}，AI 判断为{ai}，请人工复核差异及依据。" if conflict else None)


def schedule_retry(card, config, *, error=None, now=None):
    now = now or datetime.now().astimezone()
    attempts = int(card.get("automatic_attempts") or 0)
    card["status"] = "执行失败"
    card["last_error"] = error or "AI 未成功提交有效研判结果"
    card["retry_exhausted"] = attempts >= 1 + int(config["ai_max_retries"])
    card["next_retry_at"] = None if card["retry_exhausted"] else (
        now + timedelta(minutes=int(config["ai_retry_delay_minutes"]) * 2 ** max(0, attempts - 1))
    ).isoformat()


class JiangsuSmartEventAutomation:
    def __init__(self, service, *, task_service=None):
        self.service = service
        self.task_service = task_service

    async def tick(self, *, now=None):
        now = now or datetime.now().astimezone()
        root = self.service.store_path.parent
        root.mkdir(parents=True, exist_ok=True)
        # Do not block the event loop if another worker owns the tick.
        with (root / ".automation.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "already_running"}
            return await self._tick(now)

    async def _tick(self, now):
        service = self.service
        config = service.load_config()
        store = await service.aload_store()
        state = store.get("automation") or {}
        last_scan = parse_time(state.get("last_scan_at"))
        retry_scan = parse_time(state.get("scan_retry_at"))
        scan_due = (not last_scan or now >= last_scan + timedelta(minutes=config["schedule_interval_minutes"]))
        results: dict[str, Any] = {"status": "success"}
        if scan_due and (not retry_scan or now >= retry_scan):
            start = min(now - timedelta(hours=config["rescan_lookback_hours"]),
                        now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1))
            actor = {"user_id": "system", "username": "smart-event-sync"}
            errors = []
            try:
                results["alarm_sync"] = await service.sync_alarm_events(
                    start_time=start.isoformat(), end_time=now.isoformat(), actor=actor,
                    dispatch_ai=False, fetch_evidence=False)
            except Exception as exc:
                errors.append(f"告警扫描：{exc}")
            days = sorted({(start + timedelta(days=i)).date().isoformat()
                           for i in range((now.date() - start.date()).days + 1)})
            results["compliance_sync"] = []
            for day in days:
                try:
                    results["compliance_sync"].append(await service.sync_compliance_clues(
                        date=day, actor=actor, fetch_evidence=False))
                except Exception as exc:
                    errors.append(f"合规扫描 {day}：{exc}")
            store = await service.aload_store()
            state = store.setdefault("automation", {})
            state["scan_window"] = [start.isoformat(), now.isoformat()]
            state["scan_errors"] = errors
            if errors:
                state["scan_retry_at"] = (now + timedelta(minutes=config["ai_retry_delay_minutes"])).isoformat()
                results["status"] = "partial"
            else:
                state["last_scan_at"] = now.isoformat()
                state.pop("scan_retry_at", None)
            await service.asave_store(store)

        # Refresh unchanged, open events too: delayed monitoring is not a new alarm ID.
        store = await service.aload_store()
        cutoff = now - timedelta(hours=config["rescan_lookback_hours"])
        candidates = []
        for event in store.get("events", []):
            if event.get("archived") or event.get("event_status") == "已归档":
                continue
            occurrence = parse_time(event.get("event_end_time")) or parse_time(event.get("event_start_time"))
            refreshed = parse_time(event.get("evidence_checked_at"))
            if occurrence and occurrence < cutoff and not service._needs_event_evidence(event):
                continue
            delay = config["ai_retry_delay_minutes"] if service._needs_event_evidence(event) else config["evidence_refresh_minutes"]
            if refreshed and now < refreshed + timedelta(minutes=delay):
                continue
            candidates.append(event)
        candidates.sort(key=lambda event: event.get("evidence_checked_at") or "")
        results["evidence"] = await service._collect_event_evidence(store, candidates[:config["evidence_batch_size"]])
        try:
            results["ai_queue"] = await self.dispatch_queue(now=now)
        except Exception as exc:
            results["ai_queue"] = {"status": "failed", "error": str(exc)}
            results["status"] = "partial"
        return results

    async def dispatch_queue(self, *, now, human_only: bool = False):
        """派发待执行 AI 卡。

        ``human_only=True`` 时只派发人工反馈/审核退回产生的增量卡，用于演示
        冻结等暂停自动抓取的场景：人工动作仍应执行，但不派生自动卡。
        """
        from app.services.jiangsu_smart_event import SMART_EVENT_TASK_ID, _is_archived, detect_data_clue_tags
        from app.scheduled_tasks import get_scheduled_task_service
        service = self.service
        config = service.load_config()
        auto_enabled = bool(config["auto_ai_enabled"]) and not human_only
        task_service = self.task_service or get_scheduled_task_service()
        task = task_service.get_task(SMART_EVENT_TASK_ID)
        if task is None or not task.enabled:
            return {"status": "task_disabled", "dispatched": 0}
        if human_only:
            # 轻量路径：只按需加载相关事件，避免在冻结/演示场景整表加载拖垮每分钟任务。
            refs, active = await self._human_card_refs()
            if not refs:
                return {"status": "disabled", "dispatched": 0}
            slots = max(0, config["ai_max_concurrency"] - active)
            return await self._dispatch_card_refs(refs, config, now, slots)
        await asyncio.to_thread(self._recover_running, task_service, task, now)
        store = await service.aload_store()
        events = {event["event_id"]: event for event in store.get("events", [])}
        cards = store.setdefault("tasks", [])
        if auto_enabled:
            for event in events.values():
                if _is_archived(event):
                    continue
                package = event.get("evidence_package") or {}
                update_initial_assessment(event, package, detect_data_clue_tags(event, package, config))
                event["evidence_signature"] = evidence_signature(package)
                related = [card for card in cards if card.get("event_id") == event["event_id"] and card.get("task_type") == "ai_judgment"]
                if not related or (event.get("pending_delta") and all(card.get("status") in {"已完成", "已取消"} for card in related)):
                    base = next((card for card in reversed(related) if card.get("status") == "已完成"), None)
                    if not service._bucket_judged(event) or event.get("pending_delta"):
                        cards.append(service._create_ai_task(event, base_task=base, reason="delayed_evidence"))
            await service.asave_store(store)
        active = sum(card.get("status") == "执行中" and not _is_archived(events.get(card.get("event_id"), {})) for card in cards)
        slots = max(0, config["ai_max_concurrency"] - active)
        pending = [card for card in cards if card.get("task_type") == "ai_judgment"
                   and card.get("status") in {"待执行", "待调度", "执行失败"}
                   and not card.get("retry_exhausted")
                   and (not parse_time(card.get("next_retry_at")) or parse_time(card["next_retry_at"]) <= now)
                   and (auto_enabled or is_human_review_continuation(card))
                   and card.get("event_id") in events and not _is_archived(events[card["event_id"]])]
        if not auto_enabled and not pending:
            return {"status": "disabled", "dispatched": 0}
        pending.sort(key=lambda card: (
            events[card["event_id"]].get("ai_task_priority") != "urgent", card.get("created_at") or "", card["task_id"]))
        outcomes, dispatched_events = [], set()
        for queued in pending:
            if slots <= 0:
                break
            event_id = queued["event_id"]
            if event_id in dispatched_events:
                continue
            latest = await service.aload_store(event_ids={event_id})
            event = service._stored_event(latest, event_id)
            if event is None or _is_archived(event) or service._needs_event_evidence(event):
                continue
            related = [card for card in latest["tasks"] if card.get("event_id") == event_id]
            if any(card.get("status") == "执行中" for card in related):
                continue
            card = next(card for card in related if card["task_id"] == queued["task_id"])
            if int(card.get("automatic_attempts") or 0) >= 1 + config["ai_max_retries"]:
                card["retry_exhausted"] = True
                await service.asave_store(latest)
                continue
            card["automatic_attempts"] = int(card.get("automatic_attempts") or 0) + 1
            card["last_attempt_at"] = now.isoformat()
            card["status"] = "待调度"
            card["next_retry_at"] = None
            card["priority"] = event.get("ai_task_priority", "normal")
            await service.asave_store(latest)
            try:
                result = await service._dispatch_pending_tasks(
                    await service.aload_store(event_ids={event_id}), event_ids={event_id},
                    task_ids={card["task_id"]}, force_retry=True)
            except Exception as exc:
                result = [{"event_id": event_id, "status": "failed", "error": str(exc)}]
            latest = await service.aload_store(event_ids={event_id})
            latest_card = next(item for item in latest["tasks"] if item["task_id"] == card["task_id"])
            if latest_card.get("status") in {"待执行", "待调度"}:
                schedule_retry(latest_card, config, error=str(result), now=now)
                await service.asave_store(latest)
            outcomes.extend(result)
            dispatched_events.add(event_id)
            slots -= 1
        return {"status": "success", "attempted": len(dispatched_events),
                "dispatched": sum(bool(item.get("accepted_task_ids")) for item in outcomes), "outcomes": outcomes}

    async def _human_card_refs(self):
        """返回 (待派发的人工增量卡引用, 执行中的 AI 卡数)，不加载事件正文。"""
        service = self.service
        from app.services.smart_event_db import smart_event_db_enabled

        if smart_event_db_enabled():
            from app.db.sync_bridge import run_db_async
            from app.services.smart_event_db import list_ai_judgment_card_refs_async

            rows = await run_db_async(list_ai_judgment_card_refs_async())
        else:
            store = await service.aload_store()
            rows = [
                {"event_id": card.get("event_id"), "task_id": card.get("task_id"),
                 "status": card.get("status"), "human": is_human_review_continuation(card)}
                for card in store.get("tasks", []) if card.get("task_type") == "ai_judgment"
            ]
        active = sum(1 for row in rows if row.get("status") == "执行中")
        refs = [
            {"event_id": row["event_id"], "task_id": row["task_id"]}
            for row in rows
            if row.get("human") and row.get("status") in {"待执行", "待调度", "执行失败"}
            and row.get("event_id") and row.get("task_id")
        ]
        return refs, active

    async def _dispatch_card_refs(self, refs, config, now, slots):
        from app.services.jiangsu_smart_event import _is_archived

        service = self.service
        outcomes, dispatched_events = [], set()
        for ref in refs:
            if slots <= 0:
                break
            event_id, task_id = ref["event_id"], ref["task_id"]
            if event_id in dispatched_events:
                continue
            latest = await service.aload_store(event_ids={event_id})
            event = service._stored_event(latest, event_id)
            if event is None or _is_archived(event) or service._needs_event_evidence(event):
                continue
            related = [card for card in latest["tasks"] if card.get("event_id") == event_id]
            if any(card.get("status") == "执行中" for card in related):
                continue
            card = next((card for card in related if card["task_id"] == task_id), None)
            if card is None:
                continue
            if int(card.get("automatic_attempts") or 0) >= 1 + config["ai_max_retries"]:
                card["retry_exhausted"] = True
                await service.asave_store(latest)
                continue
            card["automatic_attempts"] = int(card.get("automatic_attempts") or 0) + 1
            card["last_attempt_at"] = now.isoformat()
            card["status"] = "待调度"
            card["next_retry_at"] = None
            card["priority"] = event.get("ai_task_priority", "normal")
            await service.asave_store(latest)
            try:
                result = await service._dispatch_pending_tasks(
                    await service.aload_store(event_ids={event_id}), event_ids={event_id},
                    task_ids={task_id}, force_retry=True)
            except Exception as exc:
                result = [{"event_id": event_id, "status": "failed", "error": str(exc)}]
            latest = await service.aload_store(event_ids={event_id})
            latest_card = next(item for item in latest["tasks"] if item["task_id"] == task_id)
            if latest_card.get("status") in {"待执行", "待调度"}:
                schedule_retry(latest_card, config, error=str(result), now=now)
                await service.asave_store(latest)
            outcomes.extend(result)
            dispatched_events.add(event_id)
            slots -= 1
        return {"status": "success", "attempted": len(dispatched_events),
                "dispatched": sum(bool(item.get("accepted_task_ids")) for item in outcomes), "outcomes": outcomes}

    def _recover_running(self, task_service, task, now):
        from app.services.jiangsu_smart_event import _card_accepts_execution
        service = self.service
        snapshot = service._load_store()
        for queued in snapshot.get("tasks", []):
            if queued.get("status") != "执行中" or queued.get("task_type") != "ai_judgment":
                continue
            store = service._load_store(event_ids={queued["event_id"]})
            card = next(item for item in store["tasks"] if item["task_id"] == queued["task_id"])
            event = service._stored_event(store, card["event_id"])
            if event is None or event.get("archived") or card.get("status") != "执行中":
                continue
            claim = task_service.claim_storage.get(task.task_id, card["event_id"])
            started = parse_time(card.get("last_attempt_at") or card.get("updated_at"))
            if claim and claim.status in {"failed", "succeeded"} and claim.execution_id:
                execution = task_service.get_execution(claim.execution_id)
                attributes = (getattr(execution, "event_attributes", None) or {}) if execution else {}
                if execution and attributes.get("smart_event_task_id") == card["task_id"] and _card_accepts_execution(
                        card, attributes, getattr(execution, "started_at", None)):
                    service.apply_task_execution(card["event_id"], task, execution)
                    continue
            if started and (now - started).total_seconds() > task.timeout_seconds + 120:
                if claim and claim.status == "claimed":
                    # A live engine may still be waiting for its execution semaphore.
                    if getattr(task_service, "_event_tasks", None):
                        continue
                    task_service.claim_storage.mark_status(claim.claim_id, "failed")
                if claim and claim.status == "running":
                    if not task_service.claim_storage.fail_stale_running(task.task_id, card["event_id"], timeout_seconds=task.timeout_seconds + 120, now=now):
                        continue
                schedule_retry(card, service.load_config(), error="执行中断或结果回写缺失", now=now)
                service._save_store(store)
