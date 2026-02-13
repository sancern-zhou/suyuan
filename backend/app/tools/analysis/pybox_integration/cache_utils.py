"""
缓存键生成和管理工具

优化目标: 提升EKMA分析的缓存命中率从<5%到50-70%

核心策略:
1. 参数分bin + 组成指纹哈希
2. 场景预计算（城市/工业/农村典型场景）
3. 相似缓存插值（无精确匹配时）

分bin策略:
- VOCs总量: 每20ppb一档
- NOx浓度: 每10ppb一档
- 温度: 每5K一档
- 太阳角度: 每10°一档
- VOCs组成: 芳香烃/烷烃比例分类

参考: D:\溯源\backend\app\tools\analysis\pybox_integration\EKMA_优化方案.md
"""

import os
import json
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import structlog
import numpy as np

logger = structlog.get_logger()

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), "o3_surface_cache")


# ============================================================================
# 场景预计算配置
# ============================================================================

class EKMA_Scenes:
    """
    EKMA典型场景配置

    预计算3类典型场景，后续查询通过场景匹配+插值获取结果
    """

    # 典型场景定义
    SCENES = {
        "urban": {
            "name": "城市",
            "description": "典型城市环境，VOCs/NOx比值中等",
            "voc_total": 200,  # ppb
            "nox": 40,         # ppb
            "voc_profile": {   # 典型VOC谱 (RACM2物种)
                "ETH": 5.0,
                "HC3": 15.0,
                "HC5": 10.0,
                "HC8": 8.0,
                "OL2": 3.0,
                "OLI": 2.0,
                "TOL": 12.0,
                "XYL": 8.0,
                "ALD": 5.0,
                "KET": 4.0,
                "OLE": 3.0,
                "ISO": 4.0,
                "APIN": 2.0,
                "MEOH": 2.0,
                "HCHO": 4.0,
            },
            "voc_nox_ratio": 5.0,
            "aromatics_ratio": 0.35,
        },
        "industrial": {
            "name": "工业区",
            "description": "工业区域，高NOx排放，VOCs/NOx比值偏低",
            "voc_total": 250,
            "nox": 80,
            "voc_profile": {
                "ETH": 8.0,
                "HC3": 20.0,
                "HC5": 12.0,
                "HC8": 15.0,
                "OL2": 5.0,
                "OLI": 3.0,
                "TOL": 18.0,
                "XYL": 15.0,
                "ALD": 6.0,
                "KET": 8.0,
                "OLE": 5.0,
                "ISO": 3.0,
                "APIN": 2.0,
                "MEOH": 5.0,
                "HCHO": 6.0,
                "CH4": 60.0,
            },
            "voc_nox_ratio": 3.1,
            "aromatics_ratio": 0.45,
        },
        "rural": {
            "name": "农村",
            "description": "农村区域，生物源VOCs贡献大，VOCs/NOx比值偏高",
            "voc_total": 150,
            "nox": 15,
            "voc_profile": {
                "ETH": 3.0,
                "HC3": 8.0,
                "HC5": 12.0,
                "HC8": 6.0,
                "OL2": 2.0,
                "OLI": 4.0,
                "TOL": 5.0,
                "XYL": 3.0,
                "ALD": 3.0,
                "KET": 2.0,
                "OLE": 8.0,
                "ISO": 20.0,  # 异戊二烯（生物源）
                "APIN": 5.0,
                "MEOH": 1.0,
                "HCHO": 2.0,
            },
            "voc_nox_ratio": 10.0,
            "aromatics_ratio": 0.15,
        },
    }

    @classmethod
    def get_scene_key(cls, voc_total: float, nox: float) -> str:
        """
        根据VOC/NOx比值判断所属场景

        Args:
            voc_total: VOC总量 (ppb)
            nox: NOx浓度 (ppb)

        Returns:
            场景键: "urban" / "industrial" / "rural"
        """
        ratio = voc_total / (nox + 1e-9)

        if ratio < 4:
            return "industrial"
        elif ratio < 7:
            return "urban"
        else:
            return "rural"

    @classmethod
    def get_all_scene_keys(cls) -> List[str]:
        """获取所有预计算场景"""
        return list(cls.SCENES.keys())

    @classmethod
    def get_scene_profile(cls, scene_key: str) -> Dict[str, float]:
        """获取场景的VOC谱"""
        return cls.SCENES.get(scene_key, {}).get("voc_profile", {})


