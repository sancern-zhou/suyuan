"""Fetch Xuchang station/city observations from the 中大 platform.

中大空气质量联网监测管理平台 (http://125.45.235.130:81) requires an
authenticated session: the login page serves an RSA public key, the username /
password / captcha are RSA-encrypted (JSEncrypt, UTF-8 + PKCS#1 v1.5) and the
captcha image is solved with ddddocr. Station minute/hour grids also need a
short-lived page token from ``/PageTK/GetPageToken``; day and city endpoints
do not use it.

Supported data kinds and production口径 (per接口接入说明):
- minute      站点5分钟  /FiveMinQuery/GetFiveMinDataForGrid   Act+gp, PageTK
- hour        站点小时   /HourQuery/GetHourDataForGrid         App+Act+gp, PageTK
- day         站点日均   /DayQuery/GetDayDataForGrid           App+Act+gp, standard=AQI
- city_hour   城市小时   /CityHour/GetCityHourData             isApp=true+Act
- city_day    城市日均   /CityDayQuery/GetCityDayQuery         SubstitutionBack+Act

City endpoints may legitimately return ``Data=[]`` until the platform's city
aggregation job produces rows; empty results are logged, not treated as errors.

The result is upserted into the XcAi SQL Server database, reusing the same
connection used by the other Xuchang station fetchers.
"""

from __future__ import annotations

import re
import base64
import time
from datetime import datetime, timedelta
from typing import Any

import pyodbc
import requests
import structlog
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from config.settings import settings
from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xcai_station_sql import xcai_connection_string

logger = structlog.get_logger()

MISSING = -99

# ---- response field maps -------------------------------------------------

# 站点分钟/小时：污染物字段带 Value 后缀，标记字段带 Mark 后缀。
STATION_GRID_MAP = {
    "Aqi": "aqi", "Api": "api",
    "So2Value": "so2", "NoValue": "no_val", "No2Value": "no2", "NoxValue": "nox",
    "O3Value": "o3", "CoValue": "co", "Pm10Value": "pm10", "Pm25Value": "pm25",
    "O3_8HValue": "o3_8h", "Pm1Value": "pm1",
    "So2Mark": "so2_mark", "NoMark": "no_mark", "No2Mark": "no2_mark",
    "NoxMark": "nox_mark", "O3Mark": "o3_mark", "CoMark": "co_mark",
    "Pm10Mark": "pm10_mark", "Pm25Mark": "pm25_mark",
    "O3_8hMark": "o3_8h_mark", "Pm1Mark": "pm1_mark",
}

# 站点日均：字段为大写污染物名，标记为 <污染物>Mark。
STATION_DAY_MAP = {
    "Aqi": "aqi", "Api": "api",
    "SO2": "so2", "NO": "no_val", "NO2": "no2", "NOx": "nox",
    "O3": "o3", "CO": "co", "PM10": "pm10", "PM2_5": "pm25",
    "O3_8h": "o3_8h", "PM1": "pm1",
    "SO2Mark": "so2_mark", "NOMark": "no_mark", "NO2Mark": "no2_mark",
    "NOxMark": "nox_mark", "O3Mark": "o3_mark", "COMark": "co_mark",
    "PM10Mark": "pm10_mark", "PM2_5Mark": "pm25_mark",
    "O3_8hMark": "o3_8h_mark", "PM1Mark": "pm1_mark",
    "PrimaryPollutant": "pollutant", "Type": "quality_type", "Level": "quality_level",
}

# 城市小时：含第二组评价字段。
CITY_HOUR_MAP = {
    "AQI": "aqi", "Quality": "quality", "PrimaryPollutant": "pollutant",
    "SO2": "so2", "NO": "no_val", "NO2": "no2", "NOx": "nox",
    "O3": "o3", "CO": "co", "PM10": "pm10", "PM2_5": "pm25", "PM1": "pm1",
    "PM10_2": "pm10_2", "PM2_5_2": "pm25_2",
    "AQI_2": "aqi_2", "Quality_2": "quality_2", "PrimaryPollutant_2": "pollutant_2",
}

