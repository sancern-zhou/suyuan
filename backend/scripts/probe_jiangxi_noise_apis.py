"""探测江西噪声平台接口发版状态(只读,最小参数)。

用途:目录式接入(api_catalog)的新接口上线前,在部署服务器上运行本脚本,
确认生产平台已发布对应路由,避免智能体调用打到 404。

示例:
    python scripts/probe_jiangxi_noise_apis.py --env-file .env
    python scripts/probe_jiangxi_noise_apis.py --env-file .env.jiangxi --timeout 10

探测项两处来源:
- API_CATALOG 全部条目(参数取各条目的 example,新增目录项自动纳入);
- EXTRA_PROBES:尚未入目录的候选路由(手工维护)。

按 HTTP 状态分类:200=已发版;404=未发版;400/500=已发版(探测参数不完整);
401/403=认证问题。结果打印到 stdout。
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx  # noqa: E402

from app.external_apis.jiangxi_noise_api_client import JiangxiNoiseDataClient  # noqa: E402


def _load_catalog() -> dict[str, Any]:
    """按文件路径加载接口目录,绕开 app.tools 包导入链(不依赖 agent 运行时)。"""
    import importlib.util

    catalog_path = BACKEND_DIR / "app/tools/query/query_jiangxi_noise/api_catalog.py"
    spec = importlib.util.spec_from_file_location("jiangxi_api_catalog", catalog_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.API_CATALOG


def _encode_query_params(payload: dict[str, Any]) -> dict[str, Any]:
    """GET 编码:列表按平台 name[i] 形式展开,其余平铺。"""
    query: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, list):
            for index, item in enumerate(value):
                query[f"{key}[{index}]"] = item
        else:
            query[key] = value
    return query


API_CATALOG = _load_catalog()

TOKEN_PATH = "/api/noiseproduct/AirCityBaseCommon/GetExternalApiToken"

# 尚未入目录的候选路由:(名称, 方法, 路径)
EXTRA_PROBES: list[tuple[str, str, str]] = [
    (
        "p2_directional_events",
        "GET",
        "/api/noiseproduct/airdata/NoiseEvent/GetNoiseDirectionalEventsAsync",
    ),
    (
        "p2_station_any_date",
        "GET",
        "/api/noiseproduct/airdata/DATStationDay/GetNoiseStationAnyDateDisplayPagedListAsync",
    ),
    (
        "p2_station_hour_paged2",
        "GET",
        "/api/noiseproduct/airdata/DATStationHour/GetDATStationHourDisplayPaged2ListAsync",
    ),
    (
        "p2_network_by_page",
        "GET",
        "/api/noiseproduct/netoverview/NetworkDataQuery/GetNetworkDataByPageAsync",
    ),
    (
        "p2_station_type_network",
        "GET",
        "/api/noiseproduct/netoverview/NetworkDataQuery/GetStationTypeNetworkDataAsync",
    ),
    (
        "p2_receiving_rate_by_page",
        "GET",
        "/api/noiseproduct/netoverview/DataReceivingRateQuery/GetDataReceivingRateByPageAsync",
    ),
]


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def build_catalog_probes() -> list[tuple[str, str, str, dict[str, Any] | None]]:
    """从 API_CATALOG 派生探测项:参数取 example,GET 按 name[i] 编码。"""
    probes = []
    for api, entry in API_CATALOG.items():
        method, endpoint = JiangxiNoiseDataClient.API_ROUTES[entry["route"]]
        example = dict(entry.get("example", {}))
        if method == "GET":
            probes.append((api, "GET", endpoint, _encode_query_params(example)))
        else:
            probes.append((api, "POST", endpoint, example))
    return probes


async def fetch_token(client: httpx.AsyncClient, env: dict[str, str]) -> str:
    response = await client.get(
        TOKEN_PATH,
        params={
            "UserName": env["JIANGXI_NOISE_USERNAME"],
            "SecretKey": env["JIANGXI_NOISE_SECRET_KEY"],
        },
        headers={"syscode": "NOISE"},
    )
    payload = response.json()
    token = payload.get("result") if payload.get("success") else None
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError(f"token 换取失败：{payload}")
    return token.strip()


def classify(status: int, payload: Any) -> str:
    if status == 200:
        if isinstance(payload, dict) and payload.get("success") is False:
            return "已发版(业务提示,路由存在)"
        return "已发版"
    if status == 404:
        return "未发版"
    if status in (400, 500):
        return "已发版(探测参数不完整)"
    if status in (401, 403):
        return "认证/授权问题"
    return f"其他 {status}"


async def run(base_url: str, env: dict[str, str], timeout: float, list_only: bool = False) -> int:
    probes = build_catalog_probes() + [
        (name, method, path, {}) for name, method, path in EXTRA_PROBES
    ]
    if list_only:
        for name, method, path, _params in probes:
            print(f"{name}: {method} {path}")
        print(f"\n共 {len(probes)} 条(目录 {len(probes) - len(EXTRA_PROBES)} + 额外 {len(EXTRA_PROBES)})")
        return 0
    not_deployed: list[str] = []
    exit_code = 0
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False) as client:
        try:
            token = await fetch_token(client, env)
        except Exception as exc:  # noqa: BLE001
            print(f"token 换取失败：{type(exc).__name__}: {exc}")
            print(f"base_url={base_url} —— 请确认本机到平台网络可达")
            return 2
        print(f"token=OK base={base_url} 探测项={len(probes)}")
        headers = {"Authorization": f"Bearer {token}", "syscode": "NOISE"}
        for name, method, path, params in probes:
            try:
                if method == "GET":
                    response = await client.get(path, params=params, headers=headers)
                else:
                    body = params or {}
                    response = await client.post(path, json=body, headers=headers)
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                verdict = classify(response.status_code, payload)
                if response.status_code == 404:
                    not_deployed.append(name)
            except Exception as exc:  # noqa: BLE001
                verdict = f"连接失败 {type(exc).__name__}: {exc}"
                exit_code = 3
            print(f"{name}: {verdict}")
    if not_deployed:
        exit_code = 1
        print(f"\n未发版 {len(not_deployed)} 条：{', '.join(not_deployed)}")
        print("这些接口的目录条目在生产可用前会返回 query_http_error，属预期降级。")
    else:
        print("\n全部探测项均已发版。")
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="探测江西噪声平台接口发版状态")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="环境文件路径(默认 .env；本地参照环境可用 .env.jiangxi)",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="单请求超时秒数")
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="只列出将探测的路由，不发请求",
    )
    args = parser.parse_args()

    env = {**load_env_file(BACKEND_DIR / args.env_file), **os.environ}
    base_url = (env.get("JIANGXI_NOISE_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        raise SystemExit(
            "缺少 JIANGXI_NOISE_BASE_URL —— 用 --env-file 指定包含该变量的环境文件"
        )
    missing = [
        key
        for key in ("JIANGXI_NOISE_USERNAME", "JIANGXI_NOISE_SECRET_KEY")
        if not (env.get(key) or "").strip()
    ]
    if missing and not args.list_only:
        raise SystemExit(f"环境文件缺少变量：{'、'.join(missing)}")
    exit_code = asyncio.run(run(base_url, env, args.timeout, list_only=args.list_only))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