def generate_scene_cache_key(
    vocs_dict: Dict[str, float],
    nox: float,
    temperature: float = 298.15,
    pressure: float = 101325.0,
    solar_zenith_angle: float = 30.0
) -> str:
    """
    生成场景感知的缓存键（分箱 + 场景分类）

    策略:
    1. VOC总量每20ppb一档
    2. NOx每10ppb一档
    3. 温度每5K一档
    4. 太阳角度每10°一档
    5. 芳香烃占比分类 (low/mid/high)
    6. 压力分级

    Args:
        vocs_dict: VOCs物种浓度字典
        nox: NOx总浓度 (ppb)
        temperature: 温度 (K)
        pressure: 压力 (Pa)
        solar_zenith_angle: 太阳天顶角 (度)

    Returns:
        缓存键，格式: "scene_v{vocs_bin}_n{nox_bin}_t{...}_s{...}_c{...}_p{...}"
    """
    # 1. 计算VOC总量和场景
    total_vocs = sum(vocs_dict.values())
    scene = EKMA_Scenes.get_scene_key(total_vocs, nox)

    # 2. VOC总量分bin (每100ppb一档，适应VOC波动大的情况)
    # 场景：VOC在0-100→v0, 100-200→v100, 200-300→v200, 以此类推
    vocs_bin = int(total_vocs / 100) * 100

    # 3. NOx分bin (每50ppb一档，适应NOx波动)
    nox_bin = int(nox / 50) * 50

    # 4. 气象参数分bin
    temp_bin = int(temperature / 5) * 5
    sza_bin = int(solar_zenith_angle / 10) * 10

    # 5. 芳香烃占比分类
    aromatics = sum(v for k, v in vocs_dict.items()
                   if k.upper() in ['BENZ', 'TOL', 'XYL', 'CSL', 'PHEN', 'TOLP'])
    total_organic = total_vocs + 1e-9
    aromatics_ratio = aromatics / total_organic
    if aromatics_ratio < 0.25:
        aro_class = "L"  # Low
    elif aromatics_ratio < 0.45:
        aro_class = "M"  # Mid
    else:
        aro_class = "H"  # High

    # 6. 压力分级
    if 95000 < pressure < 105000:
        pressure_level = "std"
    elif pressure >= 105000:
        pressure_level = "low"
    else:
        pressure_level = "high"

    # 7. 构建缓存键（包含场景前缀）
    cache_key = f"{scene}_v{vocs_bin}_n{nox_bin}_t{temp_bin}_s{sza_bin}_c{aro_class}_p{pressure_level}"

    logger.debug(
        "scene_cache_key_generated",
        cache_key=cache_key,
        scene=scene,
        voc_nox_ratio=round(total_vocs / (nox + 1e-9), 2)
    )

    return cache_key


def generate_smart_cache_key(
    vocs_dict: Dict[str, float],
    nox: float,
    temperature: float = 298.15,
    pressure: float = 101325.0,
    solar_zenith_angle: float = 30.0
) -> str:
    """
    智能缓存键生成（兼容旧版本）

    统一调用新函数
    """
    return generate_scene_cache_key(vocs_dict, nox, temperature, pressure, solar_zenith_angle)


def estimate_cache_similarity(key1: str, key2: str) -> float:
    """
    估算两个缓存键的相似度 (0.0-1.0)

    用于缓存未命中时，推荐最相近的历史缓存

    Args:
        key1: 缓存键1 "v120_n30_t295_s30_c3_std"
        key2: 缓存键2 "v130_n30_t295_s30_c3_std"

    Returns:
        相似度分数 (0.0-1.0)
        1.0 = 完全相同
        0.8 = 5/6 组件匹配
        0.0 = 完全不同

    Example:
        >>> estimate_cache_similarity("v120_n30_t295_s30_c3_std", "v130_n30_t295_s30_c3_std")
        0.833  # 6个组件中5个匹配 (只有vocs不同)
    """
    if key1 == key2:
        return 1.0

    # 分割组件
    components1 = key1.split('_')
    components2 = key2.split('_')

    if len(components1) != len(components2):
        return 0.0

    # 计算匹配组件数
    matches = sum(c1 == c2 for c1, c2 in zip(components1, components2))
    similarity = matches / len(components1)

    return similarity


