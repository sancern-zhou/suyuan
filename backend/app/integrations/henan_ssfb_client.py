"""Henan real-time air-quality publish platform client (ssfb).

数据来源为河南省空气质量实时发布系统（省监测中心，前端
http://222.143.24.250:8236/ssfb/#/index）。接口无鉴权，响应为
AES-128-CBC/PKCS7 加密的 Base64 文本；解密后的 JSON 中数字字段夹杂
NUL 填充字符（前端同样执行 replace(/\\u0000/g, "")）。

能力边界（2026-10 实测）：
- 城市组接口（airQualityGroupHours/Days）只认城市树 ID，覆盖河南
  17 省辖市 + 济源示范区（共 18 组），小时值约保留最近 8 天，日值
  次日发布、保留同样时长；
- 站点接口（airQualitySiteHours/Days）覆盖全省国控/省控/市控站点
  （约 500 个，含济源），树为 市 → 区县分组 → 站点 三层；
- 区县组接口没有独立数据：区县树叶子 ID 会被错误映射回城市组，
  区县口径数据需要用站点数据自行聚合。
"""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import requests
import structlog
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

logger = structlog.get_logger()

SSFB_BASE_URL = os.getenv(
    "HENAN_SSFB_BASE_URL", "http://222.143.24.250:8236/hnjczx_public"
)
SSFB_AES_KEY = "3294573829475733"
SSFB_AES_IV = "1234567890123456"

CITY_TREE_PATH = "/HNTree/GetGroupCityTree"
STATION_TREE_PATH = "/HNTree/GetGroupStationTree"
GROUP_HOURS_PATH = "/ssfbfw/airQualityGroupHours"
GROUP_DAYS_PATH = "/ssfbfw/airQualityGroupDays"
SITE_HOURS_PATH = "/ssfbfw/airQualitySiteHours"
SITE_DAYS_PATH = "/ssfbfw/airQualitySiteDays"

REQUEST_TIMEOUT_SECONDS = 60
FETCH_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5

# 前端"城市"下拉的城市树 ID（济源示范区在源数据中无独立 Code 语义）。
# 实测 groupID 体系: 21郑州 22开封 23洛阳 24平顶山 25安阳 26鹤壁 27新乡
# 28焦作 29濮阳 21许昌 211漯河 212三门峡 213南阳 214商丘 215信阳
# 216周口 217驻马店 218济源 —— ID 与树重复但接口按此表返回，采集时
# 以城市树实时解析为准，此表仅用于文档与测试对照。
CITY_NAME_ALIASES = {"济源示范区": "济源市"}


def normalize_city_name(name: str | None) -> str:
    """Map platform group names onto the province's canonical city names."""
    value = str(name or "").strip()
    return CITY_NAME_ALIASES.get(value, value)


def decrypt_payload(ciphertext: str) -> Any:
    """Decrypt an ssfb Base64 ciphertext into a parsed JSON value."""
    raw = base64.b64decode(ciphertext)
    cipher = AES.new(SSFB_AES_KEY.encode(), AES.MODE_CBC, SSFB_AES_IV.encode())
    text = unpad(cipher.decrypt(raw), AES.block_size).decode("utf-8", errors="replace")
    return json.loads(text.replace("\u0000", ""))


class HenanSsfbError(RuntimeError):
    """Raised when the publish platform returns an unusable response."""


