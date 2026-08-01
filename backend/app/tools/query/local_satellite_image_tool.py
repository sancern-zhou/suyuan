"""Read locally cached satellite images from DataRegistry catalogues."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.data_registry import DataRegistryService, data_registry
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import file_products
from app.tools.resource_refs import build_data_ref, build_file_ref, build_url_ref, build_visual_ref


class LocalSatelliteImageTool(LLMTool):
    """Base class for query-only tools that expose downloaded satellite images."""

    schema_name: str
    source_name: str
    default_title: str

    def __init__(self, *, name: str, description: str, schema_name: str, source_name: str) -> None:
        self.schema_name = schema_name
        self.source_name = source_name
        self.default_title = source_name
        super().__init__(
            name=name,
            description=description,
            category=ToolCategory.QUERY,
            function_schema={
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data_id": {
                            "type": "string",
                            "description": "可选：DataRegistry 中的卫星目录 data_id；不填时读取最新目录。",
                        },
                        "product_type": {
                            "type": "string",
                            "description": "可选：产品类型，例如 hcho、no2、so2、o3。",
                        },
                        "start_time": {
                            "type": "string",
                            "description": "可选：ISO 8601 起始观测时间。",
                        },
                        "end_time": {
                            "type": "string",
                            "description": "可选：ISO 8601 结束观测时间。",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 20,
                            "default": 1,
                            "description": "返回图片数量，默认最新一张。",
                        },
                    },
                    "required": [],
                },
            },
            version="1.0.0",
            requires_context=False,
        )
        self.registry: DataRegistryService = data_registry

    async def execute(
        self,
        data_id: str | None = None,
        product_type: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            start = self._parse_time(start_time)
            end = self._parse_time(end_time)
        except ValueError as exc:
            return self._failure(str(exc))
        if start and end and start > end:
            return self._failure("start_time 不能晚于 end_time")

        entries = self._find_entries(data_id)
        if not entries:
            return self._failure(
                f"未找到已下载的 {self.source_name} 数据",
                suggestion="请先运行对应的卫星数据抓取任务，再调用此工具。",
            )

        images: list[dict[str, Any]] = []
        for entry in entries:
            payload = self.registry.load_dataset(entry.data_id)
            if not isinstance(payload, dict):
                continue
            for product in payload.get("products", []):
                image = self._to_image(product, entry.data_id)
                if not image or not self._matches(image, product_type, start, end):
                    continue
                images.append(image)

        images.sort(key=lambda image: image["observation_time"], reverse=True)
        images = images[: max(1, min(int(limit), 20))]
        if not images:
            return self._failure(
                f"没有符合筛选条件的 {self.source_name} 图片",
                suggestion="调整 product_type 或时间范围，或先确认抓取任务已生成图片。",
            )

        visuals = [
            {
                "id": image["image_id"],
                "type": "image",
                "title": image["title"],
                "image_url": image["image_url"],
                "local_path": image["local_path"],
                "markdown_image": f"![{image['title']}]({image['image_url']})" if image["image_url"] else None,
            }
            for image in images
        ]
        refs = {
            "data": [build_data_ref(image["data_id"], usage="source") for image in images],
            "files": [
                build_file_ref(image["local_path"], type="image", format="png", usage="display")
                for image in images
            ],
            "visuals": [
                build_visual_ref(
                    id=image["image_id"],
                    type="image",
                    title=image["title"],
                    image_url=image["image_url"],
                    local_path=image["local_path"],
                )
                for image in images
            ],
        }
        urls = [
            build_url_ref(image["image_url"], usage="display", source="image_cache")
            for image in images
            if image["image_url"]
        ]
        if urls:
            refs["urls"] = urls
        return {
            "success": True,
            "status": "success",
            "data": {"source": self.source_name, "images": images, "count": len(images)},
            "visuals": visuals,
            "resources": file_products(
                [image["local_path"] for image in images],
                tool_name=self.name,
            ),
            "refs": refs,
            "llm_resume": {
                "source_data_ids": list(dict.fromkeys(image["data_id"] for image in images)),
                "tool_hint": f"Use {self.name} with a product_type or time range to retrieve another local satellite image.",
            },
            "metadata": {"generator": self.name, "schema": self.schema_name},
            "summary": f"已获取 {len(images)} 张{self.source_name}本地遥感图片。",
        }

    def _find_entries(self, data_id: str | None):
        if data_id:
            entry = self.registry.get_metadata(data_id)
            return [entry] if entry and entry.schema == self.schema_name else []
        return self.registry.list_metadata(schema=self.schema_name)

    def _to_image(self, product: Any, data_id: str) -> dict[str, Any] | None:
        if not isinstance(product, dict):
            return None
        cached = product.get("image") if isinstance(product.get("image"), dict) else {}
        local_path = cached.get("local_path") or product.get("local_path")
        if not local_path or not Path(str(local_path)).is_file():
            reduced = product.get("reduced_assets") if isinstance(product.get("reduced_assets"), dict) else {}
            local_path = reduced.get("map_path")
        if not local_path or not Path(str(local_path)).is_file():
            return None
        content_date = product.get("ContentDate") if isinstance(product.get("ContentDate"), dict) else {}
        observation_time = str(content_date.get("Start") or "")
        if not observation_time:
            return None
        product_type = str(product.get("product_type") or "unknown").lower()
        image_id = str(cached.get("image_id") or product.get("Id") or Path(str(local_path)).stem)
        return {
            "data_id": data_id,
            "image_id": image_id,
            "image_url": cached.get("url"),
            "local_path": str(local_path),
            "observation_time": observation_time,
            "product_type": product_type,
            "title": f"{self.default_title} {product_type.upper()} {observation_time}",
            "source": product.get("source") or self.source_name,
            "observation_summary": product.get("observation_summary"),
            "geographic_bounds": product.get("geographic_bounds"),
        }

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("时间必须为 ISO 8601 格式") from exc

    @staticmethod
    def _matches(
        image: dict[str, Any], product_type: str | None, start: datetime | None, end: datetime | None
    ) -> bool:
        if product_type and image["product_type"] != product_type.lower():
            return False
        timestamp = datetime.fromisoformat(image["observation_time"].replace("Z", "+00:00"))
        return (start is None or timestamp >= start) and (end is None or timestamp <= end)

    def _failure(self, error: str, suggestion: str | None = None) -> dict[str, Any]:
        result = {
            "success": False,
            "status": "not_found",
            "error": error,
            "data": {"source": self.source_name, "images": [], "count": 0},
            "metadata": {"generator": self.name, "schema": self.schema_name},
            "summary": error,
        }
        if suggestion:
            result["suggestion"] = suggestion
        return result
