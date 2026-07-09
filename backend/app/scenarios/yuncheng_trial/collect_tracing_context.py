from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.scenarios.yuncheng_trial.config import YUNCHENG_TRIAL_CONFIG
from app.scenarios.yuncheng_trial.fire_hotspot_assets import build_fire_hotspot_summary, render_fire_hotspot_map

REQUIRED_ASSETS: dict[str, str] = {
    "target_city_pollutants": "target_city_pollutants.json",
    "nearby_city_pollutants": "nearby_city_pollutants.json",
    "meteorology_history": "meteorology_history.json",
    "trajectory_analysis": "trajectory_analysis.json",
    "trajectory_image": "trajectory.png",
    "hourly_wind_field_image": "wind_field.png",
    "precipitation_forecast_image": "precipitation_forecast.png",
    "wind_forecast_24h_image": "wind_forecast_024.png",
    "wind_forecast_48h_image": "wind_forecast_048.png",
    "wind_forecast_72h_image": "wind_forecast_072.png",
    "precipitation_forecast_24h_image": "precipitation_forecast_024.png",
    "precipitation_forecast_48h_image": "precipitation_forecast_048.png",
    "precipitation_forecast_72h_image": "precipitation_forecast_072.png",
    "national_max_temperature_forecast_image": "national_tmax_forecast.png",
    "national_min_temperature_forecast_image": "national_tmin_forecast.png",
    "visibility_image": "visibility.png",
    "rainfall_24h_image": "rainfall_24h.png",
    "radar_mosaic_image": "radar_mosaic.png",
    "radar_composite_reflectivity_image": "radar_composite_reflectivity_003.png",
    "precipitable_water_image": "precipitable_water_000.png",
    "hourly_precipitation_forecast_image": "hourly_precipitation_forecast.png",
    "fire_hotspots": "fire_hotspots.json",
    "fire_hotspots_summary": "fire_hotspots_summary.json",
    "fire_hotspots_map_image": "fire_hotspots_map.png",
    "forecast_meteorology": "forecast_meteorology.json",
    "air_quality_24h_forecast": "air_quality_24h_forecast.json",
}

ToolRunner = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

_SIMPLE_CONTEXT_DATA: dict[str, Any] = {}

AIR_QUALITY_FORECAST_CITY_CODE = "140800"
AIR_QUALITY_FORECAST_TABLE = "dbo.OpenMeteoAirQualityForecast72h"
AIR_QUALITY_FORECAST_BASE_FIELDS = ["forecast_time", "city_name", "city_code", "aqi", "primary_pollutant"]
AIR_QUALITY_FORECAST_POLLUTANT_ORDER = ["pm25", "pm10", "o3", "no2", "co"]
AIR_QUALITY_FORECAST_THRESHOLDS = {
    "pm25": YUNCHENG_TRIAL_CONFIG.pm25_watch_level,
    "pm10": YUNCHENG_TRIAL_CONFIG.pm10_watch_level,
    "o3": YUNCHENG_TRIAL_CONFIG.o3_watch_level,
    "no2": YUNCHENG_TRIAL_CONFIG.no2_watch_level,
    "co": YUNCHENG_TRIAL_CONFIG.co_watch_level,
}


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _format_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def build_context_manifest(alert: dict[str, Any]) -> dict[str, Any]:
    end = _parse_time(alert["target_time"])
    lookback_hours = int(alert.get("lookback_hours") or YUNCHENG_TRIAL_CONFIG.default_lookback_hours)
    start = end - timedelta(hours=lookback_hours)

    return {
        "alert_id": alert["alert_id"],
        "city": alert.get("city", YUNCHENG_TRIAL_CONFIG.city),
        "nearby_cities": YUNCHENG_TRIAL_CONFIG.nearby_cities,
        "target_pollutant": alert["target_pollutant"],
        "analysis_window": {
            "start": _format_time(start),
            "end": _format_time(end),
        },
        "assets": dict(REQUIRED_ASSETS),
        "asset_requests": _build_asset_requests(start=start, end=end, alert=alert),
        "missing_assets": [],
        "fetch_errors": [],
        "suggested_evidence_gaps": [],
        "limitations": [
            "未接入运城市本地污染源清单、企业门禁、卡口、移动源轨迹和执法巡查数据。",
            "第一版未接入站点小时数据，不能开展同城站点偏差和站点趋势一致性判断。",
            "本报告只能形成提示性来源研判，不能确认具体污染源。",
        ],
    }


