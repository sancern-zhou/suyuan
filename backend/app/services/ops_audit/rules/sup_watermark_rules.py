"""组分站附件照片水印一致性试点（审核二期阶段 2.3）。

案例锚点：博罗石下周质控附件照片水印为河源站点（SUP_ATTACHMENT_WATERMARK_STATION，
docs/sup-audit-cases/cases-20260921-0930.txt 案例 4）。

模式：抽检 + 问题触发，不做全量——
- 工单已被其他规则命中（问题触发）→ 照片全检（受每单照片数上限约束）；
- 其余工单按工单号稳定哈希抽样，保证同一工单跨次运行判定一致；
- 每次运行的视觉调用量由 max_tasks_per_run 硬顶。

比对维度（任一不符 → 人工核验任务，中严重度，不直接判失败）：
- 地点：站点名与水印地点的字符重合度；
- 坐标：站点经纬度配置且水印含坐标时按距离判定（组分站台账缺失时自动跳过）；
- 时间：水印时间应落在检查日前 time_window_days 天窗口内。

识别失败输出技术诊断（不进报告问题清单），与主网视觉规则口径一致。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue
from app.services.ops_audit.rules.sup_form_rules import (
    SUP_FORM_PROFILES,
    attachment_filename,
    form_item_tag,
    parse_form_date,
)
from app.services.ops_audit.semantic.ocr_adapter import extract_attachment_json

WATERMARK_RULE_ID = "SUP_ATTACHMENT_WATERMARK_STATION"
WATERMARK_READ_FAILED_RULE_ID = "SUP_ATTACHMENT_WATERMARK_READ_FAILED"

WATERMARK_PROMPT = (
    "识别现场照片中的水印信息（通常在照片角落，含地点、经纬度、时间）。"
    '以JSON返回：{"地点": "...", "经纬度": "纬度N,经度E", "时间": "YYYY-MM-DD HH:MM"}。'
    '若某项缺失对应值为null；整张照片无水印时返回 {"无水印": true}。只输出JSON。'
)

_COORD_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*[°º]?\s*([NS])?[,，\s]+(\d{1,3}(?:\.\d+)?)\s*[°º]?\s*([EW])?")
_DATE_RE = re.compile(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")


def build_sup_watermark_tasks(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
    station_meta: dict[str, Any],
    has_prior_issues: bool,
) -> list[dict[str, Any]]:
    """构建水印核验任务（纯构建，不调用视觉模型）。"""

    pilot = _pilot_config()
    if not pilot.get("enabled", True):
        return []
    catalog = SUP_FORM_PROFILES.get("form_profiles") or {}

    targets = []
    for _table, form in forms:
        if form.get("_query_error"):
            continue
        tag = form_item_tag(form)
        profile = catalog.get(tag) or {}
        watermark_check = profile.get("watermark_check") or {}
        if not watermark_check.get("enabled"):
            continue
        targets.append((tag, form, profile, watermark_check))
    if not targets:
        return []

    if not has_prior_issues and not _sampled(str(order.get("WORKINGORDERCODE") or ""), pilot):
        return []

    items = _photo_items(attachments, wo_commonfiles, targets)
    if not items:
        return []
    max_photos = int(pilot.get("max_photos_per_order") or 2)
    checkdate = None
    for _tag, form, _profile, _check in targets:
        checkdate = parse_form_date(form.get("CHECKDATE") or form.get("checkdate"))
        if checkdate is not None:
            break
    return [
        {
            "task_type": "sup_watermark",
            "visual_rule_ids": {WATERMARK_RULE_ID},
            "order": order,
            "item": item,
            "station_meta": station_meta,
            "checkdate": str(checkdate) if checkdate else None,
            "watermark_check": item.pop("_watermark_check"),
        }
        for item in items[:max_photos]
    ]


def run_sup_watermark_task(task: dict[str, Any], issues: list[Issue]) -> None:
    """执行单个水印核验任务（视觉调用 + 比对）。"""

    order = task.get("order") or {}
    item = task.get("item") or {}
    station_meta = task.get("station_meta") or {}
    watermark_check = task.get("watermark_check") or {}
    source = str(item.get("source_path") or "")
    result = extract_attachment_json(source, prompt=WATERMARK_PROMPT, task="sup_watermark")
    if result.get("status") != "success":
        add_issue(
            issues,
            WATERMARK_READ_FAILED_RULE_ID,
            "附件读数一致性",
            "低",
            f"attachment.watermark.read.{item.get('typecode') or 'unknown'}",
            f"组分站照片水印识别失败：{str(result.get('error'))[:80]}",
            json.dumps(
                {
                    "working_order_code": order.get("WORKINGORDERCODE"),
                    "filename": item.get("filename"),
                    "source": source,
                    "error": result.get("error"),
                    "report_classification": "technical_diagnostic",
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        return
    data = result.get("data") or {}
    if data.get("无水印") or not (data.get("地点") or data.get("经纬度") or data.get("时间")):
        return
    mismatches = _compare_watermark(item, station_meta, watermark_check, data, task.get("checkdate"))
    if not mismatches:
        return
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "ruleitemtag": item.get("ruleitemtag"),
        "filename": item.get("filename"),
        "source": source,
        "watermark": data,
        "station": {
            "station_id": station_meta.get("station_id"),
            "station_name": station_meta.get("station_name"),
        },
        "mismatches": mismatches,
        "needs_manual_review": True,
        "review_basis": "附件照片水印与工单站点/检查日期比对不一致，需人工核验照片拍摄地点与时间。",
    }
    add_issue(
        issues,
        WATERMARK_RULE_ID,
        "附件质量",
        "中",
        f"attachment.watermark.{item.get('typecode') or 'unknown'}",
        (
            f"附件照片“{item.get('filename')}”水印（地点:{data.get('地点') or '无'}，"
            f"时间:{data.get('时间') or '无'}）与工单站点/检查日期不一致，需人工核验"
        ),
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


# ---------------------------------------------------------------------------
# 任务构建辅助
# ---------------------------------------------------------------------------


def _pilot_config() -> dict[str, Any]:
    defaults = SUP_FORM_PROFILES.get("defaults") or {}
    pilot = dict(defaults.get("watermark_pilot") or {})
    pilot.setdefault("enabled", True)
    pilot.setdefault("sample_rate", 0.3)
    pilot.setdefault("trigger_rule_prefixes", ["SUP_", "RF_", "FLOW_", "LIFECYCLE_"])
    pilot.setdefault("max_tasks_per_run", 20)
    pilot.setdefault("max_photos_per_order", 2)
    pilot.setdefault("distance_km_threshold", 5)
    # 环境变量覆盖（运维侧调参不改配置文件）。
    pilot["enabled"] = os.getenv("OPS_AUDIT_SUP_WATERMARK_ENABLED", str(pilot["enabled"])).lower() not in {"0", "false", "off"}
    try:
        pilot["sample_rate"] = float(os.getenv("OPS_AUDIT_SUP_WATERMARK_SAMPLE_RATE", str(pilot["sample_rate"])))
    except ValueError:
        pass
    try:
        pilot["max_tasks_per_run"] = int(os.getenv("OPS_AUDIT_SUP_WATERMARK_MAX_TASKS", str(pilot["max_tasks_per_run"])))
    except ValueError:
        pass
    return pilot


def _sampled(order_code: str, pilot: dict[str, Any]) -> bool:
    rate = max(0.0, min(float(pilot.get("sample_rate") or 0), 1.0))
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    digest = int(hashlib.sha1(f"sup-watermark:{order_code}".encode("utf-8")).hexdigest()[:8], 16)
    return (digest % 100) < int(rate * 100)


def _photo_items(
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
    targets: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]],
) -> list[dict[str, Any]]:
    # 照片按 "tag_监测项目" 精确归属表单（污染项目错挂附件由 SUP_ATTACHMENT_ITEM_MATCH 处理）；
    # 表单缺 pollutanttype 时退化为 tag 前缀匹配。
    prefixes: list[str] = []
    for tag, _form, _profile, _check in targets:
        prefixes.append(f"{tag.lower()}_")
    exact_by_prefix: dict[str, str] = {}
    for tag, form, _profile, _check in targets:
        pollutant = str(form.get("POLLUTANTTYPE") or form.get("pollutanttype") or "").strip().lower()
        if pollutant:
            exact_by_prefix[f"{tag.lower()}_"] = f"{tag.lower()}_{pollutant.lower()}"
    check_by_tag = {tag.lower(): (profile, check) for tag, _form, profile, check in targets}
    items = []
    for record in list(attachments) + list(wo_commonfiles):
        typecode = str(record.get("TYPECODE") or record.get("typecode") or "").strip()
        filename = attachment_filename(record)
        source_path = _first_present(
            record, ["FILEPATH", "filepath", "file_url", "FILE_URL", "URL", "url", "PATH", "path"]
        )
        if not filename or not source_path:
            continue
        lower_typecode = typecode.lower()
        matched_tag = ""
        for prefix in prefixes:
            if not lower_typecode.startswith(prefix):
                continue
            required = exact_by_prefix.get(prefix)
            if required and not lower_typecode.startswith(required):
                continue
            matched_tag = prefix.rstrip("_")
            break
        if not matched_tag:
            continue
        if not filename.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic")):
            continue
        profile, check = check_by_tag[matched_tag]
        items.append(
            {
                "filename": filename,
                "source_path": source_path,
                "typecode": typecode,
                "ruleitemtag": profile.get("display_name") or matched_tag,
                "_watermark_check": check,
            }
        )
    return items


def _first_present(record: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


# ---------------------------------------------------------------------------
# 水印比对
# ---------------------------------------------------------------------------


def _compare_watermark(
    item: dict[str, Any],
    station_meta: dict[str, Any],
    watermark_check: dict[str, Any],
    data: dict[str, Any],
    checkdate_raw: Any,
) -> list[dict[str, Any]]:
    mismatches = []
    station_name = str(station_meta.get("station_name") or "").strip()
    city_name = str(station_meta.get("city_name") or "").strip()
    address = str(station_meta.get("address") or "").strip()
    location = str(data.get("地点") or "").strip()

    if (
        station_name
        and location
        and not _location_related(station_name, location, city_name=city_name, address=address)
    ):
        mismatches.append(
            {
                "kind": "location_mismatch",
                "station_name": station_name,
                "watermark_location": location,
            }
        )

    distance_km = _coordinate_distance_km(
        station_meta.get("latitude"),
        station_meta.get("longitude"),
        str(data.get("经纬度") or ""),
    )
    if distance_km is not None:
        threshold = float(watermark_check.get("distance_km_threshold") or 5)
        if distance_km > threshold:
            mismatches.append(
                {
                    "kind": "coordinate_mismatch",
                    "distance_km": round(distance_km, 2),
                    "threshold_km": threshold,
                }
            )

    watermark_time = _parse_watermark_time(data.get("时间"))
    checkdate = parse_form_date(checkdate_raw)
    window_days = watermark_check.get("time_window_days")
    if watermark_time and checkdate is not None and window_days is not None:
        window_start = checkdate - timedelta(days=int(window_days))
        if not (window_start <= watermark_time <= checkdate):
            mismatches.append(
                {
                    "kind": "time_outside_window",
                    "watermark_time": str(watermark_time),
                    "checkdate": str(checkdate.date()),
                    "window_days": int(window_days),
                }
            )
    return mismatches


def _location_related(
    station_name: str,
    location: str,
    city_name: str = "",
    address: str = "",
) -> bool:
    """站点与水印地点相关性判定（试点口径：宁可漏报不误报，命中人工核验）。

    任一信号成立即视为相关：
    - 站点名 2 字滑窗出现在水印地点（如"石下"∈"博罗县·石下屯村"）；
    - 站点城市出现在水印地点（如站"东城"照片水印"东莞市·大气环保体验馆"）；
    - 站点地址与水印地点 2 字滑窗有重合。
    """

    normalized_station = _normalize_location(station_name)
    normalized_location = _normalize_location(location)
    if not normalized_station or not normalized_location:
        return True
    grams = {
        normalized_station[i : i + 2]
        for i in range(len(normalized_station) - 1)
        if len(normalized_station[i : i + 2]) == 2
    }
    if any(gram in normalized_location for gram in grams):
        return True
    normalized_city = _normalize_location(city_name)
    if normalized_city and normalized_city in normalized_location:
        return True
    normalized_address = _normalize_location(address)
    if normalized_address:
        address_grams = {
            normalized_address[i : i + 2]
            for i in range(len(normalized_address) - 1)
            if len(normalized_address[i : i + 2]) == 2
        }
        if sum(1 for gram in address_grams if gram in normalized_location) >= 2:
            return True
    return False


def _normalize_location(value: str) -> str:
    return re.sub(r"[\s·，,（）()\-—省市区县]", "", str(value or ""))


def _parse_watermark_time(value: Any) -> datetime | None:
    match = _DATE_RE.search(str(value or ""))
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _coordinate_distance_km(lat_a: Any, lon_a: Any, coord_text: str) -> float | None:
    lat1, lon1 = _to_float(lat_a), _to_float(lon_a)
    if lat1 is None or lon1 is None:
        return None
    match = _COORD_RE.search(str(coord_text or ""))
    if not match:
        return None
    lat2 = float(match.group(1))
    if str(match.group(2) or "").upper() == "S":
        lat2 = -lat2
    lon2 = float(match.group(3))
    if str(match.group(4) or "").upper() == "W":
        lon2 = -lon2
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        return None
    return _haversine_km(lat1, lon1, lat2, lon2)


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))
