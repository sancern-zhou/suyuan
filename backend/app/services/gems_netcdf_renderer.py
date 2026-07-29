"""Crop GEMS Level-2 NetCDF products into transparent local map overlays."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


@dataclass(frozen=True)
class GeographicBounds:
    west: float = 111.6
    south: float = 32.2
    east: float = 116.1
    north: float = 35.9


class GemsNetcdfRenderer:
    """Render a cropped GEMS grid while retaining geographic placement metadata."""

    def __init__(self, bounds: GeographicBounds | None = None) -> None:
        self.bounds = bounds or GeographicBounds()

    def render_hcho(self, source: Path, destination: Path) -> dict[str, float | int | str]:
        with xr.open_dataset(source, mask_and_scale=True) as dataset:
            latitude = self._coordinate(dataset, "lat")
            longitude = self._coordinate(dataset, "lon")
            value_name, values = self._hcho_values(dataset, latitude.shape)

            lat_values = np.asarray(latitude.values, dtype=float)
            lon_values = np.asarray(longitude.values, dtype=float)
            data_values = np.asarray(values.values, dtype=float)

        bounds = self.bounds
        mask = (
            np.isfinite(lat_values)
            & np.isfinite(lon_values)
            & np.isfinite(data_values)
            & (lon_values >= bounds.west)
            & (lon_values <= bounds.east)
            & (lat_values >= bounds.south)
            & (lat_values <= bounds.north)
        )
        if not np.any(mask):
            raise ValueError("No valid GEMS pixels intersect the configured Xuchang bounds")

        selected = data_values[mask]
        vmin, vmax = np.nanpercentile(selected, (2, 98))
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
            vmin, vmax = float(np.nanmin(selected)), float(np.nanmax(selected))
        if vmin == vmax:
            vmax = vmin + 1.0

        destination.parent.mkdir(parents=True, exist_ok=True)
        figure, axis = plt.subplots(figsize=(8, 6), dpi=160)
        figure.patch.set_alpha(0)
        axis.set_facecolor("none")
        points = axis.scatter(
            lon_values[mask],
            lat_values[mask],
            c=selected,
            s=18,
            cmap="turbo",
            vmin=vmin,
            vmax=vmax,
            marker="s",
            linewidths=0,
        )
        axis.set_xlim(bounds.west, bounds.east)
        axis.set_ylim(bounds.south, bounds.north)
        axis.set_axis_off()
        figure.subplots_adjust(left=0, right=1, bottom=0, top=1)
        figure.savefig(destination, transparent=True, bbox_inches="tight", pad_inches=0)
        plt.close(figure)

        return {
            "value_variable": value_name,
            "pixel_count": int(mask.sum()),
            "west": bounds.west,
            "south": bounds.south,
            "east": bounds.east,
            "north": bounds.north,
            "vmin": float(vmin),
            "vmax": float(vmax),
        }

    @staticmethod
    def _coordinate(dataset: xr.Dataset, token: str) -> xr.DataArray:
        candidates = [
            variable
            for name, variable in dataset.variables.items()
            if token in name.lower() and variable.ndim >= 2
        ]
        if not candidates:
            raise ValueError(f"GEMS NetCDF does not contain a two-dimensional {token} coordinate")
        return candidates[0]

    @staticmethod
    def _hcho_values(dataset: xr.Dataset, shape: tuple[int, ...]) -> tuple[str, xr.DataArray]:
        candidates = [
            (name, variable)
            for name, variable in dataset.data_vars.items()
            if "hcho" in name.lower() and variable.shape == shape and np.issubdtype(variable.dtype, np.number)
        ]
        if not candidates:
            raise ValueError("GEMS NetCDF does not contain a two-dimensional numeric HCHO field")
        return candidates[0]