def find_most_similar_cache(
    target_key: str,
    cache_dir: str,
    min_similarity: float = 0.7
) -> Optional[Tuple[str, float]]:
    """
    在缓存目录中查找最相似的缓存文件

    Args:
        target_key: 目标缓存键
        cache_dir: 缓存目录路径
        min_similarity: 最小相似度阈值 (默认0.7)

    Returns:
        (最相似的缓存键, 相似度分数) 或 None

    Example:
        >>> find_most_similar_cache("v125_n32_t298_s32_c3_std", "o3_surface_cache/")
        ("v120_n30_t295_s30_c3_std", 0.83)
    """
    if not os.path.exists(cache_dir):
        return None

    best_match = None
    best_similarity = 0.0

    # 遍历缓存文件
    for filename in os.listdir(cache_dir):
        if not filename.endswith('.json'):
            continue

        # 提取缓存键 (文件名去掉.json后缀)
        cache_key = filename.replace('.json', '')

        # 计算相似度
        similarity = estimate_cache_similarity(target_key, cache_key)

        if similarity > best_similarity and similarity >= min_similarity:
            best_similarity = similarity
            best_match = cache_key

    if best_match:
        logger.info(
            "similar_cache_found",
            target_key=target_key,
            similar_key=best_match,
            similarity=round(best_similarity, 2)
        )
        return (best_match, best_similarity)

    return None


def clean_stale_cache(
    cache_dir: str,
    max_age_days: float = float('inf'),
    dry_run: bool = False
) -> Dict[str, any]:
    """
    清理超过指定天数的旧缓存文件

    Args:
        cache_dir: 缓存目录路径
        max_age_days: 最大保留天数 (默认float('inf')=永不清理)
        dry_run: 是否仅模拟运行 (不实际删除)

    Returns:
        清理统计信息
        {
            "total_files": 150,
            "stale_files": 0,
            "deleted_files": 0,
            "freed_bytes": 0,
            "dry_run": False,
            "note": "缓存永不清理，所有历史缓存保留"
        }

    Example:
        >>> clean_stale_cache("o3_surface_cache/", max_age_days=30)
        {"total_files": 150, "stale_files": 0, "deleted_files": 0, ...}
    """
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
        return {
            "total_files": 0,
            "stale_files": 0,
            "deleted_files": 0,
            "freed_bytes": 0,
            "dry_run": dry_run,
            "note": "缓存永不清理，所有历史缓存保留"
        }

    # 统计缓存文件数量，但不清理任何文件
    total_files = len([f for f in os.listdir(cache_dir) if f.endswith('.json')])
    stale_files = 0
    deleted_files = 0
    freed_bytes = 0

    result = {
        "total_files": total_files,
        "stale_files": stale_files,
        "deleted_files": deleted_files,
        "freed_bytes": freed_bytes,
        "freed_mb": 0,
        "dry_run": dry_run,
        "note": "缓存永不清理，所有历史缓存保留"
    }

    logger.info(
        "cache_cleanup_completed",
        **result
    )

    return result


