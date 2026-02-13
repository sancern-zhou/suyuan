from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Dict, Iterable, List, MutableMapping, Optional, Sequence, Tuple, Union

from pydantic import ValidationError

from app.schemas.common import (
    DataQualityReport,
    FieldStats,
    ValidationIssue,
    ValidationSeverity,
)
from app.schemas.vocs import VOCsSample
from .base import ValidationResult

RawRecord = MutableMapping[str, Union[str, float, int, None]]

ESSENTIAL_SPECIES = {"乙烯", "丙烯", "苯", "甲苯", "乙烷"}


def validate_vocs_samples(
    records: Sequence[Union[VOCsSample, RawRecord]],
    required_species: Optional[Iterable[str]] = None,
) -> ValidationResult:
    """Validate and normalize VOCs samples."""

    normalized_samples: List[VOCsSample] = []
    issues: List[ValidationIssue] = []
    species_values: Dict[str, List[float]] = {}

    required = set(required_species or ESSENTIAL_SPECIES)

    for idx, record in enumerate(records):
        try:
            sample, conversion_warnings = _coerce_sample(record)
        except ValidationError as exc:
            issues.append(
                ValidationIssue(
                    level=ValidationSeverity.ERROR,
                    code="vocs.schema_invalid",
                    message=str(exc).split("\n")[0],
                    index=idx,
                )
            )
            continue
        except ValueError as exc:
            issues.append(
                ValidationIssue(
                    level=ValidationSeverity.ERROR,
                    code="vocs.parse_failed",
                    message=str(exc),
                    index=idx,
                )
            )
            continue

        missing_species = required - set(sample.species.keys())
        if missing_species:
            issues.append(
                ValidationIssue(
                    level=ValidationSeverity.WARNING,
                    code="vocs.missing_required_species",
                    message=f"missing species: {', '.join(sorted(missing_species))}",
                    index=idx,
                )
            )

        if conversion_warnings:
            issues.append(
                ValidationIssue(
                    level=ValidationSeverity.WARNING,
                    code="vocs.invalid_numeric",
                    message=f"ignored invalid values for: {', '.join(conversion_warnings)}",
                    index=idx,
                )
            )

        for name, value in sample.species.items():
            species_values.setdefault(name, []).append(value)

        normalized_samples.append(sample)

    total_records = len(records)
    valid_records = len(normalized_samples)
    missing_rate = 0.0
    if total_records:
        missing_rate = (total_records - valid_records) / total_records

    field_stats = _build_species_stats(species_values, total_records)

    report = DataQualityReport(
        schema_type="vocs.v1",  # 修复字段名
        total_records=total_records,
        valid_records=valid_records,
        issues=issues,
        missing_rate=missing_rate,
        summary="VOCs 样本校验完成",
    )

    return ValidationResult(
        report=report,
        field_stats=field_stats,
        normalized_samples=normalized_samples
    )


def _coerce_sample(
    record: Union[VOCsSample, RawRecord]
) -> Tuple[VOCsSample, List[str]]:
    if isinstance(record, VOCsSample):
        return record, []

    # Defensive copy
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

    unit = data.get("unit") or data.get("Unit")

    species: Dict[str, float] = {}
    conversion_issues: List[str] = []

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
        "species_data",  # vocs_unified格式的嵌套物种数据
        "measurements",  # udf_v2.0格式的测量数据
    }

    for key, raw_value in data.items():
        if key in reserved_keys:
            continue
        value = _to_float(raw_value)
        if value is None:
            if raw_value not in (None, "", "-", "—", "null", "NULL"):
                conversion_issues.append(str(key))
            continue
        species[_normalize_species_name(key)] = value

    sample = VOCsSample(
        station_code=station_code,
        station_name=station_name,
        timestamp=timestamp,
        species=species,
        unit=unit or "ppb",
    )

    return sample, conversion_issues


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


def _normalize_species_name(name: str) -> str:
    # Preserve Chinese name, but strip whitespace.
    return name.strip()


def _build_species_stats(
    species_values: Dict[str, List[float]],
    total_records: int,
) -> Tuple[FieldStats, ...]:
    stats: List[FieldStats] = []
    for species, values in species_values.items():
        if not values:
            continue
        stats.append(
            FieldStats(
                name=species,
                minimum=min(values),
                maximum=max(values),
                mean=mean(values) if values else None,
                missing=total_records - len(values),
                total=total_records,
            )
        )

    # Sort by missing rate ascending, then by name.
    stats.sort(key=lambda item: (item.missing_rate, item.name))
    return tuple(stats)
