"""Manually backfill one smart event from a real camera capture + same-day upstream alarms.

用法（分阶段执行，CONFIG 为本次回补参数 JSON）:
    E:\Tools\Python311\python.exe -X utf8 scripts/backfill_smart_event_manual.py <stage> <config.json>

stage:
  create   - 用当日真实上游告警(非偏差) + 视频线索建事件桶
  evidence - 按事件窗口抓取并持久化证据包
  photo    - 把照片拷入事件 assets 并注入 video 证据位
  status   - 打印事件/任务卡状态

CONFIG JSON 字段:
  station_code / station_name / city / district
  photo        - 照片源文件绝对路径
  photo_local  - 拍摄时间 "YYYY-MM-DDTHH:MM:SS"（本地时间）
  camera       - 摄像机名称（照片水印/平台标签）
  tag_name     - 视频线索标签（默认 人员进入采样区）
  confidence   - 视频标签置信度（默认 0.92）
"""
import asyncio
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ENV_FILE = r"E:\suyuan\backend\.env.jiangsu-ops"


def load_env(path: str) -> None:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2).strip())


load_env(ENV_FILE)
sys.path.insert(0, r"E:\suyuan\backend")

from app.services.jiangsu_smart_event import (  # noqa: E402
    SMART_EVENT_EVENT_TYPE,
    JiangsuSmartEventService,
    _initial_event_name,
    _is_deviation_clue,
    normalize_alarm_event,
)
from app.tools.jiangsu.alarm_records import JiangsuAlarmRecordsTool  # noqa: E402
from app.utils.path_config import format_agent_path, get_data_registry  # noqa: E402


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    photo_local = str(cfg["photo_local"])
    stamp = photo_local.replace("-", "").replace("T", "").replace(":", "")
    cfg.setdefault("tag_name", "人员进入采样区")
    cfg.setdefault("confidence", 0.92)
    cfg["photo_path"] = Path(cfg["photo"])
    cfg["day"] = photo_local[:10]
    cfg["day_start"] = f"{cfg['day']}T00:00:00+08:00"
    cfg["day_end"] = f"{cfg['day']}T23:59:59+08:00"
    cfg["video_event_id"] = f"video:{cfg['station_code']}:{stamp}"
    cfg["video_row_title"] = f"{cfg['camera']} {photo_local.replace('T', ' ')}"
    return cfg


def event_folder(event_id: str) -> Path:
    digest = hashlib.sha256(str(event_id).encode()).hexdigest()[:24]
    return get_data_registry() / "jiangsu_smart_events" / "events" / digest


def build_video_tag(cfg: dict) -> dict:
    vid = cfg["video_event_id"]
    return {
        "tag_id": f"{vid}:video",
        "tag_source": "视频识别",
        "tag_category": "视频",
        "tag_name": cfg["tag_name"],
        "tag_object": cfg["camera"],
        "tag_start_time": cfg["photo_local"],
        "tag_end_time": cfg["photo_local"],
        "tag_confidence": cfg["confidence"],
        "clue_id": f"{vid}:video",
        "tag_display_text": (
            f"视频：{cfg['tag_name']}（{cfg['camera']}，"
            f"{cfg['photo_local'].replace('T', ' ')}，置信度 {cfg['confidence']}）"
        ),
    }


def build_video_row(cfg: dict, photo_path: Path) -> dict:
    return {
        "title": cfg["video_row_title"],
        "camera_name": cfg["camera"],
        "captured_at": f"{cfg['photo_local']}+08:00",
        "tag_name": cfg["tag_name"],
        "tag_confidence": cfg["confidence"],
        "summary": (
            f"{cfg['photo_local'].replace('T', ' ')} {cfg['camera']} 拍摄到人员在室外采样区活动，"
            f"判定线索：{cfg['tag_name']}。"
        ),
        "image_path": format_agent_path(photo_path),
        "source": "视频监控",
    }


