"""异步江西省噪声平台 API 客户端。"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import structlog

logger = structlog.get_logger()

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

JIANGXI_CITY_CODES = {
    "南昌市": "360100",
    "景德镇市": "360200",
    "萍乡市": "360300",
    "九江市": "360400",
    "新余市": "360500",
    "鹰潭市": "360600",
    "赣州市": "360700",
    "吉安市": "360800",
    "宜春市": "360900",
    "抚州市": "361000",
    "上饶市": "361100",
}
JIANGXI_CITY_CODE_SET = frozenset(JIANGXI_CITY_CODES.values())


class JiangxiNoiseClientError(RuntimeError):
    """可安全返回给上层的江西噪声平台错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_to_shanghai(value: datetime) -> datetime:
    """将时间统一为 Asia/Shanghai；无时区时间按上海时间解释。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ)


def format_platform_time(value: datetime) -> str:
    """转换为平台要求的本地时间字符串。"""
    return normalize_to_shanghai(value).strftime("%Y-%m-%d %H:%M:%S")


def resolve_city_codes(city_names: Iterable[str]) -> list[str]:
    """严格解析江西城市名称或代码，并保持去重后的输入顺序。"""
    codes: list[str] = []
    seen: set[str] = set()
    for raw_value in city_names:
        value = raw_value.strip()
        code = JIANGXI_CITY_CODES.get(value, value)
        if code not in JIANGXI_CITY_CODE_SET:
            raise JiangxiNoiseClientError(
                "invalid_city",
                f"不支持的江西省城市：{raw_value}",
            )
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


class JiangxiNoiseDataClient:
    """江西省噪声平台异步查询客户端。"""

    API_ENDPOINTS = {
        "station_hour": (
            "/api/noiseproduct/airdata/DATStationHour/GetDATStationHourDisplayPagedListAsync"
        ),
        "station_day": (
            "/api/noiseproduct/airdata/DATStationDay/GetDATStationDayDisplayPagedListAsync"
        ),
        "city_hour": ("/api/noiseproduct/airdata/DATCityHour/GetFunCityHourDisplayListAsync"),
    }

    def __init__(
        self,
        *,
        base_url: str,
        secret_name: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        base_url = base_url.strip().rstrip("/")
        secret_name = secret_name.strip()
        if not base_url:
            raise JiangxiNoiseClientError(
                "configuration_error",
                "缺少环境变量 JIANGXI_NOISE_BASE_URL",
            )
        if not secret_name:
            raise JiangxiNoiseClientError(
                "configuration_error",
                "缺少环境变量 JIANGXI_NOISE_SECRET_NAME",
            )
        if timeout <= 0:
            raise JiangxiNoiseClientError(
                "configuration_error",
                "JIANGXI_NOISE_TIMEOUT_SECONDS 必须大于 0",
            )

        self.base_url = base_url
        self.secret_name = secret_name
        self.timeout = timeout
        self._transport = transport
        self._token: str | None = None

    @classmethod
    def from_env(cls) -> JiangxiNoiseDataClient:
        """从江西项目的运行时环境创建客户端。"""
        base_url = os.getenv("JIANGXI_NOISE_BASE_URL", "")
        secret_name = os.getenv("JIANGXI_NOISE_SECRET_NAME", "")
        timeout_value = os.getenv("JIANGXI_NOISE_TIMEOUT_SECONDS", "30")
        try:
            timeout = float(timeout_value)
        except ValueError as exc:
            raise JiangxiNoiseClientError(
                "configuration_error",
                "JIANGXI_NOISE_TIMEOUT_SECONDS 必须是数字",
            ) from exc
        return cls(
            base_url=base_url,
            secret_name=secret_name,
            timeout=timeout,
        )

    def _create_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self._transport,
        )

    @staticmethod
    def _decode_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise JiangxiNoiseClientError(
                "invalid_response",
                "江西噪声平台返回了无法解析的数据",
            ) from exc
        if not isinstance(payload, dict):
            raise JiangxiNoiseClientError(
                "invalid_response",
                "江西噪声平台返回格式不正确",
            )
        return payload

    async def _authenticate(self, client: httpx.AsyncClient) -> None:
        try:
            response = await client.get(
                "/api/auth/token/get",
                params={"secretName": self.secret_name},
            )
        except httpx.TimeoutException as exc:
            raise JiangxiNoiseClientError(
                "authentication_timeout",
                "江西噪声平台认证超时",
            ) from exc
        except httpx.RequestError as exc:
            raise JiangxiNoiseClientError(
                "authentication_unavailable",
                "无法连接江西噪声平台认证服务",
            ) from exc

        if response.status_code >= 400:
            raise JiangxiNoiseClientError(
                "authentication_failed",
                f"江西噪声平台认证失败（HTTP {response.status_code}）",
            )

        payload = self._decode_json(response)
        token = payload.get("result") if payload.get("success") else None
        if not isinstance(token, str) or not token.strip():
            raise JiangxiNoiseClientError(
                "authentication_failed",
                "江西噪声平台认证失败",
            )
        self._token = token.strip()
        logger.info("jiangxi_noise_authenticated")

    async def _request_result(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> Any:
        async with self._create_http_client() as client:
            for attempt in range(2):
                if not self._token:
                    await self._authenticate(client)

                try:
                    response = await client.get(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {self._token}",
                            "Content-Type": "application/json",
                            "syscode": "NOISE",
                        },
                        params=params,
                    )
                except httpx.TimeoutException as exc:
                    raise JiangxiNoiseClientError(
                        "query_timeout",
                        "江西噪声平台查询超时",
                    ) from exc
                except httpx.RequestError as exc:
                    raise JiangxiNoiseClientError(
                        "query_unavailable",
                        "无法连接江西噪声平台",
                    ) from exc

                if response.status_code == 401 and attempt == 0:
                    self._token = None
                    logger.info("jiangxi_noise_token_refresh")
                    continue
                if response.status_code >= 400:
                    code = (
                        "authentication_failed"
                        if response.status_code == 401
                        else "query_http_error"
                    )
                    raise JiangxiNoiseClientError(
                        code,
                        f"江西噪声平台查询失败（HTTP {response.status_code}）",
                    )

                payload = self._decode_json(response)
                if not payload.get("success"):
                    raise JiangxiNoiseClientError(
                        "platform_error",
                        "江西噪声平台返回业务错误",
                    )
                return payload.get("result")

        raise JiangxiNoiseClientError(
            "authentication_failed",
            "江西噪声平台认证失败",
        )

    @staticmethod
    def _paged_result(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise JiangxiNoiseClientError(
                "invalid_response",
                "江西噪声平台分页结果格式不正确",
            )
        items = result.get("items", [])
        if not isinstance(items, list):
            raise JiangxiNoiseClientError(
                "invalid_response",
                "江西噪声平台数据列表格式不正确",
            )
        total_count = result.get("totalCount", len(items))
        if not isinstance(total_count, int):
            total_count = len(items)
        return {
            "success": True,
            "data": items,
            "total_count": total_count,
        }

    @staticmethod
    def _base_params(
        *,
        start_time: datetime,
        end_time: datetime,
        data_type: int,
        max_result_count: int,
    ) -> dict[str, Any]:
        return {
            "skipCount": 0,
            "maxResultCount": max_result_count,
            "dataType": data_type,
            "timePoint[0]": format_platform_time(start_time),
            "timePoint[1]": format_platform_time(end_time),
        }

    async def query_station_hour_data(
        self,
        *,
        station_codes: list[str],
        start_time: datetime,
        end_time: datetime,
        data_type: int = 0,
        max_result_count: int = 50,
    ) -> dict[str, Any]:
        params = self._base_params(
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            max_result_count=max_result_count,
        )
        for index, code in enumerate(station_codes):
            params[f"codes[{index}]"] = code
        result = await self._request_result(self.API_ENDPOINTS["station_hour"], params)
        return self._paged_result(result)

    async def query_station_day_data(
        self,
        *,
        station_codes: list[str],
        start_time: datetime,
        end_time: datetime,
        data_type: int = 0,
        max_result_count: int = 50,
    ) -> dict[str, Any]:
        params = self._base_params(
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            max_result_count=max_result_count,
        )
        for index, code in enumerate(station_codes):
            params[f"codes[{index}]"] = code
        result = await self._request_result(self.API_ENDPOINTS["station_day"], params)
        return self._paged_result(result)

    async def query_city_hour_data(
        self,
        *,
        city_names: list[str],
        start_time: datetime,
        end_time: datetime,
        data_type: int = 0,
        max_result_count: int = 50,
    ) -> dict[str, Any]:
        city_codes = resolve_city_codes(city_names)
        params = self._base_params(
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            max_result_count=max_result_count,
        )
        for index, code in enumerate(city_codes):
            params[f"CityCodes[{index}]"] = code
        result = await self._request_result(self.API_ENDPOINTS["city_hour"], params)
        return self._paged_result(result)

    @classmethod
    def get_api_endpoints(cls) -> dict[str, str]:
        return cls.API_ENDPOINTS.copy()


NoiseClient = JiangxiNoiseDataClient
