"""Guarded HTTP fetching for ops-audit attachment backends.

Work-order attachment URLs originate from an upstream platform payload and are
therefore only semi-trusted. Direct ``requests.get`` on them would allow SSRF
against loopback / link-local / intranet services. All ops-audit downloads must
go through :func:`guarded_get`, which

- only accepts http/https,
- always allows the configured attachment base-url hosts,
- rejects loopback / link-local / private / CGNAT targets otherwise,
- re-validates the final URL after redirects.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

import requests
import structlog

logger = structlog.get_logger()

_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
        "fe80::/10",
        "::1/128",
    )
)


def _trusted_hosts() -> set[str]:
    hosts: set[str] = set()
    for key in (
        "OPS_ATTACHMENT_BASE_URL",
        "ATTACHMENT_BASE_URL",
    ):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        try:
            hosts.add(urlparse(raw).hostname or "")
        except ValueError:
            continue
    hosts.discard("")
    return hosts


def _extra_allowed_networks() -> tuple[ipaddress.ip_network, ...]:
    raw = (os.getenv("OPS_ATTACHMENT_EXTRA_ALLOWED_NETWORKS") or "").strip()
    if not raw:
        return ()
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("ops_attachment_extra_network_invalid", value=item)
    return tuple(networks)


def _address_in_networks(address: ipaddress.IPv4Address | ipaddress.IPv6Address, networks) -> bool:
    return any(address in network for network in networks)


def assert_public_http_url(url: str) -> None:
    parsed = urlparse(str(url))
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("仅支持 http/https 附件地址")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("附件地址缺少主机名")

    trusted = _trusted_hosts()
    extra = _extra_allowed_networks()
    if host in trusted:
        return

    candidates: list[str] = []
    try:
        ipaddress.ip_address(host)
        candidates.append(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise ValueError(f"附件主机无法解析: {host}") from exc
        candidates = sorted({info[4][0] for info in infos})

    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if _address_in_networks(address, extra):
            continue
        if _address_in_networks(address, _BLOCKED_NETWORKS):
            raise ValueError(f"附件地址指向受限网段: {host}")


def guarded_get(url: str, *, timeout: float = 30.0) -> requests.Response:
    assert_public_http_url(url)
    response = requests.get(url, timeout=timeout, allow_redirects=True)
    # 重定向后的最终地址同样必须通过校验
    assert_public_http_url(response.url)
    return response
