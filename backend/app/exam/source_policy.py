"""Minimal source-governance rules for enforcement-exam generation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo


EFFECTIVE_VALIDITY_STATUSES = {"effective", "current", "active"}
REQUIRED_SOURCE_METADATA = ("issuer", "effective_date", "official_source_url")


def evaluate_exam_source(document: Any, *, as_of: date | None = None) -> tuple[bool, str]:
    """Return whether a document is eligible to generate current-law questions."""
    metadata = dict(getattr(document, "extra_metadata", None) or {})
    if metadata.get("exam_generation_eligible") is not True:
        return False, str(metadata.get("exam_generation_reason") or "题源尚未完成有效性核验")

    validity_status = str(metadata.get("validity_status") or "").strip().lower()
    if validity_status not in EFFECTIVE_VALIDITY_STATUSES:
        return False, "题源未标记为现行有效"

    missing = [field for field in REQUIRED_SOURCE_METADATA if not metadata.get(field)]
    if missing:
        return False, f"题源缺少准入元数据：{', '.join(missing)}"

    effective_date = _parse_date(metadata.get("effective_date"))
    if effective_date is None:
        return False, "题源施行日期格式无效"
    today = as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if effective_date > today:
        return False, "题源尚未施行"

    expiry_date = _parse_date(metadata.get("expiry_date"))
    if metadata.get("expiry_date") and expiry_date is None:
        return False, "题源失效日期格式无效"
    if expiry_date is not None and expiry_date <= today:
        return False, "题源已经失效"
    return True, "现行有效且来源信息完整"


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None
