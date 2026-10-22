"""Database reads for the Xuchang permit-source upwind tool."""

from __future__ import annotations

from datetime import datetime, timedelta
from math import cos, radians
from typing import Any

from sqlalchemy import select

from app.db.database import async_session
from app.db.models import ERA5ReanalysisData, ObservedWeatherData
from app.db.weather_database import weather_async_session
from app.fetchers.emission.permit_license_crawler.models import PermitLicense, PermitPollutionDetail
from app.services.data_registry import DataRegistryService, data_registry

from .inventory_asset import XUCHANG_INVENTORY_DATA_ID


class XuchangUpwindPermitRepository:
    def __init__(
        self,
        *,
        registry: DataRegistryService = data_registry,
        inventory_data_id: str = XUCHANG_INVENTORY_DATA_ID,
    ) -> None:
        self.registry = registry
        self.inventory_data_id = inventory_data_id
        self._inventory_records: list[dict[str, Any]] | None = None
        self._inventory_status: dict[str, Any] = {
            "status": "not_loaded",
            "data_id": inventory_data_id,
        }

    @staticmethod
    def _candidate_payload(
        license_row: PermitLicense,
        detail: PermitPollutionDetail | None,
    ) -> dict[str, Any]:
        return {
            "license_id": license_row.id,
            "permit_number": license_row.permit_number,
            "permit_numbers": [license_row.permit_number],
            "unified_social_credit_code": license_row.unified_social_credit_code,
            "enterprise_name": license_row.enterprise_name,
            "industry_category": license_row.industry_category,
            "production_site_address": license_row.production_site_address,
            "latitude": float(license_row.latitude),
            "longitude": float(license_row.longitude),
            "coordinate_source": license_row.coordinate_source,
            "coordinate_crs": license_row.coordinate_crs,
            "permit_status": license_row.current_status,
            "permit_pollutants": detail.air_pollutant_types if detail else None,
            "main_pollutant_categories": detail.main_pollutant_categories if detail else None,
            "inventory_emissions": None,
            "inventory_period": None,
            "inventory_sectors": [],
            "data_sources": ["permit_license"],
        }

    async def load_weather(
        self,
        *,
        station_ids: list[str],
        start_time: datetime,
        end_time: datetime,
        receptor_lat: float,
        receptor_lon: float,
    ) -> tuple[list[ObservedWeatherData], list[ERA5ReanalysisData]]:
        async with weather_async_session() as session:
            observed = await session.scalars(
                select(ObservedWeatherData)
                .where(
                    ObservedWeatherData.station_id.in_(station_ids),
                    ObservedWeatherData.time >= start_time,
                    ObservedWeatherData.time <= end_time,
                )
                .order_by(ObservedWeatherData.time)
            )
            # ERA5 is only a stability background. Restrict the query to the
            # receiver's surrounding grid cells instead of scanning all records.
            era5 = await session.scalars(
                select(ERA5ReanalysisData)
                .where(
                    ERA5ReanalysisData.time >= start_time,
                    ERA5ReanalysisData.time <= end_time,
                    ERA5ReanalysisData.lat.between(receptor_lat - 1.0, receptor_lat + 1.0),
                    ERA5ReanalysisData.lon.between(receptor_lon - 1.0, receptor_lon + 1.0),
                )
                .order_by(ERA5ReanalysisData.time)
            )
            return list(observed), list(era5)

    async def load_candidates(
        self,
        *,
        receptor_lat: float,
        receptor_lon: float,
        radius_km: float,
        include_emission_inventory: bool = False,
    ) -> list[dict[str, Any]]:
        # A conservative latitude/longitude bounding box reduces database work;
        # exact great-circle radius filtering remains in the calculation engine.
        lat_offset = radius_km / 111.0
        lon_offset = radius_km / max(1.0, 111.0 * abs(cos(radians(receptor_lat))))
        async with async_session() as session:
            rows = await session.execute(
                select(PermitLicense, PermitPollutionDetail)
                .outerjoin(PermitPollutionDetail, PermitPollutionDetail.license_id == PermitLicense.id)
                .where(
                    PermitLicense.current_status == "valid",
                    PermitLicense.latitude.is_not(None),
                    PermitLicense.longitude.is_not(None),
                    PermitLicense.latitude.between(receptor_lat - lat_offset, receptor_lat + lat_offset),
                    PermitLicense.longitude.between(receptor_lon - lon_offset, receptor_lon + lon_offset),
                )
            )
            permit_candidates = [
                self._candidate_payload(license_row, detail)
                for license_row, detail in rows.tuples()
            ]
        if not include_emission_inventory:
            return self._merge_candidates(permit_candidates, [])
        inventory_candidates = self._inventory_candidates_in_bounds(
            min_lat=receptor_lat - lat_offset,
            max_lat=receptor_lat + lat_offset,
            min_lon=receptor_lon - lon_offset,
            max_lon=receptor_lon + lon_offset,
        )
        return self._merge_candidates(permit_candidates, inventory_candidates)

    async def load_candidates_in_bounds(
        self,
        *,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
    ) -> list[dict[str, Any]]:
        """Load and merge permit and inventory sources in a trajectory box."""
        async with async_session() as session:
            rows = await session.execute(
                select(PermitLicense, PermitPollutionDetail)
                .outerjoin(PermitPollutionDetail, PermitPollutionDetail.license_id == PermitLicense.id)
                .where(
                    PermitLicense.current_status == "valid",
                    PermitLicense.latitude.is_not(None),
                    PermitLicense.longitude.is_not(None),
                    PermitLicense.latitude.between(min_lat, max_lat),
                    PermitLicense.longitude.between(min_lon, max_lon),
                )
            )
            permit_candidates = [
                self._candidate_payload(license_row, detail)
                for license_row, detail in rows.tuples()
            ]
        inventory_candidates = self._inventory_candidates_in_bounds(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
        )
        return self._merge_candidates(permit_candidates, inventory_candidates)

    def inventory_status(self) -> dict[str, Any]:
        return dict(self._inventory_status)

    def _inventory_candidates_in_bounds(
        self,
        *,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
    ) -> list[dict[str, Any]]:
        records = self._load_inventory_records()
        return [
            self._inventory_candidate(record)
            for record in records
            if min_lat <= float(record["latitude"]) <= max_lat
            and min_lon <= float(record["longitude"]) <= max_lon
        ]

    def _load_inventory_records(self) -> list[dict[str, Any]]:
        if self._inventory_records is not None:
            return self._inventory_records
        try:
            payload = self.registry.load_dataset(self.inventory_data_id)
            entry = self.registry.get_metadata(self.inventory_data_id)
        except (KeyError, OSError, ValueError) as exc:
            self._inventory_records = []
            self._inventory_status = {
                "status": "unavailable",
                "data_id": self.inventory_data_id,
                "reason": str(exc),
            }
            return self._inventory_records
        self._inventory_records = [
            record
            for record in payload
            if isinstance(record, dict)
            and record.get("longitude") is not None
            and record.get("latitude") is not None
        ]
        self._inventory_status = {
            "status": "available",
            "data_id": self.inventory_data_id,
            "record_count": len(self._inventory_records),
            "inventory_period": (entry.metadata or {}).get("inventory_period") if entry else None,
            "created_at": entry.created_at.isoformat() if entry else None,
        }
        return self._inventory_records

    @staticmethod
    def _inventory_candidate(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "license_id": None,
            "permit_number": None,
            "permit_numbers": [],
            "unified_social_credit_code": record.get("unified_social_credit_code"),
            "enterprise_name": record.get("enterprise_name") or "",
            "industry_category": record.get("industry_category") or "",
            "production_site_address": record.get("production_site_address") or "",
            "latitude": float(record["latitude"]),
            "longitude": float(record["longitude"]),
            "coordinate_source": record.get("coordinate_source"),
            "coordinate_crs": record.get("coordinate_crs") or "EPSG:4326",
            "permit_status": None,
            "permit_pollutants": None,
            "main_pollutant_categories": None,
            "inventory_emissions": record.get("inventory_emissions") or {},
            "inventory_period": record.get("inventory_period"),
            "inventory_sectors": record.get("inventory_sectors") or [],
            "inventory_source_id": record.get("source_id"),
            "coordinate_quality": record.get("coordinate_quality"),
            "data_sources": ["emission_inventory"],
        }

    @staticmethod
    def _merge_candidates(
        permit_candidates: list[dict[str, Any]],
        inventory_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for candidate in [*permit_candidates, *inventory_candidates]:
            credit_code = str(candidate.get("unified_social_credit_code") or "").strip().upper()
            key = (
                f"credit:{credit_code}"
                if credit_code
                else f"source:{candidate.get('license_id') or candidate.get('inventory_source_id')}"
            )
            current = merged.get(key)
            if current is None:
                merged[key] = dict(candidate)
                continue
            current["data_sources"] = sorted(
                set(current.get("data_sources") or []) | set(candidate.get("data_sources") or [])
            )
            current["permit_numbers"] = sorted(
                set(filter(None, current.get("permit_numbers") or []))
                | set(filter(None, candidate.get("permit_numbers") or []))
            )
            for field in ("permit_pollutants", "main_pollutant_categories"):
                values = [current.get(field), candidate.get(field)]
                current[field] = "、".join(dict.fromkeys(filter(None, values))) or None
            if candidate.get("inventory_emissions"):
                current["inventory_emissions"] = candidate["inventory_emissions"]
                current["inventory_period"] = candidate.get("inventory_period")
                current["inventory_sectors"] = candidate.get("inventory_sectors") or []
                current["inventory_source_id"] = candidate.get("inventory_source_id")
                if not current.get("industry_category"):
                    current["industry_category"] = candidate.get("industry_category")
            if "permit_license" in (candidate.get("data_sources") or []):
                # A current permit remains authoritative for enterprise identity and site address.
                for field in (
                    "license_id",
                    "permit_number",
                    "enterprise_name",
                    "production_site_address",
                    "latitude",
                    "longitude",
                    "coordinate_source",
                    "coordinate_crs",
                    "permit_status",
                ):
                    if candidate.get(field) is not None:
                        current[field] = candidate[field]
        return list(merged.values())

    async def load_historical_wind_speeds(
        self, *, station_id: str, event_hour: datetime
    ) -> list[tuple[datetime, float | None]]:
        """Load a small bounded history; same-hour filtering stays timezone-safe in Python."""
        start = event_hour - timedelta(days=365)
        async with weather_async_session() as session:
            records = await session.scalars(
                select(ObservedWeatherData).where(
                    ObservedWeatherData.station_id == station_id,
                    ObservedWeatherData.time >= start,
                    ObservedWeatherData.time < event_hour,
                )
            )
            return [(record.time, record.wind_speed_10m) for record in records]