def build_video_candidate(cfg: dict, photo_path: Path) -> dict:
    name = _initial_event_name(cfg["station_name"], cfg["tag_name"])
    return {
        "event_id": cfg["video_event_id"],
        "site_id": cfg["station_code"],
        "site_name": cfg["station_name"],
        "city_name": cfg["city"],
        "district_name": cfg["district"],
        "event_start_time": cfg["photo_local"],
        "latest_occurrence_time": cfg["photo_local"],
        "event_end_time": cfg["photo_local"],
        "initial_event_name": name,
        "event_name": name,
        "event_status": "未研判",
        "event_type": "待 AI 研判",
        "source_alarm_rule_type": f"视频识别-{cfg['tag_name']}",
        "alarm_content": (
            f"{cfg['camera']} 于 {cfg['photo_local'].replace('T', ' ')} 拍摄到人员在室外采样区活动"
        ),
        "source_alarm_state": "视频线索",
        "event_trigger_type": SMART_EVENT_EVENT_TYPE,
        "clue_trigger_type": SMART_EVENT_EVENT_TYPE,
        "clue_tags": [build_video_tag(cfg)],
        "primary_clue_tag": cfg["tag_name"],
        "clue_count": 1,
        "merged_alarm_ids": [cfg["video_event_id"]],
        "ai_event_type": None,
        "ai_event_name": None,
        "ai_data_impact": "待确认",
        "system_data_impact": "待确认",
        "data_impact": "待确认",
        "ai_task_priority": "normal",
        "ai_suggested_level": None,
        "ai_diagnosis_note": None,
        "manual_final_event_type": None,
        "manual_final_level": None,
        "archived": False,
        "operation_records": [],
        "evidence": {"video": [build_video_row(cfg, photo_path)]},
        "source": "alarm_backfill",
    }


async def find_existing(svc: JiangsuSmartEventService, cfg: dict) -> dict | None:
    store = await svc.aload_store()
    for item in store.get("events", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("site_id")) != cfg["station_code"]:
            continue
        start = str(item.get("event_start_time") or "")
        if start.startswith(cfg["day"]):
            return {
                "event_id": item.get("event_id"),
                "event_name": item.get("event_name"),
                "event_start_time": start,
                "clue_count": item.get("clue_count"),
                "primary_clue_tag": item.get("primary_clue_tag"),
            }
    return None


async def stage_create(cfg: dict) -> None:
    svc = JiangsuSmartEventService()
    existing = await find_existing(svc, cfg)
    if existing:
        print("ALREADY EXISTS:", json.dumps(existing, ensure_ascii=False))
        return

    tool = JiangsuAlarmRecordsTool()
    res = await tool.execute_pipeline(
        station_codes=[cfg["station_code"]],
        start_time=cfg["day_start"],
        end_time=cfg["day_end"],
        max_result_count=100,
        sorting="timePoint",
    )
    records = res.get("data") or []
    print(f"upstream records for {cfg['station_code']} on {cfg['day']}: {len(records)} (status={res.get('status')})")

    alarm_candidates = []
    skipped_deviation = 0
    for record in records:
        candidate = normalize_alarm_event(record)
        if _is_deviation_clue(candidate):
            skipped_deviation += 1
            continue
        alarm_candidates.append(candidate)
    print(f"alarm candidates: {len(alarm_candidates)}, deviation skipped: {skipped_deviation}")
    for cand in alarm_candidates:
        print("  ", cand["event_id"], cand["event_start_time"], cand["primary_clue_tag"],
              str(cand.get("alarm_content"))[:60])

    video_candidate = build_video_candidate(cfg, cfg["photo_path"])
    actor = {"user_id": "manual-backfill", "username": "manual-backfill"}
    store, created_tasks, created_ids, merged_ids = await asyncio.to_thread(
        svc._upsert_events, alarm_candidates + [video_candidate], actor=actor
    )
    print("created_event_ids:", created_ids)
    print("merged_event_ids:", merged_ids)
    print("created_task_ids:", [t.get("task_id") for t in created_tasks])
    target = next((e for e in store.get("events", []) if isinstance(e, dict)
                   and str(e.get("site_id")) == cfg["station_code"]
                   and str(e.get("event_start_time") or "").startswith(cfg["day"])), None)
    if target is None:
        print("ERROR: event not found after upsert")
        return
    print("EVENT:", json.dumps({
        "event_id": target.get("event_id"),
        "event_name": target.get("event_name"),
        "event_start_time": target.get("event_start_time"),
        "event_end_time": target.get("event_end_time"),
        "primary_clue_tag": target.get("primary_clue_tag"),
        "clue_count": target.get("clue_count"),
        "clue_tags": [t.get("tag_name") for t in target.get("clue_tags", [])],
        "merged_alarm_ids": target.get("merged_alarm_ids"),
    }, ensure_ascii=False, indent=2))


async def stage_evidence(cfg: dict, event_id: str) -> None:
    svc = JiangsuSmartEventService()
    store = await svc.aload_store(event_ids={event_id})
    event = next((e for e in store.get("events", []) if isinstance(e, dict)
                  and str(e.get("event_id")) == event_id), None)
    if event is None:
        print("ERROR: event not found")
        return
    print("collecting evidence for", event_id, "window", event.get("event_start_time"), "~", event.get("event_end_time"))
    result = await svc.collect_event_evidence(event_id)
    event = result.get("event") or {}
    package = event.get("evidence_package") or {}
    print("collect result:", {k: v for k, v in result.items() if k != "event"})
    print("package status:", package.get("status"))
    print("package gaps:", json.dumps(package.get("gaps"), ensure_ascii=False)[:600])