def _build_asset_requests(start: datetime, end: datetime, alert: dict[str, Any]) -> dict[str, dict[str, Any]]:
    wind_date, wind_hour = _platform_hourly_wind_slot(end)
    visibility_date, visibility_hour = _platform_visibility_slot(end)
    rainfall_date, rainfall_hour = _platform_rainfall_24h_slot(end)
    radar_date, radar_time = _platform_radar_mosaic_slot(end)
    precip_date, precip_forecast_hour = _platform_precip_forecast_slot(end)
    forecast_image_date = _platform_forecast_image_run_date(end)
    fire_start = end - timedelta(hours=6)
    return {
        "target_city_pollutants": {
            "kind": "json",
            "tool": "query_xcai_city_history",
            "cities": [YUNCHENG_TRIAL_CONFIG.city],
            "data_type": "hour",
            "start_time": _format_time(start),
            "end_time": _format_time(end),
        },
        "nearby_city_pollutants": {
            "kind": "json",
            "tool": "query_xcai_city_history",
            "cities": YUNCHENG_TRIAL_CONFIG.nearby_cities,
            "data_type": "hour",
            "start_time": _format_time(start),
            "end_time": _format_time(end),
        },
        "meteorology_history": {
            "kind": "json",
            "tool": "get_weather_forecast",
            "lat": YUNCHENG_TRIAL_CONFIG.lat,
            "lon": YUNCHENG_TRIAL_CONFIG.lon,
            "location_name": YUNCHENG_TRIAL_CONFIG.city,
            "forecast_days": 1,
            "past_days": 1,
            "hourly": True,
            "daily": False,
        },
        "trajectory_analysis": {
            "kind": "trajectory_analysis",
            "tool": "meteorological_trajectory_analysis",
            "lat": YUNCHENG_TRIAL_CONFIG.lat,
            "lon": YUNCHENG_TRIAL_CONFIG.lon,
            "start_time": _format_time(end),
            "hours": 72,
            "heights": [10, 500, 1000],
            "direction": "Backward",
        },
        "trajectory_image": {
            "kind": "sidecar",
            "source_asset": "trajectory_analysis",
        },
        "hourly_wind_field_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "hourly_wind_field",
            "date": wind_date,
            "time": wind_hour,
            "download": True,
        },
        "precipitation_forecast_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "***REMOVED***",
            "date": precip_date,
            "time": precip_forecast_hour,
            "download": True,
        },
        "wind_forecast_24h_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "***REMOVED***",
            "date": forecast_image_date,
            "time": "024",
            "download": True,
        },
        "wind_forecast_48h_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "***REMOVED***",
            "date": forecast_image_date,
            "time": "048",
            "download": True,
        },
        "wind_forecast_72h_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "***REMOVED***",
            "date": forecast_image_date,
            "time": "072",
            "download": True,
        },
        "precipitation_forecast_24h_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "***REMOVED***",
            "date": forecast_image_date,
            "time": "024",
            "download": True,
        },
        "precipitation_forecast_48h_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "***REMOVED***",
            "date": forecast_image_date,
            "time": "048",
            "download": True,
        },
        "precipitation_forecast_72h_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "***REMOVED***",
            "date": forecast_image_date,
            "time": "072",
            "download": True,
        },
        "national_max_temperature_forecast_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "national_max_temperature_forecast",
            "date": forecast_image_date,
            "time": "024",
            "download": True,
        },
        "national_min_temperature_forecast_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "national_min_temperature_forecast",
            "date": forecast_image_date,
            "time": "024",
            "download": True,
        },
        "visibility_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "visibility",
            "date": visibility_date,
            "time": visibility_hour,
            "download": True,
        },
        "rainfall_24h_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "rainfall_24h",
            "date": rainfall_date,
            "time": rainfall_hour,
            "download": True,
        },
        "radar_mosaic_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "radar_mosaic",
            "date": radar_date,
            "time": radar_time,
            "download": True,
        },
        "radar_composite_reflectivity_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "radar_composite_reflectivity",
            "date": forecast_image_date,
            "time": "003",
            "download": True,
        },
        "precipitable_water_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "precipitable_water",
            "date": forecast_image_date,
            "time": "000",
            "download": True,
        },
        "hourly_precipitation_forecast_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "hourly_precip_forecast",
            "date": forecast_image_date,
            "time": _platform_hourly_precip_forecast_time(end),
            "download": True,
        },
        "forecast_meteorology": {
            "kind": "json",
            "tool": "get_weather_forecast",
            "lat": YUNCHENG_TRIAL_CONFIG.lat,
            "lon": YUNCHENG_TRIAL_CONFIG.lon,
            "location_name": YUNCHENG_TRIAL_CONFIG.city,
            "forecast_days": 5,
            "past_days": 1,
            "hourly": True,
            "daily": True,
        },
        "fire_hotspots": {
            "kind": "json",
            "tool": "get_fire_hotspots",
            "region": {
                "min_lat": 33.5,
                "max_lat": 36.6,
                "min_lon": 109.3,
                "max_lon": 112.7,
            },
            "start_time": _format_time(fire_start),
            "end_time": _format_time(end),
            "min_confidence": 50,
        },
        "fire_hotspots_summary": {
            "kind": "sidecar",
            "source_asset": "fire_hotspots",
        },
        "fire_hotspots_map_image": {
            "kind": "sidecar",
            "source_asset": "fire_hotspots",
        },
        "air_quality_24h_forecast": {
            "kind": "json",
            "tool": "execute_sql_query",
            "purpose": "OpenMeteoAirQualityForecast72h future 24-hour AQI and triggered/exceeded pollutant forecast",
            "city": YUNCHENG_TRIAL_CONFIG.city,
            "city_code": AIR_QUALITY_FORECAST_CITY_CODE,
            "start_time": _format_time(end),
            "end_time": _format_time(end + timedelta(hours=24)),
            "triggered_pollutants": _triggered_pollutants_from_alert(alert),
            "pollutant_thresholds": dict(AIR_QUALITY_FORECAST_THRESHOLDS),
            "sql": _build_air_quality_24h_forecast_sql(
                city_code=AIR_QUALITY_FORECAST_CITY_CODE,
                start_time=end,
                end_time=end + timedelta(hours=24),
            ),
        },
    }


