#!/usr/bin/env python3
"""Secret-safe live verification for the Suyuan gateway contract."""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass

import httpx


@dataclass
class CheckFailure(RuntimeError):
    check: str
    reason: str


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise CheckFailure("configuration", f"missing environment variable {name}")
    return value


async def check_response(
    client: httpx.AsyncClient,
    name: str,
    method: str,
    path: str,
    expected: set[int],
    **kwargs,
) -> httpx.Response:
    try:
        response = await client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise CheckFailure(name, f"network error ({type(exc).__name__})") from exc
    if response.status_code not in expected:
        if response.status_code == 404 and name.startswith("auth_route"):
            raise CheckFailure(name, "infrastructure blocker: authentication route returned 404")
        raise CheckFailure(name, f"unexpected HTTP status {response.status_code}")
    print(f"PASS {name}")
    return response


async def verify_nacos() -> None:
    base = required("NACOS_BASE_URL").rstrip("/")
    username = required("NACOS_USERNAME")
    password = required("NACOS_PASSWORD")
    async with httpx.AsyncClient(base_url=base, timeout=8) as client:
        login = await check_response(
            client,
            "nacos_login",
            "POST",
            "/nacos/v1/auth/login",
            {200},
            data={"username": username, "password": password},
        )
        token = login.json().get("accessToken", "")
        response = await check_response(
            client,
            "nacos_suyuan_agent",
            "GET",
            "/nacos/v1/ns/instance/list",
            {200},
            params={
                "serviceName": "suyuan-agent",
                "groupName": "DEFAULT_GROUP",
                "namespaceId": "normcraft-ai",
                "accessToken": token,
                "healthyOnly": "true",
            },
        )
        hosts = response.json().get("hosts") or []
        if not any(host.get("healthy") and host.get("enabled") for host in hosts):
            raise CheckFailure("nacos_suyuan_agent", "no healthy enabled instance")


async def verify_gateway() -> None:
    base = required("GATEWAY_BASE_URL").rstrip("/")
    token = required("SUYUAN_TEST_ACCESS_TOKEN")
    headers = {"Authorization": f"Bearer {token}", "SysCode": "SUYUAN"}
    async with httpx.AsyncClient(base_url=base, timeout=12) as client:
        await check_response(client, "health", "GET", "/api/suyuan/health", {200})
        await check_response(client, "ready", "GET", "/api/suyuan/ready", {200})
        await check_response(client, "anonymous_business", "GET", "/api/suyuan/info", {401})
        for suffix in (
            "token/authentication",
            "account/getCurrentUser?isLog=1&logType=4",
            "token/logout",
        ):
            await check_response(
                client,
                f"auth_route_{suffix.split('/')[0]}",
                "GET",
                f"/api/auth/{suffix}",
                {200, 400, 401, 403, 405},
                headers=headers,
            )
        authenticated = await check_response(
            client, "authenticated_business", "GET", "/api/suyuan/info", {200}, headers=headers
        )
        forged = await check_response(
            client,
            "forged_admin_ignored",
            "GET",
            "/api/suyuan/info",
            {200},
            headers={**headers, "X-User-Id": "attacker", "X-Is-Admin": "true"},
        )
        auth_body = authenticated.json()
        forged_body = forged.json()
        if forged_body.get("id") != auth_body.get("id") or (
            forged_body.get("is_admin") and not auth_body.get("is_admin")
        ):
            raise CheckFailure("forged_admin_ignored", "identity changed after forged headers")


async def main() -> int:
    try:
        await verify_nacos()
        await verify_gateway()
    except CheckFailure as exc:
        print(f"FAIL {exc.check}: {exc.reason}", file=sys.stderr)
        return 1
    print("PASS gateway_auth_acceptance")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
