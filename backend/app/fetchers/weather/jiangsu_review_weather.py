"""City weather observations used as supporting evidence for SOP-02."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import uuid
import weakref
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from app.utils.path_config import get_data_registry


WEATHER_URL = "http://data.suncereltd.top:8080/api/WeatherData/GetWeatherStationHour"
FIELDS = ("temperature", "humidity", "rain", "windDirection", "windSpeed", "pressure")
WEATHER_COLLECTION_TIMEOUT_SECONDS = 600
_LOOP_LOCKS = weakref.WeakKeyDictionary()


def _cache_read(root, hour):
    path = root / f'{hour:%Y%m%d%H}.json'
    try:
        payload = json.loads(path.read_text())
        if time.time() - payload['fetched_at'] < 86400 and isinstance(payload['rows'], list):
            return payload['rows']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _cache_write(root, hour, rows):
    root.mkdir(parents=True, exist_ok=True)
    path = root / f'{hour:%Y%m%d%H}.json'
    temporary = path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
    temporary.write_text(json.dumps({'fetched_at': time.time(), 'rows': rows}, ensure_ascii=False))
    temporary.replace(path)


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


async def fetch_city_weather(*, city_name, start_time, end_time, client=None, cache_dir=None):
    start = datetime.fromisoformat(start_time)
    end = datetime.fromisoformat(end_time)
    if end < start:
        raise ValueError('气象时间窗口结束早于开始')
    result = {
        "status": "empty", "city_name": city_name, "granularity": "hour",
        "start": start_time, "end": end_time, "data": [], "gaps": [],
        "source": "Suncere 同城气象观测站小时数据", "scope": "supporting",
        "station_scope": "same_city",
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
    station_code = str(configured_code or "")
    result.update(station_code=station_code, station_name='',
                  selection_method="configured_station" if configured_code else "coverage_ranked")
    owned_client = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15))
    root = Path(cache_dir) if cache_dir is not None else get_data_registry() / 'weather_hour_cache' / 'suncere_v1'
    locks = _LOOP_LOCKS.setdefault(asyncio.get_running_loop(), {})
    semaphore = locks.setdefault(('requests', str(root)), asyncio.Semaphore(3))
    collected = {}
    result.update(cache_hit_hours=0, requests=[], station_candidates=[])

    async def query(left, right):
        requested = list(hours(left, right))
        lock = locks.setdefault((str(root), left.date(), left.hour // 12), asyncio.Lock())
        retry = False
        try:
            async with lock:
                missing = []
                for hour in requested:
                    cached = _cache_read(root, hour)
                    if cached is None:
                        missing.append(hour)
                    else:
                        collected[hour] = cached
                        result['cache_hit_hours'] += 1
                if not missing:
                    return
                started = time.monotonic()
                diagnostic = {'start': missing[0].isoformat(), 'end': missing[-1].isoformat()}
                result['requests'].append(diagnostic)
                try:
                    async with semaphore:
                        response = await client.get(WEATHER_URL, params={
                            'token': token, 'beginTime': missing[0].strftime('%Y-%m-%d %H:%M:%S'),
                            'endTime': missing[-1].strftime('%Y-%m-%d %H:%M:%S'),
                        })
                    diagnostic['http_status'] = response.status_code
                    payload = response.json() if response.status_code == 200 else {}
                    diagnostic['api_code'] = payload.get('code') if isinstance(payload, dict) else None
                    if response.status_code in {413, 429, 500, 502, 503, 504} or str(diagnostic['api_code']) in {'413', '500'}:
                        retry = True
                        raise ValueError('retryable_response')
                    response.raise_for_status()
                    if str(payload.get('code')) != '200' or not isinstance(payload.get('dataList'), list):
                        raise ValueError('invalid_response')
                    grouped = {hour: [] for hour in missing}
                    for row in payload['dataList']:
                        if not isinstance(row, dict):
                            continue
                        try:
                            hour = datetime.fromisoformat(str(row.get('timePoint')))
                        except ValueError:
                            continue
                        if hour in grouped:
                            grouped[hour].append(row)
                    diagnostic['record_count'] = len(payload['dataList'])
                    for hour, rows in grouped.items():
                        collected[hour] = rows
                        # Empty nationwide hours may still be arriving; never cache them.
                        if rows:
                            _cache_write(root, hour, rows)
                except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
                    retry = retry or isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))
                    diagnostic['error_type'] = type(exc).__name__
                    if not retry or left == right:
                        result['gaps'].append({**diagnostic, 'reason': '气象接口请求失败或响应无效'})
                finally:
                    diagnostic['elapsed_seconds'] = round(time.monotonic() - started, 2)
            if retry and left < right:
                middle = len(requested) // 2
                await query(left, requested[middle - 1])
                await query(requested[middle], right)
        except OSError:
            result['gaps'].append({'start': left.isoformat(), 'end': right.isoformat(), 'reason': '气象缓存读写失败'})

    def hours(left, right):
        while left <= right:
            yield left
            left += timedelta(hours=1)

    first = start.replace(minute=0, second=0, microsecond=0)
    if first < start:
        first += timedelta(hours=1)
    expected = list(hours(first, end))
    grouped_hours = {}
    for hour in expected:
        grouped_hours.setdefault((hour.date(), hour.hour // 12), []).append(hour)
    ranges = [(group[0], group[-1]) for group in grouped_hours.values()]
    tasks = {asyncio.create_task(query(left, right)): (left, right) for left, right in ranges}
    try:
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=WEATHER_COLLECTION_TIMEOUT_SECONDS)
            for task in done:
                task.result()
            for task in pending:
                left, right = tasks[task]
                result['gaps'].append({'start': left.isoformat(), 'end': right.isoformat(), 'reason': '气象取证超过总时限，该分段未完整返回'})
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        else:
            pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if owned_client:
            await client.aclose()
    rows = [row for group in collected.values() for row in group if _city(row.get('cityName')) == _city(city_name)]
    candidates = {str(row.get('stationCode')): {'station_code': str(row.get('stationCode')), 'station_name': row.get('stationName'),
                  'city_name': row.get('cityName'), 'latitude': row.get('stationLat'), 'longitude': row.get('stationLng')} for row in rows if row.get('stationCode')}
    result['station_candidates'] = sorted(candidates.values(), key=lambda row: row['station_code'])
    result['city_record_count'] = len(rows)
    result['expected_hours'] = len(expected)
    coverage = {}
    for row in rows:
        code = str(row.get('stationCode') or '')
        if code and any(_number(row.get(field)) is not None for field in FIELDS):
            coverage.setdefault(code, set()).add(row.get('timePoint'))
    available = sorted(coverage, key=lambda code: (-len(coverage[code]), code))
    if station_code not in coverage:
        station_code = available[0] if available else ''
        result['selection_method'] = 'coverage_ranked'
    result['selection_reason'] = '优先使用有数据的配置站；否则按有效小时覆盖数降序、站号升序选定同城站，整个窗口不拼接站点'
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
    result["message"] = f"气象站 {result.get('station_name') or station_code or '无可用站点'}：{len(records)}/{len(expected)} 小时"
    if not records:
        result["message"] += "；接口未返回同城气象站的有效小时记录" if not result["gaps"] else "；气象接口取证失败"
    return result
