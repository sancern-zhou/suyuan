"""Shared rendering helpers for station directory tools.

Every project directory provider converts its raw source into
:class:`StationRecord`; tools then render records with these helpers so stage
tools expose identical field names and ordering regardless of the underlying
system (ops ledger, monitoring platform snapshot, component mapping).
"""

from __future__ import annotations

from typing import Any, Iterable

from .models import StationRecord


def record_to_payload(record: StationRecord) -> dict[str, Any]:
    """Render one canonical station record as a stable tool payload."""

    return {
        "station_code": record.station_code,
        "station_name": record.station_name,
        "city": record.city,
        "district": record.district,
        "station_type": record.station_type,
        "station_category": record.station_category,
        "data_domains": list(record.data_domains),
        "longitude": record.longitude,
        "latitude": record.latitude,
        "address": record.address,
        "unique_code": record.unique_code,
        "admin_code": record.admin_code,
    }


def records_to_payload(
    records: Iterable[StationRecord],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Render records in order, applying an optional hard limit."""

    payload: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if limit is not None and index >= limit:
            break
        payload.append(record_to_payload(record))
    return payload
