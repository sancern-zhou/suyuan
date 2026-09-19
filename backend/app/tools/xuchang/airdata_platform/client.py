"""
大气环境监测数据接口中台（AirDataPlatform）客户端

许昌项目专属。封装两类接口：
- 数据查询接口：POST /openapi/v1/custom-apis/{api_code}/query
- 报表汇总接口：POST /api/airdataplatform/calc-report/summary

平台约定：全部 POST + application/json，免鉴权，统一响应包装
{success, code, message, data}，业务异常 HTTP 500，限流 120/min。
"""
import os
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

DEFAULT_BASE_URL = "http://117.159.53.11:60787"
DEFAULT_TIMEOUT_SECONDS = 30.0

DATA_API_CODES = (
    "v_c_d_sb_145",
    "v_c_d_sb_155",
    "v_c_d_src_155",
    "v_s_d_app_145",
    "v_s_d_src_145",
    "v_t_d_app",
    "v_t_d_src",
    "v_t_h_app",
    "v_t_h_src",
)

REFERENCE_API_CODES = ("region", "station")

ALL_API_CODES = REFERENCE_API_CODES + DATA_API_CODES

API_PAGE_SIZE_LIMITS: dict[str, int] = {
    "region": 1000,
    "station": 1000,
    **{code: 100 for code in DATA_API_CODES},
}

DATA_API_FILTERABLE_FIELDS = ("code", "timepoint", "createtime", "modifytime")

DATA_VIEW_QUERY_FIELDS = (
    "id",
    "name",
    "code",
    "timepoint",
    "so2",
    "no2",
    "pm10",
    "co",
    "o3_8h",
    "o3",
    "pm2_5",
    "no",
    "nox",
    "so2_mark",
    "no2_mark",
    "pm10_mark",
    "co_mark",
    "o3_8h_mark",
    "o3_mark",
    "pm2_5_mark",
    "no_mark",
    "nox_mark",
    "so2_iaqi",
    "no2_iaqi",
    "pm10_iaqi",
    "co_iaqi",
    "o3_8h_iaqi",
    "o3_iaqi",
    "pm2_5_iaqi",
    "aqi",
    "qualitytype",
    "primarypollutant",
)

REFERENCE_API_FILTERABLE_FIELDS: dict[str, tuple] = {
    "region": ("areacode",),
    "station": ("areacode", "stationcode"),
}

VALID_OPERATORS = ("eq", "like", "in", "between", "gte", "lte")

VALID_AREA_TYPES = (0, 1, 2, 3)

VALID_REPORT_TIME_TYPES = (4, 5, 6, 7, 8)

VALID_NS_TYPES = (1, 2)

DEFAULT_BASE_DATA = {
    "baseDataSource": "DataCrawler",
    "stationTableName": "bsd_station",
    "regionTableName": "bsd_region",
}

DEFAULT_INPUT_DB_SOURCE = "DataCrawler"


class AirDataPlatformError(RuntimeError):
    """中台接口调用失败"""


def get_page_size_limit(api_code: str) -> int:
    if api_code not in API_PAGE_SIZE_LIMITS:
        raise AirDataPlatformError(f"接口编码错误: {api_code}")
    return API_PAGE_SIZE_LIMITS[api_code]


def get_filterable_fields(api_code: str) -> tuple:
    if api_code in REFERENCE_API_FILTERABLE_FIELDS:
        return REFERENCE_API_FILTERABLE_FIELDS[api_code]
    if api_code in DATA_API_CODES:
        return DATA_API_FILTERABLE_FIELDS
    raise AirDataPlatformError(f"接口编码错误: {api_code}")


