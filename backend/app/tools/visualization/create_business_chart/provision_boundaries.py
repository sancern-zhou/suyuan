"""全国地级市边界资产供给侧脚本（city_boundary_map 的离线数据来源）。

从 aliyun DataV GeoAtlas 逐省下载城市级边界，合并、简化并校验后落盘为
``assets/china_city_boundaries.geojson``。资产随仓库提交，运行时只读文件、
零网络——产品 ``execute_python`` 沙箱与离线部署环境均不依赖外网。

用法（backend 目录下执行）::

    python -m app.tools.visualization.create_business_chart.provision_boundaries
    python -m app.tools.visualization.create_business_chart.provision_boundaries \
        --from-cache <已下载 _full/json 文件目录>          # 离线重建
    python -m app.tools.visualization.create_business_chart.provision_boundaries \
        --out <输出路径> --cache-dir <原始文件缓存目录> --simplify-tolerance 0.002

口径说明：
- 27 个省/自治区用 ``{adcode}_full.json``（含省内全部地级市/省直辖县级单元）；
- 北京/天津/上海/重庆四个直辖市与港澳台用单域 ``{adcode}.json``——直辖市全市域
  记为一个城市单元，与空气质量数据的直辖市口径一致；
- 合并属性保留 DataV 的 ``adcode/name/center/centroid/level``，并追加
  ``province_adcode/province_name`` 供渲染器分组与调试。

校验门（任一不满足即非零退出）：34 个省级单位齐全、城市要素 ≥330、
JSON 可解析、文件 ≤3MB（超出则提高简化容差重试）。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# 用 _full.json 的省级单位（22 省 + 5 自治区，不含台湾）。
PROVINCE_FULL_CODES = [
    "130000", "140000", "150000", "210000", "220000", "230000", "320000",
    "330000", "340000", "350000", "360000", "370000", "410000", "420000",
    "430000", "440000", "450000", "460000", "510000", "520000", "530000",
    "540000", "610000", "620000", "630000", "640000", "650000",
]
# 用单域 {adcode}.json 的省级单位（直辖市全市 + 港澳台）。
SINGLE_BOUNDARY_CODES = ["110000", "120000", "310000", "500000", "710000", "810000", "820000"]
ALL_PROVINCE_CODES = PROVINCE_FULL_CODES + SINGLE_BOUNDARY_CODES

DATAV_BASE_URL = "https://geo.datav.aliyun.com/areas_v3/bound/{code}.json"
DATAV_FULL_URL = "https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json"
DOWNLOAD_TIMEOUT_SECONDS = 60

MIN_CITY_FEATURES = 330
MIN_PROVINCE_UNITS = len(ALL_PROVINCE_CODES)
MAX_ASSET_BYTES = 3 * 1024 * 1024

DEFAULT_ASSET_PATH = (
    Path(__file__).resolve().parent / "assets" / "china_city_boundaries.geojson"
)
DEFAULT_CACHE_DIR = (
    Path(__file__).resolve().parents[4] / "backend_data_registry" / "boundary_provision_cache"
)

MODULE_ROOT = Path(__file__).resolve().parents[3]  # .../backend/app


def _province_code_of(feature: dict, source_code: str) -> str:
    props = feature.get("properties") or {}
    parent = props.get("parent") or {}
    parent_adcode = str(parent.get("adcode") or "")
    if parent_adcode in ALL_PROVINCE_CODES:
        return parent_adcode
    acroutes = [str(x) for x in props.get("acroutes") or []]
    for code in reversed(acroutes):
        if code in ALL_PROVINCE_CODES:
            return code
    return source_code


def _load_raw_feature_file(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return [f for f in data.get("features", []) if isinstance(f, dict)]
    if isinstance(data, dict) and data.get("type") == "Feature":
        return [data]
    raise ValueError(f"无法识别的边界文件结构：{path}")


def fetch_raw_files(cache_dir: Path, from_cache: Path | None) -> dict[str, Path]:
    """返回 {省级adcode: 原始文件路径}；from_cache 提供时只做离线读取。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    for code in ALL_PROVINCE_CODES:
        name = f"{code}.json"
        target = cache_dir / name
        if from_cache is not None:
            source = from_cache / name
            if not source.exists():
                raise FileNotFoundError(f"缓存目录缺少 {source}")
            if not target.exists():
                target.write_bytes(source.read_bytes())
        elif not target.exists():
            template = DATAV_FULL_URL if code in PROVINCE_FULL_CODES else DATAV_BASE_URL
            url = template.format(code=code)
            print(f"download {url}")
            request = urllib.request.Request(url, headers={"User-Agent": "suyuan-provision/1.0"})
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                payload = response.read()
            if len(payload) < 1000:
                raise ValueError(f"{code} 响应过小（{len(payload)}B），疑似接口异常。")
            target.write_bytes(payload)
        else:
            print(f"cache-hit {target.name}")
        files[code] = target
    return files


