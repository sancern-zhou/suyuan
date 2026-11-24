"""乡镇小时高值检测与直推测试；所有数据库、截图、推送均为 fake。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.fetchers.xuchang_town_high_value_alert import XuchangTownHighValueAlertFetcher
from app.scenarios.xuchang_town_high_value.config import HighValueConfig
from app.scenarios.xuchang_town_high_value.detector import detect_high_value_groups
from app.scenarios.xuchang_town_high_value.message import render_message
from app.scenarios.xuchang_town_high_value.state import AlertStateStore

HOUR = datetime(2026, 11, 24, 14)
NOW = HOUR + timedelta(minutes=21)


class Rows:
    def __init__(self, rows):
        self.rows = rows

    async def latest_rows(self, **_kwargs):
        return self.rows


class Weather:
    def __init__(self, available=True):
        self.available = available

    async def get_observed_data(self, station_id, start, end):
        assert station_id == "ZzMTA"
        if not self.available:
            return []
        return [type("Observation", (), {
            "time": HOUR, "station_id": "ZzMTA", "data_quality": "good",
            "temperature_2m": 8.2, "relative_humidity_2m": 61,
            "wind_direction_10m": 315, "wind_speed_10m": 2.3,
        })()]


@pytest.mark.asyncio
async def test_five_minute_catalog_fills_missing_station_names(monkeypatch):
    from app.scenarios.xuchang_town_high_value import repository

    class Cursor:
        def __init__(self):
            self.station_query = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, query, *_args):
            self.station_query = "SELECT Tsno, StationName FROM TownStationFiveMinute" in query
            self.office_query = "FROM OfficeStationFiveMinute" in query

        async def fetchall(self):
            if self.station_query:
                return [("411025103", "襄城县山头店镇")]
            if self.office_query:
                return [{"Tsno": "411002001", "StationName": "魏都区丁庄街道办事处"}]
            return [{"Tsno": "411025103", "StationName": None}]

    class Connection:
        def cursor(self, *_args):
            return Cursor()

        def close(self):
            pass

    async def connect(**_kwargs):
        return Connection()

    monkeypatch.setattr(repository.aiomysql, "connect", connect)

    rows = await repository.TownHourRepository("mysql://user:pass@localhost/DataCrawler").latest_rows(
        now=NOW
    )
    assert rows[0]["StationName"] == "襄城县山头店镇"


def rows_for(high_pm25=(), high_pm10=()):
    rows = []
    for index in range(10):
        rows.append({
            "Tsno": f"normal-{index}", "StationName": f"普通镇{index}",
            "CollectionTime": HOUR, "PM25": 20 + index * 3, "PM10": 40 + index * 5,
        })
    for index, value in enumerate(high_pm25):
        rows.append({
            "Tsno": f"pm25-{index}", "StationName": f"高值镇{index}",
            "CollectionTime": HOUR, "PM25": value, "PM10": 35,
        })
    for index, value in enumerate(high_pm10):
        rows.append({
            "Tsno": f"pm10-{index}", "StationName": f"颗粒物镇{index}",
            "CollectionTime": HOUR, "PM25": 25, "PM10": value,
        })
    return rows


def build(monkeypatch, tmp_path, rows, weather=None, capture=None):
    sent = []
    fetcher = XuchangTownHighValueAlertFetcher(
        repository=Rows(rows), weather_repository=weather or Weather(),
        state=AlertStateStore(tmp_path), capture=capture or (lambda *args: "registry/map.png"),
        enqueue=lambda *args, **kwargs: sent.append((args, kwargs)) or {"id": str(len(sent))},
        now_factory=lambda: NOW,
    )
    async def fake_renderer(group, weather):
        stations = group["stations"]
        names = "、".join(item["station_name"] for item in stations)
        message = (
            f"【乡镇高值提醒】14时00分乡镇及办事处站数据显示{names}"
            f"{group['pollutant']}浓度实时小时数据为{stations[0]['value']:.1f}微克/立方米，"
            f"共{len(stations)}个乡镇及办事处站。"
            "请属地加强上风向及站点周边污染源排查，当前气象情况："
        )
        message += "暂无可用气象观测。" if not weather["observed_meteorology"]["station_hour_records"] else "温度8.2℃，相对湿度61%，西北风，风速2.3米/秒。"
        return message

    fetcher.message_renderer = fake_renderer
    return fetcher, sent


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2, 3, 4])
async def test_one_to_four_stations_share_one_message(monkeypatch, tmp_path, count):
    rows = rows_for(high_pm25=[90] * count)
    for row in rows:
        row["PM10"] = 40
    fetcher, sent = build(monkeypatch, tmp_path, rows)
    result = await fetcher.fetch_and_store()
    assert result["sent"] == 1
    assert len(sent) == 1
    assert f"共{count}个乡镇及办事处站" in sent[0][0][1]
    assert all(f"高值镇{index}" in sent[0][0][1] for index in range(count))


@pytest.mark.asyncio
async def test_five_stations_are_regional_pollution_and_not_sent(monkeypatch, tmp_path):
    fetcher, sent = build(monkeypatch, tmp_path, rows_for(high_pm25=[90] * 5, high_pm10=[170]))
    result = await fetcher.fetch_and_store()
    assert result["sent"] == 1 and len(sent) == 1
    assert "PM10" in sent[0][0][1] and "PM2.5" not in sent[0][0][1]
    history = fetcher.state._load()["history"]
    assert any(entry["status"] == "regional_pollution_skipped" and entry["station_count"] == 5 for entry in history)


@pytest.mark.asyncio
async def test_pollutants_are_counted_and_grouped_independently(monkeypatch, tmp_path):
    fetcher, sent = build(monkeypatch, tmp_path, rows_for(high_pm25=[90], high_pm10=[170, 180, 190]))
    result = await fetcher.fetch_and_store()
    assert result["sent"] == 2
    messages = [call[0][1] for call in sent]
    assert sum("PM2.5" in message for message in messages) == 1
    pm10 = [message for message in messages if "PM10" in message]
    assert len(pm10) == 1 and "3个乡镇及办事处站" in pm10[0]


@pytest.mark.asyncio
async def test_equipment_extremes_do_not_send_but_leave_audit(monkeypatch, tmp_path):
    # PM2.5=500：严重污染 vs 优，等级差5；PM10=600 同判极端。
    fetcher, sent = build(monkeypatch, tmp_path, rows_for(high_pm25=[500], high_pm10=[600]))
    result = await fetcher.fetch_and_store()
    assert result["sent"] == 0 and result["equipment_filtered"] == 2
    assert sent == []
    history = fetcher.state._load()["history"]
    assert {entry["status"] for entry in history} == {"equipment_filtered"}


def test_modified_z_extreme_is_equipment_anomaly():
    rows = rows_for(high_pm25=[95])
    # MAD=0 不判 z；注入非零 MAD 且远超 z 阈值。
    for index, row in enumerate(rows[:10]):
        row["PM25"] = 20 + (index % 3) * 3
    _, groups = detect_high_value_groups(rows)
    item = groups[0]["alerts"][0]
    assert item["modified_z"] >= 8
    assert item["equipment_suspected"] and not groups[0]["stations"]


@pytest.mark.asyncio
async def test_llm_receives_structured_evidence_and_organizes_text():
    class LLM:
        def __init__(self):
            self.request = None

        async def chat_anthropic(self, messages, **_kwargs):
            self.request = messages[0]["content"]
            return {"content": [{"type": "text", "text": "【乡镇高值提醒】丁庄站PM10小时浓度偏高，请加强排查。"}]}

        def clean_thinking_tags(self, text):
            return text

    rows = rows_for(high_pm25=[90])
    _, groups = detect_high_value_groups(rows)
    llm = LLM()
    message = await render_message(groups[0], {}, llm=llm)
    assert message.startswith("【乡镇高值提醒】")
    assert '"stations"' in llm.request and '"weather"' in llm.request
    assert '"value": 90.0' in llm.request and '"baseline"' in llm.request


@pytest.mark.asyncio
async def test_message_format_and_weather(monkeypatch, tmp_path):
    rows = rows_for(high_pm25=[90])
    rows[-1]["StationName"] = "魏都区颍昌街道办事处"
    rows[-1]["PM25"] = 75.5
    fetcher, sent = build(monkeypatch, tmp_path, rows)
    await fetcher.fetch_and_store()
    message = sent[0][0][1]
    assert message.startswith("【乡镇高值提醒】14时00分乡镇及办事处站数据显示魏都区颍昌街道办事处PM2.5浓度实时小时数据为75.5微克/立方米")
    assert "请属地加强上风向及站点周边污染源排查，当前气象情况：" in message
    assert "温度8.2℃" in message and "西北风" in message and "风速2.3米/秒" in message
    assert sent[0][1]["media"] == ["registry/map.png"]


@pytest.mark.asyncio
async def test_missing_weather_still_sends_with_explicit_clause(monkeypatch, tmp_path):
    fetcher, sent = build(monkeypatch, tmp_path, rows_for(high_pm25=[90]), weather=Weather(False))
    await fetcher.fetch_and_store()
    assert "当前气象情况：暂无可用气象观测。" in sent[0][0][1]


@pytest.mark.asyncio
async def test_same_hour_group_is_idempotent(monkeypatch, tmp_path):
    fetcher, sent = build(monkeypatch, tmp_path, rows_for(high_pm25=[90], high_pm10=[170]))
    first = await fetcher.fetch_and_store()
    second = await fetcher.fetch_and_store()
    assert first["sent"] == 2 and second["sent"] == 0
    assert second["status"] == "no_alert_or_duplicate" and len(sent) == 2


@pytest.mark.asyncio
async def test_screenshot_failure_never_sends(monkeypatch, tmp_path):
    def fail(*_args):
        raise RuntimeError("browser unavailable")
    fetcher, sent = build(monkeypatch, tmp_path, rows_for(high_pm25=[90]), capture=fail)
    result = await fetcher.fetch_and_store()
    assert result["status"] == "completed" and result["failed_groups"] == 1 and not sent
    assert fetcher.state._load()["history"][0]["status"] == "screenshot_failed"


@pytest.mark.asyncio
async def test_no_data_and_stale_are_safe(monkeypatch, tmp_path):
    empty, sent = build(monkeypatch, tmp_path, [])
    assert (await empty.fetch_and_store())["status"] == "no_data"
    stale, _ = build(monkeypatch, tmp_path, rows_for(high_pm25=[90]))
    stale.now_factory = lambda: NOW + timedelta(hours=4)
    assert (await stale.fetch_and_store())["status"] == "stale"
    assert not sent
