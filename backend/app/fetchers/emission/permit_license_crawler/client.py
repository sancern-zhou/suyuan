from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx


class PermitPlatformError(RuntimeError):
    """Base error for platform access."""


class PlatformBlockedError(PermitPlatformError):
    """Raised when the platform asks the crawler to stop or verify access."""


CHALLENGE_MARKERS = (
    "验证码",
    "访问过于频繁",
    "请求过于频繁",
    "安全验证",
    "稍后再试",
)


class PermitPlatformClient:
    def __init__(
        self,
        *,
        min_delay_seconds: float = 1.0,
        max_delay_seconds: float = 2.0,
        min_burst_delay_seconds: float = 0.1,
        max_burst_delay_seconds: float = 0.2,
        max_retries: int = 3,
        timeout_seconds: float = 45.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if min_delay_seconds < 0 or max_delay_seconds < min_delay_seconds:
            raise ValueError("invalid request delay range")
        if (
            min_burst_delay_seconds < 0
            or max_burst_delay_seconds < min_burst_delay_seconds
        ):
            raise ValueError("invalid burst delay range")
        self.min_delay_seconds = min_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.min_burst_delay_seconds = min_burst_delay_seconds
        self.max_burst_delay_seconds = max_burst_delay_seconds
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; XuchangPermitArchive/1.0)",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )

    async def __aenter__(self) -> PermitPlatformClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, url: str, *, burst: bool = False, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, burst=burst, **kwargs)

    async def post(self, url: str, *, burst: bool = False, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, burst=burst, **kwargs)

    async def request(
        self, method: str, url: str, *, burst: bool = False, **kwargs: Any
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise PermitPlatformError(f"request failed after retries: {exc}") from exc
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code in {403, 429}:
                raise PlatformBlockedError(f"platform returned HTTP {response.status_code}")
            if response.status_code >= 500:
                if attempt >= self.max_retries:
                    raise PermitPlatformError(
                        f"platform returned HTTP {response.status_code} after retries"
                    )
                await asyncio.sleep(2**attempt)
                continue
            final_path = response.url.path.lower()
            content_type = response.headers.get("content-type", "").lower()
            text = (
                response.text
                if not content_type or "html" in content_type or content_type.startswith("text/")
                else ""
            )
            if any(marker in text for marker in CHALLENGE_MARKERS) or "default-index!getinformation" in final_path:
                raise PlatformBlockedError("platform returned a challenge page")
            response.raise_for_status()
            await self._delay(burst=burst)
            return response
        raise PermitPlatformError(f"request failed: {last_error}")

    async def _delay(self, *, burst: bool = False) -> None:
        if burst:
            delay = random.uniform(
                self.min_burst_delay_seconds, self.max_burst_delay_seconds
            )
        else:
            delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
        if delay:
            await asyncio.sleep(delay)