def _dedupe_ring(ring: list, min_step: float = 0.0) -> list:
    """4 位小数取整 + 去相邻重复点；min_step>0 时对相邻点做最小步长抽稀（无 shapely 的降级简化）。

    闭合环收尾点与首点重复时去掉尾点（GeoJSON 允许显式闭合，不强制）。
    """
    deduped: list[list[float]] = []
    for point in ring:
        rounded = [round(float(point[0]), 4), round(float(point[1]), 4)]
        if deduped:
            previous = deduped[-1]
            distance = abs(rounded[0] - previous[0]) + abs(rounded[1] - previous[1])
            if distance < min_step and len(ring) > 2:
                continue
        if not deduped or rounded != deduped[-1]:
            deduped.append(rounded)
    if len(deduped) >= 2 and deduped[0] == deduped[-1]:
        deduped.pop()
    return deduped


def simplify_coordinates(coordinates, tolerance: float) -> list:
    """递归简化坐标：优先 shapely Douglas-Peucker，缺库时仅做 4 位小数取整。

    抽稀步长由 simplify_feature_geometry 在环级应用（shapely 路径的
    Douglas-Peucker 已含几何简化，环级 min_step 置 0 避免二次抽稀）。
    """
    try:
        from shapely.geometry import shape as shapely_shape
        from shapely.geometry import mapping as shapely_mapping
    except ImportError:
        shapely_shape = None

    def _clean(value):
        if value and isinstance(value[0], (int, float)):
            return [round(float(value[0]), 4), round(float(value[1]), 4)]
        return [_clean(item) for item in value]

    if shapely_shape is not None and tolerance > 0:
        geometry = shapely_shape({"type": "MultiPolygon", "coordinates": coordinates})
        simplified = geometry.simplify(tolerance, preserve_topology=True)
        return _clean(shapely_mapping(simplified)["coordinates"])
    return _clean(coordinates)


def simplify_feature_geometry(feature: dict, tolerance: float) -> dict | None:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates")
    if not coordinates:
        return None
    geometry_type = geometry.get("type")
    if geometry_type == "Polygon":
        polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        polygons = coordinates
    else:
        return None

    try:
        import shapely  # noqa: F401

        ring_min_step = 0.0  # shapely 可用时 D-P 已完成几何简化
    except ImportError:
        ring_min_step = tolerance  # 降级：环级最小步长抽稀

    simplified_polygons = []
    for polygon in simplify_coordinates(polygons, tolerance):
        rings = [_dedupe_ring(ring, ring_min_step) for ring in polygon]
        rings = [ring for ring in rings if len(ring) >= 4]
        if rings:
            simplified_polygons.append(rings)
    if not simplified_polygons:
        return None
    if len(simplified_polygons) == 1:
        return {"type": "Polygon", "coordinates": simplified_polygons[0]}
    return {"type": "MultiPolygon", "coordinates": simplified_polygons}


