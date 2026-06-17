"""S3-compatible object storage for temporary social media URLs."""

from __future__ import annotations

import hashlib
import mimetypes
import time
from pathlib import Path
from typing import Optional

import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)


class MediaObjectStore:
    """Upload local media and return short-lived S3 presigned URLs."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "social-media",
        ttl_seconds: int = 600,
        s3_client=None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.ttl_seconds = ttl_seconds
        self._s3_client = s3_client

    @property
    def enabled(self) -> bool:
        return bool(self.bucket and self._s3_client is not None)

    def upload_and_presign(self, local_path: str | Path, *, content_type: Optional[str] = None) -> Optional[str]:
        if not self.enabled:
            return None
        path = Path(local_path)
        if not path.exists() or not path.is_file():
            logger.warning("media_object_store_file_missing", path=str(path))
            return None

        object_key = self._object_key(path)
        extra_args = {}
        resolved_content_type = content_type or mimetypes.guess_type(path.name)[0]
        if resolved_content_type:
            extra_args["ContentType"] = resolved_content_type

        self._s3_client.upload_file(
            str(path),
            self.bucket,
            object_key,
            ExtraArgs=extra_args or None,
        )
        return self.create_presigned_url(object_key)

    def create_presigned_url(self, object_key: str, *, expires_in: Optional[int] = None) -> str:
        return self._s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=expires_in or self.ttl_seconds,
        )

    def _object_key(self, path: Path) -> str:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        date_part = time.strftime("%Y%m%d")
        safe_name = path.name.replace("/", "_").replace("\\", "_")
        return f"{self.prefix}/{date_part}/{digest}-{safe_name}" if self.prefix else f"{date_part}/{digest}-{safe_name}"


_store: Optional[MediaObjectStore] = None


def get_media_object_store() -> MediaObjectStore:
    global _store
    if _store is None:
        _store = _build_store_from_settings()
    return _store


def _build_store_from_settings() -> MediaObjectStore:
    if not settings.media_object_store_enabled:
        return MediaObjectStore(bucket="", s3_client=None)
    if not (
        settings.media_object_store_bucket
        and settings.media_object_store_access_key_id
        and settings.media_object_store_secret_access_key
    ):
        logger.warning("media_object_store_disabled_missing_config")
        return MediaObjectStore(bucket="", s3_client=None)

    try:
        import boto3
    except ImportError:
        logger.warning("media_object_store_disabled_missing_boto3")
        return MediaObjectStore(bucket="", s3_client=None)

    client = boto3.client(
        "s3",
        endpoint_url=settings.media_object_store_endpoint_url,
        aws_access_key_id=settings.media_object_store_access_key_id,
        aws_secret_access_key=settings.media_object_store_secret_access_key,
        region_name=settings.media_object_store_region,
    )
    return MediaObjectStore(
        bucket=settings.media_object_store_bucket,
        prefix=settings.media_object_store_prefix,
        ttl_seconds=settings.media_object_store_presign_ttl_seconds,
        s3_client=client,
    )
