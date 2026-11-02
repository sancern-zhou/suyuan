# -*- coding: utf-8 -*-
"""站点门禁出入事件同步(每日, sync-daily.cmd 调用)。

源: 平台海康门禁 API stationintegrate/HK/GetACSDoorRecordsAsync(省控 101 站一把查询,
数组下标参数 + ConfigType=2, 缺 ConfigType 接口恒返回空 — 2026-11-02 实测定案)。
目标: jiangsu_ods.acs_door_records, 主键 event_id 幂等 upsert。
水位: jiangsu_sync.sync_watermark 存最大 event_time; 增量窗口 = 水位 - 3 天重叠
      (事件时间/接收时间可能回拨, 重叠 + 主键 upsert 保证不丢不重)。
首次运行回填 BACKFILL_DAYS 天(~1.5 万行, 全省约 40 条/天)。

站点编码来源: API 响应只给设备名 devName, 以 jiangsu_mart.dim_station 的
station_name 精确匹配回填 station_code; 匹配不上的行 station_code 为空,
由 mart 层 warn 级测试兜住, dev_name 原文保留可追溯。

用法:
    E:\Tools\Python311\python.exe sync_door_access.py            # 增量(首次自动回填)
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_table  # noqa: E402  复用水位/日志/建表机制

import asyncpg  # noqa: E402

TABLE = "acs_door_records"
DOOR_PATH = "stationintegrate/HK/GetACSDoorRecordsAsync"
TOKEN_PATH = "AirCityBaseCommon/GetExternalApiToken"
PAGE_SIZE = 1000
MAX_PAGES = 100
OVERLAP = dt.timedelta(days=3)
BACKFILL_DAYS = 400

# 门禁设备名 devName 与 dim_station.station_name 的已知差异(手工登记, 2026-11-02 对账;
# 差异形态=后缀多"站"/省名前缀/简称/门禁侧错别字)。值必须是对应 dim_station 的 station_name。
# 出现新的 unmatched devName 时先在这里登记再重跑; 真无站点台账的设备(如 涟水涟缘水务站/
# 阜宁金沙湖街道/东台实中南校区/海门社会福利院/睢宁永康路/盐都郭猛社区)不登记, 留空可追溯。
DEV_NAME_ALIASES = {
    "洪泽水利局站": "洪泽水利局",
    "盱眙泵站路站": "盱眙泵站路",
    "盱眙淮河大桥站": "盱眙淮河大桥",
    "邳州中山路站": "邳州中山路",
    "邳州环境监测站": "邳州监测站",
    "丰县文体站": "丰县凤城文体站",
    "丰县闸站管理处站": "丰县闸站管理处",
    "沛县汉源宾馆站": "沛县汉源宾馆",
    "沛县煤电公司研发中心站": "沛县煤电公司研发中心",
    "金湖二中站": "金湖二中",
    "东台西溪植物园站": "东台西溪植物园",
    "苏州太仓科教新城实小": "太仓科教新城实小",
    "盐都严塘河公园": "盐都盐塘河公园",  # 门禁侧错别字: 严塘河→盐塘河
}

DDL = """
CREATE TABLE IF NOT EXISTS jiangsu_ods.acs_door_records (
    event_id        text PRIMARY KEY,
    station_code    text,
    dev_name        text,
    door_name       text,
    event_time      timestamp,
    receive_time    timestamp,
    event_name      text,
    event_type      integer,
    in_and_out_type integer,
    person_id       text,
    person_name     text,
    card_no         text,
    org_name        text,
    cert_no         text,
    reader_dev_name text,
    pic_uri         text,
    raw             jsonb,
    _src_incremental text,
    _sync_batch     uuid,
    _synced_at      timestamp default now()
);
"""

UPSERT = """
INSERT INTO jiangsu_ods.acs_door_records (
    event_id, station_code, dev_name, door_name, event_time, receive_time,
    event_name, event_type, in_and_out_type, person_id, person_name,
    card_no, org_name, cert_no, reader_dev_name, pic_uri, raw,
    _src_incremental, _sync_batch
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
ON CONFLICT (event_id) DO UPDATE SET
    station_code=EXCLUDED.station_code, dev_name=EXCLUDED.dev_name,
    door_name=EXCLUDED.door_name, event_time=EXCLUDED.event_time,
    receive_time=EXCLUDED.receive_time, event_name=EXCLUDED.event_name,
    event_type=EXCLUDED.event_type, in_and_out_type=EXCLUDED.in_and_out_type,
    person_id=EXCLUDED.person_id, person_name=EXCLUDED.person_name,
    card_no=EXCLUDED.card_no, org_name=EXCLUDED.org_name,
    cert_no=EXCLUDED.cert_no, reader_dev_name=EXCLUDED.reader_dev_name,
    pic_uri=EXCLUDED.pic_uri, raw=EXCLUDED.raw,
    _src_incremental=EXCLUDED._src_incremental, _sync_batch=EXCLUDED._sync_batch
"""


def _air_api_cfg() -> dict:
    """平台接口地址与凭据: 与后端同一份 .env(dq_check.py 同套路)。"""
    from dotenv import load_dotenv

    load_dotenv(r"E:\suyuan\backend\.env.jiangsu-ops")
    cfg = {
        "base_url": os.getenv("JIANGSU_AIR_API_BASE_URL", "").rstrip("/"),
        "username": os.getenv("JIANGSU_AIR_API_USERNAME", ""),
        "password": os.getenv("JIANGSU_AIR_API_PASSWORD", ""),
    }
    if not all(cfg.values()):
        raise SystemExit("JIANGSU_AIR_API_* 未配置(查 E:\\suyuan\\backend\\.env.jiangsu-ops)")
    return cfg


class AirApiClient:
    """同步脚本用的最小鉴权客户端(对齐后端 _JiangsuAuthenticatedApi)。"""

    def __init__(self, cfg: dict) -> None:
        self.base_url = cfg["base_url"]
        self._username = cfg["username"]
        self._password = cfg["password"]
        self._token: str | None = None

    def _get_token(self) -> str:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{self.base_url}/{TOKEN_PATH}",
                params={"UserName": self._username, "Pwd": self._password},
            )
        resp.raise_for_status()
        token = resp.json().get("result")
        if not isinstance(token, str) or not token:
            raise RuntimeError("江苏接口 Token 获取失败")
        return token

    def __call__(self, path: str, params: list[tuple[str, str]]) -> dict:
        if self._token is None:
            self._token = self._get_token()
        with httpx.Client(timeout=60) as client:
            resp = client.get(
                f"{self.base_url}/{path.lstrip('/')}", params=params,
                headers={"Authorization": f"Bearer {self._token}",
                         "SysCode": "SunAirProvince", "Accept": "application/json"},
            )
        if resp.status_code == 401:  # token 过期, 重取一次
            self._token = None
            return self(path, params)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(str(payload.get("msg") or "江苏接口返回失败"))
        return payload


def _parse_ts(value) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _clean_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    return text or None


def fetch_all_pages(client: AirApiClient, codes: list[str], start: dt.datetime,
                    end: dt.datetime) -> list[dict]:
    """全省一把查询(数组下标绑定), skipCount 翻页到拉满 total。"""
    rows: list[dict] = []
    for page in range(MAX_PAGES):
        params: list[tuple[str, str]] = [
            ("skipCount", str(page * PAGE_SIZE)),
            ("sorting", "id"),
            ("maxResultCount", str(PAGE_SIZE)),
            ("ConfigType", "2"),
        ]
        params += [(f"StationCode[{i}]", c) for i, c in enumerate(codes)]
        params += [
            ("EventTime[0]", start.strftime("%Y-%m-%d %H:%M:%S")),
            ("EventTime[1]", end.strftime("%Y-%m-%d %H:%M:%S")),
        ]
        payload = client(DOOR_PATH, params)
        result = payload.get("result") if isinstance(payload, dict) else None
        items = (result or {}).get("list") or []
        rows.extend(r for r in items if isinstance(r, dict))
        total = (result or {}).get("total") or 0
        if len(rows) >= total or not items:
            break
    else:
        raise RuntimeError(f"门禁记录翻页超上限({MAX_PAGES} 页), 拒绝带缺推进水位")
    return rows


def row_tuple(record: dict, station_map: dict[str, str], batch_id: uuid.UUID) -> tuple:
    dev_name = _clean_str(record.get("devName")) or ""
    station_code = station_map.get(DEV_NAME_ALIASES.get(dev_name, dev_name))
    event_time = _parse_ts(record.get("eventTime"))
    return (
        _clean_str(record.get("eventId")),
        station_code,
        dev_name or None,
        _clean_str(record.get("doorName")),
        event_time,
        _parse_ts(record.get("receiveTime")),
        _clean_str(record.get("eventName")),
        record.get("eventType") if isinstance(record.get("eventType"), int) else None,
        record.get("inAndOutType") if isinstance(record.get("inAndOutType"), int) else None,
        _clean_str(record.get("personId")),
        _clean_str(record.get("personName")),
        _clean_str(record.get("cardNo")),
        _clean_str(record.get("orgName")),
        _clean_str(record.get("certNo")),
        _clean_str(record.get("readerDevName")),
        _clean_str(record.get("picUri")),
        json.dumps(record, ensure_ascii=False, default=str),
        str(event_time) if event_time else None,
        batch_id,
    )


async def main_async() -> int:
    cfg_dsn = sync_table.load_config()["target"]
    batch_id = uuid.uuid4()
    started = dt.datetime.now()
    entry = {"batch_id": batch_id, "table_name": TABLE, "mode": "incremental",
             "started_at": started, "status": "running", "rows_fetched": 0}
    pg = await asyncpg.connect(cfg_dsn["dsn"])
    try:
        await sync_table.ensure_meta(pg)
        await pg.execute(DDL)

        # 只同步省控 101 站(与门禁平台配置一致; 全量站点会让 URL 超 414 上限)
        stations = await pg.fetch(
            "SELECT station_code, station_name FROM jiangsu_mart.dim_station "
            "WHERE is_active_provincial = true")
        station_map = {(s["station_name"] or "").strip(): s["station_code"] for s in stations}
        codes = sorted(s["station_code"] for s in stations if s["station_code"])
        print(f"stations from dim_station: {len(codes)}", flush=True)

        wm = await sync_table.get_watermark(pg, TABLE)
        end = dt.datetime.now()
        if wm:
            start = dt.datetime.fromisoformat(wm) - OVERLAP
        else:
            start = end - dt.timedelta(days=BACKFILL_DAYS)
        entry["watermark_before"] = wm
        print(f"window: {start} -> {end} (watermark={wm})", flush=True)

        client = AirApiClient(_air_api_cfg())
        records = fetch_all_pages(client, codes, start, end)
        print(f"fetched {len(records)} records from door API", flush=True)

        tuples = [row_tuple(r, station_map, batch_id) for r in records]
        await pg.executemany(UPSERT, tuples)
        unmatched = sorted({t[2] for t in tuples if t[1] is None and t[2]})
        if unmatched:
            print(f"WARN unmatched devName (station_code left null): {unmatched}", flush=True)

        new_wm = wm
        for t in tuples:
            if t[4] is not None:
                candidate = str(t[4])
                if new_wm is None or candidate > str(new_wm):
                    new_wm = candidate
        await pg.execute(
            """INSERT INTO jiangsu_sync.sync_watermark
               (table_name, watermark, rows_total, last_batch, last_mode, last_status, updated_at)
               VALUES ($1,$2,$3,$4,'incremental','ok',now())
               ON CONFLICT (table_name) DO UPDATE SET
                 watermark=EXCLUDED.watermark, rows_total=EXCLUDED.rows_total,
                 last_batch=EXCLUDED.last_batch, last_mode='incremental',
                 last_status='ok', updated_at=now()""",
            TABLE, new_wm, len(tuples), batch_id,
        )
        entry.update(finished_at=dt.datetime.now(), rows_fetched=len(tuples),
                     watermark_after=new_wm, status="ok")
        await sync_table.log_batch(pg, entry)
        print(f"[{TABLE}] DONE rows={len(tuples)} watermark={new_wm}", flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        entry.update(finished_at=dt.datetime.now(), status="failed",
                     error=f"{type(exc).__name__}: {exc}")
        try:
            await sync_table.log_batch(pg, entry)
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
        print(f"[{TABLE}] FAILED: {entry['error']}", file=sys.stderr, flush=True)
        return 1
    finally:
        await pg.close()


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