async def stage_photo(cfg: dict, event_id: str) -> None:
    svc = JiangsuSmartEventService()
    folder = event_folder(event_id)
    assets = folder / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    stamp = cfg["photo_local"].replace("-", "").replace("T", "_").replace(":", "")
    target_photo = assets / f"{stamp}_{cfg['station_code']}_outdoor_sampling_area.png"
    shutil.copy2(cfg["photo_path"], target_photo)
    print("photo copied to:", target_photo, f"({target_photo.stat().st_size} bytes)")

    store = await svc.aload_store(event_ids={event_id})
    event = next((e for e in store.get("events", []) if isinstance(e, dict)
                  and str(e.get("event_id")) == event_id), None)
    if event is None:
        print("ERROR: event not found")
        return
    row = build_video_row(cfg, target_photo)
    event.setdefault("evidence", {})["video"] = [row]
    package = event.get("evidence_package")
    if isinstance(package, dict) and "sources" not in package and package.get("persisted_path"):
        # DB 主模式事件只存 stub，改包前先从文件回填完整包，避免覆盖已抓取来源。
        package = svc.packages.read_evidence_package(str(package["persisted_path"]), event_id)
    if not isinstance(package, dict):
        package = {"event_id": event_id, "status": "partial", "sources": {}, "gaps": []}
    sources = package.setdefault("sources", {})
    sources["video"] = {
        "status": "success",
        "summary": "视频监控记录：1 张画面，1 条视频标签。",
        "record_count": 1,
        "source": "视频监控",
        "metadata": {"camera_name": cfg["camera"], "captured_at": f"{cfg['photo_local']}+08:00",
                     "detail": "平台原始视频线索接口尚未接入，本次画面由人工回补。"},
        "data": [row],
    }
    gaps = package.get("gaps")
    if isinstance(gaps, list):
        package["gaps"] = [g for g in gaps if not (isinstance(g, dict) and g.get("source") == "video")]
    package.setdefault("event_id", event_id)
    event["evidence_package"] = package
    event["evidence_updated_at"] = datetime.now().astimezone().isoformat()
    event["updated_at"] = datetime.now().astimezone().isoformat()
    await svc.asave_store(store)
    print("event saved; evidence.video rows:", len((event.get("evidence") or {}).get("video") or []))

    package_path = svc._evidence_package_path(event_id)
    print("package path:", package_path)
    full = svc.packages.read_evidence_package(format_agent_path(package_path), event_id)
    video = ((full.get("sources") or {}).get("video") or {})
    rows = video.get("data") or []
    print("readback video rows:", len(rows), "| image_path:", (rows[0] or {}).get("image_path") if rows else None)


async def stage_status(cfg: dict) -> None:
    svc = JiangsuSmartEventService()
    existing = await find_existing(svc, cfg)
    if not existing:
        print("ERROR: event not found")
        return
    event_id = existing["event_id"]
    store = await svc.aload_store(event_ids={event_id})
    event = next((e for e in store.get("events", []) if isinstance(e, dict)
                  and str(e.get("event_id")) == event_id), None)
    cards = [t for t in store.get("tasks", []) if t.get("event_id") == event_id]
    print("event_status:", event.get("event_status"), "| ai_event_type:", event.get("ai_event_type"),
          "| level:", event.get("ai_suggested_level"), "| data_impact:", event.get("ai_data_impact"))
    print("event_name:", event.get("event_name"))
    judgment = event.get("ai_judgment") or {}
    print("judgment_status:", judgment.get("status"), "| completed_at:", judgment.get("completed_at"))
    if judgment.get("final_response"):
        print("---- final_response ----")
        print(judgment["final_response"][:4000])
    for card in cards:
        print("card:", json.dumps({k: card.get(k) for k in
              ("task_id", "status", "dispatch_status", "dispatch_error", "created_at", "updated_at")},
              ensure_ascii=False))


async def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        return
    stage, config_path = sys.argv[1], sys.argv[2]
    cfg = load_config(config_path)
    if stage == "create":
        await stage_create(cfg)
        return
    svc = JiangsuSmartEventService()
    existing = await find_existing(svc, cfg)
    if not existing:
        print("ERROR: create the event first")
        return
    if stage == "evidence":
        await stage_evidence(cfg, existing["event_id"])
    elif stage == "photo":
        await stage_photo(cfg, existing["event_id"])
    elif stage == "status":
        await stage_status(cfg)
    else:
        print(f"unknown stage: {stage}")


asyncio.run(main())