def _build_air_quality_24h_forecast_sql(city_code: str, start_time: datetime, end_time: datetime) -> str:
    return (
        "SELECT forecast_time, city_name, city_code, aqi, primary_pollutant, "
        "pm25, pm10, o3, no2, co "
        f"FROM {AIR_QUALITY_FORECAST_TABLE} "
        f"WHERE city_code = N'{city_code}' "
        f"AND forecast_time > '{_format_time(start_time)}' "
        f"AND forecast_time <= '{_format_time(end_time)}' "
        "ORDER BY forecast_time"
    )


def _triggered_pollutants_from_alert(alert: dict[str, Any]) -> list[str]:
    pollutants: list[str] = []
    for hit in alert.get("rule_hits") or []:
        if not isinstance(hit, dict):
            continue
        pollutant = _pollutant_from_rule_id(str(hit.get("rule_id") or ""))
        if pollutant and pollutant not in pollutants:
            pollutants.append(pollutant)

    target_pollutant = _normalize_forecast_pollutant(alert.get("target_pollutant"))
    if target_pollutant and target_pollutant not in pollutants:
        pollutants.append(target_pollutant)

    return pollutants


def _pollutant_from_rule_id(rule_id: str) -> str | None:
    if rule_id.startswith("pm25"):
        return "pm25"
    if rule_id.startswith("pm10"):
        return "pm10"
    if rule_id.startswith("o3"):
        return "o3"
    if rule_id.startswith("no2"):
        return "no2"
    if rule_id.startswith("co"):
        return "co"
    return None