def get_cache_statistics(cache_dir: str) -> Dict[str, any]:
    """
    获取缓存目录统计信息

    Args:
        cache_dir: 缓存目录路径

    Returns:
        统计信息
        {
            "total_files": 150,
            "total_size_mb": 45.6,
            "oldest_file": "2024-07-15",
            "newest_file": "2026-01-11",
            "avg_file_size_kb": 304.5
        }
    """
    if not os.path.exists(cache_dir):
        return {
            "total_files": 0,
            "total_size_mb": 0,
            "oldest_file": None,
            "newest_file": None,
            "avg_file_size_kb": 0
        }

    total_files = 0
    total_size = 0
    oldest_time = None
    newest_time = None

    for filename in os.listdir(cache_dir):
        filepath = os.path.join(cache_dir, filename)

        if not os.path.isfile(filepath):
            continue

        total_files += 1
        total_size += os.path.getsize(filepath)

        file_time = datetime.fromtimestamp(os.path.getmtime(filepath))

        if oldest_time is None or file_time < oldest_time:
            oldest_time = file_time

        if newest_time is None or file_time > newest_time:
            newest_time = file_time

    return {
        "total_files": total_files,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "oldest_file": oldest_time.strftime("%Y-%m-%d") if oldest_time else None,
        "newest_file": newest_time.strftime("%Y-%m-%d") if newest_time else None,
        "avg_file_size_kb": round(total_size / (1024 * total_files), 1) if total_files > 0 else 0
    }


# ============================================================================
# 相似缓存插值功能
# ============================================================================

def interpolate_from_similar_cache(
    target_key: str,
    voc_factors: List[float],
    nox_factors: List[float],
    cache_dir: str = CACHE_DIR,
    min_similarity: float = 0.6
) -> Optional[np.ndarray]:
    """
    从相似缓存插值获取O3曲面

    当精确匹配失败时，查找最相似的缓存并进行插值

    Args:
        target_key: 目标缓存键
        voc_factors: VOC因子列表
        nox_factors: NOx因子列表
        cache_dir: 缓存目录
        min_similarity: 最小相似度阈值

    Returns:
        插值后的O3曲面矩阵，或None（无可用缓存）
    """
    from scipy.interpolate import RegularGridInterpolator

    # 查找最相似的缓存
    similar = find_most_similar_cache(target_key, cache_dir, min_similarity)
    if similar is None:
        logger.warning("no_similar_cache_found", target_key=target_key)
        return None

    cache_key, similarity = similar
    cache_path = os.path.join(cache_dir, f"{cache_key}.json")

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        cached_surface = np.array(cache_data["o3_surface"])
        cached_voc_axis = np.array(cache_data.get("voc_axis", cache_data.get("voc_factors", [])))
        cached_nox_axis = np.array(cache_data.get("nox_axis", cache_data.get("nox_factors", [])))

        if len(cached_voc_axis) == 0 or len(cached_nox_axis) == 0:
            logger.warning("cached_axis_empty", cache_key=cache_key)
            return None

        # 创建插值器
        interpolator = RegularGridInterpolator(
            (cached_voc_axis, cached_nox_axis),
            cached_surface,
            method='linear',
            bounds_error=False,
            fill_value=np.nan
        )

        # 插值到目标网格
        voc_mesh, nox_mesh = np.meshgrid(voc_factors, nox_factors, indexing='ij')
        query_points = np.column_stack([voc_mesh.ravel(), nox_mesh.ravel()])

        result = interpolator(query_points)
        result = result.reshape(len(voc_factors), len(nox_factors))

        logger.info(
            "interpolated_from_similar_cache",
            target_key=target_key,
            similar_key=cache_key,
            similarity=round(similarity, 2),
            method="linear_interpolation"
        )

        return result

    except Exception as e:
        logger.error("interpolation_failed", error=str(e), cache_key=cache_key)
        return None


def load_cached_surface(cache_key: str, cache_dir: str = CACHE_DIR) -> Optional[Dict[str, Any]]:
    """
    加载指定缓存键的O3曲面数据

    Args:
        cache_key: 缓存键
        cache_dir: 缓存目录

    Returns:
        缓存数据字典，或None（不存在）
    """
    cache_path = os.path.join(cache_dir, f"{cache_key}.json")

    if not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error("cache_load_failed", error=str(e), cache_key=cache_key)
        return None


