"""City weather observations used as supporting evidence for SOP-02."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from datetime import datetime, timedelta

import httpx


WEATHER_URL = "http://data.suncereltd.top:8080/api/WeatherData/GetWeatherStationHour"
FIELDS = ("temperature", "humidity", "rain", "windDirection", "windSpeed", "pressure")
WEATHER_COLLECTION_TIMEOUT_SECONDS = 75
# City seats from https://www.weather.com.cn/data/city3jdata/provshi/10119.html
# and its station/10119XX.html directories. Never substitute a county station.
URBAN_STATIONS = {
    "南京": "101190101", "无锡": "101190201", "镇江": "101190301",
    "苏州": "101190401", "南通": "101190501", "扬州": "101190601",
    "盐城": "101190701", "徐州": "101190801", "淮安": "101190901",
    "连云港": "101191001", "常州": "101191101", "泰州": "101191201",
    "宿迁": "101191301",
}


class _WeatherCredentialFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(
                arg.copy_remove_param("token")
                if isinstance(arg, httpx.URL) and str(arg).startswith(WEATHER_URL)
                else arg for arg in record.args
            )
        return True


logging.getLogger("httpx").addFilter(_WeatherCredentialFilter())


def _city(value):
    return str(value or "").strip().removesuffix("市")


def _number(value):
    if value is None or str(value).strip() in {"", "-", "--"}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and abs(number) < 9999 else None


async def fetch_city_weather(*, city_name, start_time, end_time, client=None):
    start = datetime.fromisoformat(start_time)
    end = datetime.fromisoformat(end_time)
    result = {
        "status": "empty", "city_name": city_name, "granularity": "hour",
        "start": start_time, "end": end_time, "data": [], "gaps": [],
        "source": "Suncere 城区气象观测站小时数据", "scope": "supporting",
        "station_scope": "urban",
    }
    token = os.getenv("SUNCERE_WEATHER_TOKEN", "")
    if not _city(city_name) or not token:
        result.update(status="unavailable", message="缺少站点归属城市或气象接口尚未配置")
        return result
    try:
        mapping = json.loads(os.getenv("JIANGSU_REVIEW_WEATHER_STATIONS", "{}"))
        if not isinstance(mapping, dict):
            raise ValueError("invalid mapping")
    except (ValueError, TypeError):
        result.update(status="unavailable", message="城市气象站映射配置无效")
        return result
    configured_code = mapping.get(city_name) or mapping.get(_city(city_name))
    station_code = str(configured_code or URBAN_STATIONS.get(_city(city_name)) or "")
    result.update(station_code=station_code, station_name=f"{_city(city_name)}城区",
                  selection_method="configured_urban_station" if configured_code else "city_seat_catalog")
    if not station_code:
        result.update(status="unavailable", message="未配置该城市的城区气象站")
        return result
    owned_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    semaphore = asyncio.Semaphore(3)

    async def query(left, right):
        try:
            async with semaphore:
                response = await client.get(WEATHER_URL, params={
                    "token": token, "beginTime": left.strftime("%Y-%m-%d %H:%M:%S"),
                    "endTime": right.strftime("%Y-%m-%d %H:%M:%S"),
                })
            payload = response.json() if response.status_code == 200 else {}
            if (response.status_code in {413, 500} or str(payload.get("code")) in {"413", "500"}) and left < right:
                parts = await asyncio.gather(*(query(hour, hour) for hour in hours(left, right)))
                return [row for part in parts for row in part]
            response.raise_for_status()
            if str(payload.get("code")) != "200" or not isinstance(payload.get("dataList"), list):
                raise ValueError("invalid response")
            return [row for row in payload["dataList"] if isinstance(row, dict) and _city(row.get("cityName")) == _city(city_name)]
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            # Exception strings may contain the credential-bearing request URL.
            result["gaps"].append({"start": left.isoformat(), "end": right.isoformat(), "reason": "气象接口请求失败或响应无效"})
            return []

    def hours(left, right):
        while left <= right:
            yield left
            left += timedelta(hours=1)

    first = start.replace(minute=0, second=0, microsecond=0)
    if first < start:
        first += timedelta(hours=1)
    expected = list(hours(first, end))
    ranges = [(expected[i], expected[min(i + 11, len(expected) - 1)]) for i in range(0, len(expected), 12)]
    tasks = {asyncio.create_task(query(left, right)): (left, right) for left, right in ranges}
    try:
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=WEATHER_COLLECTION_TIMEOUT_SECONDS)
            chunks = [task.result() for task in done]
            for task in pending:
                left, right = tasks[task]
                result['gaps'].append({'start': left.isoformat(), 'end': right.isoformat(), 'reason': '气象取证超过总时限，该分段未完整返回'})
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        else:
            chunks = []
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if owned_client:
            await client.aclose()
    rows = [row for chunk in chunks for row in chunk]
    records = {}
    for row in rows:
        if str(row.get("stationCode")) != station_code:
            continue
        try:
            timestamp = datetime.fromisoformat(str(row.get("timePoint")))
            if timestamp not in expected:
                continue
        except (ValueError, TypeError):
            continue
        values = {field: _number(row.get(field)) for field in FIELDS}
        for field in ("humidity", "rain", "windDirection", "windSpeed", "pressure"):
            if values[field] is not None and values[field] < 0:
                values[field] = None
        if values["humidity"] is not None and values["humidity"] > 100:
            values["humidity"] = None
        if values["windDirection"] is not None and values["windDirection"] > 360:
            values["windDirection"] = None
        records[timestamp] = {"timePoint": timestamp.isoformat(), **values}
        result["station_name"] = row.get("stationName")
    result.update(station_code=station_code, data=[records[time] for time in sorted(records)],
                  expected_hours=len(expected), record_count=len(records),
                  missing_hours=[time.isoformat() for time in expected if time not in records])
    result["missing_parameters"] = {field: sum(record[field] is None for record in records.values()) for field in FIELDS}
    result["status"] = "success" if records and not result["gaps"] and not result["missing_hours"] and not any(result["missing_parameters"].values()) else "partial" if records else "failed" if result["gaps"] else "empty"
    result["message"] = f"城区气象站 {result.get('station_name') or station_code}：{len(records)}/{len(expected)} 小时"
    if not records:
        result["message"] += "；接口未返回该城区站的有效小时记录" if not result["gaps"] else "；气象接口取证失败"
    return result
