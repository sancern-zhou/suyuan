"""GEMS HCHO NetCDF downloader and Xuchang regional-overlay renderer."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.external_apis.gems_open_api_client import GemsOpenApiClient
from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.data_registry import DataRegistryService, data_registry
from app.services.gems_netcdf_renderer import GemsNetcdfRenderer
from app.services.image_cache import ImageCache, get_image_cache


class GemsHchoDataFetcher(DataFetcher):
    """Fetch a raw HCHO scene and expose a cropped transparent PNG map overlay."""

    def __init__(
        self,
        client: GemsOpenApiClient | None = None,
        registry: DataRegistryService | None = None,
        renderer: GemsNetcdfRenderer | None = None,
        image_cache: ImageCache | None = None,
        now_factory: Any = lambda: datetime.now(timezone.utc),
        lookback_hours: int | None = None,
    ) -> None:
        super().__init__(
            name="gems_xuchang_hcho_data_fetcher",
            description="许昌周边 GEMS HCHO 原始数据裁剪与地图叠加层生成",
            schedule="35 * * * *",
            version="1.0.0",
        )
        self.client = client or GemsOpenApiClient()
        self.registry = registry or data_registry
        self.renderer = renderer or GemsNetcdfRenderer()
        self.image_cache = image_cache
        self.now_factory = now_factory
        self.lookback_hours = lookback_hours or int(os.getenv("GEMS_LOOKBACK_HOURS", "8"))
        self.raw_dir = self.registry.base_dir / "satellite" / "gems" / "raw"
        self.overlay_dir = self.registry.base_dir / "satellite" / "gems" / "xuchang"
        self.state_path = self.registry.base_dir / "satellite" / "gems_xuchang_hcho_data_latest.json"

    async def fetch_and_store(self) -> dict[str, Any]:
        if not self.client.is_data_configured_for("hcho"):
            return {"fetched": 0, "changed": False, "configured": False}

        now = self.now_factory().astimezone(timezone.utc)
        observation_time = await self.client.find_latest_observation_time(
            product_type="hcho",
            since=now - timedelta(hours=self.lookback_hours),
            until=now,
        )
        if observation_time is None:
            return {"fetched": 0, "changed": False, "configured": True}

        observation_iso = observation_time.isoformat()
        if self._load_state().get("observation_time") == observation_iso:
            return {"fetched": 0, "changed": False, "configured": True}

        timestamp = observation_time.strftime("%Y%m%d%H%M%S")
        raw_path = self.raw_dir / f"gems_hcho_{timestamp}.nc"
        overlay_path = self.overlay_dir / f"gems_hcho_xuchang_{timestamp}.png"
        download = await self.client.download_data(
            product_type="hcho",
            observation_time=observation_time,
            destination=raw_path,
        )
        render = self.renderer.render_hcho(raw_path, overlay_path)
        image_id = f"gems_xuchang_hcho_{timestamp}"
        image = (self.image_cache or get_image_cache()).save(
            base64.b64encode(overlay_path.read_bytes()).decode("ascii"),
            chart_id=image_id,
        )
        product = {
            "Id": image_id,
            "Name": overlay_path.name,
            "product_type": "hcho",
            "source": "NIER GEMS Level-2 NetCDF",
            "ContentDate": {"Start": observation_iso, "End": observation_iso},
            "local_path": str(overlay_path),
            "raw_data_path": str(raw_path),
            "image": image,
            "geographic_bounds": render,
            "remote_name": download.get("remote_name"),
        }
        entry = self.registry.register_payload(
            schema="satellite_gems_catalogue",
            version="v1",
            payload={
                "source": "NIER GEMS Level-2 NetCDF",
                "region": "xuchang_surrounding_200km",
                "retrieved_at": now.isoformat(),
                "products": [product],
                "limitations": [
                    "GEMS HCHO 为柱浓度遥感产品，不能直接等同地面浓度。",
                    "覆盖层应与道路或地形底图叠加显示。",
                ],
            },
            metadata={"source": "NIER GEMS", "region": "xuchang", "product": "HCHO"},
        )
        self._save_state({"observation_time": observation_iso})
        return {
            "fetched": 1,
            "changed": True,
            "configured": True,
            "data_id": entry.data_id,
            "products": ["hcho"],
        }

    def _load_state(self) -> dict[str, str]:
        if not self.state_path.exists():
            return {}
        try:
            return dict(json.loads(self.state_path.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError):
            return {}

    def _save_state(self, state: dict[str, str]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
