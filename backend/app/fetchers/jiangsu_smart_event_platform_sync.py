"""Poll platform work-order progress for dispatched smart events (closed loop).

智能事件人工派单后在平台创建真实工单（platform_order_code）；本抓取器周期性
回查这些工单的节点状态，把处置进展回写到事件审计，工单完成后事件转“已反馈”
并自动排队一次增量 AI 研判，形成 派单 → 平台处置 → 反馈复盘 的闭环。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.tools.jiangsu.fault_diagnosis import (
    _JiangsuAuthenticatedApi,
    JiangsuFaultWorkOrdersTool,
)

logger = structlog.get_logger(__name__)

_MAX_TRACKED_EVENTS = 50
_API_TIMEOUT_SECONDS = 45


class JiangsuSmartEventPlatformSyncFetcher(DataFetcher):
    def __init__(self):
        super().__init__(
            "jiangsu_smart_event_platform_sync",
            "智能事件平台工单状态回流",
            "*/5 * * * *",
        )

    @property
    def _state_path(self) -> Path:
        from app.utils.path_config import get_data_registry

        directory = get_data_registry() / "jiangsu_smart_event_platform_sync"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "state.json"

    def _read_state(self) -> dict[str, Any]:
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write_state(self, state: dict[str, Any]) -> None:
        temporary = self._state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        temporary.replace(self._state_path)

    async def fetch_and_store(self) -> dict[str, Any]:
        from app.tools.jiangsu.platform_workflow import platform_writeback_enabled

        if not platform_writeback_enabled():
            return {"success": True, "status": "skipped", "summary": "平台写回开关未开启"}

        from app.services.jiangsu_smart_event import JiangsuSmartEventService

        service = JiangsuSmartEventService()
        store = await service.aload_store()
        tracked = [
            (str(event.get("event_id") or ""), str(event.get("platform_order_code") or "").strip())
            for event in store.get("events", [])
            if isinstance(event, dict)
            and event.get("event_status") == "待反馈"
            and str(event.get("platform_order_code") or "").strip()
        ][: _MAX_TRACKED_EVENTS]
        if not tracked:
            return {"success": True, "status": "empty", "summary": "无待回流的平台派单事件"}

        api = _JiangsuAuthenticatedApi(source="ops")
        node_names = await self._load_node_names(api)
        state = self._read_state()
        synced = 0
        finished = 0
        failed = 0
        for event_id, code in tracked:
            try:
                row = await self._fetch_order_row(api, code)
            except Exception as exc:
                failed += 1
                logger.warning("jiangsu_smart_event_platform_sync_query_failed",
                               event_id=event_id, work_order_code=code, error=str(exc))
                continue
            if row is None:
                failed += 1
                continue
            order_status = str(row.get("orderStatus") or "").strip()
            node_name = node_names.get(str(row.get("currentPoint") or "").strip(), "")
            signature = f"{order_status}|{node_name}"
            previous = (state.get(code) or {}).get("signature")
            if order_status != "Finish" and signature == previous:
                continue
            try:
                await asyncio.to_thread(
                    service.record_platform_order_sync,
                    event_id,
                    work_order_code=code,
                    order_status=order_status,
                    node_name=node_name,
                )
            except Exception as exc:
                failed += 1
                logger.warning("jiangsu_smart_event_platform_sync_write_failed",
                               event_id=event_id, work_order_code=code, error=str(exc))
                continue
            state[code] = {"signature": signature, "checked_at": row.get("updateTime") or ""}
            synced += 1
            if order_status == "Finish":
                finished += 1
        self._write_state(state)
        result = {
            "tracked_events": len(tracked),
            "synced_events": synced,
            "finished_events": finished,
            "failed_queries": failed,
        }
        logger.info("jiangsu_smart_event_platform_sync_completed", **result)
        return {"success": failed == 0, "status": "success" if synced or not failed else "failed",
                "summary": f"平台工单回流完成：同步 {synced}，完成 {finished}，失败 {failed}",
                **result}

    @staticmethod
    async def _load_node_names(api: _JiangsuAuthenticatedApi) -> dict[str, str]:
        try:
            payload = await asyncio.wait_for(
                api.get(JiangsuFaultWorkOrdersTool._WORKFLOW_PATH, [("Type", "Fault")]),
                timeout=_API_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("jiangsu_smart_event_platform_sync_workflow_failed", error=str(exc))
            return {}
        names: dict[str, str] = {}
        for step in (payload.get("result") or {}).get("stepList") or []:
            if isinstance(step, dict) and step.get("guid") and step.get("taskName"):
                names[str(step["guid"]).strip()] = str(step["taskName"]).strip()
        return names

    @staticmethod
    async def _fetch_order_row(api: _JiangsuAuthenticatedApi, code: str) -> dict[str, Any] | None:
        payload = await asyncio.wait_for(
            api.get(JiangsuFaultWorkOrdersTool._LIST_PATH, [
                ("OrderType", "Fault"),
                ("MaxResultCount", "10"),
                ("SkipCount", "0"),
                ("WorkingOrderCode", code),
            ]),
            timeout=_API_TIMEOUT_SECONDS,
        )
        items = (payload.get("result") or {}).get("items") or []
        for row in items:
            if isinstance(row, dict) and \
                    str(row.get("workingOrderCode") or "").strip() == code:
                return row
        return None
