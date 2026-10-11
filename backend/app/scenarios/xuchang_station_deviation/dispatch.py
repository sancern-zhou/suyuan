"""Fetcher-owned upwind road evidence and PNGs; never sends notifications."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from app.utils.path_config import PROJECT_ROOT, format_agent_path, get_data_registry

TZ = ZoneInfo("Asia/Shanghai")
CONFIG_PATH = PROJECT_ROOT / "projects/xuchang/upwind_road_dispatch.json"


def local_time(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def station_name(value: Any) -> str:
    return re.sub(r"[（(].*?[）)]|\s+", "", str(value or ""))


def resolve_station(alert: dict, rows: list[dict]) -> dict | None:
    """Minute platform IDs cannot be joined to national IDs; match city/name."""
    name = station_name(alert.get("station_name") or alert.get("name"))
    candidates = [r for r in rows if name and station_name(r.get("station_name") or r.get("name")) == name]
    candidates.sort(key=lambda r: str(r.get("data_time") or r.get("time") or ""), reverse=True)
    for row in candidates:
        lon, lat = number(row.get("lon")), number(row.get("lat"))
        if lon is not None and lat is not None and 113.0 < lon < 115.0 and 33.0 < lat < 35.0:
            return {"station_name": name, "longitude": lon, "latitude": lat,
                    "canonical_station_id": str(row.get("station_id") or ""),
                    "coordinate_source": "许昌国控站点小时资料按站点名称匹配"}
    # Only explicitly mapped coordinates may bypass the hourly context.
    if alert.get("coordinate_source") and alert.get("canonical_station_id"):
        lon, lat = number(alert.get("lon")), number(alert.get("lat"))
        if lon is not None and lat is not None and 113.0 < lon < 115.0 and 33.0 < lat < 35.0:
            return {"station_name": name, "longitude": lon, "latitude": lat,
                    "canonical_station_id": alert["canonical_station_id"],
                    "coordinate_source": alert["coordinate_source"]}
    return None


def destination(lon: float, lat: float, bearing: float, distance_km: float) -> tuple[float, float]:
    a, b, angle, distance = math.radians(lon), math.radians(lat), math.radians(bearing), distance_km / 6371.0088
    target_lat = math.asin(math.sin(b) * math.cos(distance) + math.cos(b) * math.sin(distance) * math.cos(angle))
    target_lon = a + math.atan2(math.sin(angle) * math.sin(distance) * math.cos(b), math.cos(distance) - math.sin(b) * math.sin(target_lat))
    return math.degrees(target_lon), math.degrees(target_lat)


def distance_bearing(lon: float, lat: float, target_lon: float, target_lat: float) -> tuple[float, float]:
    a, b, c, d = map(math.radians, (lon, lat, target_lon, target_lat))
    h = math.sin((d-b)/2)**2 + math.cos(b)*math.cos(d)*math.sin((c-a)/2)**2
    distance = 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))
    bearing = math.degrees(math.atan2(math.sin(c-a)*math.cos(d), math.cos(b)*math.sin(d)-math.sin(b)*math.cos(d)*math.cos(c-a))) % 360
    return distance, bearing


def select_wind(observed: dict, event_time: Any, config: dict) -> dict:
    end = local_time(event_time)
    valid = []
    for row in observed.get("station_hour_records", []):
        if row.get("station_id") != "ZzMTA" or row.get("data_quality") not in (None, "good", "valid"):
            continue
        try:
            timestamp = local_time(row.get("time"))
        except (ValueError, TypeError):
            continue
        if end - timedelta(minutes=config.get("max_wind_age_minutes", 180)) <= timestamp <= end:
            valid.append((timestamp, row))
    if not valid:
        return {"status": "unavailable", "reason": "告警时段缺少有效风向观测"}
    valid.sort(key=lambda item: item[0])
    timestamp, row = valid[-1]
    speed, direction = number(row.get("wind_speed_10m")), number(row.get("wind_direction_10m"))
    result = {"observation_time": timestamp.isoformat(), "weather_station": "许昌", "weather_station_id": "ZzMTA", "source": observed.get("source", "NMC"), "wind_speed_ms": speed}
    if speed is None or speed < config.get("calm_wind_ms", 0.5) or direction is None or not 0 <= direction <= 360:
        return {**result, "status": "unavailable", "reason": "静风或风向无效，无法确定上风向"}
    directions = [math.radians(v % 360) for _, r in valid
                  if (v := number(r.get("wind_direction_10m"))) is not None and 0 <= v <= 360
                  and (number(r.get("wind_speed_10m")) or 0) >= config.get("calm_wind_ms", 0.5)]
    concentration = math.hypot(sum(math.cos(v) for v in directions), sum(math.sin(v) for v in directions)) / len(directions)
    if concentration < config.get("min_direction_concentration", 0.6):
        return {**result, "status": "unavailable", "reason": "近期风向变化较大，暂不限定上风向道路", "direction_concentration": concentration}
    # Meteorological wind direction is where the wind comes FROM, not +180°.
    return {**result, "status": "success", "wind_from_degrees": direction % 360,
            "direction_concentration": round(concentration, 3)}


def select_roads(pois: list[dict], station: dict, wind: dict, config: dict) -> list[dict]:
    candidates: dict[str, dict] = {}
    for poi in pois:
        name = str(poi.get("name") or "").strip()
        if not name or poi.get("typecode") != "190301" or poi.get("cityname") != "许昌市":
            continue
        if name in config.get("road_name_denylist", []):
            continue
        explicit = name in config.get("road_name_allowlist", [])
        if not explicit and (not re.search(config.get("road_name_include", r"大道|公路|国道|省道|快速路|环路|路$|[GS]\d{3}"), name) or re.search(config.get("road_name_exclude", r"胡同|巷|步行|辅路|匝道|内部|小区|支路|高速"), name)):
            continue
        try:
            lon, lat = map(float, str(poi["location"]).split(","))
            if not math.isfinite(lon) or not math.isfinite(lat):
                continue
        except (ValueError, KeyError):
            continue
        distance, bearing = distance_bearing(station["longitude"], station["latitude"], lon, lat)
        difference = abs((bearing - wind["wind_from_degrees"] + 180) % 360 - 180)
        if distance > config.get("radius_km", 3) or difference > config.get("sector_degrees", 60) / 2:
            continue
        road = {"name": name, "poi_id": poi.get("id"), "longitude": lon, "latitude": lat,
                "distance_km": round(distance, 3), "bearing_degrees": round(bearing, 1),
                "classification": "人工配置主干道" if explicit else "候选主干道（名称筛选，等级待核实）",
                "geometry_type": "road_name_poi", "coordinate_crs": "GCJ-02"}
        if name not in candidates or road["distance_km"] < candidates[name]["distance_km"]:
            candidates[name] = road
    return [{**road, "map_number": index} for index, road in enumerate(
        sorted(candidates.values(), key=lambda r: (r["distance_km"], r["name"]))[:config.get("max_roads", 8)], 1)]


class MapServiceError(Exception):
    """Contains only a safe error code, never a credential-bearing request URL."""


class UpwindRoadDispatchBuilder:
    def __init__(self, output_root: Path | None = None, config: dict | None = None, api_key: str | None = None):
        self.config = config or json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.output_root = output_root or get_data_registry() / "xuchang_station_deviation_alerts"
        self._last_request_at = 0.0
        self.key = api_key if api_key is not None else (os.getenv("AMAP_WEB_SERVICE_KEY") or os.getenv("AMAP_API_KEY") or os.getenv("AMAP_PUBLIC_KEY") or "")
        if not 0 < self.config["radius_km"] <= 3:
            raise ValueError("PM10 map radius must be in (0,3] km")

    def _request(self, endpoint: str, params: dict, deadline: float, image: bool = False):
        for attempt in range(3):
            # Web keys may have a low QPS quota; pace cold-cache pagination.
            delay = max(0, 0.4 - (time.monotonic() - self._last_request_at))
            if delay:
                time.sleep(min(delay, max(0, deadline-time.monotonic())))
            self._last_request_at = time.monotonic()
            try:
                return self._request_once(endpoint, params, deadline, image)
            except MapServiceError as exc:
                if not str(exc).endswith(("_10021", "_10019")) or attempt == 2:
                    raise
                time.sleep(min(0.8*(attempt+1), max(0, deadline-time.monotonic())))

    def _request_once(self, endpoint: str, params: dict, deadline: float, image: bool = False):
        if not self.key:
            raise MapServiceError("missing_amap_key")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MapServiceError("map_budget_exceeded")
        url = "https://restapi.amap.com/v3/" + endpoint + "?" + urlencode({**params, "key": self.key})
        try:
            with urlopen(url, timeout=min(self.config["request_timeout_seconds"], remaining)) as response:
                body = response.read(8 * 1024 * 1024)
            if image and body.startswith(b"\x89PNG\r\n\x1a\n"):
                with Image.open(io.BytesIO(body)) as bitmap:
                    bitmap.verify()
                return body
            result = json.loads(body)
            if result.get("status") != "1" or image:
                code = re.sub(r"[^0-9]", "", str(result.get("infocode", "")))[:8]
                raise MapServiceError(f"amap_{endpoint.replace('/', '_')}_{code or 'invalid_response'}")
            return result
        except MapServiceError:
            raise
        except Exception as exc:
            raise MapServiceError(f"amap_{endpoint.replace('/', '_')}_{type(exc).__name__}") from None

    def _cache(self, name: str, params: dict, loader):
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        path = self.output_root / "road_cache" / f"{name}-{key}.json"
        try:
            if time.time() - path.stat().st_mtime < self.config["cache_hours"] * 3600:
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        data = loader()
        self._write_json(path, data)
        return data

    @staticmethod
    def _write_json(path: Path, data: Any):
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(path)

    def _station_gcj(self, station: dict, deadline: float) -> dict:
        crs = self.config["station_coordinate_crs"].upper()
        if crs == "GCJ-02":
            return {**station, "coordinate_crs": crs}
        if crs != "WGS84":
            raise MapServiceError("unsupported_station_crs")
        params = {"locations": f"{station['longitude']:.6f},{station['latitude']:.6f}", "coordsys": "gps"}
        result = self._cache("coordinate", params, lambda: self._request("assistant/coordinate/convert", params, deadline))
        try:
            lon, lat = map(float, result["locations"].split(","))
            if not (113 < lon < 115 and 33 < lat < 35):
                raise ValueError
        except (KeyError, ValueError):
            raise MapServiceError("invalid_converted_coordinate") from None
        return {**station, "source_coordinate_crs": crs, "source_longitude": station["longitude"], "source_latitude": station["latitude"],
                "longitude": lon, "latitude": lat, "coordinate_crs": "GCJ-02"}

    def _roads(self, station: dict, deadline: float) -> dict:
        params = {"location": f"{station['longitude']:.6f},{station['latitude']:.6f}", "radius": round(self.config["radius_km"]*1000),
                  "types": "190301", "sortrule": "distance", "offset": 25, "extensions": "base"}
        def fetch():
            pois = []
            total = 0
            for page in range(1, self.config["max_search_pages"] + 1):
                result = self._request("place/around", {**params, "page": page}, deadline)
                items = result.get("pois", [])
                total = int(result.get("count") or 0)
                pois.extend(items)
                if len(items) < 25 or len(pois) >= total:
                    break
            return {"pois": pois, "total_count": total, "truncated": len(pois) < total,
                    "queried_at": datetime.now(TZ).isoformat()}
        return self._cache("roads", {**params, "max_pages": self.config["max_search_pages"]}, fetch)

    def _map(self, scope: dict, deadline: float) -> bytes:
        station = scope["station"]
        lon, lat = station["longitude"], station["latitude"]
        circle = [destination(lon, lat, b, scope["radius_km"]) for b in range(0, 361, 10)]
        def path(points):
            return ";".join(f"{x:.6f},{y:.6f}" for x, y in points)
        paths = ["2,0x2563EB,0.8,,0:" + path(circle)]
        markers = [f"large,0x2563EB,站:{lon:.6f},{lat:.6f}"]
        markers += [f"mid,0xDC2626,{r['map_number']}:{r['longitude']:.6f},{r['latitude']:.6f}" for r in scope["roads"]]
        params = {"size": "900*720", "scale": 1, "paths": "|".join(paths), "markers": "|".join(markers)}
        return self._request("staticmap", params, deadline, image=True)

    def _render(self, scope: dict, map_bytes: bytes | None, path: Path):
        from app.utils.font_utils import select_preferred_chinese_font_path, chinese_font_prop
        from matplotlib.font_manager import findfont
        font_path = str(select_preferred_chinese_font_path() or findfont(chinese_font_prop()))
        font = ImageFont.truetype(font_path, 20)
        small = ImageFont.truetype(font_path, 17)
        title_font = ImageFont.truetype(font_path, 26)
        footer_lines = []
        canvas = Image.new("RGB", (900, 845), "white")
        draw = ImageDraw.Draw(canvas)
        name = scope.get("station", {}).get("station_name") or scope.get("station_name") or "站点"
        draw.text((20, 12), f"{name}｜PM10高值3公里范围图", font=title_font, fill="#12304a")
        draw.text((20, 48), f"告警时间 {scope['event_time'][0:16]}；排查半径 {scope['radius_km']:g} 公里", font=small, fill="#334155")
        if map_bytes:
            with Image.open(io.BytesIO(map_bytes)) as background:
                canvas.paste(background.convert("RGB"), (0, 80))
        else:
            draw.rectangle((0, 80, 899, 844), fill="#f1f5f9")
            draw.text((80, 370), "地图暂不可用", font=font, fill="#b91c1c")
        for i, line in enumerate(footer_lines):
            draw.text((20, 842 + 28*i), line, font=small, fill="#334155")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".png", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
        canvas.save(temporary, format="PNG")
        temporary.replace(path)

    def build(self, alert: dict, evidence: dict) -> dict:
        deadline = time.monotonic() + self.config["total_timeout_seconds"]
        if str(alert.get("target_pollutant") or "").upper() != "PM10":
            return {"schema_version": "xuchang_pm10_road_scope/v2", "status": "not_applicable", "roads": [],
                    "map_status": "not_applicable", "reason": "仅PM10高值告警生成3公里范围图",
                    "event_time": local_time(alert["occurred_at"]).isoformat(), "station_name": alert.get("station_name"),
                    "radius_km": self.config["radius_km"], "sector": "none", "source": "not_generated"}
        scope = {"schema_version": "xuchang_pm10_road_scope/v2", "status": "unavailable", "roads": [], "wind": {"status": "not_used", "reason": "本规则不使用风向扇区"},
                 "event_time": local_time(alert["occurred_at"]).isoformat(), "station_name": alert.get("station_name"),
                 "radius_km": self.config["radius_km"], "sector": "none",
                 "source": "高德静态地图", "errors": [],
                 "selection_note": "固定展示站点周围3公里范围，不检索道路、不划分风向扇区"}
        station = resolve_station(alert, evidence.get("air_quality_context", {}).get("local_station_hour_records", []))
        map_bytes = None
        if station is None:
            scope["reason"] = "无法匹配许昌站点可靠坐标，暂不生成3公里范围图"
        else:
            try:
                scope["station"] = self._station_gcj(station, deadline)
                map_bytes = self._map(scope, deadline)
                scope["status"] = "success" if map_bytes else "unavailable"
            except MapServiceError as exc:
                scope["errors"].append(str(exc))
                scope["reason"] = "3公里范围地图查询暂不可用，需根据站点位置核实"
                scope["status"] = "partial" if scope["roads"] else "unavailable"
        scope["map_status"] = "success" if map_bytes else "unavailable"
        # A content identity includes event, wind, scope config and station;
        # unlike legacy event IDs it cannot collide between stations.
        digest = hashlib.sha256(json.dumps([alert.get("station_id"), scope, self.config], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        base = "upwind-roads-" + local_time(alert["occurred_at"]).strftime("%Y%m%d%H%M") + "-" + digest
        image_path = self.output_root / "charts" / f"{base}.png"
        scope["upwind_road_scope_image_path"] = format_agent_path(image_path)
        scope["upwind_road_scope_path"] = format_agent_path(self.output_root / "road_scopes" / f"{base}.json")
        self._render(scope, map_bytes, image_path)
        self._write_json(self.output_root / "road_scopes" / f"{base}.json", scope)
        return scope

    def guidance(self, alert: dict, scope: dict) -> dict:
        pollutant = str(alert.get("target_pollutant") or "").upper()
        canonical = "NO2" if pollutant == "NOX" else pollutant
        return {"pollutant": canonical, "observed_indicator": alert.get("observed_indicator", canonical),
                "road_names": [r["name"] for r in scope["roads"]], "scope_status": scope["status"],
                "actions": self.config["pollutant_actions"].get(canonical, ["核验站点及周边异常，反馈现场观测结果"]),
                "location_instruction": ("请以告警站点为中心，在固定3公里范围内组织道路及周边排查。"
                                         if canonical == "PM10" and scope.get("map_status") == "success" else "本污染物不生成3公里范围图，请按监测事实组织核查。"),
                "feedback": "回传排查路段、异常点位置、现场照片、处置情况及复测结果。",
                "boundary": "现场排查指令，不是污染来源或企业责任认定，不自动下达停产封路指令。"}
