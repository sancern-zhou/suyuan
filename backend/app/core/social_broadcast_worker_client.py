"""HTTP client for assistant-to-Worker targeted social broadcasts."""

from __future__ import annotations

from typing import Any

import httpx

from config.settings import settings


class SocialBroadcastWorkerUnavailable(RuntimeError):
    """The authenticated Worker broadcast endpoint could not be used."""


class SocialBroadcastWorkerClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float = 30.0,
    ):
        self.base_url = base_url or settings.social_worker_internal_url
        self.token = (
            settings.social_worker_internal_token if token is None else token
        )
        self.timeout_seconds = timeout_seconds

    async def broadcast(
        self,
        *,
        message: str,
        target_user_names: list[str],
        media: list[str] | None = None,
        context_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/internal/social/broadcast"
        headers = {}
        if self.token:
            headers["x-social-worker-token"] = self.token
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    url,
                    json={
                        "message": message,
                        "target_user_names": target_user_names,
                        "media": media or [],
                        "context_metadata": context_metadata or {},
                    },
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise SocialBroadcastWorkerUnavailable(
                f"Worker returned HTTP {exc.response.status_code}"
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise SocialBroadcastWorkerUnavailable(str(exc)) from exc
