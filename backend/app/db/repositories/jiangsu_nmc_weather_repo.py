"""Persistence for Jiangsu-project NMC observed weather records."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.db.database import async_session, engine
from app.db.models import JiangsuNMCObservedWeatherData


class JiangsuNMCWeatherRepository:
    """Create and upsert the project-owned administrative weather table."""

    def __init__(self) -> None:
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with self._schema_lock:
            if self._schema_ready:
                return
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync_connection: JiangsuNMCObservedWeatherData.__table__.create(
                        sync_connection,
                        checkfirst=True,
                    )
                )
            self._schema_ready = True

    async def save_records(self, records: Iterable[Any]) -> int:
        values = [record.to_dict() for record in records]
        if not values:
            return 0

        await self.ensure_schema()
        async with async_session() as session:
            statement = insert(JiangsuNMCObservedWeatherData).values(values)
            statement = statement.on_conflict_do_update(
                index_elements=["time", "station_id"],
                set_={
                    "province_name": statement.excluded.province_name,
                    "city_code": statement.excluded.city_code,
                    "city_name": statement.excluded.city_name,
                    "district_code": statement.excluded.district_code,
                    "district_name": statement.excluded.district_name,
                    "location_level": statement.excluded.location_level,
                    "nmc_location_name": statement.excluded.nmc_location_name,
                    "forecast_url": statement.excluded.forecast_url,
                    "temperature_2m": statement.excluded.temperature_2m,
                    "relative_humidity_2m": statement.excluded.relative_humidity_2m,
                    "wind_speed_10m": statement.excluded.wind_speed_10m,
                    "wind_direction_10m": statement.excluded.wind_direction_10m,
                    "surface_pressure": statement.excluded.surface_pressure,
                    "precipitation": statement.excluded.precipitation,
                    "data_source": statement.excluded.data_source,
                    "data_quality": statement.excluded.data_quality,
                    "updated_at": statement.excluded.updated_at,
                },
            )
            await session.execute(statement)
            await session.commit()
        return len(values)

    @staticmethod
    def _area_candidates(values: Iterable[str], suffixes: tuple[str, ...]) -> set[str]:
        candidates: set[str] = set()
        for value in values:
            raw = str(value or "").strip().replace(" ", "")
            if not raw:
                continue
            base = raw.rstrip("省市区县")
            candidates.add(raw)
            candidates.add(base)
            candidates.update(f"{base}{suffix}" for suffix in suffixes)
        return candidates

    @classmethod
    def _area_conditions(
        cls,
        *,
        city_names: Iterable[str] = (),
        district_names: Iterable[str] = (),
    ) -> list[Any]:
        conditions: list[Any] = []
        city_candidates = cls._area_candidates(city_names, ("市",))
        district_candidates = cls._area_candidates(
            district_names,
            ("区", "县", "市"),
        )
        if city_candidates:
            conditions.append(JiangsuNMCObservedWeatherData.city_name.in_(city_candidates))
        if district_candidates:
            conditions.append(
                JiangsuNMCObservedWeatherData.district_name.in_(district_candidates)
            )
        return conditions

    async def get_area_targets(
        self,
        *,
        city_names: Iterable[str] = (),
        district_names: Iterable[str] = (),
    ) -> list[dict[str, Any]]:
        """Return compact station metadata for matching administrative areas."""
        conditions = self._area_conditions(
            city_names=city_names,
            district_names=district_names,
        )
        if not conditions:
            return []
        await self.ensure_schema()
        async with async_session() as session:
            statement = (
                select(
                    JiangsuNMCObservedWeatherData.station_id,
                    JiangsuNMCObservedWeatherData.city_code,
                    JiangsuNMCObservedWeatherData.city_name,
                    JiangsuNMCObservedWeatherData.district_code,
                    JiangsuNMCObservedWeatherData.district_name,
                    JiangsuNMCObservedWeatherData.location_level,
                    JiangsuNMCObservedWeatherData.nmc_location_name,
                )
                .where(or_(*conditions))
                .distinct()
                .order_by(
                    JiangsuNMCObservedWeatherData.city_code,
                    JiangsuNMCObservedWeatherData.district_code,
                    JiangsuNMCObservedWeatherData.station_id,
                )
            )
            result = await session.execute(statement)
            return [dict(row) for row in result.mappings().all()]

    async def get_area_observed_data(
        self,
        *,
        start_time: Any,
        end_time: Any,
        city_names: Iterable[str] = (),
        district_names: Iterable[str] = (),
    ) -> list[JiangsuNMCObservedWeatherData]:
        """Query observations by city or district without exposing station IDs."""
        conditions = self._area_conditions(
            city_names=city_names,
            district_names=district_names,
        )
        if not conditions:
            return []
        await self.ensure_schema()
        async with async_session() as session:
            statement = (
                select(JiangsuNMCObservedWeatherData)
                .where(
                    or_(*conditions),
                    JiangsuNMCObservedWeatherData.time >= start_time,
                    JiangsuNMCObservedWeatherData.time <= end_time,
                )
                .order_by(
                    JiangsuNMCObservedWeatherData.time,
                    JiangsuNMCObservedWeatherData.city_code,
                    JiangsuNMCObservedWeatherData.district_code,
                    JiangsuNMCObservedWeatherData.station_id,
                )
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
