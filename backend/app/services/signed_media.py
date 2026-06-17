"""Temporary signed URLs for local social media files."""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote, urlencode

import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)


class SignedMediaService:
    """Create and validate expiring URLs for files under approved media roots."""

    def __init__(
        self,
        media_roots: Iterable[Path],
        secret: str,
        base_url: str,
        ttl_seconds: int = 600,
    ) -> None:
        self.media_roots = [Path(root).resolve() for root in media_roots]
        self.secret = secret
        self.base_url = base_url.rstrip("/")
        self.ttl_seconds = ttl_seconds

    def create_url(self, file_path: str | Path) -> Optional[str]:
        path = Path(file_path).resolve()
        relative_path = self._relative_path(path)
        if relative_path is None:
            logger.warning("signed_media_path_outside_allowed_roots", path=str(path))
            return None
        if not path.exists() or not path.is_file():
            logger.warning("signed_media_file_missing", path=str(path))
            return None

        expires = int(time.time()) + max(1, int(self.ttl_seconds))
        signature = self._sign(relative_path, expires)
        encoded_path = quote(relative_path, safe="/")
        query = urlencode({"expires": expires, "signature": signature})
        return f"{self.base_url}/api/signed-media/{encoded_path}?{query}"

    def resolve(self, relative_path: str, expires: int, signature: str) -> Path:
        if int(expires) < int(time.time()):
            raise PermissionError("signed media URL expired")

        normalized = Path(relative_path)
        if normalized.is_absolute() or any(part == ".." for part in normalized.parts):
            raise PermissionError("invalid signed media path")

        normalized_str = normalized.as_posix()
        expected = self._sign(normalized_str, int(expires))
        if not hmac.compare_digest(expected, signature):
            raise PermissionError("invalid signed media signature")

        for root in self.media_roots:
            candidate = (root / normalized).resolve()
            if self._is_under_root(candidate, root) and candidate.exists() and candidate.is_file():
                return candidate

        raise FileNotFoundError("signed media file not found")

    def _relative_path(self, path: Path) -> Optional[str]:
        for root in self.media_roots:
            if not self._is_under_root(path, root):
                continue
            return path.relative_to(root).as_posix()
        return None

    @staticmethod
    def _is_under_root(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _sign(self, relative_path: str, expires: int) -> str:
        payload = f"{relative_path}\n{int(expires)}".encode("utf-8")
        return hmac.new(self.secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


_service: Optional[SignedMediaService] = None


def get_signed_media_service() -> SignedMediaService:
    global _service
    if _service is None:
        backend_root = Path(__file__).resolve().parents[2]
        secret = settings.signed_media_secret or settings.minimax_api_key or "development-signed-media-secret"
        base_url = settings.signed_media_base_url or settings.backend_host
        _service = SignedMediaService(
            media_roots=[backend_root / "backend_data_registry" / "social"],
            secret=secret,
            base_url=base_url,
            ttl_seconds=settings.signed_media_ttl_seconds,
        )
    return _service