def build_feature_collection(
    raw_files: dict[str, Path], tolerance: float
) -> tuple[list[dict], list[str]]:
    features: list[dict] = []
    skipped: list[str] = []
    for code in ALL_PROVINCE_CODES:
        path = raw_files[code]
        for feature in _load_raw_feature_file(path):
            props = feature.get("properties") or {}
            name = str(props.get("name") or "")
            geometry = simplify_feature_geometry(feature, tolerance)
            if not name or geometry is None:
                skipped.append(f"{code}:{name or 'unnamed'}")
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "adcode": int(props.get("adcode") or 0),
                        "name": name,
                        "center": props.get("center"),
                        "centroid": props.get("centroid"),
                        "level": str(props.get("level") or "city"),
                        "province_adcode": int(_province_code_of(feature, code)),
                        "province_name": "",
                    },
                    "geometry": geometry,
                }
            )
    province_names = {
        int(code): str(
            (_load_raw_feature_file(raw_files[code])[0].get("properties") or {}).get("name") or code
        )
        for code in ALL_PROVINCE_CODES
    }
    for feature in features:
        code = feature["properties"]["province_adcode"]
        feature["properties"]["province_name"] = province_names.get(code, str(code))
    return features, skipped


def verify_asset(path: Path, features: list[dict]) -> None:
    problems: list[str] = []
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if parsed.get("type") != "FeatureCollection":
        problems.append("顶层不是 FeatureCollection")
    province_units = {f["properties"]["province_adcode"] for f in features}
    if len(province_units) < MIN_PROVINCE_UNITS:
        problems.append(f"省级单位不全：{len(province_units)}/{MIN_PROVINCE_UNITS}")
    if len(features) < MIN_CITY_FEATURES:
        problems.append(f"城市要素不足：{len(features)}/{MIN_CITY_FEATURES}")
    size = path.stat().st_size
    if size > MAX_ASSET_BYTES:
        problems.append(f"文件超限：{size}B > {MAX_ASSET_BYTES}B")
    if problems:
        raise ValueError("资产校验未通过：" + "；".join(problems))
    print(
        f"verify ok: {len(features)} features, {len(province_units)} province units, "
        f"{size / 1024:.0f} KB"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成全国地级市边界 GeoJSON 资产")
    parser.add_argument("--out", type=Path, default=DEFAULT_ASSET_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--from-cache", type=Path, default=None,
        help="离线重建：从该目录读取已下载的原始边界文件（{adcode}.json）",
    )
    parser.add_argument(
        "--simplify-tolerance", type=float, default=0.002,
        help="Douglas-Peucker 容差（度），0 表示仅坐标取整",
    )
    parser.add_argument(
        "--no-network", action="store_true",
        help="禁止网络下载，仅允许 --from-cache / 已有缓存文件",
    )
    args = parser.parse_args(argv)

    from_cache = args.from_cache
    if args.no_network and from_cache is None:
        parser.error("--no-network 需要配合 --from-cache 使用。")

    raw_files = fetch_raw_files(args.cache_dir, from_cache)
    tolerance = args.simplify_tolerance
    for attempt in range(3):
        features, skipped = build_feature_collection(raw_files, tolerance)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": features},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        size = args.out.stat().st_size
        print(f"built {args.out} tolerance={tolerance} size={size / 1024:.0f} KB")
        if size <= MAX_ASSET_BYTES:
            break
        tolerance = round(tolerance + 0.001, 4)
        print(f"资产超过 {MAX_ASSET_BYTES}B，提高容差重试：{tolerance}")
    if skipped:
        print(f"skipped {len(skipped)} features: {skipped[:10]}{'...' if len(skipped) > 10 else ''}")
    verify_asset(args.out, features)
    return 0


if __name__ == "__main__":
    sys.exit(main())
