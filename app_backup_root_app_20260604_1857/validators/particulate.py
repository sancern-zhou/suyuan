from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Dict, Iterable, List, MutableMapping, Optional, Sequence, Tuple, Union

from app.schemas.common import (
    DataQualityReport,
    FieldStats,
    ValidationIssue,
    ValidationSeverity,
)
from app.schemas.particulate import ParticulateSample
from .base import ValidationResult

RawRecord = MutableMapping[str, Union[str, float, int, None]]

CORE_COMPONENTS = {"SO4", "NO3", "NH4", "OC", "EC"}


def validate_particulate_samples(
    records: Sequence[Union[ParticulateSample, RawRecord]],
    required_components: Optional[Iterable[str]] = None,
) -> ValidationResult:
    """Validate particulate component samples."""

    normalized: List[ParticulateSample] = []
    issues: List[ValidationIssue] = []
    component_values: Dict[str, List[float]] = {}

    required = set(required_components or CORE_COMPONENTS)

    for idx, record in enumerate(records):
        try:
            sample, conversion_warnings = _coerce_sample(record)
        except ValueError as exc:
            issues.append(
                ValidationIssue(
                    level=ValidationSeverity.ERROR,
                    code="particulate.parse_failed",
                    message=str(exc),
                    index=idx,
                )
            )
            continue

        missing_components = required - set(sample.components.keys())
        if missing_components:
            issues.append(
                ValidationIssue(
                    level=ValidationSeverity.WARNING,
                    code="particulate.missing_required_component",
                    message=f"missing components: {', '.join(sorted(missing_components))}",
                    index=idx,
                )
            )

        if conversion_warnings:
            issues.append(
                ValidationIssue(
                    level=ValidationSeverity.WARNING,
                    code="particulate.invalid_numeric",
                    message=f"ignored invalid values for: {', '.join(conversion_warnings)}",
                    index=idx,
                )
            )

        for name, value in sample.components.items():
            component_values.setdefault(name, []).append(value)

        normalized.append(sample)

    total_records = len(records)
    valid_records = len(normalized)
    missing_rate = 0.0
    if total_records:
        missing_rate = (total_records - valid_records) / total_records

    field_stats = _build_component_stats(component_values, total_records)

    report = DataQualityReport(
        schema_type="particulate.v1",  # 修复字段名
        total_records=total_records,
        valid_records=valid_records,
        issues=issues,
        missing_rate=missing_rate,
        summary="颗粒物组分样本校验完成",
    )

    return ValidationResult(
        report=report,
        field_stats=field_stats,
        normalized_samples=normalized
    )


def _coerce_sample(
    record: Union[ParticulateSample, RawRecord]
) -> Tuple[ParticulateSample, List[str]]:
    if isinstance(record, ParticulateSample):
        return record, []

    data: Dict[str, Union[str, float, int, None]] = dict(record)

    station_name = _pick_value(
        data, ["station_name", "StationName", "stationName"]
    )
    station_code = _pick_value(
        data, ["station_code", "StationCode", "stationCode", "Code"]
    )

    if not station_name or not station_code:
        raise ValueError("station name or code missing")

    timestamp_raw = _pick_value(
        data, ["time", "TimePoint", "timestamp", "Timestamp"]
    )
    if not timestamp_raw:
        raise ValueError("timestamp missing")

    timestamp = _parse_timestamp(str(timestamp_raw))
    unit = data.get("unit") or data.get("Unit") or "ug_m3"

    conversion_warnings: List[str] = []
    components: Dict[str, float] = {}
    reserved_keys = {
        "station_name",
        "StationName",
        "stationName",
        "station_code",
        "StationCode",
        "stationCode",
        "Code",
        "time",
        "TimePoint",
        "timestamp",
        "Timestamp",
        "unit",
        "Unit",
        "DataType",
        "TimeType",
        "qc_flag",
        "QCFlag",
    }

    for key, raw_value in data.items():
        if key in reserved_keys:
            continue
        value = _to_float(raw_value)
        if value is None:
            if raw_value not in (None, "", "-", "—", "null", "NULL"):
                conversion_warnings.append(str(key))
            continue
        components[key.strip()] = value

    if not components:
        raise ValueError("component data empty")

    sample = ParticulateSample(
        station_code=station_code,
        station_name=station_name,
        timestamp=timestamp,
        components=components,
        unit=unit,
    )

    return sample, conversion_warnings


def _pick_value(data: Dict[str, Union[str, float, int, None]], keys: List[str]) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if value is None or value == "":
            continue
        return str(value)
    return None


def _parse_timestamp(value: str) -> datetime:
    cleaned = value.replace("T", " ")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value}") from exc


def _to_float(value: Union[str, float, int, None]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "—", "null", "NULL"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _build_component_stats(
    values: Dict[str, List[float]],
    total_records: int,
) -> Tuple[FieldStats, ...]:
    stats: List[FieldStats] = []
    for name, series in values.items():
        if not series:
            continue
        stats.append(
            FieldStats(
                name=name,
                minimum=min(series),
                maximum=max(series),
                mean=mean(series) if series else None,
                missing=total_records - len(series),
                total=total_records,
            )
        )
    stats.sort(key=lambda item: (item.missing_rate, item.name))
    return tuple(stats)