def _normalize_forecast_pollutant(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace(".", "").replace("_", "")
    aliases = {
        "pm25": "pm25",
        "pm10": "pm10",
        "o3": "o3",
        "no2": "no2",
        "co": "co",
    }
    return aliases.get(normalized)


def _platform_hourly_wind_slot(alert_time: datetime) -> tuple[str, str]:
    event_utc = alert_time - timedelta(hours=8)
    platform_hour = min(max(event_utc.hour, 0), 7)
    return event_utc.strftime("%Y%m%d"), f"{platform_hour:02d}"


def _platform_visibility_slot(alert_time: datetime) -> tuple[str, str]:
    event_utc = alert_time - timedelta(hours=8)
    return event_utc.strftime("%Y%m%d"), f"{event_utc.hour:02d}"


def _platform_rainfall_24h_slot(alert_time: datetime) -> tuple[str, str]:
    event_utc = alert_time - timedelta(hours=8)
    for hour in (12, 6, 0):
        if event_utc.hour >= hour:
            return event_utc.strftime("%Y%m%d"), f"{hour:02d}"
    previous_day = event_utc - timedelta(days=1)
    return previous_day.strftime("%Y%m%d"), "12"


def _platform_radar_mosaic_slot(alert_time: datetime) -> tuple[str, str]:
    event_utc = alert_time - timedelta(hours=8)
    radar_time = event_utc.replace(second=0, microsecond=0)
    radar_time -= timedelta(minutes=radar_time.minute % 6)
    if radar_time.hour < 8:
        radar_time = (event_utc - timedelta(days=1)).replace(hour=23, minute=36, second=0, microsecond=0)
    elif radar_time.hour == 23 and radar_time.minute > 36:
        radar_time = radar_time.replace(minute=36)
    return radar_time.strftime("%Y%m%d"), radar_time.strftime("%H:%M")


def _platform_precip_forecast_slot(alert_time: datetime) -> tuple[str, str]:
    event_utc = alert_time - timedelta(hours=8)
    forecast_hour = 24 + event_utc.hour
    return _platform_forecast_image_run_date(alert_time), f"{forecast_hour:03d}"


def _platform_hourly_precip_forecast_time(alert_time: datetime) -> str:
    event_utc = alert_time - timedelta(hours=8)
    for forecast_hour in (6, 12, 18, 24):
        if event_utc.hour <= forecast_hour:
            return f"{forecast_hour:02d}"
    return "24"


def _platform_forecast_image_run_date(alert_time: datetime) -> str:
    event_utc = alert_time - timedelta(hours=8)
    forecast_run = event_utc - timedelta(days=1)
    return forecast_run.strftime("%Y%m%d")


def create_tool_request(manifest: dict[str, Any], asset_name: str) -> dict[str, Any]:
    requests = manifest.get("asset_requests") or {}
    if asset_name not in requests:
        raise KeyError(f"Unknown Yuncheng tracing asset: {asset_name}")
    return dict(requests[asset_name])


def _extract_image_content(result: dict[str, Any]) -> bytes | None:
    content = result.get("content")
    if isinstance(content, str):
        return content.encode("utf-8")
    if isinstance(content, bytes):
        return content

    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    for path_value in (result.get("file_path"), data.get("local_path")):
        content = _read_image_path(path_value)
        if content:
            return content

    for image_ref in _iter_visual_image_refs(result.get("visuals")):
        content = _read_image_path(image_ref.get("local_path") or image_ref.get("file_path"))
        if content:
            return content
        image_id = image_ref.get("image_id") or _image_id_from_url(image_ref.get("image_url") or image_ref.get("url"))
        if image_id:
            content = _read_image_cache(image_id)
            if content:
                return content
    return None


def _iter_visual_image_refs(visuals: Any) -> list[dict[str, Any]]:
    if not isinstance(visuals, list):
        return []

    refs: list[dict[str, Any]] = []
    for visual in visuals:
        if not isinstance(visual, dict):
            continue
        refs.append(visual)
        for key in ("payload", "data", "meta", "metadata"):
            nested = visual.get(key)
            if isinstance(nested, dict):
                refs.append(nested)
    return refs


def _read_image_path(path_value: Any) -> bytes | None:
    if not path_value:
        return None
    source = Path(str(path_value))
    if source.exists():
        return source.read_bytes()
    return None


def _image_id_from_url(url_value: Any) -> str | None:
    if not isinstance(url_value, str):
        return None
    marker = "/api/image/"
    if marker not in url_value:
        return None
    return url_value.rsplit(marker, 1)[-1].split("?", 1)[0].strip("/") or None


def _read_image_cache(image_id: str) -> bytes | None:
    try:
        from app.services.image_cache import get_image_cache

        return get_image_cache().get_image_bytes(image_id)
    except Exception:
        return None


class SimpleToolContext:
    """Minimal context compatible with existing context-aware tools."""

    def __init__(self, session_id: str = "yuncheng_trial_context"):
        self.session_id = session_id
        self.iteration = 1

    @property
    def data_manager(self):
        return self

    def save_data(self, data, schema, metadata=None):
        data_id = f"yuncheng_trial_{schema}:{datetime.now().strftime('%H%M%S%f')}"
        _SIMPLE_CONTEXT_DATA[data_id] = data
        return data_id

    def get_data(self, data_id):
        return _SIMPLE_CONTEXT_DATA.get(data_id)


async def default_tool_runner(asset_name: str, request: dict[str, Any]) -> dict[str, Any]:
    context = SimpleToolContext(session_id=f"yuncheng_trial_{asset_name}")
    tool_name = request.get("tool")
    try:
        if tool_name == "query_xcai_city_history":
            from app.tools.query.query_xcai_city_history import QueryXcAiCityHistoryTool

            return await QueryXcAiCityHistoryTool().execute(
                context=context,
                cities=request["cities"],
                data_type=request["data_type"],
                start_time=request["start_time"],
                end_time=request["end_time"],
            )
        if tool_name == "get_weather_data":
            from app.tools.query.get_weather_data.tool import GetWeatherDataTool

            return await GetWeatherDataTool().execute(
                context=context,
                data_type=request["data_type"],
                lat=request["lat"],
                lon=request["lon"],
                start_time=request["start_time"],
                end_time=request["end_time"],
            )
        if tool_name == "get_platform_weather_image":
            from app.tools.query.get_platform_weather_image import GetPlatformWeatherImageTool

            return await GetPlatformWeatherImageTool().execute(
                product=request["product"],
                date=request["date"],
                time=request["time"],
                download=request.get("download", True),
            )
        if tool_name == "meteorological_trajectory_analysis":
            from app.tools.analysis.meteorological_trajectory_analysis.tool import (
                MeteorologicalTrajectoryAnalysisTool,
            )

            return await MeteorologicalTrajectoryAnalysisTool().execute(
                context=context,
                lat=request["lat"],
                lon=request["lon"],
                start_time=request.get("start_time"),
                hours=request.get("hours", 72),
                heights=request.get("heights", [10, 500, 1000]),
                direction=request.get("direction", "Backward"),
                meteo_source=request.get("meteo_source", "gdas1"),
            )
        if tool_name == "get_weather_forecast":
            from app.tools.query.get_weather_forecast import GetWeatherForecastTool

            return await GetWeatherForecastTool().execute(
                context=context,
                lat=request["lat"],
                lon=request["lon"],
                location_name=request["location_name"],
                forecast_days=request["forecast_days"],
                past_days=request["past_days"],
                hourly=request["hourly"],
                daily=request["daily"],
            )
        if tool_name == "get_fire_hotspots":
            from app.tools.query.get_fire_hotspots import GetFireHotspotsTool

            return await GetFireHotspotsTool().execute(
                region=request["region"],
                start_time=request["start_time"],
                end_time=request["end_time"],
                min_confidence=request.get("min_confidence", 50),
            )
        if tool_name == "execute_sql_query":
            from app.tools.query.execute_sql_query.tool import ExecuteSQLQueryTool

            return await ExecuteSQLQueryTool().execute(
                context=context,
                sql=request["sql"],
                database=request.get("database", "XcAiDb"),
                limit=request.get("limit", 100),
            )
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    return {"success": False, "error": f"Unsupported tool: {tool_name}"}


async def collect_required_assets(
    manifest: dict[str, Any],
    output_dir: Path,
    tool_runner: ToolRunner,
    data_context: Any | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    requests = manifest.get("asset_requests") or {}

    for asset_name, filename in manifest["assets"].items():
        request = requests.get(asset_name, {"kind": "json"})
        if request.get("kind") == "sidecar":
            continue

        result = await tool_runner(asset_name, request)
        if not result.get("success"):
            _record_missing(manifest, asset_name, result.get("error") or "tool returned no data")
            if request.get("kind") == "trajectory_analysis":
                _record_missing(manifest, "trajectory_image", "trajectory analysis failed")
            continue

        target_path = output_dir / filename
        if request.get("kind") == "trajectory_analysis":
            target_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, default=_json_default),
                encoding="utf-8",
            )
            image_content = _extract_image_content(result)
            if image_content:
                trajectory_filename = manifest.get("assets", {}).get("trajectory_image", "trajectory.png")
                (output_dir / trajectory_filename).write_bytes(image_content)
            else:
                _record_missing(manifest, "trajectory_image", "tool returned no trajectory image")
        elif request.get("kind") == "image":
            content = _extract_image_content(result)
            if not content:
                _record_missing(manifest, asset_name, "tool returned no file")
                continue
            target_path.write_bytes(content)
        else:
            payload = _resolve_json_payload(result, data_context=data_context)
            if asset_name == "air_quality_24h_forecast":
                payload = create_air_quality_24h_forecast_payload(result, request, data_context=data_context)
            target_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
                encoding="utf-8",
            )
            if asset_name == "fire_hotspots":
                _write_fire_hotspot_sidecars(
                    manifest=manifest,
                    payload=payload,
                    output_dir=output_dir,
                    request=request,
                )

    manifest_path = output_dir / "tracing_context_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return manifest_path


