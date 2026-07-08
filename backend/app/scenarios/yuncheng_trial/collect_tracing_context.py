from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.scenarios.yuncheng_trial.config import YUNCHENG_TRIAL_CONFIG

REQUIRED_ASSETS: dict[str, str] = {
    "target_city_pollutants": "target_city_pollutants.json",
    "nearby_city_pollutants": "nearby_city_pollutants.json",
    "meteorology_history": "meteorology_history.json",
    "trajectory_analysis": "trajectory_analysis.json",
    "trajectory_image": "trajectory.png",
    "hourly_wind_field_image": "wind_field.png",
    "precipitation_forecast_image": "precipitation_forecast.png",
    "national_max_temperature_forecast_image": "national_tmax_forecast.png",
    "forecast_meteorology": "forecast_meteorology.json",
    "air_quality_5day_forecast": "air_quality_5day_forecast.json",
}

ToolRunner = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


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
        "asset_requests": _build_asset_requests(start=start, end=end),
        "missing_assets": [],
        "fetch_errors": [],
        "suggested_evidence_gaps": [],
        "limitations": [
            "未接入运城市本地污染源清单、企业门禁、卡口、移动源轨迹和执法巡查数据。",
            "第一版未接入站点小时数据，不能开展同城站点偏差和站点趋势一致性判断。",
            "本报告只能形成提示性来源研判，不能确认具体污染源。",
        ],
    }


def _build_asset_requests(start: datetime, end: datetime) -> dict[str, dict[str, Any]]:
    date_text = end.strftime("%Y%m%d")
    wind_hour = min(max(end.hour, 0), 7)
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
            "tool": "get_weather_data",
            "data_type": "era5",
            "lat": YUNCHENG_TRIAL_CONFIG.lat,
            "lon": YUNCHENG_TRIAL_CONFIG.lon,
            "start_time": _format_time(start),
            "end_time": _format_time(end),
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
            "date": date_text,
            "time": f"{wind_hour:02d}",
            "download": True,
        },
        "precipitation_forecast_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "precip_forecast_24h",
            "date": date_text,
            "time": "024",
            "download": True,
        },
        "national_max_temperature_forecast_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
            "product": "national_max_temperature_forecast",
            "date": date_text,
            "time": "024",
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
        "air_quality_5day_forecast": {
            "kind": "json",
            "tool": "execute_sql_query",
            "purpose": "WeatherForecast7Day future 5-day air quality forecast",
            "city": YUNCHENG_TRIAL_CONFIG.city,
            "days": 5,
        },
    }


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
        return f"yuncheng_trial_{schema}:{datetime.now().strftime('%H%M%S%f')}"

    def get_data(self, data_id):
        return None


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
        if tool_name == "execute_sql_query":
            from app.tools.query.execute_sql_query.tool import ExecuteSQLQueryTool

            city = str(request["city"]).replace("'", "''")
            sql = (
                "SELECT TOP 5 TimePoint, cityname, MinAqi, MaxAqi, MaxPollution, "
                "WeatherCondition, Temperature, WindLevel, WindDirection "
                "FROM WeatherForecast7Day "
                f"WHERE cityname = N'{city}' "
                "AND TimePoint IS NOT NULL "
                "AND UpdateDate = ("
                "SELECT MAX(UpdateDate) FROM WeatherForecast7Day "
                f"WHERE cityname = N'{city}' AND TimePoint IS NOT NULL"
                ") "
                "ORDER BY TimePoint"
            )
            return await ExecuteSQLQueryTool().execute(context=context, sql=sql, database="XcAiDb", limit=5)
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    return {"success": False, "error": f"Unsupported tool: {tool_name}"}


async def collect_required_assets(
    manifest: dict[str, Any],
    output_dir: Path,
    tool_runner: ToolRunner,
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
            payload = result.get("data", result)
            target_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
                encoding="utf-8",
            )

    manifest_path = output_dir / "tracing_context_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return manifest_path


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
    parser.add_argument("--latest-alert", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    manifest_path = asyncio.run(
        collect_from_alert_file(
            alert_path=Path(args.latest_alert),
            output_dir=Path(args.output_dir),
        )
    )
    print(f"TRACING_CONTEXT_MANIFEST:{manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