# 城市日均：标记字段为 <污染物>_Mark。
CITY_DAY_MAP = {
    "AQI": "aqi", "PrimaryPollutant": "pollutant",
    "Type": "quality_type", "Level": "quality_level", "Description": "description",
    "SO2": "so2", "NO": "no_val", "NO2": "no2", "NOx": "nox",
    "O3": "o3", "O3_1h": "o3_1h", "O3_8h": "o3_8h", "CO": "co",
    "PM10": "pm10", "PM2_5": "pm25", "PM1": "pm1",
    "SO2_Mark": "so2_mark", "NO_Mark": "no_mark", "NO2_Mark": "no2_mark",
    "NOx_Mark": "nox_mark", "O3_Mark": "o3_mark", "O3_1h_Mark": "o3_1h_mark",
    "O3_8h_Mark": "o3_8h_mark", "CO_Mark": "co_mark",
    "PM10_Mark": "pm10_mark", "PM2_5_Mark": "pm25_mark", "PM1_Mark": "pm1_mark",
}

MARK_COLUMNS = {
    name for name in (
        list(STATION_GRID_MAP.values())
        + list(STATION_DAY_MAP.values())
        + list(CITY_DAY_MAP.values())
    ) if name.endswith("_mark")
}

# 站点日均接口的气态/颗粒物字段以 mg/m3 返回（页面展示时乘 1000）。
# 已实测核对：day pm25=0.015 对应同日小时均值 15.375 μg/m3；CO 与 AQI 不缩放。
# 落库统一换算为 μg/m3，与分钟/小时表一致；None/-99 跳过。
DAY_UNIT_SCALE_FIELDS = ("so2", "no_val", "no2", "nox", "o3", "o3_8h", "pm10", "pm25", "pm1")

STATION_TABLE = "dbo.dat_zhongda_station_minute"
STATION_HOUR_TABLE = "dbo.dat_zhongda_station_hour"
STATION_DAY_TABLE = "dbo.dat_zhongda_station_day"
CITY_HOUR_TABLE = "dbo.dat_zhongda_city_hour"
CITY_DAY_TABLE = "dbo.dat_zhongda_city_day"


