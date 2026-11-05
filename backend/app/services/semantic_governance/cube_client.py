# -*- coding: utf-8 -*-
"""Cube REST 客户端原语：JWT 签名、查询组装、行展平/截断、HTTP 调用。

base_url/secret 由调用方传入（项目工具从自己的环境变量装配），本模块不做
任何项目假设。连库侧鉴权仍由部署的 agent_reader 只读角色约束，这里只负责
与 Cube 服务之间的短时效 HS256 JWT。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional, Sequence

import httpx


def make_token(secret: str, ttl_seconds: int = 300) -> str:
    """HS256 JWT（Cube API_SECRET 鉴权, 短时效, 每次调用现签）。"""
    def b64url(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64url(json.dumps({"exp": int(time.time()) + ttl_seconds}).encode())
    sig = b64url(hmac.new(secret.encode(), f"{header}.{payload}".encode(),
                          hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def build_query(
    measures: Sequence[str],
    dimensions: Optional[Sequence[str]] = None,
    time_dimension: Optional[str] = None,
    date_range: Any = None,
    granularity: Optional[str] = None,
    filters: Optional[List[Dict[str, Any]]] = None,
    order: Optional[Dict[str, str]] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """组装 Cube /load 查询体；limit 建议传 requested+1 供截断探测。"""
    query: Dict[str, Any] = {"measures": list(measures)}
    if dimensions:
        query["dimensions"] = list(dimensions)
    if time_dimension:
        td: Dict[str, Any] = {"dimension": time_dimension}
        if date_range:
            td["dateRange"] = date_range
        if granularity:
            td["granularity"] = granularity
        query["timeDimensions"] = [td]
    if filters:
        query["filters"] = filters
    if order:
        query["order"] = order
    if limit is not None:
        query["limit"] = limit
    return query


def flatten_rows(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Cube 返回的 {member: {value: ...}} 行展平为 {member: value}。"""
    return [
        {k: (v.get("value") if isinstance(v, dict) else v)
         for k, v in row.items()}
        for row in body.get("data", [])
    ]


def truncate_rows(rows: List[Dict[str, Any]], limit: int) -> "tuple[List[Dict[str, Any]], bool]":
    """按请求上限截断；返回 (行, 是否被截断)。"""
    truncated = len(rows) > limit
    return rows[:limit], truncated


async def query_cube(base_url: str, secret: str, query: Dict[str, Any],
                     *, timeout: float = 30.0) -> Dict[str, Any]:
    """POST {base_url}/load；非 200 / body.error 一律抛 RuntimeError。"""
    if not secret:
        raise RuntimeError("Cube API secret 未配置(语义层鉴权)")
    token = make_token(secret)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/load",
            json={"query": query},
            headers={"Authorization": token},
        )
        if resp.status_code != 200:
            detail = resp.text[:500]
            raise RuntimeError(f"语义层返回 {resp.status_code}: {detail}")
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"语义层错误: {body['error']}")
        return body
