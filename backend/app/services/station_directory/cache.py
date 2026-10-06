"""Shared cache for station directory payloads.

Every provider caches its normalised directory under the data registry with a
single, configurable TTL.  This replaces the per-tool caches (data registry,
process memory, none) that used to drift apart.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import structlog

from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

DEFAULT_CACHE_TTL_SECONDS = 7 * 24 * 3600.0
CACHE_ROOT_NAME = "station_directory"
CACHE_FILE_NAME = "cache.json"


class StationDirectoryCache:
    """File-backed cache namespaced per provider."""

    def __init__(
        self,
        namespace: str,
        *,
        ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        base_dir: str | Path | None = None,
    ) -> None:
        self.namespace = str(namespace).strip() or "default"
        self.ttl_seconds = float(ttl_seconds)
        self._base_dir = Path(base_dir) if base_dir is not None else None

    @property
    def directory(self) -> Path:
        root = self._base_dir if self._base_dir is not None else get_data_registry()
        return root / CACHE_ROOT_NAME / self.namespace

    @property
    def path(self) -> Path:
        return self.directory / CACHE_FILE_NAME

    def load(self) -> dict[str, Any] | None:
        """Return the cached payload when present and fresh, else ``None``."""

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None
        generated_at = payload.get("generated_at")
        try:
            generated = float(generated_at)
        except (TypeError, ValueError):
            return None
        if self.ttl_seconds >= 0 and time.time() - generated > self.ttl_seconds:
            return None
        payload["from_cache"] = True
        return payload

    def save(self, payload: dict[str, Any], *, generated_at: float | None = None) -> Path:
        """Persist ``payload`` and return the written path."""

        stored = dict(payload)
        stored.setdefault(
            "generated_at", float(generated_at if generated_at is not None else time.time())
        )
        stored["namespace"] = self.namespace
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "station_directory_cache_write_failed",
                namespace=self.namespace,
                error=str(exc),
            )
        return self.path

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning(
                "station_directory_cache_clear_failed",
                namespace=self.namespace,
                error=str(exc),
            )
