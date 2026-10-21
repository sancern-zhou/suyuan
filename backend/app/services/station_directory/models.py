"""Canonical station directory models shared across projects.

This module is the single source of truth for station metadata shape and
station-type normalisation.  Project-specific directory providers (air data
platform, provincial APIs, checked-in tables) convert their raw rows into
:class:`StationRecord` before returning them to tools, so every tool and
report sees the same field names and the same Chinese type labels.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum, StrEnum
from typing import Any


class StationCategory(StrEnum):
    """Broad station role, independent of the control level."""

    REGULAR = "regular"
    TOWNSHIP = "township"
    COMPONENT = "component"
    UNKNOWN = "unknown"


class StationType(StrEnum):
    """Canonical control-level labels used across projects."""

    NATIONAL = "国控"
    PROVINCIAL = "省控"
    MUNICIPAL = "市控"
    DISTRICT = "区县控"
    TOWNSHIP = "乡镇控"
    OTHER = "其他"
    BACKGROUND = "背景站"
    REGIONAL = "区域站"
    TRAFFIC = "交通站"
    SPECIAL = "专项站"


ALL_STATION_TYPES = "全部"

STATION_TYPE_BY_ID: dict[int, StationType] = {
    1: StationType.NATIONAL,
    2: StationType.PROVINCIAL,
    3: StationType.MUNICIPAL,
    4: StationType.DISTRICT,
    5: StationType.TOWNSHIP,
    6: StationType.OTHER,
    7: StationType.BACKGROUND,
    8: StationType.REGIONAL,
    9: StationType.TRAFFIC,
    15: StationType.SPECIAL,
}

STATION_TYPE_NAME_BY_ID: dict[int, str] = {
    key: value.value for key, value in STATION_TYPE_BY_ID.items()
}

STATION_CATEGORY_VALUES: frozenset[str] = frozenset(item.value for item in StationCategory)

_ALL_TYPE_ALIASES: frozenset[str] = frozenset({"全部", "所有", "all", "*", "any"})

_TYPE_ALIASES: dict[StationType, frozenset[str]] = {
    StationType.NATIONAL: frozenset(
        {"国控", "国家控", "国家级", "national", "nationalcontrol", "national_control", "1", "1.0"}
    ),
    StationType.PROVINCIAL: frozenset(
        {"省控", "省级", "provincial", "provincialcontrol", "provincial_control", "2", "2.0"}
    ),
    StationType.MUNICIPAL: frozenset(
        {"市控", "市级", "municipal", "municipalcontrol", "municipal_control", "3", "3.0"}
    ),
    StationType.DISTRICT: frozenset({"区县控", "区控", "县控", "district", "county", "4", "4.0"}),
    StationType.TOWNSHIP: frozenset({"乡镇控", "乡镇站", "乡镇", "5", "5.0"}),
    StationType.OTHER: frozenset({"其他", "other", "6", "6.0"}),
    StationType.BACKGROUND: frozenset({"背景站", "背景", "background", "7", "7.0"}),
    StationType.REGIONAL: frozenset({"区域站", "区域", "regional", "8", "8.0"}),
    StationType.TRAFFIC: frozenset({"交通站", "交通", "traffic", "9", "9.0"}),
    StationType.SPECIAL: frozenset({"专项站", "专项", "special", "15", "15.0"}),
}

_TYPE_NAME_KEYS: tuple[str, ...] = (
    "station_type_name",
    "stationTypeName",
    "StationTypeName",
    "typeName",
    "TypeName",
    "type_name",
    "站点类型名称",
    "站点类型",
)

_TYPE_ID_KEYS: tuple[str, ...] = (
    "station_type_id",
    "stationTypeId",
    "stationTypeID",
    "StationTypeId",
    "StationTypeID",
    "stationtypeid",
    "typeId",
    "typeID",
    "TypeId",
    "TypeID",
    "站点类型ID",
    "stationTypeCode",
    "station_type_code",
)

_TYPE_VALUE_KEYS: tuple[str, ...] = (
    "station_type",
    "stationType",
    "StationType",
    "站点类别",
    "station_category",
)

_CATEGORY_VALUE_KEYS: tuple[str, ...] = (
    "station_category",
    "stationCategory",
    "category",
    "站点类别",
)


def _token(value: Any) -> str:
    return "".join(str(value or "").strip().lower().split()).replace("－", "-")


def normalize_station_type(value: Any, *, allow_all: bool = False) -> str | None:
    """Return the canonical Chinese station type, or ``None`` when unknown."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, Mapping):
        value = value.get("name") or value.get("typeName") or value.get("id")
    token = _token(value)
    if not token:
        return None
    if token in _ALL_TYPE_ALIASES or token == _token(ALL_STATION_TYPES):
        return ALL_STATION_TYPES if allow_all else None
    for canonical, aliases in _TYPE_ALIASES.items():
        if token in aliases or token == _token(canonical.value):
            return canonical.value
    try:
        numeric = float(token)
    except (TypeError, ValueError):
        return None
    if numeric.is_integer():
        return STATION_TYPE_NAME_BY_ID.get(int(numeric))
    return None