def _write_fire_hotspot_sidecars(
    *,
    manifest: dict[str, Any],
    payload: Any,
    output_dir: Path,
    request: dict[str, Any],
) -> None:
    if not isinstance(payload, dict):
        _record_missing(manifest, "fire_hotspots_summary", "fire hotspot payload is not a JSON object")
        _record_missing(manifest, "fire_hotspots_map_image", "fire hotspot payload is not a JSON object")
        return
    try:
        alert_time = _parse_time(str(request["end_time"]))
        summary = build_fire_hotspot_summary(payload, alert_time=alert_time)
        map_summary = build_fire_hotspot_summary(payload, alert_time=alert_time, max_hotspots=10_000)
        summary_filename = manifest.get("assets", {}).get("fire_hotspots_summary", "fire_hotspots_summary.json")
        map_filename = manifest.get("assets", {}).get("fire_hotspots_map_image", "fire_hotspots_map.png")
        (output_dir / summary_filename).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        render_fire_hotspot_map(map_summary, output_dir / map_filename, bbox=request["region"])
    except Exception as exc:
        _record_missing(manifest, "fire_hotspots_summary", str(exc))
        _record_missing(manifest, "fire_hotspots_map_image", str(exc))


def create_air_quality_24h_forecast_payload(
    result: dict[str, Any],
    request: dict[str, Any],
    data_context: Any | None = None,
) -> dict[str, Any]:
    payload = _resolve_json_payload(result, data_context=data_context)
    rows = _extract_forecast_rows(payload)
    threshold_exceeded = _threshold_exceeded_pollutants(rows, request.get("pollutant_thresholds") or {})
    triggered = [
        pollutant
        for pollutant in request.get("triggered_pollutants") or []
        if pollutant in AIR_QUALITY_FORECAST_POLLUTANT_ORDER
    ]
    selected_pollutants = []
    for pollutant in triggered + threshold_exceeded:
        if pollutant in AIR_QUALITY_FORECAST_POLLUTANT_ORDER and pollutant not in selected_pollutants:
            selected_pollutants.append(pollutant)

    return {
        "source_table": AIR_QUALITY_FORECAST_TABLE,
        "city": request.get("city"),
        "city_code": request.get("city_code"),
        "forecast_window": {
            "start_exclusive": request.get("start_time"),
            "end_inclusive": request.get("end_time"),
            "hours": 24,
        },
        "base_fields": list(AIR_QUALITY_FORECAST_BASE_FIELDS),
        "pollutant_fields": selected_pollutants,
        "selection_basis": {
            "triggered_pollutants": triggered,
            "threshold_exceeded_pollutants": threshold_exceeded,
            "pollutant_thresholds": request.get("pollutant_thresholds") or {},
        },
        "rows": [_select_forecast_row_fields(row, selected_pollutants) for row in rows],
    }


