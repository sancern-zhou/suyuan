"""Station-type normalization shared by Jiangsu station tools.

The provincial APIs have used slightly different names for the station type
field over time (and some deployments return the numeric id only).  Keep the
mapping in one place so the data and operations graph tools apply the same
classification rules.
"""

from __future__ import annotations

from typing import Any


STATION_TYPE_BY_ID = {
    1.0: "国控",
    2.0: "省控",
    3.0: "市控",
}

_ALIASES = {
    "国控": {"国控", "国家控", "国家级", "national", "nationalcontrol", "national_control", "1", "1.0"},
    "省控": {"省控", "省级", "provincial", "provincialcontrol", "provincial_control", "2", "2.0"},
    "市控": {"市控", "市级", "municipal", "municipalcontrol", "municipal_control", "3", "3.0"},
    "全部": {"全部", "所有", "all", "*"},
}

_TYPE_NAME_KEYS = (
    "stationTypeName",
    "StationTypeName",
    "station_type_name",
    "typeName",
    "TypeName",
    "站点类型",
    "站点类型名称",
)
_TYPE_ID_KEYS = (
    "stationTypeId",
    "stationTypeID",
    "StationTypeId",
    "StationTypeID",
    "typeId",
    "typeID",
    "TypeId",
    "TypeID",
    "站点类型ID",
    "station_type_id",
    "stationTypeCode",
    "station_type_code",
)
_TYPE_VALUE_KEYS = ("stationType", "StationType", "station_type", "站点类别", "station_category")


def _token(value: Any) -> str:
    return "".join(str(value or "").strip().lower().split()).replace("－", "-")


def normalize_station_type(value: Any, *, allow_all: bool = False) -> str | None:
    """Return the canonical Chinese station type, or ``None`` if unknown."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        value = value.get("name") or value.get("typeName") or value.get("id")
    token = _token(value)
    if not token:
        return None
    for canonical, aliases in _ALIASES.items():
        if token in aliases or token == _token(canonical):
            if canonical == "全部" and not allow_all:
                return None
            return canonical
    try:
        numeric = float(token)
    except (TypeError, ValueError):
        return None
    return STATION_TYPE_BY_ID.get(numeric)


def station_type_from_row(row: dict[str, Any]) -> str | None:
    """Extract a canonical type from a live directory row."""

    for key in _TYPE_NAME_KEYS + _TYPE_VALUE_KEYS:
        result = normalize_station_type(row.get(key))
        if result:
            return result
    for key in _TYPE_ID_KEYS:
        result = normalize_station_type(row.get(key))
        if result:
            return result
    return None


def filter_station_rows(
    rows: list[dict[str, Any]], requested_type: str | None, *, allow_all: bool = True
) -> tuple[list[dict[str, Any]], bool]:
    """Filter rows by type.

    ``applied`` is false when the upstream directory contains no recognizable
    type fields.  In that case retaining rows is safer and preserves backward
    compatibility with older deployments whose directory endpoint omitted the
    field; callers can surface the unavailable classification in metadata.
    """

    requested = normalize_station_type(requested_type, allow_all=allow_all)
    if requested in (None, "全部"):
        return rows, False
    typed_rows = [(row, station_type_from_row(row)) for row in rows]
    if not any(kind for _, kind in typed_rows):
        return rows, False
    return [row for row, kind in typed_rows if kind == requested], True
