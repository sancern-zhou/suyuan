from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable


ToolRunner = Callable[..., Awaitable[dict[str, Any]]]


class PollutionEventEvidenceEnhancer:
    def __init__(
        self,
        *,
        tool_runner: ToolRunner | None = None,
        include_trajectory: bool = True,
        include_upwind_enterprises: bool = True,
        include_component_models: bool = True,
        include_synoptic_weather: bool = True,
    ) -> None:
        self.tool_runner = tool_runner or self._run_real_tool
        self.include_trajectory = include_trajectory
        self.include_upwind_enterprises = include_upwind_enterprises
        self.include_component_models = include_component_models
        self.include_synoptic_weather = include_synoptic_weather

    async def enhance(
        self,
        *,
        context: Any,
        city: str,
        event: dict[str, Any],
        event_dir: Path,
        station_records: list[dict[str, Any]],
        weather_records: list[dict[str, Any]],
        component_results: dict[str, Any],
        fetch_start: datetime,
        fetch_end: datetime,
    ) -> dict[str, Any]:
        event_dir.mkdir(parents=True, exist_ok=True)
        branch = self._branch_for(event.get("main_pollutant"))
        target_station = self._target_station(station_records, event.get("main_pollutant"))
        errors: list[dict[str, Any]] = []

        trajectory = await self._run_trajectory(
            context=context,
            event_dir=event_dir,
            target_station=target_station,
            fetch_end=fetch_end,
            errors=errors,
        )
        upwind = await self._run_upwind(
            context=context,
            event_dir=event_dir,
            city=city,
            target_station=target_station,
            weather_records=weather_records,
            errors=errors,
        )
        component_analysis = await self._run_component_analysis(
            context=context,
            event_dir=event_dir,
            branch=branch,
            target_station=target_station,
            main_pollutant=event.get("main_pollutant"),
            component_results=component_results,
            errors=errors,
        )
        synoptic_weather = await self._run_synoptic_weather(
            event_dir=event_dir,
            city=city,
            branch=branch,
            fetch_end=fetch_end,
            errors=errors,
        )

        return {
            "schema_version": "pollution_event_auto_analysis/v1",
            "main_pollutant_branch": branch,
            "target_station": target_station,
            "trajectory": trajectory,
            "upwind_enterprises": upwind,
            "component_analysis": component_analysis,
            "synoptic_weather": synoptic_weather,
            "analysis_errors": errors,
        }

    def _branch_for(self, pollutant: Any) -> str:
        normalized = str(pollutant or "").upper().replace(".", "_").replace("-", "_")
        if normalized in {"PM2_5", "PM25", "PM10"}:
            return "pm"
        if normalized in {"O3", "O3_8H"}:
            return "o3"
        if normalized in {"NO2", "SO2", "CO"}:
            return "gas"
        return "unknown"

    def _target_station(self, records: list[dict[str, Any]], pollutant: Any) -> dict[str, Any]:
        aliases = self._pollutant_aliases(pollutant)
        candidates = []
        for record in records:
            value = self._record_value(record, aliases)
            lat = self._first_present(record, ["lat", "latitude", "station_lat", "Latitude"])
            lon = self._first_present(record, ["lon", "lng", "longitude", "station_lon", "Longitude"])
            if value is None:
                continue
            candidates.append((float(value), record, lat, lon))
        candidates.sort(key=lambda item: item[0], reverse=True)
        for value, record, lat, lon in candidates:
            station_name = self._station_name(record)
            if lat is not None and lon is not None:
                return {
                    "station_name": station_name,
                    "lat": float(lat),
                    "lon": float(lon),
                    "main_pollutant_peak": value,
                    "peak_time": str(record.get("time") or record.get("timestamp") or ""),
                    "selection_reason": "highest_station_peak",
                }
            station_coords = self._station_coordinates(station_name)
            if station_coords:
                return {
                    "station_name": station_name,
                    "lat": station_coords["lat"],
                    "lon": station_coords["lon"],
                    "main_pollutant_peak": value,
                    "peak_time": str(record.get("time") or record.get("timestamp") or ""),
                    "selection_reason": "highest_station_peak_geo_backfill",
                }
        return {"selection_reason": "missing_station_location"}

    def _station_name(self, record: dict[str, Any]) -> str:
        return str(record.get("station_name") or record.get("station") or record.get("name") or "")

    def _station_coordinates(self, station_name: str) -> dict[str, float] | None:
        if not station_name:
            return None
        try:
            from app.utils.geo_matcher import get_geo_matcher

            station = get_geo_matcher().station_index.get(station_name)
        except Exception:
            return None
        if not station:
            return None
        lat = station.get("lat") or station.get("latitude") or station.get("纬度")
        lon = station.get("lon") or station.get("lng") or station.get("longitude") or station.get("经度")
        if lat is None or lon is None:
            return None
        try:
            return {"lat": float(lat), "lon": float(lon)}
        except (TypeError, ValueError):
            return None

    def _pollutant_aliases(self, pollutant: Any) -> list[str]:
        key = str(pollutant or "")
        normalized = key.upper().replace(".", "_").replace("-", "_")
        if normalized in {"O3", "O3_8H"}:
            return ["O3", "o3", "O3_8h", "o3_8h", "O3-8h"]
        if normalized in {"PM2_5", "PM25"}:
            return ["PM2_5", "PM2.5", "pm25", "pm2_5"]
        if normalized == "PM10":
            return ["PM10", "pm10"]
        aliases = [key, key.replace(".", "_"), key.replace("_", "."), key.upper(), key.lower()]
        return list(dict.fromkeys(item for item in aliases if item))

    def _record_value(self, record: dict[str, Any], aliases: list[str]) -> float | None:
        measurements = record.get("measurements") if isinstance(record.get("measurements"), dict) else {}
        for alias in aliases:
            for container in (record, measurements):
                value = container.get(alias)
                if value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        return None
        return None

    def _first_present(self, record: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            value = record.get(key)
            if value is not None:
                return value
        return None

    async def _run_trajectory(
        self,
        *,
        context: Any,
        event_dir: Path,
        target_station: dict[str, Any],
        fetch_end: datetime,
        errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.include_trajectory:
            return {"status": "skipped", "reason": "disabled"}
        if target_station.get("lat") is None or target_station.get("lon") is None:
            errors.append({
                "stage": "trajectory",
                "code": "missing_station_location",
                "severity": "warning",
                "message": "No station coordinates available.",
            })
            return {"status": "skipped", "reason": "missing_station_location"}
        return await self._safe_tool_call(
            "trajectory",
            "meteorological_trajectory_analysis",
            event_dir / "trajectory_analysis.json",
            errors=errors,
            context=context,
            lat=target_station["lat"],
            lon=target_station["lon"],
            start_time=fetch_end.isoformat(sep=" "),
            hours=72,
            direction="Backward",
        )

    async def _run_upwind(
        self,
        *,
        context: Any,
        event_dir: Path,
        city: str,
        target_station: dict[str, Any],
        weather_records: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.include_upwind_enterprises:
            return {"status": "skipped", "reason": "disabled"}
        weather_data_id = self._weather_data_id(weather_records, context)
        if not weather_data_id:
            errors.append({
                "stage": "upwind_enterprises",
                "code": "missing_weather_data_id",
                "severity": "warning",
                "message": "No weather data_id available for upwind enterprise analysis.",
            })
            return {"status": "skipped", "reason": "missing_weather_data_id"}
        return await self._safe_tool_call(
            "upwind_enterprises",
            "analyze_upwind_enterprises",
            event_dir / "upwind_enterprises.json",
            errors=errors,
            context=context,
            city_name=city,
            station_name=target_station.get("station_name") or None,
            weather_data_id=weather_data_id,
            weather_records=weather_records,
            output_dir=str(event_dir / "assets" / "images"),
        )

    async def _run_component_analysis(
        self,
        *,
        context: Any,
        event_dir: Path,
        branch: str,
        target_station: dict[str, Any],
        main_pollutant: Any,
        component_results: dict[str, Any],
        errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        outputs: list[dict[str, Any]] = []
        if not self.include_component_models:
            return {"status": "skipped", "branch": branch, "outputs": outputs}
        component_dir = event_dir / "component_analysis"
        component_dir.mkdir(parents=True, exist_ok=True)
        refs = component_results.get("data_refs") if isinstance(component_results.get("data_refs"), dict) else {}
        station_name = target_station.get("station_name") or "unknown_station"
        if branch == "pm":
            pm_data_id = refs.get("pm25_components_data_id")
            outputs.append(await self._component_tool(
                "calculate_pm_pmf",
                component_dir / "pm_pmf.json",
                errors=errors,
                context=context,
                station_name=station_name,
                data_id=pm_data_id,
                pollutant_type=str(main_pollutant or "PM2.5").replace("_", "."),
            ))
            outputs.append(await self._component_tool("calculate_reconstruction", component_dir / "reconstruction.json", errors=errors, context=context, data_id=pm_data_id))
        elif branch == "o3":
            vocs_data_id = refs.get("vocs_components_data_id")
            outputs.append(await self._component_tool(
                "calculate_vocs_pmf",
                component_dir / "vocs_pmf.json",
                errors=errors,
                context=context,
                station_name=station_name,
                data_id=vocs_data_id,
            ))
        else:
            return {"status": "skipped", "branch": branch, "outputs": outputs}
        success_count = sum(1 for item in outputs if item.get("status") == "success")
        status = "success" if success_count == len(outputs) else "partial" if success_count else "failed"
        return {"status": status, "branch": branch, "outputs": outputs}

    async def _run_synoptic_weather(
        self,
        *,
        event_dir: Path,
        city: str,
        branch: str,
        fetch_end: datetime,
        errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.include_synoptic_weather:
            return {"status": "skipped", "reason": "disabled", "images": []}
        output_path = event_dir / "synoptic_weather_images.json"
        images: list[dict[str, Any]] = []
        image_errors: list[dict[str, Any]] = []
        for request in self._synoptic_weather_requests(city=city, branch=branch, fetch_end=fetch_end):
            request_errors: list[dict[str, Any]] = []
            result = await self._safe_tool_call(
                "synoptic_weather",
                "get_platform_weather_image",
                event_dir / f"synoptic_weather_{request['product']}_{request['date']}_{request['time']}.json",
                errors=request_errors,
                product=request["product"],
                date=request["date"],
                time=request["time"],
                download=True,
            )
            if result.get("status") == "success":
                image = self._synoptic_image_record(request, result)
                if image:
                    images.append(image)
            else:
                image_errors.append({
                    "product": request["product"],
                    "date": request["date"],
                    "time": request["time"],
                    "summary": result.get("summary"),
                    "details": request_errors,
                })

        status = "success" if images else "failed" if image_errors else "skipped"
        if status == "failed":
            errors.append({
                "stage": "synoptic_weather",
                "code": "weather_images_unavailable",
                "severity": "warning",
                "message": "No platform weather images were fetched.",
            })
        payload = {
            "status": status,
            "images": images,
            "errors": image_errors,
            "policy": "Use local_path images in report.qmd for large-scale meteorological background and forecast outlook.",
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return {**payload, "file": str(output_path)}

    def _synoptic_weather_requests(self, *, city: str, branch: str, fetch_end: datetime) -> list[dict[str, str]]:
        date_key = fetch_end.strftime("%Y%m%d")
        requests = [
            {"product": "hourly_wind_field", "date": date_key, "time": self._hourly_wind_time(fetch_end), "analysis_role": "historical_context"},
            {"product": "rainfall_24h", "date": date_key, "time": "00", "analysis_role": "historical_context"},
            {"product": "visibility", "date": date_key, "time": f"{fetch_end.hour:02d}", "analysis_role": "historical_context"},
            {"product": "***REMOVED***", "date": date_key, "time": "024", "analysis_role": "forecast_outlook"},
            {"product": "***REMOVED***", "date": date_key, "time": "048", "analysis_role": "forecast_outlook"},
            {"product": "***REMOVED***", "date": date_key, "time": "072", "analysis_role": "forecast_outlook"},
            {"product": "***REMOVED***", "date": date_key, "time": "024", "analysis_role": "forecast_outlook"},
            {"product": "***REMOVED***", "date": date_key, "time": "048", "analysis_role": "forecast_outlook"},
            {"product": "***REMOVED***", "date": date_key, "time": "072", "analysis_role": "forecast_outlook"},
            {"product": "forecast_trajectory", "date": (fetch_end + timedelta(days=1)).strftime("%Y%m%d"), "time": city, "analysis_role": "forecast_outlook"},
        ]
        if branch == "o3":
            requests.extend([
                {"product": "national_max_temperature_forecast", "date": date_key, "time": "024", "analysis_role": "forecast_outlook"},
                {"product": "national_max_temperature_forecast", "date": date_key, "time": "048", "analysis_role": "forecast_outlook"},
                {"product": "national_max_temperature_forecast", "date": date_key, "time": "072", "analysis_role": "forecast_outlook"},
            ])
        return requests

    def _hourly_wind_time(self, fetch_end: datetime) -> str:
        return f"{min(max(fetch_end.hour, 0), 7):02d}"

    def _synoptic_image_record(self, request: dict[str, str], result: dict[str, Any]) -> dict[str, Any] | None:
        data = result.get("raw_data") if isinstance(result.get("raw_data"), dict) else None
        if data is None:
            data = {}
        source_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        if not source_data:
            return None
        return {
            "analysis_role": request["analysis_role"],
            "product": source_data.get("product") or request["product"],
            "product_name": source_data.get("product_name"),
            "date": source_data.get("date") or request["date"],
            "time_key": source_data.get("time_key") or request["time"],
            "local_path": source_data.get("local_path"),
            "image_url": source_data.get("image_url"),
            "downloaded": source_data.get("downloaded"),
            "source": source_data.get("source"),
            "summary": result.get("summary"),
        }

    async def _component_tool(self, name: str, output_path: Path, errors: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        if not kwargs.get("data_id"):
            errors.append({
                "stage": "component_analysis",
                "code": "missing_component_data_id",
                "severity": "warning",
                "message": f"{name} skipped because component data_id is missing.",
            })
            return {"name": name, "status": "skipped", "reason": "missing_data_id"}
        return await self._safe_tool_call("component_analysis", name, output_path, errors=errors, **kwargs)

    async def _safe_tool_call(
        self,
        stage: str,
        name: str,
        output_path: Path,
        errors: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            result = await self.tool_runner(name, **kwargs)
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            status = "success" if result.get("success", True) is not False else "failed"
            if status == "failed":
                errors.append({
                    "stage": stage,
                    "code": "tool_returned_failure",
                    "severity": "error",
                    "message": result.get("summary") or f"{name} returned failure.",
                })
            response = {
                "name": name,
                "status": status,
                "tool": name,
                "data_id": result.get("data_id"),
                "file": str(output_path),
                "summary": result.get("summary"),
                "raw_data": result,
            }
            if name == "analyze_upwind_enterprises":
                response["top_enterprises"] = self._extract_top_enterprises(result)
                response["map_images"] = self._extract_map_images(result)
            return response
        except Exception as exc:
            errors.append({
                "stage": stage,
                "code": "tool_call_failed",
                "severity": "error",
                "message": f"{name} failed: {exc}",
            })
            return {"name": name, "status": "failed", "tool": name, "file": str(output_path), "summary": str(exc)}

    def _extract_top_enterprises(self, result: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        enterprises: list[dict[str, Any]] = []
        for visual in result.get("visuals") or []:
            if not isinstance(visual, dict):
                continue
            payload = visual.get("payload") if isinstance(visual.get("payload"), dict) else {}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            station = data.get("station") if isinstance(data.get("station"), dict) else {}
            station_name = station.get("name")
            for enterprise in data.get("enterprises") or []:
                if not isinstance(enterprise, dict):
                    continue
                enterprises.append({
                    "station_name": station_name,
                    "name": enterprise.get("name"),
                    "industry": enterprise.get("industry"),
                    "distance_km": self._round_number(enterprise.get("distance_km"), 3),
                    "lat": self._round_number(enterprise.get("lat"), 6),
                    "lng": self._round_number(enterprise.get("lng"), 6),
                    "hit_ratio": self._round_number(enterprise.get("hit_ratio"), 6),
                    "score_sum": self._round_number(enterprise.get("score_sum"), 6),
                    "emissions": enterprise.get("emissions"),
                })
        enterprises.sort(
            key=lambda item: (
                self._sort_number(item.get("score_sum")),
                self._sort_number(item.get("hit_ratio")),
                self._sort_number((item.get("emissions") or {}).get("VOCs") if isinstance(item.get("emissions"), dict) else None),
            ),
            reverse=True,
        )
        return [
            {"rank": index + 1, **enterprise}
            for index, enterprise in enumerate(enterprises[:limit])
        ]

    def _extract_map_images(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        existing = result.get("map_images")
        if isinstance(existing, list) and existing:
            return [item for item in existing if isinstance(item, dict)]
        images: list[dict[str, Any]] = []
        for visual in result.get("visuals") or []:
            if not isinstance(visual, dict):
                continue
            payload = visual.get("payload") if isinstance(visual.get("payload"), dict) else {}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            local_path = data.get("map_local_path") or data.get("local_path")
            if not local_path:
                continue
            images.append({
                "station_name": (data.get("station") or {}).get("name") if isinstance(data.get("station"), dict) else None,
                "map_url": data.get("map_url") or data.get("public_url"),
                "local_path": str(local_path),
                "visual_id": visual.get("id") or payload.get("id"),
            })
        return images

    def _sort_number(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("-inf")

    def _round_number(self, value: Any, digits: int) -> Any:
        try:
            return round(float(value), digits)
        except (TypeError, ValueError):
            return value

    def _weather_data_id(self, weather_records: list[dict[str, Any]], context: Any = None) -> str | None:
        for record in weather_records:
            for key in ("data_id", "weather_data_id"):
                value = record.get(key)
                if value:
                    return str(value)
        if weather_records and context is not None and hasattr(context, "save_data"):
            ref = context.save_data(
                weather_records,
                schema="pollution_event_weather",
                metadata={"source": "pollution_event_evidence_enhancer"},
            )
            if isinstance(ref, str):
                return ref
            if isinstance(ref, dict) and ref.get("data_id"):
                return str(ref["data_id"])
            data_id = getattr(ref, "data_id", None)
            if data_id:
                return str(data_id)
            return str(ref)
        return None

    def supported_tool_names(self) -> list[str]:
        return [
            "meteorological_trajectory_analysis",
            "analyze_upwind_enterprises",
            "calculate_pm_pmf",
            "calculate_reconstruction",
            "calculate_vocs_pmf",
            "get_platform_weather_image",
        ]

    async def _run_real_tool(self, name: str, **kwargs: Any) -> dict[str, Any]:
        context = kwargs.pop("context", None)
        if name == "meteorological_trajectory_analysis":
            from app.tools.analysis.meteorological_trajectory_analysis.tool import MeteorologicalTrajectoryAnalysisTool

            return await MeteorologicalTrajectoryAnalysisTool().execute(context=context, **kwargs)
        if name == "analyze_upwind_enterprises":
            from app.tools.analysis.analyze_upwind_enterprises.tool import AnalyzeUpwindEnterprisesTool

            return await AnalyzeUpwindEnterprisesTool().execute(context=context, **kwargs)
        if name == "calculate_pm_pmf":
            from app.tools.analysis.calculate_pm_pmf.tool import CalculatePMFTool

            return await CalculatePMFTool().execute(context=context, **kwargs)
        if name == "calculate_reconstruction":
            from app.tools.analysis.calculate_reconstruction.calculate_reconstruction import CalculateReconstructionTool

            return await CalculateReconstructionTool().execute(context=context, **kwargs)
        if name == "calculate_vocs_pmf":
            from app.tools.analysis.calculate_vocs_pmf.tool import CalculateVOCSPMFTool

            return await CalculateVOCSPMFTool().execute(context=context, **kwargs)
        if name == "get_platform_weather_image":
            from app.tools.query.get_platform_weather_image.tool import GetPlatformWeatherImageTool

            return await GetPlatformWeatherImageTool().execute(**kwargs)
        raise ValueError(f"unsupported auto evidence tool: {name}")