def normalize_filters(filters: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """校验并规范化过滤条件为平台要求的 {field, operator, value, secondValue}"""
    normalized: list[dict[str, Any]] = []
    for item in filters or []:
        if not isinstance(item, dict):
            raise AirDataPlatformError(f"过滤条件必须是对象: {item!r}")
        field = str(item.get("field", "")).strip()
        if not field:
            raise AirDataPlatformError("过滤条件缺少 field")
        operator = str(item.get("operator") or "eq").strip().lower()
        if operator not in VALID_OPERATORS:
            raise AirDataPlatformError(f"不支持的过滤谓词: {operator}")
        value = item.get("value")
        if value is None or value == "":
            raise AirDataPlatformError(f"过滤条件 {field} 缺少 value")
        condition: dict[str, Any] = {"field": field, "operator": operator, "value": value}
        if operator == "between":
            second_value = item.get("second_value", item.get("secondValue"))
            if second_value is None or second_value == "":
                raise AirDataPlatformError(f"between 条件 {field} 缺少 second_value")
            condition["secondValue"] = second_value
        normalized.append(condition)
    return normalized


def normalize_sort_config(sort_config: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in sort_config or []:
        if not isinstance(item, dict):
            raise AirDataPlatformError(f"排序配置必须是对象: {item!r}")
        field = str(item.get("field", "")).strip()
        if not field:
            raise AirDataPlatformError("排序配置缺少 field")
        order = str(item.get("order") or "asc").strip().lower()
        if order not in ("asc", "desc"):
            raise AirDataPlatformError(f"排序方向必须是 asc/desc: {order}")
        normalized.append({"field": field, "order": order})
    return normalized


class AirDataPlatformClient:
    """中台 HTTP 客户端（同步 httpx）"""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
    ):
        configured_url = base_url or os.getenv("AIRDATA_PLATFORM_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = configured_url.rstrip("/")
        configured_timeout = timeout or os.getenv("AIRDATA_PLATFORM_TIMEOUT")
        self.timeout = float(configured_timeout) if configured_timeout else DEFAULT_TIMEOUT_SECONDS

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        start = time.monotonic()
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            logger.error("airdata_platform_request_failed", url=url, error=str(exc))
            raise AirDataPlatformError(f"中台请求失败: {exc}") from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)
        try:
            body = response.json()
        except ValueError as exc:
            raise AirDataPlatformError(f"中台返回非 JSON 响应（HTTP {response.status_code}）") from exc

        if not isinstance(body, dict) or "success" not in body:
            raise AirDataPlatformError(f"中台响应格式异常（HTTP {response.status_code}）")
        if not body.get("success"):
            message = body.get("message") or "未知错误"
            logger.error(
                "airdata_platform_business_error",
                url=url,
                code=body.get("code"),
                message=message,
            )
            raise AirDataPlatformError(f"中台返回错误: {message}")

        logger.info(
            "airdata_platform_request_success",
            url=url,
            elapsed_ms=elapsed_ms,
        )
        return body.get("data")

    @staticmethod
    def _build_query_payload(
        api_code: str,
        filters: list[dict[str, Any]] | None,
        selected_fields: list[str] | None,
        sort_config: list[dict[str, Any]] | None,
        page: int,
        size: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"page": max(int(page), 1), "size": int(size)}
        normalized_filters = normalize_filters(filters)
        if normalized_filters:
            payload["filters"] = normalized_filters
        if selected_fields:
            payload["selectedFields"] = [str(field) for field in selected_fields]
        elif api_code in DATA_API_CODES:
            # 中台乡镇视图未配置默认输出字段，空字段列表会生成非法 SQL，这里显式带上全量字段
            payload["selectedFields"] = list(DATA_VIEW_QUERY_FIELDS)
        normalized_sort = normalize_sort_config(sort_config)
        if normalized_sort:
            payload["sortConfig"] = normalized_sort
        return payload

    def query_page(
        self,
        api_code: str,
        filters: list[dict[str, Any]] | None = None,
        selected_fields: list[str] | None = None,
        sort_config: list[dict[str, Any]] | None = None,
        page: int = 1,
        size: int | None = None,
    ) -> dict[str, Any]:
        """查询单页数据，返回 {columns, rows, total, page, size}"""
        size_limit = get_page_size_limit(api_code)
        effective_size = int(size) if size else size_limit
        if effective_size < 1:
            effective_size = 1
        effective_size = min(effective_size, size_limit)
        payload = self._build_query_payload(
            api_code, filters, selected_fields, sort_config, page, effective_size
        )
        data = self._post(f"/openapi/v1/custom-apis/{api_code}/query", payload)
        if not isinstance(data, dict):
            raise AirDataPlatformError("中台查询接口响应 data 结构异常")
        return {
            "columns": data.get("columns", []),
            "rows": data.get("rows", []),
            "total": int(data.get("total") or 0),
            "page": int(data.get("page") or page),
            "size": int(data.get("size") or effective_size),
            "execution_time_ms": data.get("executionTimeMs"),
        }

    def query_all(
        self,
        api_code: str,
        filters: list[dict[str, Any]] | None = None,
        selected_fields: list[str] | None = None,
        sort_config: list[dict[str, Any]] | None = None,
        max_rows: int = 2000,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """自动翻页聚合查询，最多取 max_rows 行"""
        size_limit = get_page_size_limit(api_code)
        effective_page_size = min(int(page_size) if page_size else size_limit, size_limit)
        max_rows = max(int(max_rows), 1)

        rows: list[dict[str, Any]] = []
        columns: list[dict[str, Any]] = []
        total = 0
        page = 1
        pages_fetched = 0
        truncated = False

        while len(rows) < max_rows:
            result = self.query_page(
                api_code,
                filters=filters,
                selected_fields=selected_fields,
                sort_config=sort_config,
                page=page,
                size=effective_page_size,
            )
            columns = result["columns"] or columns
            total = result["total"]
            batch = result["rows"]
            if not batch:
                break
            remaining = max_rows - len(rows)
            rows.extend(batch[:remaining])
            pages_fetched += 1
            if len(batch) < effective_page_size or len(rows) >= total:
                break
            if len(rows) >= max_rows:
                truncated = len(rows) < total
                break
            page += 1

        truncated = truncated or (0 < total > len(rows))
        return {
            "columns": columns,
            "rows": rows,
            "total": total,
            "pages_fetched": pages_fetched,
            "truncated": truncated,
        }

    def calc_report_summary(
        self,
        start_time: str,
        end_time: str,
        input_table_name: str,
        year: int,
        area_type: int,
        report_time_type: int,
        ns_type: int = 2,
        region_area: dict[str, Any] | None = None,
        region_area_name: dict[str, Any] | None = None,
        need_keys: list[str] | None = None,
        input_db_source: str = DEFAULT_INPUT_DB_SOURCE,
        base_data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """调用报表汇总接口，返回统计行列表（键名为 PascalCase）"""
        if area_type not in VALID_AREA_TYPES:
            raise AirDataPlatformError(f"area_type 必须是 {VALID_AREA_TYPES}: {area_type}")
        if report_time_type not in VALID_REPORT_TIME_TYPES:
            raise AirDataPlatformError(
                f"report_time_type 必须是 {VALID_REPORT_TIME_TYPES}: {report_time_type}"
            )
        if ns_type not in VALID_NS_TYPES:
            raise AirDataPlatformError(f"ns_type 必须是 {VALID_NS_TYPES}: {ns_type}")

        table_name = input_table_name.strip()
        if "." not in table_name:
            table_name = f"{input_db_source}.{table_name}"

        effective_base_data = dict(DEFAULT_BASE_DATA)
        if base_data:
            effective_base_data.update(base_data)

        payload = {
            "timeRanges": [
                {
                    "inputDataDBSource": input_db_source,
                    "inputTableName": table_name,
                    "startTime": start_time,
                    "endTime": end_time,
                }
            ],
            "baseData": effective_base_data,
            "year": int(year),
            "areaType": int(area_type),
            "reportTimeType": int(report_time_type),
            "nsType": int(ns_type),
            "regionArea": region_area or {},
            "regionAreaName": region_area_name or {},
            "needKeys": list(need_keys) if need_keys else [],
        }
        data = self._post("/api/airdataplatform/calc-report/summary", payload)
        if data is None:
            return []
        if not isinstance(data, list):
            raise AirDataPlatformError("中台报表汇总接口响应 data 结构异常")
        return data


_client_instance: AirDataPlatformClient | None = None


def get_airdata_platform_client() -> AirDataPlatformClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = AirDataPlatformClient()
    return _client_instance