class HenanSsfbClient:
    """Small GET-only client for the Henan real-time publish platform."""

    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str = SSFB_BASE_URL,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": "suyuan-henan-ssfb-client/1.0", "Accept": "*/*"}
        )
        self.base_url = base_url.rstrip("/")

    def _query(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        last_error: Exception | None = None
        for attempt in range(1, FETCH_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
                payload = decrypt_payload(response.text.strip())
                if not isinstance(payload, dict) or payload.get("code") != 1:
                    raise HenanSsfbError(
                        f"{path} returned unusable payload: {str(payload)[:200]}"
                    )
                return payload.get("data")
            except (requests.RequestException, ValueError, HenanSsfbError) as error:
                last_error = error
                logger.warning(
                    "henan_ssfb_request_retry",
                    path=path,
                    attempt=attempt,
                    retries=FETCH_RETRIES,
                    error=str(error),
                )
                if attempt < FETCH_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS)
        raise HenanSsfbError(f"ssfb request failed for {path}: {last_error}")

    def city_tree(self) -> list[dict[str, Any]]:
        return self._query(CITY_TREE_PATH) or []

    def station_tree(self) -> list[dict[str, Any]]:
        return self._query(STATION_TREE_PATH) or []

    def group_hours(
        self, city_ids: list[int], start: str, end: str
    ) -> list[dict[str, Any]]:
        return self._query(
            GROUP_HOURS_PATH,
            {
                "cityIDs": ",".join(str(value) for value in city_ids),
                "sDate": start,
                "eDate": end,
                "queryType": "1",
            },
        )

    def group_days(
        self, city_ids: list[int], start: str, end: str
    ) -> list[dict[str, Any]]:
        return self._query(
            GROUP_DAYS_PATH,
            {
                "cityIDs": ",".join(str(value) for value in city_ids),
                "sDate": start,
                "eDate": end,
                "queryType": "1",
            },
        )

    def site_hours(
        self, site_ids: list[int], start: str, end: str
    ) -> list[dict[str, Any]]:
        return self._query(
            SITE_HOURS_PATH,
            {
                "siteIDs": ",".join(str(value) for value in site_ids),
                "sDate": start,
                "eDate": end,
                # 前端语义: queryType 1=省辖市根(城市站) / 2=县级根(县级站)
                "queryType": "2",
            },
        )

    def site_days(
        self, site_ids: list[int], start: str, end: str
    ) -> list[dict[str, Any]]:
        return self._query(
            SITE_DAYS_PATH,
            {
                "siteIDs": ",".join(str(value) for value in site_ids),
                "sDate": start,
                "eDate": end,
                "queryType": "2",
            },
        )


def _walk_leaves(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    leaves: list[dict[str, Any]] = []
    for node in nodes or []:
        children = node.get("Children") or []
        if children:
            leaves.extend(_walk_leaves(children))
        else:
            leaves.append(node)
    return leaves


def city_groups_from_tree(tree: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Flatten the city tree into {group_id: {"name", "code"}}.

    平台不同后端节点的树结构不一致：有的返回扁平城市列表
    （data=[{ID,Name,Code},...]），有的在顶层包"省辖市/县级"根节点，
    且 ID 体系有旧(区号式)/新(行政区划码)两套 —— 因此每次运行都以
    实时拉取的树为准。同一 ID 以先出现的为准，"济源示范区"统一
    归一化为"济源市"。
    """

    def _collect(node: dict[str, Any], groups: dict[int, dict[str, Any]]) -> None:
        node_id = node.get("ID")
        name = normalize_city_name(node.get("Name"))
        children = node.get("Children") or []
        looks_like_city = name and not str(name).endswith(("省辖市", "县级"))
        if node_id is not None and looks_like_city and node_id not in groups:
            code = str(node.get("Code") or "").strip() or None
            groups[int(node_id)] = {"name": name, "code": code}
        for child in children:
            _collect(child, groups)

    groups: dict[int, dict[str, Any]] = {}
    for node in tree or []:
        _collect(node, groups)
    return groups


def build_henan_district_directory(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """全省区县目录：[{city, name, code, system}]，system 为树根（省辖市/县级）。"""
    districts: dict[tuple[str, str], dict[str, Any]] = {}
    for root in tree:
        system = str(root.get("Name") or "").strip()
        for city in root.get("Children") or []:
            city_name = str(city.get("Name") or "").strip()
            if not city_name:
                continue
            for county in city.get("Children") or []:
                county_name = str(county.get("Name") or "").strip()
                if not county_name:
                    continue
                key = (city_name, county_name)
                if key in districts:
                    continue
                districts[key] = {
                    "city": city_name,
                    "name": county_name,
                    "code": str(county.get("Code") or "").strip() or None,
                    "system": system,
                }
    return sorted(districts.values(), key=lambda item: (item["city"], item["name"]))


def site_leaves_from_tree(
    tree: list[dict[str, Any]],
    root_names: set[str] | None = None,
    city_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Flatten the station tree into rows with city/county provenance.

    树为 根(省辖市/县级) → 市 → 区县分组 → 站点 四层；站点叶子通过
    ``Note`` 携带类别（GK=国控、SCK=省控、SK=市控）。``root_names``
    可限定根分支（如 {"县级"}），``city_names`` 可限定城市（如
    {"许昌市"}）；两者为 None 时返回全部。
    """
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for root in tree:
        root_name = str(root.get("Name") or "").strip()
        if root_names and root_name not in root_names:
            continue
        for city in root.get("Children") or []:
            city_name = normalize_city_name(city.get("Name"))
            if city_names and city_name not in city_names:
                continue
            for county in city.get("Children") or []:
                county_name = str(county.get("Name") or "").strip()
                for leaf in _walk_leaves([county]):
                    site_id = leaf.get("ID")
                    if site_id is None or int(site_id) in seen:
                        continue
                    seen.add(int(site_id))
                    rows.append(
                        {
                            "site_id": int(site_id),
                            "site_name": str(leaf.get("Name") or "").strip(),
                            "city": city_name,
                            "county": county_name,
                            "online_type": str(leaf.get("Note") or "").strip() or None,
                            "root": root_name,
                        }
                    )
    return rows
