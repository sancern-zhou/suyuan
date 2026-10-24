"""许昌数据大屏快照 fetcher：聚合、单段降级、乡镇站口径回退、告警窗口。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.fetchers.xuchang_screen_snapshot import (
    SNAPSHOT_DIR,
    SNAPSHOT_FILE,
    XuchangScreenSnapshotFetcher,
)

NOW = datetime(2026, 10, 24, 15, 0, 0)
CUTOFF = "2026-10-24T14:00:00.000"


def _cube_rows(cube: str, members: dict[str, Any]) -> list[dict[str, Any]]:
    return [{f"{cube}.{key}": value for key, value in members.items()}]


def _make_cube_load(handlers: dict[str, Any]):
    """按 measures[0] 分发的 cube_load 假实现；值为异常则抛出。"""

    async def _load(query: dict[str, Any]) -> list[dict[str, Any]]:
        key = query["measures"][0]
        handler = handlers.get(key)
        if handler is None:
            raise AssertionError(f"未预期的 Cube 查询: {query}")
        if isinstance(handler, Exception):
            raise handler
        return handler(query)

    return _load


def _default_handlers() -> dict[str, Any]:
    return {
        # cutoff 探测
        "SsfbCityHour.count": _cube_rows("SsfbCityHour", {"dataTime": CUTOFF, "count": 1}),
        # header（dimensions 含 quality）
        "SsfbCityHour.maxAqi": lambda query: (
            _cube_rows("SsfbCityHour", {
                "maxAqi": 82, "avgPm25": 58, "avgPm10": 96, "avgO3": 105,
                "avgNo2": 34, "avgSo2": 8, "avgCo": 0.6,
                "quality": "良", "primaryPollutant": "PM2.5",
            })
            if "SsfbCityHour.quality" in query.get("dimensions", [])
            else _cube_rows("SsfbCityHour", {
                "dataTime": CUTOFF, "maxAqi": 82, "avgPm25": 58,
                "avgPm10": 96, "avgO3": 105,
            })
        ),
        "SsfbCityHourRank.rankAqi": [
            *_cube_rows("SsfbCityHourRank", {
                "city": "漯河市", "rankAqi": 1, "avgAqi": 61, "avgPm25": 43,
                "quality": "良", "primaryPollutant": None,
            }),
            *_cube_rows("SsfbCityHourRank", {
                "city": "许昌市", "rankAqi": 5, "avgAqi": 82, "avgPm25": 58,
                "quality": "良", "primaryPollutant": "PM2.5",
            }),
        ],
        "SsfbCountyHourRank.rankAqi": _cube_rows("SsfbCountyHourRank", {
            "county": "建安区", "rankAqi": 1, "avgAqi": 79, "avgPm25": 55,
            "quality": "良", "primaryPollutant": "PM2.5",
        }),
        # 区县代表点（地图 counties 层）
        "SsfbCountyHour.maxAqi": _cube_rows("SsfbCountyHour", {
            "county": "建安区", "maxAqi": 79, "avgPm25": 55,
            "quality": "良", "primaryPollutant": "PM2.5",
        }),
        "XuchangCityYearTarget.pm25Target": _cube_rows("XuchangCityYearTarget", {
            "year": "2026", "pm25Target": 44, "pm10Target": 76,
            "goodDaysTarget": 285, "heavyDaysTarget": 3,
        }),
        "ProvinceMonthCum.pm25": _cube_rows("ProvinceMonthCum", {
            "dataMonth": "2026-09-01T00:00:00.000", "pm25": 43.2, "pm10": 74,
            "goodDays": 218, "heavyDays": 1, "goodDaysRatio": 79.9,
        }),
        "SsfbCityDay.count": [
            *_cube_rows("SsfbCityDay", {"quality": "优", "count": 4, "avgPm25": 30}),
            *_cube_rows("SsfbCityDay", {"quality": "良", "count": 10, "avgPm25": 52}),
            *_cube_rows("SsfbCityDay", {"quality": "轻度污染", "count": 2, "avgPm25": 88}),
        ],
    }


def _write_episode_state(registry: Path, episodes: dict[str, list[dict[str, Any]]]) -> None:
    directory = registry / "xuchang_station_deviation_alerts"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "episode_state.json").write_text(
        json.dumps({"active": episodes.get("active", []), "history": episodes.get("history", [])}),
        encoding="utf-8",
    )


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.fetchers.xuchang_screen_snapshot.get_data_registry",
        lambda: tmp_path,
    )
    return tmp_path


def _make_fetcher(monkeypatch, handlers) -> XuchangScreenSnapshotFetcher:
    monkeypatch.setattr(
        "app.fetchers.xuchang_screen_snapshot.cube_load", _make_cube_load(handlers)
    )
    monkeypatch.setattr(
        XuchangScreenSnapshotFetcher, "_observed_met",
        lambda self: {"time": "2026-10-24T14:00:00", "temperature": 18.2,
                      "humidity": 61, "wind_speed": 8.0, "wind_direction": 45.0},
    )
    monkeypatch.setattr(
        XuchangScreenSnapshotFetcher, "_forecast_72h",
        lambda self: {"hourly": [{"data_time": "2026-10-24T15:00:00", "aqi": 79, "pm25": 55}],
                      "daily": [{"date": "2026-10-25", "aqi": 80, "min_aqi": 70,
                                 "max_aqi": 90, "primary_pollutant": "PM2.5"}]},
    )
    monkeypatch.setattr(
        XuchangScreenSnapshotFetcher, "_national_stations",
        lambda self, alert_names: [{
            "station_id": "1008A", "station_name": "许昌学院", "type": "national",
            "lon": 113.8611, "lat": 34.0443, "data_time": CUTOFF,
            "aqi": 85, "pm25": 60, "pm10": 100, "o3": 110, "alerting": False,
        }],
    )
    monkeypatch.setattr(
        XuchangScreenSnapshotFetcher, "_broadcast",
        lambda self: [{"time": "2026-10-24T08:05:00", "task_name": "站点日污染溯源报告",
                       "station_name": "许昌学院", "text": "结论摘要"}],
    )
    monkeypatch.setattr(
        XuchangScreenSnapshotFetcher, "_assets",
        lambda self: [{
            "kind": "transport", "title": "区域后向轨迹走廊图",
            "asset_path": "xuchang_transport_analysis/20261024/j1.regional-paths.png",
            "taken_at": "2026-10-24T09:30:00",
        }],
    )
    return XuchangScreenSnapshotFetcher(now_factory=lambda: NOW)


@pytest.fixture
def episodes_writer(registry):
    return _write_episode_state


async def test_fetch_and_store_writes_full_snapshot(
    monkeypatch, registry, episodes_writer
):
    episodes_writer({
        "active": [{
            "episode_id": "ep-1", "station_id": "1008A", "station_name": "许昌学院",
            "target_pollutant": "pm25", "alert_type": "deviation", "status": "active",
            "started_at": "2026-10-24T10:00:00", "last_seen_at": "2026-10-24T14:00:00",
            "hour_count": 5, "peak_station_value": 96, "peak_deviation_ratio": 1.8,
        }],
        "history": [],
    })
    handlers = _default_handlers()
    # 乡镇站：app 口径无数据 → 回退 src
    handlers["TownHour.count"] = lambda query: (
        [] if query["filters"][0]["values"] == ["app"]
        else _cube_rows("TownHour", {"dataTime": "2026-10-24T14:00:00.000", "count": 1})
    )
    handlers["TownHour.avgPm25"] = _cube_rows("TownHour", {
        "stationName": "禹州市范坡镇", "avgPm25": 61, "maxAqi": 86,
    })

    fetcher = _make_fetcher(monkeypatch, handlers)
    result = await fetcher.fetch_and_store()

    snapshot_path = registry / SNAPSHOT_DIR / SNAPSHOT_FILE
    assert snapshot_path.exists()
    assert result["segments_failed"] == []
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert snapshot["schema_version"] == 1
    assert snapshot["data_cutoff_hour"] == CUTOFF
    assert snapshot["errors"] is None
    # header
    assert snapshot["header"]["aqi"] == 82
    assert snapshot["header"]["quality"] == "良"
    assert snapshot["header"]["met"]["humidity"] == 61
    # 排名
    assert snapshot["city_hour_rank"]["rows"][0]["city"] == "漯河市"
    assert snapshot["city_hour_rank"]["rows"][1]["rank"] == 5
    assert snapshot["county_hour_rank"]["rows"][0]["county"] == "建安区"
    # 达标：官方累计截至 9 月，本地 10 月自算 14 天中 14 天优良
    assert snapshot["year_target"]["official_cum"]["as_of_month"] == "2026-09"
    local = snapshot["year_target"]["local_since_official"]
    assert local["from"] == "2026-10-01"
    assert local["to"] == "2026-10-23"
    assert local["good_days"] == 14
    assert local["days_total"] == 16
    assert local["pm25_avg"] == 51.0
    # 告警
    assert snapshot["alerts"][0]["station_name"] == "许昌学院"
    assert snapshot["alerts"][0]["status"] == "active"
    assert snapshot["alerts"][0]["lon"] == 113.8611
    # 站点：国控 + 乡镇（src 回退）
    assert snapshot["stations"]["national"][0]["station_id"] == "1008A"
    townships = snapshot["stations"]["townships"]
    assert townships and townships[0]["caliber"] == "src"
    assert townships[0]["lon"] == 113.531
    # 区县代表点：仅内置坐标表中的区县 + 最新小时值
    counties = snapshot["stations"]["counties"]
    assert counties and counties[0]["station_name"] == "建安区"
    assert counties[0]["type"] == "county"
    assert counties[0]["aqi"] == 79
    # 轮播素材段
    assert snapshot["assets"][0]["kind"] == "transport"
    assert "xuchang_transport_analysis" in snapshot["assets"][0]["asset_path"]
    # 播报
    assert snapshot["broadcast"][0]["task_name"] == "站点日污染溯源报告"


async def test_segment_failure_degrades_without_killing_screen(monkeypatch, registry):
    handlers = _default_handlers()
    handlers["SsfbCityHourRank.rankAqi"] = RuntimeError("语义层排队超时")
    _write_episode_state(registry, {"active": [], "history": []})

    fetcher = _make_fetcher(monkeypatch, handlers)
    result = await fetcher.fetch_and_store()

    snapshot = json.loads(
        (registry / SNAPSHOT_DIR / SNAPSHOT_FILE).read_text(encoding="utf-8")
    )
    assert snapshot["city_hour_rank"] is None
    assert "语义层排队超时" in snapshot["errors"]["city_hour_rank"]
    assert snapshot["header"]["aqi"] == 82
    assert result["segments_failed"] == ["city_hour_rank"]


async def test_cutoff_missing_skips_realtime_segments(monkeypatch, registry):
    handlers = _default_handlers()
    handlers["SsfbCityHour.count"] = []
    _write_episode_state(registry, {"active": [], "history": []})

    fetcher = _make_fetcher(monkeypatch, handlers)
    await fetcher.fetch_and_store()

    snapshot = json.loads(
        (registry / SNAPSHOT_DIR / SNAPSHOT_FILE).read_text(encoding="utf-8")
    )
    assert snapshot["data_cutoff_hour"] is None
    assert snapshot["header"] is None
    assert snapshot["city_hour_rank"] is None
    # 与 cutoff 无关的段照常生成
    assert snapshot["year_target"]["official_cum"]["good_days"] == 218


async def test_alerts_window_and_order(monkeypatch, registry):
    _write_episode_state(registry, {
        "active": [{
            "episode_id": "ep-active", "station_id": "1008A", "station_name": "许昌学院",
            "status": "active", "started_at": "2026-10-24T09:00:00",
            "last_seen_at": "2026-10-24T13:00:00",
        }],
        "history": [
            {
                "episode_id": "ep-recent", "station_id": "1005A", "station_name": "市一中",
                "status": "closed", "started_at": "2026-10-23T10:00:00",
                "last_seen_at": "2026-10-24T07:00:00",
            },
            {
                "episode_id": "ep-stale", "station_id": "1003A", "station_name": "开发区",
                "status": "closed", "started_at": "2026-10-18T10:00:00",
                "last_seen_at": "2026-10-19T07:00:00",
            },
        ],
    })
    handlers = _default_handlers()
    fetcher = _make_fetcher(monkeypatch, handlers)

    alerts = fetcher._alerts()

    assert [item["episode_id"] for item in alerts] == ["ep-active", "ep-recent"]


def test_screen_snapshot_fetcher_is_registered_for_xuchang():
    from types import SimpleNamespace

    from app.services import lifecycle_manager

    context = SimpleNamespace(
        enabled_modules={"legacy", "xuchang-air-quality"},
        manifest=SimpleNamespace(
            backend=SimpleNamespace(
                fetchers=["xuchang_screen_snapshot_fetcher"],
                weather_history=None,
            )
        ),
    )
    fetchers = lifecycle_manager._configured_fetchers(context)

    assert [fetcher.name for fetcher in fetchers] == ["xuchang_screen_snapshot_fetcher"]
    assert fetchers[0].schedule == "11,41 * * * *"


def test_assets_scanner_picks_latest_per_kind_with_window(registry, monkeypatch):
    from app.fetchers.xuchang_screen_snapshot import (
        ASSETS_PER_KIND,
        XuchangScreenSnapshotFetcher as F,
    )
    import os

    now_ts = NOW.timestamp()
    transport_dir = registry / "xuchang_transport_analysis" / "20261024"
    transport_dir.mkdir(parents=True, exist_ok=True)
    gems_dir = registry / "satellite" / "gems" / "xuchang"
    gems_dir.mkdir(parents=True, exist_ok=True)
    stale_dir = registry / "xuchang_transport_analysis" / "20260101"
    stale_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        transport_dir / "job-a.regional-paths.png": now_ts - 100,
        transport_dir / "job-a.local-enterprise.png": now_ts - 200,
        gems_dir / "gems_AOD_xuchang_20261024100000.png": now_ts - 300,
        stale_dir / "job-old.regional-paths.png": now_ts - 200 * 86400,
    }
    for path, mtime in paths.items():
        path.write_bytes(b"png")
        os.utime(path, (mtime, mtime))

    # 超出每类上限的多余文件
    extra = transport_dir / "job-b.regional-paths.png"
    extra.write_bytes(b"png")
    os.utime(extra, (now_ts - 50, now_ts - 50))

    fetcher = F(now_factory=lambda: NOW)
    assets = fetcher._assets()

    kinds = [item["kind"] for item in assets]
    assert kinds.count("transport") <= ASSETS_PER_KIND
    assert "gems" in kinds
    # 窗口外的旧文件不入快照
    assert all("job-old" not in item["asset_path"] for item in assets)
    # 按 mtime 倒序，最新的 job-b 优先于 job-a
    assert assets[0]["asset_path"].endswith("job-b.regional-paths.png")
