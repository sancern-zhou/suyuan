"""Database reads for the Xuchang permit-source upwind tool."""

from __future__ import annotations

from datetime import datetime, timedelta
from math import cos, radians
from typing import Any

from sqlalchemy import select

from app.db.database import async_session
from app.db.weather_database import weather_async_session
from app.db.models import ERA5ReanalysisData, ObservedWeatherData
from app.fetchers.emission.permit_license_crawler.models import PermitLicense, PermitPollutionDetail


class XuchangUpwindPermitRepository:
    @staticmethod
    def _candidate_payload(
        license_row: PermitLicense,
        detail: PermitPollutionDetail | None,
    ) -> dict[str, Any]:
        return {
            "license_id": license_row.id,
            "permit_number": license_row.permit_number,
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

    async def load_candidates(self, *, receptor_lat: float, receptor_lon: float, radius_km: float) -> list[dict[str, Any]]:
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
            return [self._candidate_payload(license_row, detail) for license_row, detail in rows.tuples()]

    async def load_candidates_in_bounds(
        self,
        *,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
    ) -> list[dict[str, Any]]:
        """Load valid geocoded permits intersecting a trajectory coverage box."""
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
            return [self._candidate_payload(license_row, detail) for license_row, detail in rows.tuples()]

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
