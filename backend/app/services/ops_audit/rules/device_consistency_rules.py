"""Cross-order device identity consistency rules."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.services.ops_audit.config import (
    load_brand_aliases,
    load_device_identity_profiles,
)
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


ZERO_GUID = "00000000-0000-0000-0000-000000000000"
DEVICE_PROFILE = load_device_identity_profiles()
BRAND_ALIASES = load_brand_aliases()
_DEVICE_HISTORY_INDEX_CACHE: dict[
    tuple[int, tuple[Any, ...]],
    tuple[list[dict[str, Any]], dict[str, list[tuple[str, dict[str, Any]]]]],
] = {}
_DEVICE_HISTORY_INDEX_CACHE_LIMIT = 16


def check_device_identity_consistency(
    current_order: dict[str, Any],
    current_forms: list[tuple[str, dict[str, Any]]],
    all_orders: list[dict[str, Any]],
    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
    devices_by_id: dict[str, dict[str, Any]],
    devices_by_code: dict[str, dict[str, Any]],
    issues: list[Issue],
) -> None:
    """Check the current order against same-device order identities.

    The rule uses the current fetched batch plus optional ``device_history``
    records added during dataset extraction. It compares normalized brand,
    model, and device code while keeping raw values in evidence.
    """

    if not _is_rule_applicable(current_order):
        return

    current_identity = _build_identity(
        current_order,
        current_forms,
        devices_by_id,
        devices_by_code,
    )
    match_keys = set(current_identity.get("match_keys", []))
    if not match_keys:
        return
    if _has_replacement_evidence(current_forms):
        return

    comparisons_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    current_code = current_order.get("WORKINGORDERCODE")
    current_create = _parse_time(current_order.get("CREATETIME"))

    for other_order in all_orders:
        other_code = other_order.get("WORKINGORDERCODE")
        if not other_code or other_code == current_code or not _is_rule_applicable(other_order):
            continue

        other_forms = forms_by_code.get(str(other_code), [])
        if _has_replacement_evidence(other_forms):
            continue

        other_identity = _build_identity(
            other_order,
            other_forms,
            devices_by_id,
            devices_by_code,
        )
        shared_match_keys = sorted(match_keys & set(other_identity.get("match_keys", [])))
        if not shared_match_keys:
            continue

        other_create = _parse_time(other_order.get("CREATETIME"))
        if current_create and other_create:
            history_days = int(DEVICE_PROFILE.get("history_days", 90))
            if other_create >= current_create or (current_create - other_create).days > history_days:
                continue

        for field_config in DEVICE_PROFILE.get("identity_fields", []):
            field_key = str(field_config.get("key") or "")
            current_value = current_identity["normalized"].get(field_key)
            other_value = other_identity["normalized"].get(field_key)
            if not current_value or not other_value or current_value == other_value:
                continue
            comparisons_by_field[field_key].append(
                {
                    "compare_order_code": other_code,
                    "compare_create_time": other_order.get("CREATETIME"),
                    "compare_maintenance_type": other_order.get("MAINTENANCETYPE"),
                    "shared_match_keys": shared_match_keys,
                    "current_raw": current_identity["raw"].get(field_key),
                    "compare_raw": other_identity["raw"].get(field_key),
                    "current_source": current_identity["sources"].get(field_key),
                    "compare_source": other_identity["sources"].get(field_key),
                }
            )

    field_configs = {
        str(item.get("key")): item
        for item in DEVICE_PROFILE.get("identity_fields", [])
        if item.get("key")
    }
    for field_key, comparisons in comparisons_by_field.items():
        field_config = field_configs.get(field_key, {})
        label = str(field_config.get("label") or field_key)
        severity = str(field_config.get("severity") or "中")
        sample_comparisons = comparisons[:5]
        evidence = {
            "current_order_code": current_code,
            "current_create_time": current_order.get("CREATETIME"),
            "current_maintenance_type": current_order.get("MAINTENANCETYPE"),
            "device_match_keys": sorted(match_keys),
            "field": field_key,
            "current_value": current_identity["raw"].get(field_key),
            "compare_count": len(comparisons),
            "comparisons": sample_comparisons,
        }
        add_issue(
            issues,
            "RF_DEVICE_IDENTITY_INCONSISTENT",
            "跨工单一致性",
            severity,
            f"device_identity.{field_key}",
            f"同设备跨工单{label}不一致",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def merge_device_history(dataset: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[tuple[str, dict[str, Any]]]]]:
    """Return current and historical orders/forms indexed for consistency checks.

    The merged history index is reused by multiple rule/report paths for the
    same in-memory dataset. A small signature cache avoids rebuilding the
    order/form index repeatedly while keeping the returned containers detached
    from the cached copy.
    """

    cache_key = _device_history_cache_key(dataset)
    cached = _DEVICE_HISTORY_INDEX_CACHE.get(cache_key)
    if cached:
        return _copy_history_index(cached)

    all_orders = list(dataset.get("orders", []))
    history = dataset.get("device_history") or {}
    seen_codes = {order.get("WORKINGORDERCODE") for order in all_orders if order.get("WORKINGORDERCODE")}
    for order in history.get("orders", []):
        code = order.get("WORKINGORDERCODE")
        if code and code not in seen_codes:
            all_orders.append(order)
            seen_codes.add(code)

    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for table, forms in dataset.get("rf_forms", {}).items():
        for form in forms:
            code = form.get("WORKINGORDERCODE")
            if code:
                forms_by_code[str(code)].append((table, form))
    for table, forms in history.get("rf_forms", {}).items():
        for form in forms:
            code = form.get("WORKINGORDERCODE")
            if code:
                forms_by_code[str(code)].append((table, form))
    _remember_history_index(cache_key, all_orders, forms_by_code)
    return all_orders, forms_by_code


def _device_history_cache_key(dataset: dict[str, Any]) -> tuple[int, tuple[Any, ...]]:
    history = dataset.get("device_history") or {}
    rf_forms = dataset.get("rf_forms", {}) or {}
    history_rf_forms = history.get("rf_forms", {}) or {}
    signature = (
        len(dataset.get("orders", []) or []),
        tuple(sorted((str(table), len(forms or [])) for table, forms in rf_forms.items())),
        len(history.get("orders", []) or []),
        tuple(sorted((str(table), len(forms or [])) for table, forms in history_rf_forms.items())),
    )
    return id(dataset), signature


def _remember_history_index(
    cache_key: tuple[int, tuple[Any, ...]],
    all_orders: list[dict[str, Any]],
    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> None:
    if len(_DEVICE_HISTORY_INDEX_CACHE) >= _DEVICE_HISTORY_INDEX_CACHE_LIMIT:
        _DEVICE_HISTORY_INDEX_CACHE.pop(next(iter(_DEVICE_HISTORY_INDEX_CACHE)))
    _DEVICE_HISTORY_INDEX_CACHE[cache_key] = (
        list(all_orders),
        {code: list(forms) for code, forms in forms_by_code.items()},
    )


def _copy_history_index(
    cached: tuple[list[dict[str, Any]], dict[str, list[tuple[str, dict[str, Any]]]]],
) -> tuple[list[dict[str, Any]], dict[str, list[tuple[str, dict[str, Any]]]]]:
    all_orders, forms_by_code = cached
    return list(all_orders), defaultdict(list, {code: list(forms) for code, forms in forms_by_code.items()})


def _is_rule_applicable(order: dict[str, Any]) -> bool:
    enabled_order_types = {str(item) for item in DEVICE_PROFILE.get("enabled_order_types", [])}
    if enabled_order_types and str(order.get("DDWORKINGORDERTYPE") or "") not in enabled_order_types:
        return False

    enabled_maintenance_types = {str(item) for item in DEVICE_PROFILE.get("enabled_maintenance_types", [])}
    maintenance_type = str(order.get("MAINTENANCETYPE") or "")
    return not enabled_maintenance_types or not maintenance_type or maintenance_type in enabled_maintenance_types


def _build_identity(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    devices_by_id: dict[str, dict[str, Any]],
    devices_by_code: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    form_rows = [form for _, form in forms if not form.get("_query_error")]
    base_device = _resolve_base_device(order, form_rows, devices_by_id, devices_by_code)
    raw: dict[str, Any] = {}
    sources: dict[str, str] = {}

    for field_key, candidates in DEVICE_PROFILE.get("rf_identity_fields", {}).items():
        value, source = _first_form_value(form_rows, candidates)
        if _has_text(value):
            raw[field_key] = value
            sources[field_key] = source

    for field_key, candidates in DEVICE_PROFILE.get("base_device_fields", {}).items():
        if field_key in raw:
            continue
        value = _first_mapping_value(base_device, candidates)
        if _has_text(value):
            raw[field_key] = value
            sources[field_key] = "base_device"

    normalized = {
        "brand": _normalize_brand(raw.get("brand"), raw.get("model")),
        "model": _normalize_text(raw.get("model")),
        "device_code": _normalize_text(raw.get("device_code")),
    }

    station_id = _normalize_text(order.get("STATIONID"))
    device_id = _normalize_text(order.get("DEVICEID"))
    if device_id == ZERO_GUID:
        device_id = ""
    match_keys = _build_match_keys(order, forms, station_id, device_id, normalized.get("device_code"))
    return {
        "match_key": match_keys[0] if match_keys else "",
        "match_keys": match_keys,
        "raw": raw,
        "normalized": normalized,
        "sources": sources,
    }


def _build_match_keys(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    station_id: str,
    device_id: str,
    device_code: str,
) -> list[str]:
    keys: list[str] = []
    if station_id and device_id:
        keys.append(f"device_id|{station_id}|{device_id}")
    if station_id and device_code:
        keys.append(f"device_code|{station_id}|{device_code}")

    deduped: list[str] = []
    for key in keys:
        if key and key not in deduped:
            deduped.append(key)
    return deduped


def _resolve_base_device(
    order: dict[str, Any],
    forms: list[dict[str, Any]],
    devices_by_id: dict[str, dict[str, Any]],
    devices_by_code: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    device_id = _normalize_text(order.get("DEVICEID"))
    if device_id and device_id in devices_by_id:
        return devices_by_id[device_id]
    for form in forms:
        device_code = _normalize_text(form.get("DEVICECODE") or form.get("DEVICECODEN"))
        if device_code and device_code in devices_by_code:
            return devices_by_code[device_code]
    return {}


def _first_form_value(forms: list[dict[str, Any]], fields: list[str]) -> tuple[Any, str]:
    for form in forms:
        for field in fields:
            if field in form and _has_text(form.get(field)):
                return form.get(field), f"rf_form.{field}"
    return None, ""


def _first_mapping_value(record: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        if field in record and _has_text(record.get(field)):
            return record.get(field)
    return None


def _has_replacement_evidence(forms: list[tuple[str, dict[str, Any]]]) -> bool:
    replacement_tables = {str(item) for item in DEVICE_PROFILE.get("replacement_tables", [])}
    replacement_keywords = [str(item) for item in DEVICE_PROFILE.get("replacement_keywords", [])]
    for table, form in forms:
        if table in replacement_tables:
            return True
        text = " ".join(str(value) for value in form.values() if value is not None)
        if any(keyword in text for keyword in replacement_keywords):
            return True
    return False


def _has_text(value: Any) -> bool:
    return value is not None and str(value).strip() not in {"", "/", "-", "无", "None", "NULL"}


def _normalize_brand(brand: Any, model: Any = None) -> str:
    brand_text = _normalize_text(brand)
    model_text = _normalize_text(model)
    for canonical, aliases in BRAND_ALIASES.items():
        normalized_aliases = {_normalize_text(alias) for alias in aliases}
        if brand_text in normalized_aliases:
            return canonical
    if model_text.startswith(("43", "48", "49")) and brand_text in {"", "TE", "THERMO", "热电"}:
        return "THERMO"
    return brand_text


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None
