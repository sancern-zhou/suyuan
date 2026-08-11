"""Static map artifacts for Xuchang Scenario 2 transport analysis."""

from __future__ import annotations

import tempfile
from collections import defaultdict
from math import cos, radians, sin
from pathlib import Path
from typing import Any

from .spatial_analysis import ENTERPRISE_FILTERS, _haversine_km

HEIGHT_COLORS = ("#d95f02", "#1b9e77", "#5e4fa2")
CORRIDOR_COLOR = "#2b6cb0"


def _trajectory_groups(
    endpoints: list[dict[str, Any]],
) -> dict[tuple[int, int], list[dict[str, Any]]]:
    groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for endpoint in endpoints:
        key = (int(endpoint.get("batch_index", 0)), int(endpoint.get("trajectory_id", 1)))
        groups[key].append(endpoint)
    return groups


def _save_figure(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", dir=path.parent, delete=False) as handle:
        temp_path = Path(handle.name)
    fig.savefig(temp_path, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    temp_path.replace(path)


def _configure_map(
    ax: Any, lons: list[float], lats: list[float], *, ccrs: Any, cfeature: Any
) -> None:
    lon_span = max(lons) - min(lons) if lons else 1.0
    lat_span = max(lats) - min(lats) if lats else 1.0
    extent = [
        min(lons) - max(0.15, lon_span * 0.08),
        max(lons) + max(0.15, lon_span * 0.08),
        min(lats) - max(0.15, lat_span * 0.08),
        max(lats) + max(0.15, lat_span * 0.08),
    ]
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    # Match the existing backward-trajectory tool: an offline-safe light map
    # with cached Natural Earth boundaries, rather than runtime web tiles.
    ax.set_facecolor("#f4f6f2")
    ax.add_feature(
        cfeature.LAKES.with_scale("10m"),
        facecolor="#dcecf4",
        edgecolor="#76a9c2",
        linewidth=0.4,
        zorder=1,
    )
    ax.add_feature(
        cfeature.COASTLINE.with_scale("10m"), edgecolor="#536878", linewidth=0.65, zorder=1
    )
    ax.add_feature(
        cfeature.BORDERS.with_scale("10m"), edgecolor="#59636b", linewidth=0.55, zorder=1
    )
    ax.add_feature(
        cfeature.STATES.with_scale("10m"),
        edgecolor="#87929b",
        facecolor="none",
        linewidth=0.45,
        linestyle="--",
        zorder=1,
    )
    gridlines = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        linewidth=0.45,
        color="#718096",
        alpha=0.55,
        linestyle=":",
        zorder=1,
    )
    gridlines.top_labels = False
    gridlines.right_labels = False


def generate_transport_maps(
    *,
    output_dir: Path,
    job_id: str,
    endpoints: list[dict[str, Any]],
    corridors: list[dict[str, Any]],
    enterprise_screening: dict[str, Any],
    receptor_lat: float,
    receptor_lon: float,
    pollutant: str,
) -> list[dict[str, Any]]:
    """Write a regional trajectory map and a local enterprise coverage map."""
    import matplotlib

    matplotlib.use("Agg")
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    from app.utils.font_utils import apply_font_to_figure, configure_chinese_font

    configure_chinese_font()
    projection = ccrs.PlateCarree()

    if not endpoints:
        return []

    groups = _trajectory_groups(endpoints)
    height_order = sorted({key[1] for key in groups})
    trajectory_color = {
        trajectory_id: HEIGHT_COLORS[index % len(HEIGHT_COLORS)]
        for index, trajectory_id in enumerate(height_order)
    }
    height_labels = {}
    for trajectory_id in height_order:
        starts = [
            endpoint
            for endpoint in endpoints
            if int(endpoint.get("trajectory_id", 1)) == trajectory_id
            and abs(float(endpoint.get("age_hours", 0))) < 0.01
        ]
        start_height = (
            sum(float(item.get("height", 0)) for item in starts) / len(starts) if starts else 0
        )
        height_labels[trajectory_id] = f"{start_height:.0f}米起始高度"
    artifacts = []

    regional_path = output_dir / f"{job_id}.regional-paths.png"
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(1, 1, 1, projection=projection)
    all_lons = [float(item["lon"]) for item in endpoints] + [receptor_lon]
    all_lats = [float(item["lat"]) for item in endpoints] + [receptor_lat]
    _configure_map(ax, all_lons, all_lats, ccrs=ccrs, cfeature=cfeature)
    for key, points in sorted(groups.items()):
        ordered = sorted(points, key=lambda item: abs(float(item.get("age_hours", 0))))
        ax.plot(
            [float(item["lon"]) for item in ordered],
            [float(item["lat"]) for item in ordered],
            color=trajectory_color[key[1]],
            linewidth=1.4,
            alpha=0.68,
            zorder=2,
            transform=projection,
        )
    arrow_length = max(0.5, min(2.0, (max(all_lons) - min(all_lons)) * 0.22))
    for corridor in corridors[:4]:
        bearing = radians(float(corridor["mean_bearing_deg"]))
        dx = sin(bearing) * arrow_length
        dy = cos(bearing) * arrow_length
        ax.annotate(
            "",
            xy=(receptor_lon + dx, receptor_lat + dy),
            xytext=(receptor_lon, receptor_lat),
            arrowprops={
                "arrowstyle": "-|>",
                "color": CORRIDOR_COLOR,
                "linewidth": 3.0 + 4.0 * float(corridor["trajectory_share"]),
                "alpha": 0.4 + 0.45 * float(corridor["trajectory_share"]),
                "mutation_scale": 18,
            },
            zorder=3,
        )
        ax.text(
            receptor_lon + dx * 1.04,
            receptor_lat + dy * 1.04,
            f"{corridor['label']} {float(corridor['trajectory_share']) * 100:.0f}%",
            fontsize=9,
            color="#1a365d",
            ha="center",
            va="center",
            transform=projection,
        )
    ax.scatter(
        [receptor_lon],
        [receptor_lat],
        marker="*",
        s=260,
        color="#c53030",
        edgecolor="white",
        zorder=5,
        transform=projection,
    )
    ax.set_title(f"许昌市{pollutant}后向轨迹与输送走廊")
    ax.legend(
        handles=[
            Line2D(
                [0],
                [0],
                color=trajectory_color[trajectory_id],
                lw=2,
                label=height_labels[trajectory_id],
            )
            for trajectory_id in height_order[:3]
        ]
        + [
            Line2D([0], [0], color=CORRIDOR_COLOR, lw=5, alpha=0.5, label="主要输送走廊"),
            Line2D(
                [0],
                [0],
                marker="*",
                color="w",
                markerfacecolor="#c53030",
                markersize=13,
                label="异常受体站",
            ),
        ],
        loc="best",
        frameon=True,
    )
    fig.text(0.99, 0.01, "底图：Natural Earth / Cartopy", ha="right", fontsize=8, color="#667085")
    apply_font_to_figure(fig)
    fig.tight_layout()
    _save_figure(fig, regional_path)
    plt.close(fig)
    artifacts.append(
        {
            "type": "image",
            "role": "regional_trajectory_corridor_map",
            "path": regional_path,
            "title": "区域后向轨迹与输送走廊图",
        }
    )

    enterprises = enterprise_screening.get("enterprises", [])
    local_config = ENTERPRISE_FILTERS[pollutant]
    local_endpoints = [
        endpoint
        for endpoint in endpoints
        if float(endpoint.get("height", 0)) <= local_config["max_height_m"]
        and abs(float(endpoint.get("age_hours", 0))) <= local_config["max_age_hours"]
        and _haversine_km(
            receptor_lat, receptor_lon, float(endpoint["lat"]), float(endpoint["lon"])
        )
        <= 150.0
    ]
    local_path = output_dir / f"{job_id}.enterprise-coverage.png"
    fig = plt.figure(figsize=(10, 9))
    ax = fig.add_subplot(1, 1, 1, projection=projection)
    local_lons = [float(item["lon"]) for item in local_endpoints] + [receptor_lon]
    local_lats = [float(item["lat"]) for item in local_endpoints] + [receptor_lat]
    local_lons.extend(float(item["longitude"]) for item in enterprises)
    local_lats.extend(float(item["latitude"]) for item in enterprises)
    _configure_map(ax, local_lons, local_lats, ccrs=ccrs, cfeature=cfeature)
    local_groups = _trajectory_groups(local_endpoints)
    for key, points in sorted(local_groups.items()):
        ordered = sorted(points, key=lambda item: abs(float(item.get("age_hours", 0))))
        ax.plot(
            [float(item["lon"]) for item in ordered],
            [float(item["lat"]) for item in ordered],
            color=trajectory_color.get(key[1], HEIGHT_COLORS[0]),
            linewidth=1.8,
            alpha=0.72,
            zorder=2,
            transform=projection,
        )
    if enterprises:
        exact = [item for item in enterprises if item["pollutant_relevance"] == "exact_match"]
        precursor = [
            item for item in enterprises if item["pollutant_relevance"] == "precursor_match"
        ]
        other = [item for item in enterprises if item["pollutant_relevance"] == "no_recorded_match"]
        for items, color, label in (
            (exact, "#c53030", "许可证污染物匹配"),
            (precursor, "#dd6b20", "许可证前体物匹配"),
            (other, "#718096", "许可证未记录匹配污染物"),
        ):
            if items:
                ax.scatter(
                    [float(item["longitude"]) for item in items],
                    [float(item["latitude"]) for item in items],
                    marker="s",
                    s=45,
                    color=color,
                    edgecolor="white",
                    linewidth=0.7,
                    label=label,
                    zorder=4,
                    transform=projection,
                )
        for index, item in enumerate(enterprises[:15], 1):
            ax.annotate(
                str(index),
                (float(item["longitude"]), float(item["latitude"])),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=8,
                color="#1a202c",
            )
    ax.scatter(
        [receptor_lon],
        [receptor_lat],
        marker="*",
        s=260,
        color="#2b6cb0",
        edgecolor="white",
        label="异常受体站",
        zorder=5,
        transform=projection,
    )
    ax.set_title(
        f"许昌市{pollutant}近地层轨迹覆盖企业分布\n"
        f"回溯{local_config['max_age_hours']:.0f}小时 / 高度不超过{local_config['max_height_m']:.0f}米 / "
        f"筛查缓冲区{local_config['buffer_km']:.0f}公里"
    )
    ax.legend(loc="best", frameon=True)
    fig.text(0.99, 0.01, "底图：Natural Earth / Cartopy", ha="right", fontsize=8, color="#667085")
    apply_font_to_figure(fig)
    fig.tight_layout()
    _save_figure(fig, local_path)
    plt.close(fig)
    artifacts.append(
        {
            "type": "image",
            "role": "local_enterprise_coverage_map",
            "path": local_path,
            "title": "近地层轨迹覆盖企业分布图",
        }
    )
    return artifacts
