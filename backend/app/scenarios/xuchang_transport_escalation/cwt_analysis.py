"""Concentration-weighted trajectory analysis for accumulated Scenario 3 samples."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.integrations.xcai_station_sql import xcai_connection_string

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
POLLUTANT_COLUMNS = {"PM2.5": "pm25", "O3": "o3", "NOX": "no2"}


class XuchangStationConcentrationLoader:
    """Load receptor concentrations only when a CWT archive is ready to calculate."""

    def load(
        self,
        *,
        station_id: str,
        pollutant: str,
        event_hours: list[str],
    ) -> dict[str, float]:
        if not event_hours:
            return {}
        import pyodbc

        column = POLLUTANT_COLUMNS[pollutant]
        parsed_hours = sorted(datetime.fromisoformat(value) for value in set(event_hours))
        start = parsed_hours[0].astimezone(TZ_SHANGHAI).replace(tzinfo=None)
        end = parsed_hours[-1].astimezone(TZ_SHANGHAI).replace(tzinfo=None)
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT data_time, {column} AS concentration
                FROM dbo.dat_station_hour
                WHERE station_id = ? AND data_time >= ? AND data_time <= ?
                ORDER BY data_time
                """,  # noqa: S608 - column is selected from the fixed mapping above.
                [station_id, start, end],
            )
            result = {}
            requested = set(event_hours)
            for data_time, concentration in cursor.fetchall():
                if concentration is None or float(concentration) < 0:
                    continue
                key = data_time.replace(tzinfo=TZ_SHANGHAI).isoformat()
                if key in requested:
                    result[key] = float(concentration)
            return result
        finally:
            connection.close()


def _trajectory_residence_hours(
    endpoints: list[dict[str, Any]], grid_resolution_deg: float
) -> dict[tuple[int, int], float]:
    ordered = sorted(endpoints, key=lambda item: abs(float(item.get("age_hours", 0))))
    residence: dict[tuple[int, int], float] = defaultdict(float)
    for first, second in zip(ordered, ordered[1:], strict=False):
        duration = abs(float(second.get("age_hours", 0)) - float(first.get("age_hours", 0)))
        if duration <= 0:
            continue
        lat_delta = float(second["lat"]) - float(first["lat"])
        lon_delta = float(second["lon"]) - float(first["lon"])
        steps = max(
            1,
            math.ceil(max(abs(lat_delta), abs(lon_delta)) / grid_resolution_deg),
        )
        step_hours = duration / steps
        for index in range(steps):
            ratio = (index + 0.5) / steps
            lat = float(first["lat"]) + lat_delta * ratio
            lon = float(first["lon"]) + lon_delta * ratio
            cell = (
                math.floor(lat / grid_resolution_deg),
                math.floor(lon / grid_resolution_deg),
            )
            residence[cell] += step_hours
    return dict(residence)


def _cell_weight(trajectory_count: int, average_count: float) -> float:
    if average_count <= 0:
        return 0.0
    if trajectory_count > 3 * average_count:
        return 1.0
    if trajectory_count > 1.5 * average_count:
        return 0.7
    if trajectory_count > average_count:
        return 0.4
    return 0.2


def calculate_wcwt(
    samples: list[dict[str, Any]],
    *,
    heights_m_agl: list[int],
    backtrack_hours: int,
    grid_resolution_deg: float = 0.1,
    minimum_trajectories_per_height: int = 30,
    high_value_limit: int = 10,
) -> dict[str, Any]:
    """Calculate residence-time WCWT separately for every configured start height."""
    valid_samples = [
        sample
        for sample in samples
        if isinstance(sample.get("concentration"), (int, float))
        and float(sample["concentration"]) >= 0
    ]
    height_results = {}
    all_ready = True
    for trajectory_id, height in enumerate(heights_m_agl, 1):
        cell_stats: dict[tuple[int, int], dict[str, Any]] = defaultdict(
            lambda: {
                "weighted_concentration_hours": 0.0,
                "residence_hours": 0.0,
                "trajectory_keys": set(),
            }
        )
        valid_trajectory_count = 0
        for sample in valid_samples:
            endpoints = [
                endpoint
                for endpoint in sample.get("endpoints", [])
                if int(endpoint.get("trajectory_id", 1)) == trajectory_id
            ]
            coverage = max(
                (abs(float(item.get("age_hours", 0))) for item in endpoints),
                default=0.0,
            )
            if coverage < backtrack_hours * 0.8:
                continue
            residence = _trajectory_residence_hours(endpoints, grid_resolution_deg)
            if not residence:
                continue
            valid_trajectory_count += 1
            concentration = float(sample["concentration"])
            sample_key = sample["arrival_time"]
            for cell, residence_hours in residence.items():
                stats = cell_stats[cell]
                stats["weighted_concentration_hours"] += concentration * residence_hours
                stats["residence_hours"] += residence_hours
                stats["trajectory_keys"].add(sample_key)

        ready = valid_trajectory_count >= minimum_trajectories_per_height
        all_ready = all_ready and ready
        average_count = (
            sum(len(item["trajectory_keys"]) for item in cell_stats.values()) / len(cell_stats)
            if cell_stats
            else 0.0
        )
        cells = []
        for (lat_index, lon_index), stats in cell_stats.items():
            residence_hours = stats["residence_hours"]
            cwt = stats["weighted_concentration_hours"] / residence_hours
            trajectory_count = len(stats["trajectory_keys"])
            weight = _cell_weight(trajectory_count, average_count)
            min_lat = lat_index * grid_resolution_deg
            min_lon = lon_index * grid_resolution_deg
            cells.append(
                {
                    "min_lat": round(min_lat, 6),
                    "min_lon": round(min_lon, 6),
                    "max_lat": round(min_lat + grid_resolution_deg, 6),
                    "max_lon": round(min_lon + grid_resolution_deg, 6),
                    "center_lat": round(min_lat + grid_resolution_deg / 2, 6),
                    "center_lon": round(min_lon + grid_resolution_deg / 2, 6),
                    "trajectory_count": trajectory_count,
                    "residence_hours": round(residence_hours, 3),
                    "cwt": round(cwt, 3),
                    "sample_weight": weight,
                    "wcwt": round(cwt * weight, 3),
                }
            )
        cells.sort(key=lambda item: (item["wcwt"], item["trajectory_count"]), reverse=True)
        height_results[str(height)] = {
            "status": "ready" if ready else "insufficient_samples",
            "valid_trajectory_count": valid_trajectory_count,
            "minimum_trajectory_count": minimum_trajectories_per_height,
            "occupied_grid_count": len(cells),
            "average_trajectories_per_grid": round(average_count, 3),
            "high_value_cells": cells[:high_value_limit] if ready else [],
            "cells": cells if ready else [],
        }

    return {
        "status": "completed" if all_ready and height_results else "accumulating_samples",
        "method": "residence_time_weighted_cwt_with_low_sample_weight",
        "grid_resolution_deg": grid_resolution_deg,
        "backtrack_hours": backtrack_hours,
        "concentration_sample_count": len(valid_samples),
        "heights": height_results,
        "interpretation_limit": (
            "WCWT表示经过网格的气团与受体浓度的统计关联，单位与受体浓度一致；"
            "不表示网格排放量、贡献率或企业责任。"
        ),
    }
