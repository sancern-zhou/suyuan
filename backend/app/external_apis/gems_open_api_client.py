"""NIER GEMS Open-API client for official Level-2 rendered images."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import httpx


GEMS_PRODUCT_CODES = {
    "no2": "NO2",
    "so2": "SO2",
    "hcho": "HCHO",
    "o3": "O3T",
}


class GemsOpenApiClient:
    """Download official GEMS images and Level-2 scientific data products."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 90.0,
        proxy: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMS_API_KEY")
        self.proxy = (
            proxy
            or os.getenv("GEMS_PROXY_SERVER")
            or os.getenv("QIANLIMA_PROXY_SERVER")
            or None
        )
        self.timeout = httpx.Timeout(timeout_seconds, connect=15.0)

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key)

    def is_configured_for(self, product_type: str) -> bool:
        return bool(self.api_key and self._template(product_type))

    def is_data_configured_for(self, product_type: str) -> bool:
        return bool(self.api_key and self._data_template(product_type))

    async def download_image(
        self,
        *,
        product_type: str,
        observation_time: datetime | str,
        destination: Path,
    ) -> dict[str, str]:
        if not self.has_credentials:
            raise RuntimeError("GEMS_API_KEY is required for GEMS Open-API downloads")
        template = self._template(product_type)
        if not template:
            raise RuntimeError(f"GEMS_{product_type.upper()}_IMAGE_URL_TEMPLATE is not configured")

        timestamp = self._format_timestamp(observation_time)
        try:
            url = template.format(
                api_key=self.api_key,
                timestamp=timestamp,
                product=GEMS_PRODUCT_CODES[product_type],
            )
        except KeyError as exc:
            raise ValueError(
                "GEMS image URL templates may use only {api_key}, {timestamp}, and {product}"
            ) from exc

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            proxy=self.proxy,
        ) as client:
            response = await client.get(url)
            if response.status_code == 404:
                raise FileNotFoundError(f"GEMS {product_type} is not published for {timestamp}")
            response.raise_for_status()

        if not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            content_type = response.headers.get("content-type", "unknown")
            raise ValueError(f"GEMS returned a non-PNG response ({content_type})")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return {"timestamp": timestamp}

    async def download_data(
        self,
        *,
        product_type: str,
        observation_time: datetime | str,
        destination: Path,
    ) -> dict[str, str]:
        """Stream one NetCDF product to disk without retaining it in memory."""
        if not self.has_credentials:
            raise RuntimeError("GEMS_API_KEY is required for GEMS Open-API downloads")
        template = self._data_template(product_type)
        if not template:
            raise RuntimeError(f"GEMS_{product_type.upper()}_DATA_URL_TEMPLATE is not configured")

        timestamp = self._format_timestamp(observation_time)
        try:
            url = template.format(
                api_key=self.api_key,
                timestamp=timestamp,
                product=GEMS_PRODUCT_CODES[product_type],
            )
        except KeyError as exc:
            raise ValueError(
                "GEMS data URL templates may use only {api_key}, {timestamp}, and {product}"
            ) from exc

        destination.parent.mkdir(parents=True, exist_ok=True)
        partial_destination = destination.with_suffix(f"{destination.suffix}.part")
        timeout_seconds = float(os.getenv("GEMS_DATA_DOWNLOAD_TIMEOUT_SECONDS", "10800"))
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds, connect=30.0),
                follow_redirects=True,
                proxy=self.proxy,
            ) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code == 404:
                        raise FileNotFoundError(
                            f"GEMS {product_type} is not published for {timestamp}"
                        )
                    response.raise_for_status()
                    with partial_destination.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            output.write(chunk)
                    content_type = response.headers.get("content-type", "unknown")
                    remote_name = response.headers.get("headerData", "")
            with partial_destination.open("rb") as downloaded_file:
                magic = downloaded_file.read(8)
            if not magic.startswith(b"\x89HDF\r\n\x1a\n"):
                raise ValueError(f"GEMS returned a non-NetCDF response ({content_type})")
            partial_destination.replace(destination)
            return {"timestamp": timestamp, "remote_name": remote_name}
        except Exception:
            partial_destination.unlink(missing_ok=True)
            raise

    async def find_latest_observation_time(
        self,
        *,
        product_type: str,
        since: datetime,
        until: datetime,
    ) -> datetime | None:
        """Return the newest NESC-published observation time in the requested window."""
        if not self.has_credentials:
            raise RuntimeError("GEMS_API_KEY is required for GEMS Open-API downloads")
        template = self._date_list_template(product_type)
        if not template:
            raise RuntimeError(
                f"GEMS_{product_type.upper()}_DATE_LIST_URL_TEMPLATE is not configured"
            )
        try:
            url = template.format(
                api_key=self.api_key,
                start_timestamp=self._format_search_timestamp(since),
                end_timestamp=self._format_search_timestamp(until),
                product=GEMS_PRODUCT_CODES[product_type],
            )
        except KeyError as exc:
            raise ValueError(
                "GEMS date-list URL templates may use only {api_key}, "
                "{start_timestamp}, {end_timestamp}, and {product}"
            ) from exc

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            proxy=self.proxy,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
        try:
            rows = response.json().get("list", [])
        except ValueError as exc:
            raise ValueError("GEMS date-list response was not valid JSON") from exc
        available_times = [
            parsed
            for row in rows
            if isinstance(row, dict)
            for parsed in [self._parse_timestamp(str(row.get("item", "")))]
            if parsed is not None
        ]
        return max(available_times, default=None)

    @staticmethod
    def _template(product_type: str) -> str | None:
        if product_type not in GEMS_PRODUCT_CODES:
            raise ValueError(f"Unsupported GEMS product: {product_type}")
        return os.getenv(f"GEMS_{product_type.upper()}_IMAGE_URL_TEMPLATE")

    @staticmethod
    def _date_list_template(product_type: str) -> str | None:
        if product_type not in GEMS_PRODUCT_CODES:
            raise ValueError(f"Unsupported GEMS product: {product_type}")
        return os.getenv(f"GEMS_{product_type.upper()}_DATE_LIST_URL_TEMPLATE")

    @staticmethod
    def _data_template(product_type: str) -> str | None:
        if product_type not in GEMS_PRODUCT_CODES:
            raise ValueError(f"Unsupported GEMS product: {product_type}")
        return os.getenv(f"GEMS_{product_type.upper()}_DATA_URL_TEMPLATE")

    @staticmethod
    def _format_timestamp(observation_time: datetime | str) -> str:
        if isinstance(observation_time, str):
            if observation_time.isdigit() and len(observation_time) in (12, 14):
                return observation_time
            raise ValueError("GEMS observation times must be 12 or 14 digit UTC timestamps")
        return observation_time.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")

    @staticmethod
    def _parse_timestamp(timestamp: str) -> datetime | None:
        for pattern in ("%Y%m%d%H%M%S", "%Y%m%d%H%M"):
            try:
                return datetime.strptime(timestamp, pattern).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    @staticmethod
    def _format_search_timestamp(observation_time: datetime) -> str:
        """NESC getFileDateList accepts minute-resolution query bounds only."""
        return observation_time.astimezone(timezone.utc).strftime("%Y%m%d%H%M")
