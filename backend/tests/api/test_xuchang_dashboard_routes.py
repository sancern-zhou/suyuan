"""大屏快照 API：文件读、ETag 304、快照缺失 503。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.xuchang_dashboard_routes import router
from app.auth.dependencies import optional_current_user, require_current_user
from app.fetchers.xuchang_screen_snapshot import SNAPSHOT_DIR, SNAPSHOT_FILE
from config.settings import settings as app_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.api.xuchang_dashboard_routes.get_data_registry",
        lambda: tmp_path,
    )
    app = FastAPI()
    app.include_router(router)
    # 大屏已开放给全部登录用户：require_dashboard_reader 只要求已登录
    app.dependency_overrides[optional_current_user] = lambda: SimpleNamespace(is_admin=True)
    return TestClient(app)


def test_non_admin_authenticated_user_can_read_snapshot(tmp_path, monkeypatch):
    """大屏开放给所有登录用户：非管理员登录身份不再 403。"""
    monkeypatch.setattr(
        "app.api.xuchang_dashboard_routes.get_data_registry",
        lambda: tmp_path,
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[optional_current_user] = lambda: SimpleNamespace(
        is_admin=False
    )
    non_admin_client = TestClient(app)
    _write_snapshot(tmp_path, {"schema_version": 1, "header": {"aqi": 82}})

    response = non_admin_client.get("/api/xuchang-dashboard/screen-snapshot")
    assert response.status_code == 200
    assert response.json()["header"]["aqi"] == 82


@pytest.fixture
def token_client(tmp_path, monkeypatch):
    """带部署级大屏令牌的客户端（模拟大屏设备免登录直连）。"""
    monkeypatch.setattr(
        "app.api.xuchang_dashboard_routes.get_data_registry",
        lambda: tmp_path,
    )
    monkeypatch.setattr(app_settings, "dashboard_access_token", "screen-token-123")
    app = FastAPI()
    app.include_router(router)
    # 不注入 current_user，模拟无网关会话的大屏设备
    return TestClient(app)


def _write_snapshot(registry, payload):
    directory = registry / SNAPSHOT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SNAPSHOT_FILE).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_returns_503_before_first_snapshot(client, tmp_path):
    response = client.get("/api/xuchang-dashboard/screen-snapshot")

    assert response.status_code == 503
    assert "尚未生成" in response.json()["detail"]


def test_serves_snapshot_and_304_on_unchanged(client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1, "header": {"aqi": 82}})

    first = client.get("/api/xuchang-dashboard/screen-snapshot")
    assert first.status_code == 200
    assert first.json()["header"]["aqi"] == 82
    etag = first.headers["ETag"]

    unchanged = client.get(
        "/api/xuchang-dashboard/screen-snapshot", headers={"If-None-Match": etag}
    )
    assert unchanged.status_code == 304

    _write_snapshot(tmp_path, {"schema_version": 1, "header": {"aqi": 71}})
    changed = client.get(
        "/api/xuchang-dashboard/screen-snapshot", headers={"If-None-Match": etag}
    )
    assert changed.status_code == 200
    assert changed.json()["header"]["aqi"] == 71


def test_hot_alerts_merge_overrides_snapshot_alerts(client, tmp_path):
    # 夹具时间相对当前时刻：closed 告警只保留 24h 窗内的，写死日期过一天就会漏
    from datetime import datetime, timedelta

    started = datetime.now() - timedelta(hours=10)
    last_seen = datetime.now() - timedelta(hours=5)
    _write_snapshot(tmp_path, {
        "schema_version": 1,
        "alerts": [{
            "episode_id": "ep-1", "station_name": "许昌学院", "status": "active",
            "lon": 113.8611, "lat": 34.0443,
            "dispatch": {"time": "2026-10-24T10:05:00", "text": "通报正文"},
        }],
    })
    directory = tmp_path / "xuchang_station_deviation_alerts"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "episode_state.json").write_text(json.dumps({
        "active": [{
            "episode_id": "ep-1", "station_id": "1008A", "station_name": "许昌学院",
            "status": "closed", "started_at": started.isoformat(),
            "last_seen_at": last_seen.isoformat(),
        }, {
            "episode_id": "ep-new", "station_id": "1005A", "station_name": "市一中",
            "status": "active", "started_at": "2026-10-24T15:40:00",
            "last_seen_at": "2026-10-24T15:45:00",
        }],
        "history": [],
    }), encoding="utf-8")

    response = client.get("/api/xuchang-dashboard/screen-snapshot")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    # 状态机以 episode_state 为准，ep-1 变 closed，且新增 ep-new
    statuses = {item["episode_id"]: item["status"] for item in alerts}
    assert statuses == {"ep-1": "closed", "ep-new": "active"}
    # 快照里已有的坐标在热合并时保留
    coords = {item["episode_id"]: item["lon"] for item in alerts}
    assert coords["ep-1"] == 113.8611
    assert coords["ep-new"] is None
    # 通报正文由快照段查库产出，热合并不查库，同样按 episode_id 沿用；
    # 快照里还没有的新告警要等下一次快照才有
    dispatch = {item["episode_id"]: item.get("dispatch") for item in alerts}
    assert dispatch == {
        "ep-1": {"time": "2026-10-24T10:05:00", "text": "通报正文"},
        "ep-new": None,
    }
    # 热合并行带 hot 标记
    assert all(item["hot"] for item in alerts)


def test_hot_alerts_can_be_disabled(client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1, "alerts": [{"episode_id": "ep-x"}]})

    response = client.get(
        "/api/xuchang-dashboard/screen-snapshot?hot_alerts=false"
    )
    assert response.json()["alerts"] == [{"episode_id": "ep-x"}]


def test_asset_route_rejects_traversal_and_non_images(client, tmp_path):
    # 目录穿越
    response = client.get("/api/xuchang-dashboard/asset", params={"path": "../secret.png"})
    assert response.status_code == 400
    # 绝对路径
    response = client.get("/api/xuchang-dashboard/asset", params={"path": "/etc/passwd"})
    assert response.status_code == 400
    # 非白名单扩展名
    response = client.get(
        "/api/xuchang-dashboard/asset", params={"path": "xuchang_transport_analysis/20261024/job.json"}
    )
    assert response.status_code == 400


def test_asset_route_serves_registry_image(client, tmp_path):
    import os

    asset = tmp_path / "xuchang_transport_analysis" / "20261024"
    asset.mkdir(parents=True, exist_ok=True)
    png = asset / "job-a.regional-paths.png"
    png.write_bytes(b"\x89PNG-fake-bytes")
    os.utime(png, None)

    response = client.get(
        "/api/xuchang-dashboard/asset",
        params={"path": "xuchang_transport_analysis/20261024/job-a.regional-paths.png"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_asset_route_404_for_missing_file(client, tmp_path):
    response = client.get(
        "/api/xuchang-dashboard/asset",
        params={"path": "xuchang_transport_analysis/20261024/none.png"},
    )
    assert response.status_code == 404


def test_station_series_queries_selected_metric(client, monkeypatch):
    async def fake_cube_load(query):
        assert query["measures"] == ["TownFiveMinute.avgPm10"]
        assert query["filters"][0]["values"] == ["禹州市范坡镇"]
        return [{"TownFiveMinute.dataTime": "2026-11-23T21:05:00", "TownFiveMinute.avgPm10": 61.2}]

    monkeypatch.setattr("app.tools.query.xuchang_cube_metrics.tool.cube_load", fake_cube_load)
    response = client.get("/api/xuchang-dashboard/station-series", params={
        "station_name": "禹州市范坡镇", "station_type": "township", "metric": "pm10",
    })
    assert response.status_code == 200
    assert response.json()["points"] == [{"time": "2026-11-23T21:05:00", "value": 61}]


def test_pm25_series_forced_to_hour_caliber(client, monkeypatch):
    """PM2.5 固定小时口径：显式传 5min 也强制走 TownHour(app) 小时值。"""
    async def fake_cube_load(query):
        assert query["measures"] == ["TownHour.avgPm25"]
        caliber = next(f for f in query["filters"] if f["member"] == "TownHour.caliber")
        assert caliber["values"] == ["app"]
        return [{"TownHour.dataTime": "2026-11-23T21:00:00", "TownHour.avgPm25": 61.2}]

    monkeypatch.setattr("app.tools.query.xuchang_cube_metrics.tool.cube_load", fake_cube_load)
    response = client.get("/api/xuchang-dashboard/station-series", params={
        "station_name": "禹州市范坡镇", "station_type": "township", "metric": "pm25",
        "granularity": "5min",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["granularity"] == "hour"
    assert payload["points"] == [{"time": "2026-11-23T21:00:00", "value": 61}]


def test_office_unsupported_metric_returns_empty_without_query(client):
    response = client.get("/api/xuchang-dashboard/station-series", params={
        "station_name": "东城区邓庄街道办事处", "station_type": "office", "metric": "o3",
    })
    assert response.status_code == 200
    assert response.json()["points"] == []


def test_national_station_series_uses_hour_table_and_caliber(client, monkeypatch):
    async def fake_to_thread(func, *args):
        assert args == ("许昌学院", "pm25", "hour")
        return [{"time": "2026-11-24T09:00:00", "value": 58}]

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    response = client.get("/api/xuchang-dashboard/station-series", params={
        "station_name": "许昌学院", "station_type": "national", "metric": "pm25",
        "granularity": "hour",
    })
    assert response.status_code == 200
    assert response.json()["granularity"] == "hour"


def test_national_series_normalizes_platform_station_suffix(monkeypatch):
    from datetime import datetime

    from app.api.xuchang_dashboard_routes import _national_station_series

    class Cursor:
        description = [("station_name",), ("time_point",), ("aqi",), ("pm25",),
                       ("pm10",), ("o3",), ("so2",), ("no2",), ("co",)]

        def execute(self, sql, *params):
            assert "dat_zhongda_station_hour" in sql

        def fetchall(self):
            return [("望田路111号（启用20250213）", datetime(2026, 11, 24, 23),
                     50, 26, 40, 30, 4, 30, 0.5)]

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr("pyodbc.connect", lambda *args, **kwargs: Connection())
    points = _national_station_series("望田路111号", "pm25", "hour")
    assert points == [{"time": "2026-11-24T23:00:00", "value": 26.0}]


def test_shengkong_does_not_fake_five_minute_series(client):
    # PM2.5 已强制小时口径，这里用 PM10 验证省控 5 分钟 guard
    response = client.get("/api/xuchang-dashboard/station-series", params={
        "station_name": "禹州神龙公司", "station_type": "shengkong", "metric": "pm10",
        "granularity": "5min",
    })
    assert response.status_code == 200
    assert response.json()["points"] == []


def test_station_series_rejects_unknown_type(client):
    response = client.get("/api/xuchang-dashboard/station-series", params={
        "station_name": "测试站", "station_type": "unknown", "metric": "pm25",
    })
    assert response.status_code == 400


def test_token_client_without_token_is_401(token_client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1, "header": {"aqi": 82}})

    response = token_client.get("/api/xuchang-dashboard/screen-snapshot")
    assert response.status_code == 401


def test_token_client_with_valid_token_reads_snapshot(token_client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1, "header": {"aqi": 82}})

    response = token_client.get(
        "/api/xuchang-dashboard/screen-snapshot?access_token=screen-token-123"
    )
    assert response.status_code == 200
    assert response.json()["header"]["aqi"] == 82


def test_token_client_with_wrong_token_is_401(token_client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1})

    response = token_client.get(
        "/api/xuchang-dashboard/screen-snapshot?access_token=wrong"
    )
    assert response.status_code == 401


def test_token_grants_asset_route_too(token_client, tmp_path):
    import os

    asset = tmp_path / "xuchang_transport_analysis" / "20261024"
    asset.mkdir(parents=True, exist_ok=True)
    (asset / "job-a.regional-paths.png").write_bytes(b"\x89PNG-fake-bytes")

    ok = token_client.get(
        "/api/xuchang-dashboard/asset",
        params={
            "path": "xuchang_transport_analysis/20261024/job-a.regional-paths.png",
            "access_token": "screen-token-123",
        },
    )
    assert ok.status_code == 200
    denied = token_client.get(
        "/api/xuchang-dashboard/asset",
        params={"path": "xuchang_transport_analysis/20261024/job-a.regional-paths.png"},
    )
    assert denied.status_code == 401
