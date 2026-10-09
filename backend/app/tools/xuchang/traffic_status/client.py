"""百度地图实时路况查询（Traffic API）HTTP 客户端。

- 周边实时路况查询：``GET /traffic/v1/around``（center + radius，radius 上限 1000 米）
- 道路实时路况查询：``GET /traffic/v1/road``（road_name + city）

鉴权采用服务端 AK + SN 校验（BAIDU_MAP_AK / BAIDU_MAP_SK），
返回坐标统一 gcj02。车速、拥堵距离、趋势等明细仅在存在拥堵路段时返回。
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx
import structlog

from .signing import build_signed_url

logger = structlog.get_logger()

BAIDU_TRAFFIC_BASE_URL = "https://api.map.baidu.com"
TRAFFIC_AROUND_PATH = "/traffic/v1/around"
TRAFFIC_ROAD_PATH = "/traffic/v1/road"

# 常见错误码的处理提示（完整列表见百度地图开放平台错误码说明）
_STATUS_HINTS: dict[int, str] = {
    1: "服务不可用",
    2: "参数无效",
    101: "AK 不存在，检查 BAIDU_MAP_AK",
    102: "AK 未开通实时路况查询权限，需在百度控制台为 AK 勾选",
    210: "AK 类型或校验方式不匹配",
    211: "SN 校验失败，检查 BAIDU_MAP_SK",
}


class BaiduTrafficError(RuntimeError):
    """百度路况接口调用失败（含业务错误码与网络异常）。"""

    def __init__(self, status: int | str, message: str) -> None:
        self.status = status
        super().__init__(message)


class BaiduTrafficClient:
    """封装 SN 签名与两个路况查询接口。"""

    def __init__(
        self,
        ak: str | None = None,
        sk: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.ak = ak or os.getenv("BAIDU_MAP_AK")
        self.sk = sk or os.getenv("BAIDU_MAP_SK")
        self.timeout = timeout

    async def query_around(
        self,
        latitude: float,
        longitude: float,
        radius: int = 1000,
        coord_type: str = "wgs84",
        road_grade: int = 0,
    ) -> dict[str, Any]:
        """查询中心点周边圆形区域路况。"""
        self._require_credentials()
        params: dict[str, object] = {
            # 百度 center 为“纬度,经度”顺序，且小数点后不超过 6 位
            "center": f"{round(float(latitude), 6)},{round(float(longitude), 6)}",
            "coord_type_input": coord_type,
            "coord_type_output": "gcj02",
            "radius": str(max(1, min(int(radius), 1000))),
            "road_grade": str(int(road_grade)),
        }
        return await self._request(TRAFFIC_AROUND_PATH, params)

    async def query_road(self, road_name: str, city: str = "许昌市") -> dict[str, Any]:
        """按道路名称查询指定城市道路的双向路况。"""
        self._require_credentials()
        params: dict[str, object] = {
            "city": city,
            "road_name": road_name,
        }
        return await self._request(TRAFFIC_ROAD_PATH, params)

    def _require_credentials(self) -> None:
        if not self.ak or not self.sk:
            raise BaiduTrafficError(
                "missing_credentials",
                "缺少百度地图凭证，请配置 BAIDU_MAP_AK 与 BAIDU_MAP_SK 环境变量",
            )

    async def _request(self, path: str, params: Mapping[str, object]) -> dict[str, Any]:
        url = build_signed_url(BAIDU_TRAFFIC_BASE_URL, path, params, self.ak, self.sk)
        try:
            payload = await self._fetch(url)
        except BaiduTrafficError:
            raise
        except Exception as exc:
            logger.warning("baidu_traffic_request_failed", path=path, error=str(exc))
            raise BaiduTrafficError("network_error", f"请求百度路况接口失败: {exc}") from exc

        status = payload.get("status")
        if status != 0:
            message = str(payload.get("message") or "未知错误")
            hint = _STATUS_HINTS.get(status) if isinstance(status, int) else None
            detail = f"{message}（status={status}{'；' + hint if hint else ''}）"
            logger.info("baidu_traffic_api_error", path=path, status=status, message=message)
            raise BaiduTrafficError(status, detail)
        return payload

    async def _fetch(self, url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(url)
        response.raise_for_status()
        return response.json()