def _number(value: Any) -> float | None:
    if value in (None, "", "NA", "—", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    # 城市接口返回 ASP.NET JSON 日期：/Date(1768320000000)/（UTC 毫秒）
    asp_date = re.fullmatch(r"/Date\((-?\d+)\)/", text)
    if asp_date:
        return datetime.fromtimestamp(int(asp_date.group(1)) / 1000)
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _fmt_window(dt: datetime) -> str:
    # 平台时间格式：yyyy/M/d H:mm（月/日不补零）
    return f"{dt.year}/{dt.month}/{dt.day} {dt.hour}:{dt.minute:02d}"


def _fmt_date(dt: datetime) -> str:
    # 日均接口日期格式：yyyy/MM/dd（补零）
    return f"{dt.year}/{dt.month:02d}/{dt.day:02d}"


def _apply_map(row: dict[str, Any], field_map: dict[str, str]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for resp_field, col in field_map.items():
        if col.endswith("_mark"):
            record[col] = (str(row.get(resp_field) or "").strip() or None)
        elif col in ("pollutant", "quality", "quality_type", "quality_level", "description"):
            value = row.get(resp_field)
            record[col] = (str(value).strip() or None) if value is not None else None
        else:
            record[col] = _number(row.get(resp_field))
    return record


# 平台在连续登录失败3次后锁定约10分钟；命中该消息时必须立刻停止重试。
_LOCKOUT_PATTERN = re.compile(r"连续登录失败|10分钟")
# 平台验证码实测为4位字母数字；OCR 读出中文或异常长度时基本必然错误，
# 直接换图重读，不提交登录（避免消耗平台的连续失败计数）。
_CAPTCHA_SHAPE = re.compile(r"[0-9A-Za-z]{4}")
LOCKOUT_SECONDS = 630  # 10.5 分钟，留少量余量

# 城市接口的 DataTypePlan 按规划期互斥：查询窗口落在哪个规划期就必须用哪个
# 参数，用错返回空数组（实测 145th 查 2026 年为空，155th 查 2025-12 也为空）。
_PLAN_PERIODS = [
    (datetime(2021, 1, 1), "145th"),  # 十四五
    (datetime(2026, 1, 1), "155th"),  # 十五五
]


def plan_for_date(value: datetime) -> str:
    plan = "135th"  # 十三五及更早
    for start, name in _PLAN_PERIODS:
        if value >= start:
            plan = name
    return plan


def split_window_by_plan(start: datetime, end: datetime) -> list[tuple[str, datetime, datetime]]:
    """把查询窗口按规划期边界切分，返回 [(plan, seg_start, seg_end), ...]。"""
    segments: list[tuple[str, datetime, datetime]] = []
    cur = start
    while cur < end:
        next_boundary = end
        for boundary, _ in _PLAN_PERIODS:
            if cur < boundary < next_boundary:
                next_boundary = boundary
        segments.append((plan_for_date(cur), cur, next_boundary))
        cur = next_boundary
    return segments


class ZhongdaSession:
    """Authenticate against the 中大 platform and issue authenticated requests."""

    def __init__(self, base_url: str, username: str, password: str, timeout: float, retries: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.retries = retries
        self._session: requests.Session | None = None
        self._ocr = None
        self._locked_until = 0.0

    def _get_ocr(self):
        if self._ocr is None:
            import ddddocr

            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr

    def _extract_public_key(self, html: str) -> str:
        m = re.search(
            r'data-val="(-----BEGIN PUBLIC KEY-----[\s\S]*?-----END PUBLIC KEY-----)"',
            html,
        )
        if not m:
            raise ValueError("中大平台登录页未找到 RSA 公钥")
        return m.group(1)

    def _rsa_encrypt(self, value: str, pem: str) -> str:
        key = RSA.import_key(pem)
        cipher = PKCS1_v1_5.new(key)
        return base64.b64encode(cipher.encrypt(value.encode("utf-8"))).decode()

    def _read_captcha(self, session: requests.Session) -> str:
        """读取并识别验证码；形态明显异常时换图重读（最多3次），不提交明显误读。"""
        code = ""
        for _ in range(4):
            vc_resp = session.get(
                f"{self.base_url}/Img/GetImgVerifyChars", timeout=self.timeout
            )
            vc_resp.raise_for_status()
            code = (self._get_ocr().classification(vc_resp.content) or "").strip()
            if _CAPTCHA_SHAPE.fullmatch(code):
                return code
            logger.warning("zhongda_captcha_shape_retry", read=code)
        return code

    def login(self) -> requests.Session:
        """Login (solving captcha, retrying on failure) and return an authed session."""
        wait = self._locked_until - time.time()
        if wait > 0:
            raise RuntimeError(f"中大平台登录锁定中，约 {int(wait)}s 后解除，本次跳过")
        last_err = None
        for attempt in range(1, self.retries + 1):
            session = requests.Session()
            session.headers.update({"User-Agent": "suyuan-xuchang-zhongda-fetcher/1.0"})
            try:
                page = session.get(
                    f"{self.base_url}/Account/Login?ReturnUrl=/", timeout=self.timeout
                )
                page.raise_for_status()
                pem = self._extract_public_key(page.text)

                code = self._read_captcha(session)

                payload = {
                    "b": self._rsa_encrypt(self.username, pem),
                    "a": self._rsa_encrypt(self.password, pem),
                    "VcCode": self._rsa_encrypt(code, pem),
                }
                result = session.post(
                    f"{self.base_url}/Account/Login", data=payload, timeout=self.timeout
                ).json()
                if result.get("isSucceed"):
                    logger.info("zhongda_login_ok", attempt=attempt, username=self.username)
                    self._session = session
                    return session
                msg = str(result.get("msg") or "")
                last_err = f"登录失败 msg={msg} code={code}"
                if _LOCKOUT_PATTERN.search(msg):
                    # 平台已锁定：停止重试，避免锤击延长锁定窗口。
                    self._locked_until = time.time() + LOCKOUT_SECONDS
                    logger.warning(
                        "zhongda_login_locked_out",
                        unlock_in_seconds=LOCKOUT_SECONDS,
                        msg=msg,
                    )
                    break
            except Exception as exc:  # noqa: BLE001 - 验证码识别失败需重试
                last_err = f"{type(exc).__name__}: {exc}"
            logger.warning("zhongda_login_retry", attempt=attempt, reason=last_err)
            time.sleep(1)
        raise RuntimeError(f"中大平台登录失败（已重试 {self.retries} 次）: {last_err}")

    def get_session(self) -> requests.Session:
        if self._session is None:
            self.login()
        return self._session

    def get_token(self, controller: str, action: str) -> dict:
        sess = self.get_session()
        resp = sess.post(
            f"{self.base_url}/PageTK/GetPageToken",
            data={"controller": controller, "action": action},
            timeout=self.timeout,
        )
        if resp.status_code == 302 or "Login" in resp.url:
            # 会话失效，重新登录后再取令牌
            self.login()
            resp = self.get_session().post(
                f"{self.base_url}/PageTK/GetPageToken",
                data={"controller": controller, "action": action},
                timeout=self.timeout,
            )
        return resp.json()

    def _post_grid(self, endpoint: str, body: dict) -> requests.Response:
        return self.get_session().post(
            f"{self.base_url}/{endpoint}", data=body, timeout=self.timeout
        )

    def fetch_grid(
        self,
        endpoint: str,
        params: dict,
        controller: str | None = None,
        action: str | None = None,
        page_size: int = 500,
    ) -> list[dict[str, Any]]:
        """Page through a Kendo-grid style data endpoint and return all rows.

        Station minute/hour grids require a PageTK token (controller/action);
        day and city endpoints pass ``controller=None`` and skip the token.
        """
        token: dict | None = None
        if controller and action:
            token = self.get_token(controller, action)
        rows: list[dict[str, Any]] = []
        page = 1
        retried_login = False
        while True:
            body = {
                **params,
                "page": page,
                "pageSize": page_size,
                "sort": "",
                "group": "",
                "filter": "",
            }
            if token is not None:
                body["tk"] = token["key"]
                body["val"] = token["value"]
            resp = self._post_grid(endpoint, body)
            if (resp.status_code == 302 or "Login" in resp.url) and not retried_login:
                # 会话过期：重新登录并刷新令牌后重试当前页
                retried_login = True
                self.login()
                if controller and action:
                    token = self.get_token(controller, action)
                continue
            payload = resp.json()
            batch = payload.get("Data") or []
            rows.extend(batch)
            total = payload.get("Total") or 0
            if not batch or len(rows) >= total:
                break
            page += 1
            if page > 1000:
                logger.warning("zhongda_too_many_pages", endpoint=endpoint)
                break
        return rows


# 所有中大 fetcher 共享同一会话/登录状态：平台对连续登录失败有10分钟锁定，
# 独立登录会把失败次数放大并触发锁定。worker 进程内无真实并发，单例安全。
_SHARED_CLIENT: ZhongdaSession | None = None


def get_shared_zhongda_client() -> ZhongdaSession:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        _SHARED_CLIENT = ZhongdaSession(
            base_url=settings.zhongda_api_base_url,
            username=settings.zhongda_username,
            password=settings.zhongda_password,
            timeout=settings.zhongda_timeout_seconds,
            retries=settings.zhongda_login_retries,
        )
    return _SHARED_CLIENT


class _ZhongdaBaseFetcher(DataFetcher):
    """Shared plumbing for all 中大 platform fetchers."""

    data_kind = "minute"

    def __init__(self, *, name: str, description: str, schedule: str) -> None:
        super().__init__(name=name, description=description, schedule=schedule, version="1.2.0")
        self._zhongda_client: ZhongdaSession | None = None

    def _client(self) -> ZhongdaSession:
        if self._zhongda_client is None:
            self._zhongda_client = get_shared_zhongda_client()
        return self._zhongda_client

    # ---- SQL --------------------------------------------------------------
    @staticmethod
    def _create_table_sql(table: str, columns: list[str], unique_cols: list[str]) -> str:
        return (
            f"IF OBJECT_ID('{table}', 'U') IS NULL "
            f"CREATE TABLE {table} ({', '.join(columns)}, "
            f"UNIQUE ({', '.join(unique_cols)}));"
        )

    TABLE_SPECS: dict[str, dict[str, Any]] = {}

    def _ensure_tables(self, conn: pyodbc.Connection) -> None:
        with conn.cursor() as cur:
            for spec in self.TABLE_SPECS.values():
                cur.execute(
                    self._create_table_sql(spec["table"], spec["columns"], spec["unique"])
                )
        conn.commit()

    def _upsert(self, cursor: pyodbc.Cursor, table: str, unique_cols: list[str], record: dict[str, Any]) -> None:
        value_cols = list(record.keys())
        update_cols = [c for c in value_cols if c not in unique_cols]
        using_ph = ", ".join(f"? AS {c}" for c in unique_cols)
        on_clause = " AND ".join(f"target.{c} = source.{c}" for c in unique_cols)
        update_clause = ", ".join(f"{c}=?" for c in update_cols) or "create_time=GETDATE()"
        insert_cols = ", ".join(value_cols)
        insert_ph = ", ".join(["?"] * len(value_cols))
        merge = f"""
            MERGE {table} AS target
            USING (SELECT {using_ph}) AS source
              ON {on_clause}
            WHEN MATCHED THEN UPDATE SET {update_clause}, create_time=GETDATE()
            WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_ph});
        """
        params = (
            [record[c] for c in unique_cols]
            + [record[c] for c in update_cols]
            + [record[c] for c in value_cols]
        )
        cursor.execute(merge, params)

    def _store(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        spec = self.TABLE_SPECS[self.data_kind]
        conn = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            self._ensure_tables(conn)
            cursor = conn.cursor()
            for record in records:
                self._upsert(cursor, spec["table"], spec["unique"], record)
            conn.commit()
        finally:
            conn.close()
        return {
            "kind": self.data_kind,
            "saved": len(records),
            "window": f"{records[0].get('time_point') or records[0].get('data_date')} ~ "
                      f"{records[-1].get('time_point') or records[-1].get('data_date')}",
        }

    async def fetch_and_store(self) -> dict[str, Any]:
        if not settings.zhongda_username or not settings.zhongda_password:
            raise RuntimeError("未配置 ZHONGDA_USERNAME / ZHONGDA_PASSWORD，无法登录中大平台")
        records = self.fetch_rows()
        if not records:
            # 城市接口在平台聚合任务生成数据前合法返回空数组，不算异常。
            # 仍创建表结构，避免"表不存在"造成未接入的误解。
            conn = pyodbc.connect(xcai_connection_string(), timeout=30)
            try:
                self._ensure_tables(conn)
            finally:
                conn.close()
            logger.info("zhongda_no_data", kind=self.data_kind)
            return {"kind": self.data_kind, "saved": 0}
        result = self._store(records)
        logger.info("zhongda_fetch_completed", **result)
        return result


def _station_grid_columns() -> list[str]:
    cols = [
        "id BIGINT IDENTITY PRIMARY KEY",
        "station_code NVARCHAR(32) NOT NULL",
        "station_name NVARCHAR(128)",
        "area NVARCHAR(64)",
        "time_point DATETIME NOT NULL",
        "data_table_type NVARCHAR(8)",
        "parameter_type NVARCHAR(8)",
    ]
    cols += [f"{c} FLOAT" for c in STATION_GRID_MAP.values() if not c.endswith("_mark")]
    cols += [f"{c} NVARCHAR(16)" for c in STATION_GRID_MAP.values() if c.endswith("_mark")]
    cols.append("create_time DATETIME DEFAULT GETDATE()")
    return cols


_STATION_GRID_UNIQUE = ["station_code", "time_point", "data_table_type", "parameter_type"]


def _station_day_columns() -> list[str]:
    cols = [
        "id BIGINT IDENTITY PRIMARY KEY",
        "station_code NVARCHAR(32) NOT NULL",
        "station_name NVARCHAR(128)",
        "unique_code NVARCHAR(32)",
        "area NVARCHAR(64)",
        "data_date DATE NOT NULL",
        "standard NVARCHAR(8)",
        "data_source_type NVARCHAR(16)",
        "data_table_type NVARCHAR(8)",
        "parameter_type NVARCHAR(8)",
    ]
    for col in STATION_DAY_MAP.values():
        if col.endswith("_mark"):
            cols.append(f"{col} NVARCHAR(16)")
        elif col in ("pollutant", "quality_type", "quality_level"):
            cols.append(f"{col} NVARCHAR(64)")
        else:
            cols.append(f"{col} FLOAT")
    cols.append("create_time DATETIME DEFAULT GETDATE()")
    return cols


_STATION_DAY_UNIQUE = ["station_code", "data_date", "data_table_type", "parameter_type"]


def _city_hour_columns() -> list[str]:
    cols = [
        "id BIGINT IDENTITY PRIMARY KEY",
        "area NVARCHAR(64) NOT NULL",
        "city_code NVARCHAR(32)",
        "province NVARCHAR(64)",
        "province_code NVARCHAR(32)",
        "time_point DATETIME NOT NULL",
        "data_type_plan NVARCHAR(8)",
        "is_app NVARCHAR(8)",
        "data_table_type NVARCHAR(8)",
    ]
    for col in CITY_HOUR_MAP.values():
        if col in ("quality", "pollutant", "quality_2", "pollutant_2"):
            cols.append(f"{col} NVARCHAR(64)")
        else:
            cols.append(f"{col} FLOAT")
    cols.append("create_time DATETIME DEFAULT GETDATE()")
    return cols


_CITY_HOUR_UNIQUE = ["area", "time_point", "data_type_plan", "data_table_type"]


def _city_day_columns() -> list[str]:
    cols = [
        "id BIGINT IDENTITY PRIMARY KEY",
        "area NVARCHAR(64) NOT NULL",
        "city_code NVARCHAR(32)",
        "data_date DATE NOT NULL",
        "data_type_plan NVARCHAR(8)",
        "data_source_type NVARCHAR(32)",
        "data_table_type NVARCHAR(8)",
    ]
    for col in CITY_DAY_MAP.values():
        if col.endswith("_mark"):
            cols.append(f"{col} NVARCHAR(16)")
        elif col in ("pollutant", "quality_type", "quality_level", "description"):
            cols.append(f"{col} NVARCHAR(128)")
        else:
            cols.append(f"{col} FLOAT")
    cols.append("create_time DATETIME DEFAULT GETDATE()")
    return cols


_CITY_DAY_UNIQUE = ["area", "data_date", "data_type_plan", "data_source_type"]


class XuchangZhongdaStationFetcher(_ZhongdaBaseFetcher):
    """Persist 中大 platform station minute/hour/day observations."""

    TABLE_SPECS = {
        "minute": {
            "table": STATION_TABLE,
            "columns": _station_grid_columns(),
            "unique": _STATION_GRID_UNIQUE,
        },
        "hour": {
            "table": STATION_HOUR_TABLE,
            "columns": _station_grid_columns(),
            "unique": _STATION_GRID_UNIQUE,
        },
        "day": {
            "table": STATION_DAY_TABLE,
            "columns": _station_day_columns(),
            "unique": _STATION_DAY_UNIQUE,
        },
    }

    def __init__(self, data_kind: str = "minute") -> None:
        if data_kind not in ("minute", "hour", "day"):
            raise ValueError("data_kind must be 'minute', 'hour' or 'day'")
        meta = {
            "minute": (
                "xuchang_zhongda_station_minute_fetcher",
                "抓取中大平台许昌市站点5分钟数据",
                # 中大平台的5分钟批次通常在时间点后约1分钟才可查询；
                # 例如16:45批次在16:46抓取，避免整点触发时读不到最新批次。
                "1-59/5 * * * *",
            ),
            "hour": (
                "xuchang_zhongda_station_hour_fetcher",
                "抓取中大平台许昌市站点小时数据",
                "10 * * * *",
            ),
            "day": (
                "xuchang_zhongda_station_day_fetcher",
                "抓取中大平台许昌市站点日均数据（审核后）",
                "35 1 * * *",
            ),
        }[data_kind]
        super().__init__(name=meta[0], description=meta[1], schedule=meta[2])
        self.data_kind = data_kind

    def _endpoint(self) -> tuple[str, str | None, str | None]:
        if self.data_kind == "minute":
            return "FiveMinQuery/GetFiveMinDataForGrid", "GetFiveMinDataForGrid", "FiveMinQuery"
        if self.data_kind == "hour":
            return "HourQuery/GetHourDataForGrid", "GetHourDataForGrid", "HourQuery"
        return "DayQuery/GetDayDataForGrid", None, None

    def _window(self) -> tuple[datetime, datetime]:
        now = datetime.now().replace(second=0, microsecond=0)
        if self.data_kind == "minute":
            return now - timedelta(minutes=25), now
        if self.data_kind == "hour":
            end = now.replace(minute=0)
            # 日污染回顾在次日读取前一整天原始小时数据；每次小时任务
            # 回填 26 小时，保证跨日运行和平台延迟不会留下空白日。
            return end - timedelta(hours=26), end
        end = now.replace(hour=0, minute=0)
        start = end - timedelta(days=settings.zhongda_day_lookback_days)
        return start, end

    def _query_params(self, start: datetime, end: datetime) -> dict:
        params: dict[str, Any] = {
            "stationCode": settings.zhongda_station_codes,
            "parameterType": settings.zhongda_parameter_type,
            "dataTableType": settings.zhongda_data_table_type,
        }
        if self.data_kind in ("minute", "hour"):
            params["startTime"] = _fmt_window(start)
            params["endTime"] = _fmt_window(end)
            if self.data_kind == "hour":
                # 小时数据要求及时性，使用原始口径；审核数据可能滞后。
                params["dataSourceType"] = settings.zhongda_hour_data_source_type
                params["hasMark"] = "Yes"
        else:
            params["standard"] = "AQI"
            params["dataSourceType"] = settings.zhongda_data_source_type
            params["DataTypePlan"] = settings.zhongda_data_type_plan
            params["startTime"] = _fmt_date(start)
            params["endTime"] = _fmt_date(end)
        return params

    def fetch_rows(self) -> list[dict[str, Any]]:
        endpoint, controller, action = self._endpoint()
        start, end = self._window()
        raw = self._client().fetch_grid(
            endpoint, self._query_params(start, end), controller, action
        )
        records: list[dict[str, Any]] = []
        if self.data_kind == "day":
            for row in raw:
                station_code = str(row.get("StationCode") or "").strip()
                data_date = _parse_time(row.get("Date"))
                if not station_code or data_date is None:
                    continue
                record = {
                    "station_code": station_code,
                    "station_name": str(row.get("PositionName") or "").strip(),
                    "unique_code": str(row.get("UniqueCode") or "").strip() or None,
                    "area": str(row.get("Area") or "").strip(),
                    "data_date": data_date.date(),
                    "standard": "AQI",
                    "data_source_type": settings.zhongda_data_source_type,
                    "data_table_type": settings.zhongda_data_table_type,
                    "parameter_type": settings.zhongda_parameter_type,
                }
                record.update(_apply_map(row, STATION_DAY_MAP))
                for col in DAY_UNIT_SCALE_FIELDS:
                    value = record.get(col)
                    if value is not None and value != MISSING:
                        record[col] = value * 1000
                records.append(record)
        else:
            for row in raw:
                station_code = str(row.get("StationCode") or "").strip()
                time_point = _parse_time(row.get("TimePoint"))
                if not station_code or time_point is None:
                    continue
                record = {
                    "station_code": station_code,
                    "station_name": str(row.get("StationName") or "").strip(),
                    "area": str(row.get("Area") or "").strip(),
                    "time_point": time_point,
                    "data_table_type": settings.zhongda_data_table_type,
                    "parameter_type": settings.zhongda_parameter_type,
                }
                record.update(_apply_map(row, STATION_GRID_MAP))
                records.append(record)
        return records


class XuchangZhongdaCityFetcher(_ZhongdaBaseFetcher):
    """Persist 中大 platform city hour/day observations.

    City endpoints currently return empty arrays on the platform side; empty
    results are logged and stored as zero rows, never raised as errors.
    """

    TABLE_SPECS = {
        "city_hour": {
            "table": CITY_HOUR_TABLE,
            "columns": _city_hour_columns(),
            "unique": _CITY_HOUR_UNIQUE,
        },
        "city_day": {
            "table": CITY_DAY_TABLE,
            "columns": _city_day_columns(),
            "unique": _CITY_DAY_UNIQUE,
        },
    }

    def __init__(self, data_kind: str = "city_hour") -> None:
        if data_kind not in ("city_hour", "city_day"):
            raise ValueError("data_kind must be 'city_hour' or 'city_day'")
        meta = {
            "city_hour": (
                "xuchang_zhongda_city_hour_fetcher",
                "抓取中大平台城市小时数据（审核后）",
                "20 * * * *",
            ),
            "city_day": (
                "xuchang_zhongda_city_day_fetcher",
                "抓取中大平台城市日均数据（替代回算）",
                "50 1 * * *",
            ),
        }[data_kind]
        super().__init__(name=meta[0], description=meta[1], schedule=meta[2])
        self.data_kind = data_kind

    def _endpoint(self) -> tuple[str, str | None, str | None]:
        if self.data_kind == "city_hour":
            return "CityHour/GetCityHourData", None, None
        return "CityDayQuery/GetCityDayQuery", None, None

    def _window(self) -> tuple[datetime, datetime]:
        now = datetime.now().replace(second=0, microsecond=0)
        if self.data_kind == "city_hour":
            end = now.replace(minute=0)
            return end - timedelta(hours=3), end
        end = now.replace(hour=0, minute=0)
        start = end - timedelta(days=settings.zhongda_city_day_lookback_days)
        return start, end

    def _query_params(self, plan: str, start: datetime, end: datetime) -> dict:
        act = settings.zhongda_data_table_type
        if self.data_kind == "city_hour":
            return {
                "DataTypePlan": plan,
                "isApp": "true",
                "start": _fmt_window(start),
                "end": _fmt_window(end),
                "dataTableType": act,
            }
        return {
            "DataTypePlan": plan,
            "startTime": _fmt_date(start),
            "endTime": _fmt_date(end),
            "dataSourceType": "SubstitutionBack",
            "dataTableType": act,
            "isCoverData": 1,
        }

    def fetch_rows(self) -> list[dict[str, Any]]:
        endpoint, controller, action = self._endpoint()
        start, end = self._window()
        raw: list[dict[str, Any]] = []
        # DataTypePlan 按规划期互斥，跨 2026-01-01 等边界时必须分段查询
        for plan, seg_start, seg_end in split_window_by_plan(start, end):
            raw.extend(
                self._client().fetch_grid(
                    endpoint, self._query_params(plan, seg_start, seg_end), controller, action
                )
            )
        records: list[dict[str, Any]] = []
        if self.data_kind == "city_hour":
            for row in raw:
                area = str(row.get("Area") or "").strip()
                time_point = _parse_time(row.get("TimePoint"))
                if not area or time_point is None:
                    continue
                record = {
                    "area": area,
                    "city_code": str(row.get("CityCode") or "").strip() or None if row.get("CityCode") is not None else None,
                    "province": str(row.get("Province") or "").strip() or None,
                    "province_code": str(row.get("ProvinceCode") or "").strip() or None,
                    "time_point": time_point,
                    "data_type_plan": plan_for_date(time_point),
                    "is_app": "true",
                    "data_table_type": settings.zhongda_data_table_type,
                }
                record.update(_apply_map(row, CITY_HOUR_MAP))
                records.append(record)
        else:
            for row in raw:
                area = str(row.get("Area") or "").strip()
                data_date = _parse_time(row.get("Date"))
                if not area or data_date is None:
                    continue
                record = {
                    "area": area,
                    "city_code": str(row.get("CityCode") or "").strip() or None if row.get("CityCode") is not None else None,
                    "data_date": data_date.date(),
                    "data_type_plan": plan_for_date(data_date),
                    "data_source_type": "SubstitutionBack",
                    "data_table_type": settings.zhongda_data_table_type,
                }
                record.update(_apply_map(row, CITY_DAY_MAP))
                records.append(record)
        return records