def _extract_forecast_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("records", "rows", "result", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _threshold_exceeded_pollutants(rows: list[dict[str, Any]], thresholds: dict[str, Any]) -> list[str]:
    exceeded: list[str] = []
    for pollutant in AIR_QUALITY_FORECAST_POLLUTANT_ORDER:
        threshold = _as_float(thresholds.get(pollutant))
        if threshold is None:
            continue
        if any((_as_float(row.get(pollutant)) or 0) >= threshold for row in rows):
            exceeded.append(pollutant)
    return exceeded


def _select_forecast_row_fields(row: dict[str, Any], pollutants: list[str]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for field in AIR_QUALITY_FORECAST_BASE_FIELDS + pollutants:
        if field in row:
            selected[field] = row[field]
    return selected


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_json_payload(result: dict[str, Any], data_context: Any | None = None) -> Any:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    data_id = metadata.get("data_id")
    total_records = metadata.get("total_records")
    returned_records = metadata.get("returned_records")
    if data_id and _is_preview_payload(total_records, returned_records):
        full_data = _get_context_data(data_context, str(data_id))
        if full_data is not None:
            return full_data
    return result.get("data", result)


def _is_preview_payload(total_records: Any, returned_records: Any) -> bool:
    try:
        return int(total_records) > int(returned_records)
    except (TypeError, ValueError):
        return False


def _get_context_data(data_context: Any | None, data_id: str) -> Any:
    for context in (data_context, SimpleToolContext()):
        if context is None or not hasattr(context, "get_data"):
            continue
        data = context.get_data(data_id)
        if data is not None:
            return data
    return None


def _record_missing(manifest: dict[str, Any], asset_name: str, reason: str) -> None:
    manifest.setdefault("missing_assets", []).append(asset_name)
    manifest.setdefault("fetch_errors", []).append({
        "source": asset_name,
        "severity": "warning",
        "error": reason,
    })
    manifest.setdefault("suggested_evidence_gaps", []).append({
        "priority": "medium",
        "evidence": asset_name,
        "reason": f"{asset_name}缺失：{reason}。相关机制判断置信度需要下调。",
    })


async def collect_from_alert_file(alert_path: Path, output_dir: Path) -> Path:
    alert = json.loads(alert_path.read_text(encoding="utf-8"))
    manifest = build_context_manifest(alert)
    return await collect_required_assets(manifest, output_dir, default_tool_runner)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Yuncheng alert tracing context.")
    parser.add_argument("--alert-json", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    manifest_path = asyncio.run(
        collect_from_alert_file(
            alert_path=Path(args.alert_json),
            output_dir=Path(args.output_dir),
        )
    )
    print(f"TRACING_CONTEXT_MANIFEST:{manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
