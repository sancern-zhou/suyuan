"""Display-only cropper for official GEMS full-domain rendered PNG products."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class GemsImageExtent:
    west: float = 72.0
    south: float = 19.0
    east: float = 133.0
    north: float = 45.0
    plot_left: int = 187
    plot_top: int = 310
    plot_right: int = 1350
    plot_bottom: int = 889
    reference_width: int = 1500
    reference_height: int = 1300


class GemsOfficialImageCropper:
    """Crop the map plot region using the fixed geographic extent on NIER PNGs."""

    def __init__(
        self,
        *,
        west: float = 111.6,
        south: float = 32.2,
        east: float = 116.1,
        north: float = 35.9,
        source_extent: GemsImageExtent | None = None,
    ) -> None:
        self.west, self.south, self.east, self.north = west, south, east, north
        self.source_extent = source_extent or GemsImageExtent()

    def crop(self, source: Path, destination: Path) -> dict[str, float | str]:
        source_extent = self.source_extent
        with Image.open(source) as image:
            scale_x = image.width / source_extent.reference_width
            scale_y = image.height / source_extent.reference_height
            plot_left = source_extent.plot_left * scale_x
            plot_right = source_extent.plot_right * scale_x
            plot_top = source_extent.plot_top * scale_y
            plot_bottom = source_extent.plot_bottom * scale_y
            width, height = plot_right - plot_left, plot_bottom - plot_top
            left = plot_left + (self.west - source_extent.west) / (source_extent.east - source_extent.west) * width
            right = plot_left + (self.east - source_extent.west) / (source_extent.east - source_extent.west) * width
            top = plot_top + (source_extent.north - self.north) / (source_extent.north - source_extent.south) * height
            bottom = plot_top + (source_extent.north - self.south) / (source_extent.north - source_extent.south) * height
            crop = image.crop((round(left), round(top), round(right), round(bottom)))
            crop = crop.resize((768, 640), Image.Resampling.NEAREST)
            destination.parent.mkdir(parents=True, exist_ok=True)
            crop.save(destination, format="PNG")
        return {
            "crop_mode": "official_rendered_image_geographic_crop",
            "west": self.west,
            "south": self.south,
            "east": self.east,
            "north": self.north,
        }