def save_surface_to_cache(
    cache_key: str,
    o3_surface: np.ndarray,
    voc_axis: List[float],
    nox_axis: List[float],
    base_vocs: Dict[str, float],
    base_nox: float,
    voc_range: Tuple[float, float],
    nox_range: Tuple[float, float],
    cache_dir: str = CACHE_DIR
) -> bool:
    """
    保存O3曲面到缓存

    Args:
        cache_key: 缓存键
        o3_surface: O3曲面矩阵
        voc_axis: VOC轴
        nox_axis: NOx轴
        base_vocs: 基准VOC浓度
        base_nox: 基准NOx浓度
        voc_range: VOC范围
        nox_range: NOx范围
        cache_dir: 缓存目录

    Returns:
        是否成功
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{cache_key}.json")

    try:
        cache_data = {
            "cache_key": cache_key,
            "created_at": datetime.now().isoformat(),
            "voc_range": list(voc_range),
            "nox_range": list(nox_range),
            "voc_axis": list(voc_axis),
            "nox_axis": list(nox_axis),
            "base_vocs": base_vocs,
            "base_nox": base_nox,
            "o3_surface": o3_surface.tolist()
        }

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        logger.info("surface_cached", cache_key=cache_key, path=cache_path)
        return True

    except Exception as e:
        logger.error("cache_save_failed", error=str(e), cache_key=cache_key)
        return False


# ============================================================================
# 场景预计算
# ============================================================================

def precompute_all_scenes(
    pybox_adapter,
    scenes: List[str] = None,
    grid_size: int = 21,
    simulation_time: float = 25200.0,
    temperature: float = 298.15,
    pressure: float = 101325.0,
    solar_zenith_angle: float = 30.0,
    progress_callback: callable = None
) -> Dict[str, Dict[str, Any]]:
    """
    预计算所有典型场景的O3曲面

    Args:
        pybox_adapter: PyBox适配器
        scenes: 场景列表，默认所有场景
        grid_size: 网格大小
        simulation_time: 模拟时长
        temperature: 温度
        pressure: 压力
        solar_zenith_angle: 太阳天顶角
        progress_callback: 进度回调

    Returns:
        各场景的缓存结果
    """
    from .precomputed_surface import O3SurfacePrecomputer

    if scenes is None:
        scenes = EKMA_Scenes.get_all_scene_keys()

    results = {}
    total = len(scenes)

    for i, scene_key in enumerate(scenes):
        scene = EKMA_Scenes.SCENES.get(scene_key, {})
        voc_profile = scene.get("voc_profile", {})

        if not voc_profile:
            logger.warning("empty_voc_profile", scene_key=scene_key)
            continue

        logger.info(
            "precomputing_scene",
            scene_key=scene_key,
            scene_name=scene.get("name", ""),
            progress=f"{i+1}/{total}"
        )

        # 生成缓存键
        cache_key = generate_scene_cache_key(
            vocs_dict=voc_profile,
            nox=scene.get("nox", 40),
            temperature=temperature,
            pressure=pressure,
            solar_zenith_angle=solar_zenith_angle
        )

        # 计算范围
        voc_total = sum(voc_profile.values())
        voc_range = (0.0, voc_total * 2.0)
        nox_range = (0.0, scene.get("nox", 40) * 2.0)

        # 检查是否已有缓存
        existing = load_cached_surface(cache_key)
        if existing is not None:
            logger.info("scene_cache_exists", scene_key=scene_key, cache_key=cache_key)
            results[scene_key] = {"status": "cached", "cache_key": cache_key}
            continue

        # 计算完整ODE网格
        precomputer = O3SurfacePrecomputer(cache_key=cache_key)
        o3_surface = precomputer.compute_full_grid(
            pybox_adapter=pybox_adapter,
            base_vocs=voc_profile,
            base_nox=scene.get("nox", 40),
            voc_range=voc_range,
            nox_range=nox_range,
            grid_size=grid_size,
            simulation_time=simulation_time,
            temperature=temperature,
            pressure=pressure,
            solar_zenith_angle=solar_zenith_angle,
            progress_callback=progress_callback
        )

        results[scene_key] = {
            "status": "computed",
            "cache_key": cache_key,
            "max_o3": float(np.max(o3_surface)),
            "voc_range": voc_range,
            "nox_range": nox_range
        }

        if progress_callback:
            progress_callback(i + 1, total, f"场景 {scene_key}")

    logger.info("all_scenes_precomputed", results_summary={k: v["status"] for k, v in results.items()})
    return results
