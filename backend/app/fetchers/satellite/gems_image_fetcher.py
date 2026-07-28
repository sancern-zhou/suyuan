"""Hourly GEMS Level-2 image fetcher for the Xuchang tracing region."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.external_apis.gems_open_api_client import GemsOpenApiClient
from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.data_registry import DataRegistryService, data_registry
from app.services.image_cache import ImageCache, get_image_cache
from app.services.gems_image_cropper import GemsOfficialImageCropper

logger = structlog.get_logger()

GEMS_PRODUCTS = ("no2", "so2", "hcho", "o3")


class GemsImageFetcher(DataFetcher):
    """Cache the newest official GEMS product image for alert tracing."""

    def __init__(
        self,
        client: GemsOpenApiClient | None = None,
        registry: DataRegistryService | None = None,
        now_factory: Any = lambda: datetime.now(timezone.utc),
        image_cache: ImageCache | None = None,
        cropper: GemsOfficialImageCropper | None = None,
        lookback_hours: int | None = None,
    ) -> None:
        super().__init__(
            name="gems_xuchang_image_fetcher",
            description="许昌周边 GEMS 小时级遥感产品图抓取",
            schedule="20 * * * *",
            version="1.0.0",
        )
        self.client = client or GemsOpenApiClient()
        self.registry = registry or data_registry
        self.now_factory = now_factory
        self.image_cache = image_cache
        self.cropper = cropper or GemsOfficialImageCropper()
        self.lookback_hours = lookback_hours or int(os.getenv("GEMS_LOOKBACK_HOURS", "8"))
        self.state_path = self.registry.base_dir / "satellite" / "gems_xuchang_latest.json"
        self.image_dir = self.registry.base_dir / "satellite" / "gems" / "xuchang"

    async def fetch_and_store(self) -> dict[str, Any]:
        if not self.client.has_credentials:
            return {"fetched": 0, "changed": False, "configured": False, "products": [], "failed": {}}

        now = self.now_factory().astimezone(timezone.utc)
        previous = self._load_state()
        products: list[dict[str, Any]] = []
        failed: dict[str, str] = {}
        for product_type in GEMS_PRODUCTS:
            if not self.client.is_configured_for(product_type):
                continue
            product = await self._fetch_latest_product(product_type, now, previous, failed)
            if product:
                products.append(product)

        if not products:
            return {"fetched": 0, "changed": False, "configured": True, "products": [], "failed": failed}

        payload = {
            "source": "NIER GEMS Level-2",
            "region": "xuchang_surrounding_200km",
            "retrieved_at": now.isoformat(),
            "products": products,
            "limitations": ["GEMS 产品图为柱浓度或遥感指数，不能直接等同地面浓度。"],
        }
        entry = self.registry.register_payload(
            schema="satellite_gems_catalogue",
            version="v1",
            payload=payload,
            metadata={"source": "NIER GEMS", "region": "xuchang"},
        )
        self._save_state({product["product_type"]: product["ContentDate"]["Start"] for product in products})
        return {
            "fetched": len(products),
            "changed": True,
            "configured": True,
            "data_id": entry.data_id,
            "products": [product["product_type"] for product in products],
            "failed": failed,
        }

    async def _fetch_latest_product(
        self,
        product_type: str,
        now: datetime,
        previous: dict[str, str],
        failed: dict[str, str],
    ) -> dict[str, Any] | None:
        try:
            observation_time = await self.client.find_latest_observation_time(
                product_type=product_type,
                since=now - timedelta(hours=self.lookback_hours),
                until=now,
            )
        except Exception as exc:
            failed[product_type] = str(exc)
            return None
        if observation_time is None:
            return None
        observation_iso = observation_time.isoformat()
        if previous.get(product_type) == observation_iso:
            return None

        image_path = self.image_dir / f"gems_{product_type}_{observation_time:%Y%m%d%H%M%S}.png"
        try:
            await self.client.download_image(
                product_type=product_type,
                observation_time=observation_time,
                destination=image_path,
            )
        except Exception as exc:
            failed[product_type] = str(exc)
            return None

        display_path = self.image_dir / f"gems_{product_type}_xuchang_{observation_time:%Y%m%d%H%M%S}.png"
        crop_metadata = self.cropper.crop(image_path, display_path)

        image_id = f"gems_xuchang_{product_type}_{observation_time:%Y%m%d%H%M%S}"
        image_cache = self.image_cache or get_image_cache()
        image = image_cache.save(
            base64.b64encode(display_path.read_bytes()).decode("ascii"),
            chart_id=image_id,
        )
        return {
            "Id": image_id,
            "Name": display_path.name,
            "product_type": product_type,
            "source": "NIER GEMS Level-2",
            "ContentDate": {"Start": observation_iso, "End": observation_iso},
            "local_path": str(display_path),
            "source_image_path": str(image_path),
            "image": image,
            "geographic_bounds": crop_metadata,
            "observation_summary": {
                "product_mode": "official_rendered_image_geographic_crop",
                "statistics": None,
            },
        }

    def _load_state(self) -> dict[str, str]:
        if not self.state_path.exists():
            return {}
        try:
            return dict(json.loads(self.state_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return {}

    def _save_state(self, state: dict[str, str]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
