"""Observed meteorology query tool for HourSpiData pages."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import requests
import structlog
from bs4 import BeautifulSoup

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()

DEFAULT_BASE_URL = os.getenv("OBSERVED_METEOROLOGY_BASE_URL", "http://10.10.10.137:18405")


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def _to_float(value: str | None) -> float | None:
    text = _clean_text(value)
    if not text or text in {"-", "--", "NaN", "nan", "null"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number):
        return None
    return number


def _normalize_time(value: str) -> str:
    text = _clean_text(value)
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return text


def build_hour_spi_url(
    *,
    base_url: str = DEFAULT_BASE_URL,
    province_ajc: str,
    city_code: str,
    start_time: str,
    end_time: str,
    page_index: int = 1,
    page_size: int = 50,
) -> str:
    params = {
        "province": province_ajc,
        "city": city_code,
        "startTime": start_time,
        "endTime": end_time,
    }
    if page_index > 1:
        params["pageIndex"] = str(page_index)
    if page_size:
        params["pageSize"] = str(page_size)
    return f"{base_url.rstrip('/')}/Meteorology/HourSpiData?{urlencode(params)}"


def parse_city_options(payload: str) -> dict[str, dict[str, Any]]:
    data = json.loads(payload)
    cities: dict[str, dict[str, Any]] = {}
    for item in data:
        name = str(item.get("CityName") or "").strip()
        if not name:
            continue
        cities[name] = {
            "city_code": str(item.get("CityCode") or "").strip(),
            "station_code": str(item.get("StationCode") or "").strip(),
            "city_name": name,
            "city_name_py": str(item.get("CityNamePY") or "").strip(),
            "province_ajc": str(item.get("ProvinceAJC") or "").strip(),
            "lon": item.get("Lon"),
            "lat": item.get("Lat"),
            "trajectories": bool(item.get("Trajectories")),
        }
    return cities


def parse_province_options(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    select = soup.find("select", id="province")
    if not select:
        return {}
    provinces: dict[str, str] = {}
    for option in select.find_all("option"):
        code = str(option.get("value") or "").strip()
        name = _clean_text(option.get_text())
        if code and name:
            provinces[name] = code
            provinces[name.replace("省", "").replace("市", "").replace("自治区", "")] = code
    return provinces


HEADER_ALIASES = {
    "城市": "city",
    "时间": "timestamp",
    "风向(deg)": "wind_direction_10m",
    "风速(m/s)": "wind_speed_10m",
    "气压(hPa)": "surface_pressure",
    "气温(°C)": "temperature_2m",
    "降雨量(mm)": "precipitation",
    "湿度(%)": "relative_humidity_2m",
    "体感温度(°C)": "apparent_temperature",
}


def parse_hour_spi_table(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=lambda value: value and "data-table" in value)
    if not table:
        return {"records": [], "page_count": 1}

    headers = [_clean_text(th.get_text()) for th in table.find_all("th")]
    records: list[dict[str, Any]] = []
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else []
    for row in rows:
        cells = [_clean_text(td.get_text()) for td in row.find_all("td")]
        if len(cells) < 2:
            continue
        raw = dict(zip(headers, cells))
        city = raw.get("城市", "")
        timestamp = raw.get("时间", "")
        measurements: dict[str, float] = {}
        for label, key in HEADER_ALIASES.items():
            if key in {"city", "timestamp"}:
                continue
            value = _to_float(raw.get(label))
            if value is not None:
                measurements[key] = value
        records.append(
            {
                "city": city,
                "timestamp": _normalize_time(timestamp),
                "measurements": measurements,
                "source": "observed_meteorology_hour_spi",
            }
        )

    page_count = 1
    pager_text = soup.get_text(" ", strip=True)
    match = re.search(r"(\d+)\s*/\s*(\d+)", pager_text)
    if match:
        page_count = int(match.group(2))

    return {"records": records, "page_count": page_count}


class ObservedMeteorologyClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, session_cookie: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        cookie = session_cookie or os.getenv("OBSERVED_METEOROLOGY_SESSION_COOKIE")
        if cookie:
            self.session.headers.update({"Cookie": cookie})
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=30, allow_redirects=False)
        response.raise_for_status()
        return response

    def fetch_home(self) -> str:
        return self.get(f"{self.base_url}/Meteorology/HourSpiData").text

    def fetch_cities(self, province_ajc: str) -> dict[str, dict[str, Any]]:
        url = f"{self.base_url}/Ajax/GetJsonCityListByProvinceAJC"
        response = self.session.get(
            url,
            params={"provinceAJC": province_ajc},
            timeout=30,
            allow_redirects=False,
        )
        response.raise_for_status()
        return parse_city_options(response.text)

    def fetch_hour_page(
        self,
        *,
        province_ajc: str,
        city_code: str,
        start_time: str,
        end_time: str,
        page_index: int,
        page_size: int,
    ) -> str:
        url = build_hour_spi_url(
            base_url=self.base_url,
            province_ajc=province_ajc,
            city_code=city_code,
            start_time=start_time,
            end_time=end_time,
            page_index=page_index,
            page_size=page_size,
        )
        response = self.get(url)
        if response.status_code in {301, 302} or "/Home/Index" in response.headers.get("Location", ""):
            raise RuntimeError("Meteorology site redirected to Home/Index; session cookie may be missing or expired.")
        return response.text


class GetObservedMeteorologyTool(LLMTool):
    def __init__(self):
        function_schema = {
            "name": "get_observed_meteorology",
            "description": "查询逐小时地面气象观测数据，自动解析省份和城市编码，返回风向、风速、气压、气温、降雨量、湿度等字段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "province_ajc": {"type": "string", "description": "省份AJC编码，如AJX=江西、AJL=吉林、AGD=广东"},
                    "province_name": {"type": "string", "description": "省份名称，如江西、吉林、广东；无province_ajc时自动解析"},
                    "city_code": {"type": "string", "description": "城市编码，如101240101"},
                    "city_name": {"type": "string", "description": "城市名称，如南昌、长春、广州；无city_code时自动解析"},
                    "start_time": {"type": "string", "description": "开始时间，格式YYYY-MM-DD HH:mm"},
                    "end_time": {"type": "string", "description": "结束时间，格式YYYY-MM-DD HH:mm"},
                    "page_size": {"type": "integer", "description": "每页条数，默认50", "default": 50},
                    "max_pages": {"type": "integer", "description": "最大分页数，默认20", "default": 20},
                    "session_cookie": {"type": "string", "description": "ASP.NET_SessionId Cookie，可不填，默认读取环境变量"},
                },
                "required": ["start_time", "end_time"],
            },
        }
        super().__init__(
            name="get_observed_meteorology",
            description="Query hourly observed meteorology from internal HourSpiData pages",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        *,
        start_time: str,
        end_time: str,
        province_ajc: str | None = None,
        province_name: str | None = None,
        city_code: str | None = None,
        city_name: str | None = None,
        page_size: int = 50,
        max_pages: int = 20,
        session_cookie: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        try:
            client = ObservedMeteorologyClient(session_cookie=session_cookie)
            province_ajc, city_code, city_meta = self._resolve_location(
                client=client,
                province_ajc=province_ajc,
                province_name=province_name,
                city_code=city_code,
                city_name=city_name,
            )

            records: list[dict[str, Any]] = []
            first = client.fetch_hour_page(
                province_ajc=province_ajc,
                city_code=city_code,
                start_time=start_time,
                end_time=end_time,
                page_index=1,
                page_size=page_size,
            )
            parsed = parse_hour_spi_table(first)
            records.extend(parsed["records"])
            page_count = min(parsed["page_count"], max_pages)
            for page_index in range(2, page_count + 1):
                html = client.fetch_hour_page(
                    province_ajc=province_ajc,
                    city_code=city_code,
                    start_time=start_time,
                    end_time=end_time,
                    page_index=page_index,
                    page_size=page_size,
                )
                records.extend(parse_hour_spi_table(html)["records"])

            data_id = None
            if context is not None and hasattr(context, "save_data") and records:
                data_id = context.save_data(
                    records,
                    schema="observed_meteorology_hourly",
                    metadata={
                        "source": "HourSpiData",
                        "province_ajc": province_ajc,
                        "city_code": city_code,
                    },
                )

            valid_wind_count = sum(
                1
                for record in records
                if record.get("measurements", {}).get("wind_speed_10m") is not None
                and record.get("measurements", {}).get("wind_direction_10m") is not None
            )
            return {
                "status": "success",
                "success": True,
                "data_id": data_id,
                "data": records,
                "metadata": {
                    "tool_name": self.name,
                    "source": "HourSpiData",
                    "province_ajc": province_ajc,
                    "city_code": city_code,
                    "city": city_meta,
                    "record_count": len(records),
                    "valid_wind_count": valid_wind_count,
                },
                "summary": f"[OK] 查询到{len(records)}条小时气象观测数据，其中{valid_wind_count}条包含有效风向风速。",
            }
        except Exception as exc:
            logger.warning("observed_meteorology_query_failed", error=str(exc))
            return {
                "status": "failed",
                "success": False,
                "error": str(exc),
                "data": [],
                "metadata": {"tool_name": self.name},
                "summary": f"[FAIL] 小时气象观测数据查询失败: {str(exc)}",
            }

    def _resolve_location(
        self,
        *,
        client: ObservedMeteorologyClient,
        province_ajc: str | None,
        province_name: str | None,
        city_code: str | None,
        city_name: str | None,
    ) -> tuple[str, str, dict[str, Any]]:
        if province_ajc and city_code:
            return province_ajc, city_code, {"city_code": city_code, "city_name": city_name}

        if not province_ajc:
            if not province_name:
                raise ValueError("缺少 province_ajc 或 province_name，无法解析城市编码。")
            provinces = parse_province_options(client.fetch_home())
            province_ajc = provinces.get(province_name) or provinces.get(province_name.rstrip("省市"))
            if not province_ajc:
                raise ValueError(f"未找到省份编码: {province_name}")

        cities = client.fetch_cities(province_ajc)
        if city_code:
            for meta in cities.values():
                if meta.get("city_code") == city_code:
                    return province_ajc, city_code, meta
            return province_ajc, city_code, {"city_code": city_code, "city_name": city_name}

        if not city_name:
            raise ValueError("缺少 city_code 或 city_name，无法查询城市小时气象。")
        city_meta = cities.get(city_name) or cities.get(city_name.rstrip("市"))
        if not city_meta:
            raise ValueError(f"未在{province_ajc}下找到城市: {city_name}")
        return province_ajc, city_meta["city_code"], city_meta
