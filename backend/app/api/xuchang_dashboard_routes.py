"""Project-owned read-only API for the Xuchang big-screen dashboard.

The snapshot is materialized by ``xuchang_screen_snapshot_fetcher`` (worker
process) into the shared data registry; this endpoint only reads the file, so
all uvicorn workers serve byte-identical screens without touching Cube or
SQL Server per request.

P1: 告警热更新 —— snapshot 返回前实时重读场景一 episode_state.json，把
分钟级的新告警合并进 alerts 段（快照本体每 5 分钟刷新一次，告警不需要等）。
P1: 资产出网 —— /asset 按 registry 相对路径白名单校验后回图，供焦点轮播
展示传输轨迹 / GEMS 卫星图；素材路径不直接暴露绝对路径，且要求登录。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi import status

from app.auth.dependencies import optional_current_user
from app.auth.models import CurrentUser
from app.fetchers.xuchang_screen_snapshot import (
    ALERT_WINDOW,
    ASSET_EXTENSIONS,
    SNAPSHOT_DIR,
    SNAPSHOT_FILE,
)
from app.utils.path_config import get_data_registry

router = APIRouter(prefix="/api/xuchang-dashboard", tags=["xuchang-dashboard"])

_STATION_SERIES_CUBES = {
    "township": "TownFiveMinute",
    "shengkong": "ShengkongHour",
    "office": "OfficeFiveMinute",
}
_SERIES_MEASURES = {
    "pm25": "avgPm25", "pm10": "avgPm10", "o3": "avgO3",
    "so2": "avgSo2", "no2": "avgNo2", "co": "avgCo",
}
_OFFICE_UNSUPPORTED_METRICS = {"o3", "so2", "no2", "co"}

_MEDIA_TYPE = "application/json"
# 快照资产路径只允许 registry 内的相对路径；.. 与绝对路径一律拒绝
_UNSAFE_ASSET_PATH = re.compile(r"(^[/\\])|\.\.|[\x00-\x1f]")


async def require_dashboard_reader(
    request: Request,
    user: CurrentUser | None = Depends(optional_current_user),
) -> CurrentUser | None:
    """大屏读取鉴权：超级管理员网关身份，或部署级大屏直连令牌（?access_token=）。

    页面开发阶段：登录身份仅超级管理员放行；令牌直连（墙屏设备）保留，
    令牌校验与中间件 _valid_dashboard_access 同源（dashboard_access_token），
    此处复核是防止中间件配置遗漏时令牌直接命中路由，也覆盖 POST/非 GET 语义。
    """
    if user is not None:
        if not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="dashboard_admin_only",
            )
        return user
    from config.settings import settings

    configured = settings.dashboard_access_token
    if configured:
        supplied = request.query_params.get("access_token") or ""
        if supplied and hmac.compare_digest(supplied, configured):
            return None
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication_required",
    )


def _snapshot_path() -> Path:
    return get_data_registry() / SNAPSHOT_DIR / SNAPSHOT_FILE


def _read_alert_episodes() -> List[Dict[str, Any]]:
    """读场景一 episode 状态并整理成快照 alerts 行（快照缺失时兜底数据源）。

    逻辑与 fetcher._alerts 对齐：活跃优先，24h 内关闭的保留回看；
    这里不查站点坐标（热合并场景沿用快照已有行的坐标，新行置空由
    前端按站点名匹配），避免 API 层触碰数据库。
    """
    from app.scenarios.xuchang_daily_review.episodes import (
        iter_episodes,
        load_episode_state,
    )

    state_path = (
        get_data_registry()
        / "xuchang_station_deviation_alerts"
        / "episode_state.json"
    )
    try:
        state = load_episode_state(state_path)
    except Exception:
        state = None
    if not state:
        return []

    window_start = datetime.now() - ALERT_WINDOW
    rows: List[Dict[str, Any]] = []
    for episode in iter_episodes(state):
        status = str(episode.get("status") or "unknown").strip()
        started = episode.get("started_at")
        last_seen = episode.get("last_seen_at") or started
        if status != "active":
            moment = _safe_dt(last_seen)
            if moment is None or moment < window_start:
                continue
        rows.append({
            "episode_id": episode.get("episode_id"),
            "station_id": episode.get("station_id"),
            "station_name": episode.get("station_name") or episode.get("station_id"),
            "target_pollutant": episode.get("target_pollutant"),
            "alert_type": episode.get("alert_type"),
            "status": status,
            "started_at": started,
            "last_seen_at": last_seen,
            "hour_count": episode.get("hour_count"),
            "peak_station_value": episode.get("peak_station_value"),
            "peak_deviation_ratio": episode.get("peak_deviation_ratio"),
            "lon": None,
            "lat": None,
            "hot": True,  # 标记热合并行，便于前端区分提示
        })
    rows.sort(key=lambda item: item.get("last_seen_at") or "", reverse=True)
    rows.sort(key=lambda item: item.get("status") != "active")
    return rows[:12]


def _safe_dt(value: Any):
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment


def _merge_hot_alerts(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """以 episode_state 为准刷新 alerts 段。

    快照行的坐标在热合并时按 episode_id 保留（episode_state 无坐标）；
    状态机权威在 episode_state，快照里的旧状态一律以热读为准。
    """
    hot = _read_alert_episodes()
    if not hot:
        return snapshot
    coords_by_id = {
        str(item.get("episode_id")): (item.get("lon"), item.get("lat"))
        for item in snapshot.get("alerts") or []
        if item.get("episode_id")
    }
    for row in hot:
        lon, lat = coords_by_id.get(str(row.get("episode_id")), (None, None))
        row["lon"] = lon
        row["lat"] = lat
    snapshot["alerts"] = hot
    return snapshot


@router.get("/screen-snapshot")
async def get_screen_snapshot(
    request: Request,
    hot_alerts: bool = Query(default=True, description="返回前实时合并告警状态"),
    user: CurrentUser | None = Depends(require_dashboard_reader),
) -> Response:
    path = _snapshot_path()
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return Response(
            content='{"detail": "大屏快照尚未生成，请等待快照任务首次运行"}',
            status_code=503,
            media_type=_MEDIA_TYPE,
        )
    if hot_alerts:
        # 热合并在 ETag 计算之前：ETag 覆盖合并后的最终响应体，告警热段
        # 变化会换 ETag，客户端重校验即可拿到新告警（304 语义保持准确）。
        try:
            snapshot = json.loads(payload)
            if isinstance(snapshot, dict):
                snapshot = _merge_hot_alerts(snapshot)
                payload = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    etag = '"' + hashlib.sha256(payload).hexdigest()[:32] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(
        content=payload,
        media_type=_MEDIA_TYPE,
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )


def _national_station_series(station_name: str, metric: str) -> List[Dict[str, Any]]:
    """国控站近 6 小时 5 分钟序列；无发布 AQI 时按六参数推算。"""
    import pyodbc

    from app.fetchers.xuchang_screen_snapshot import STATION_TABLE
    from app.scenarios.xuchang_city_exceedance.aqi import hourly_aqi_and_primary
    from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client

    client = get_sql_server_client()
    connection = pyodbc.connect(client.connection_string, timeout=15)
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT time_point, aqi, pm25, pm10, o3, so2, no2, co
            FROM {STATION_TABLE}
            WHERE station_name = ? AND time_point >= ?
            ORDER BY time_point ASC, id ASC
            """,
            station_name, (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()
    result = []
    for row in rows:
        raw = row.get(metric)
        if metric == "aqi":
            raw = row.get("aqi")
            if raw in (None, 0, -99):
                raw = hourly_aqi_and_primary({
                key: row.get(key) for key in ("pm25", "pm10", "o3", "so2", "no2", "co")
            })[0]
        value = None if raw in (None, -99) else float(raw)
        result.append({"time": row["time_point"].isoformat(), "value": value})
    return result


@router.get("/station-series")
async def get_station_series(
    station_name: str = Query(..., min_length=1, max_length=80),
    station_type: str = Query(...),
    metric: str = Query(...),
    user: CurrentUser | None = Depends(require_dashboard_reader),
) -> Dict[str, Any]:
    """站点近 6 小时曲线：国控/乡镇/办事处为 5 分钟，省控为小时。"""
    import asyncio

    from app.tools.query.xuchang_cube_metrics.tool import cube_load

    if metric not in {"aqi", *_SERIES_MEASURES}:
        raise HTTPException(status_code=400, detail="不支持的指标")
    if station_type == "office" and metric in _OFFICE_UNSUPPORTED_METRICS:
        return {"station_name": station_name, "metric": metric, "granularity": "5min", "points": []}
    if station_type == "national":
        points = await asyncio.to_thread(_national_station_series, station_name, metric)
        return {"station_name": station_name, "metric": metric, "granularity": "5min", "points": points}
    cube = _STATION_SERIES_CUBES.get(station_type)
    if not cube:
        raise HTTPException(status_code=400, detail="不支持的站点类型")
    measures = [f"{cube}.{member}" for member in (
        _SERIES_MEASURES.values() if metric == "aqi" and station_type != "office"
        else ["avgPm25", "avgPm10"] if metric == "aqi"
        else [_SERIES_MEASURES[metric]]
    )]
    now = datetime.now()
    rows = await cube_load({
        "measures": measures,
        "dimensions": [f"{cube}.dataTime"],
        "timeDimensions": [{
            "dimension": f"{cube}.dataTime",
            "dateRange": [(now - timedelta(hours=6)).isoformat(), (now + timedelta(minutes=5)).isoformat()],
        }],
        "filters": [{"member": f"{cube}.stationName", "operator": "equals", "values": [station_name]}],
        "order": {f"{cube}.dataTime": "asc"},
        "limit": 100,
    })
    points = []
    for row in rows:
        values = {
            key: row.get(f"{cube}.{member}") for key, member in _SERIES_MEASURES.items()
        }
        if metric == "aqi":
            from app.scenarios.xuchang_city_exceedance.aqi import hourly_aqi_and_primary
            raw = hourly_aqi_and_primary(values)[0]
        else:
            raw = values[metric]
        value = float(raw) if raw is not None else None
        if metric != "co" and value is not None:
            value = round(value)
        points.append({
            "time": row.get(f"{cube}.dataTime"),
            "value": value,
        })
    return {
        "station_name": station_name, "metric": metric,
        "granularity": "hour" if station_type == "shengkong" else "5min", "points": points,
    }


@router.get("/asset")
async def get_dashboard_asset(
    path: str = Query(..., description="registry 内素材相对路径"),
    user: CurrentUser | None = Depends(require_dashboard_reader),
) -> Response:
    """按快照 assets 段提供的相对路径回传素材图片。

    安全约束：仅 registry 内相对路径、仅图片扩展名、拒绝任何形式的
    目录穿越；素材必须真实存在于磁盘（快照段本身由 worker 扫描产出）。
    """
    registry = get_data_registry()
    if _UNSAFE_ASSET_PATH.search(path):
        raise HTTPException(status_code=400, detail="非法素材路径")
    suffix = Path(path).suffix.lower()
    if suffix not in ASSET_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的素材类型")
    target = (registry / path).resolve()
    try:
        target.relative_to(registry.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="素材越界")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="素材不存在或已清理")
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    return FileResponse(target, media_type=media_type, headers={"Cache-Control": "no-cache"})