def station_type_from_row(row: Mapping[str, Any]) -> str | None:
    """Extract a canonical station type from a raw directory row."""

    for key in _TYPE_NAME_KEYS + _TYPE_VALUE_KEYS:
        result = normalize_station_type(row.get(key))
        if result:
            return result
    for key in _TYPE_ID_KEYS:
        result = normalize_station_type(row.get(key))
        if result:
            return result
    return None


def normalize_station_category(value: Any) -> str | None:
    """Return a canonical station category value, or ``None`` when unknown."""

    if isinstance(value, Enum):
        value = value.value
    token = _token(value)
    if not token:
        return None
    if token in {item.value for item in StationCategory}:
        return token
    if token in {"乡镇站", "乡镇", "township"}:
        return StationCategory.TOWNSHIP.value
    if token in {"组分站", "组分", "component"}:
        return StationCategory.COMPONENT.value
    return None


def _first(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str:
    return str(value or "").strip()


def _to_domains(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Iterable):
        values = list(value)
    else:
        return ()
    return tuple(item for item in (_to_str(item) for item in values) if item)


@dataclass(frozen=True)
class StationRecord:
    """Canonical, provider-independent station metadata."""

    station_code: str
    station_name: str
    city: str = ""
    district: str = ""
    longitude: float | None = None
    latitude: float | None = None
    address: str = ""
    unique_code: str = ""
    admin_code: str = ""
    station_type: str = ""
    type_id: int | None = None
    station_category: str = StationCategory.REGULAR.value
    data_domains: tuple[str, ...] = field(default_factory=tuple)
    source: str = ""

    @property
    def type_name(self) -> str:
        return self.station_type or ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["type_name"] = self.station_type
        payload["data_domains"] = list(self.data_domains)
        return payload

    @classmethod
    def from_mapping(
        cls,
        row: Mapping[str, Any],
        *,
        source: str = "",
        station_category: str | None = None,
    ) -> StationRecord:
        """Build a record from a provider row using tolerant key aliases."""

        type_id_raw = _first(row, _TYPE_ID_KEYS)
        try:
            type_id = int(float(type_id_raw)) if type_id_raw not in (None, "") else None
        except (TypeError, ValueError):
            type_id = None

        station_type = (
            station_type_from_row(row)
            or (STATION_TYPE_NAME_BY_ID.get(type_id) if type_id is not None else None)
            or ""
        )

        resolved_category = station_category
        if resolved_category is None:
            resolved_category = normalize_station_category(_first(row, _CATEGORY_VALUE_KEYS))
        if resolved_category is None:
            resolved_category = normalize_station_category(_first(row, _TYPE_VALUE_KEYS))
        if resolved_category is None:
            resolved_category = StationCategory.UNKNOWN.value

        return cls(
            station_code=_to_str(
                _first(
                    row,
                    (
                        "station_code",
                        "stationCode",
                        "StationCode",
                        "stationcode",
                        "code",
                        "站点编码",
                    ),
                )
            ),
            station_name=_to_str(
                _first(
                    row,
                    (
                        "station_name",
                        "stationName",
                        "StationName",
                        "positionname",
                        "positionName",
                        "name",
                        "站点名称",
                    ),
                )
            ),
            city=_to_str(_first(row, ("city", "cityName", "city_name", "城市名称", "城市"))),
            district=_to_str(
                _first(row, ("district", "districtName", "district_name", "区县", "区县名称"))
            ),
            longitude=_to_float(_first(row, ("longitude", "lon", "lng", "Longitude", "经度"))),
            latitude=_to_float(_first(row, ("latitude", "lat", "Latitude", "纬度"))),
            address=_to_str(_first(row, ("address", "Address", "详细地址"))),
            unique_code=_to_str(
                _first(row, ("unique_code", "uniquecode", "uniqueCode", "唯一编码"))
            ),
            admin_code=_to_str(_first(row, ("admin_code", "areacode", "areaCode", "行政区划代码"))),
            station_type=station_type,
            type_id=type_id,
            station_category=resolved_category,
            data_domains=_to_domains(_first(row, ("data_domains", "dataDomains"))),
            source=source or _to_str(_first(row, ("source", "data_source", "dataSource"))),
        )
