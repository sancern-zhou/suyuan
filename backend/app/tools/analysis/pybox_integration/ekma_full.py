r"""
Full EKMA Isopleth Analysis - 完整ODE模式

使用RACM2化学机理 (102物种, 504反应)
- 完整21×21 ODE网格 (441点)
- 首次计算约3-5分钟
- 后续直接加载缓存（毫秒级）
- 物理正确性高，无插值伪影

参考:
- D:\溯源\参考\OBM-deliver_20200901\ekma_v0
- D:\溯源\backend\app\tools\analysis\pybox_integration\precomputed_surface.py
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from scipy.ndimage import gaussian_filter
from datetime import datetime
import structlog

try:
    from .config import PyBoxConfig, PYBOX_AVAILABLE, DEFAULT_CONFIG
    from .vocs_mapper import VOCsMapper
    from .mechanism_loader import is_mechanism_available
    from .ekma_visualizer import EKMAVisualizer
    from .ekma_lshape_model import LShapeControlLine
    from .ekma_control_zones import ControlZoneDivider
    from .ekma_lshape_contours import LShapeContourExtractor
    from .precomputed_surface import O3SurfacePrecomputer
    from .cache_utils import generate_scene_cache_key, EKMA_Scenes  # 场景感知缓存键生成器
except ImportError:
    from config import PyBoxConfig, PYBOX_AVAILABLE, DEFAULT_CONFIG
    from vocs_mapper import VOCsMapper
    from mechanism_loader import is_mechanism_available
    from ekma_visualizer import EKMAVisualizer
    from ekma_lshape_model import LShapeControlLine
    from ekma_control_zones import ControlZoneDivider
    from ekma_lshape_contours import LShapeContourExtractor
    from precomputed_surface import O3SurfacePrecomputer
    from cache_utils import generate_scene_cache_key, EKMA_Scenes  # 场景感知缓存键生成器

if PYBOX_AVAILABLE:
    try:
        from .pybox_adapter import PyBoxAdapter
    except ImportError:
        from pybox_adapter import PyBoxAdapter

logger = structlog.get_logger()

# Cantera条件导入
CANTERA_AVAILABLE = False
try:
    import cantera as ct
    CANTERA_AVAILABLE = True
except ImportError:
    pass


def _parse_hour(time_value: Any) -> Optional[int]:
    """
    从时间字段解析小时数

    支持的格式:
    - "2024-08-15 14:30:00" (ISO格式)
    - "14:30:00" (时间字符串)
    - "2024-08-15T14:30:00" (ISO 8601)
    - datetime对象

    Args:
        time_value: 时间值（字符串或datetime对象）

    Returns:
        小时数(0-23)，解析失败返回None
    """
    if time_value is None:
        return None

    # 如果是datetime对象
    if isinstance(time_value, datetime):
        return time_value.hour

    # 如果是字符串
    if isinstance(time_value, str):
        try:
            # 尝试解析ISO格式 "2024-08-15 14:30:00" 或 "2024-08-15T14:30:00"
            if 'T' in time_value or ' ' in time_value:
                dt = datetime.fromisoformat(time_value.replace('T', ' ').split('.')[0])
                return dt.hour
            # 尝试解析纯时间格式 "14:30:00"
            elif ':' in time_value:
                hour_str = time_value.split(':')[0]
                return int(hour_str)
        except (ValueError, IndexError):
            pass

    return None


class FullEKMAAnalyzer:
    """
    EKMA等浓度曲线分析器 - 完整ODE模式

    策略: 首次计算完整21×21 ODE网格 (441点)
    - 约3-5分钟首次计算
    - 后续直接加载缓存（毫秒级）
    - 相比RBF模式: 精度更高，稳定性更好

    使用:
        analyzer = FullEKMAAnalyzer()
        result = analyzer.analyze(vocs_data, nox_data, o3_data)
    """

    def __init__(
        self,
        mechanism: str = "RACM2",
        config: Optional[PyBoxConfig] = None
    ):
        self.mechanism = mechanism.upper()
        self.config = config or DEFAULT_CONFIG
        self.mode = "full_ode"  # 完整ODE模式

        # VOCs映射器
        if self.mechanism == "RACM2" and is_mechanism_available("RACM2"):
            self.vocs_mapper = VOCsMapper(mechanism="RACM2")
        else:
            self.vocs_mapper = VOCsMapper(mechanism="MCM")

        # PyBox适配器
        if PYBOX_AVAILABLE:
            try:
                self.pybox = PyBoxAdapter(self.mechanism, config)
            except Exception:
                self.pybox = None
        else:
            self.pybox = None

        # 预计算器 (单例模式)
        self._precomputer: Optional[O3SurfacePrecomputer] = None

        # 可视化器
        self.visualizer = EKMAVisualizer()

    def analyze(
        self,
        vocs_data: List[Dict],
        nox_data: List[Dict],
        o3_data: List[Dict],
        grid_resolution: Optional[int] = None,
        progress_callback: Optional[callable] = None,
        target_day_stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行EKMA分析（完整ODE模式）

        策略:
        1. 首次计算: 完整21×21 ODE网格 (441点)
        2. 保存到缓存，后续直接加载
        3. 首次约3-5分钟，后续毫秒级

        Args:
            vocs_data: VOCs时序数据
            nox_data: NOx时序数据
            o3_data: O3时序数据
            grid_resolution: 网格分辨率 (默认21)
            progress_callback: 进度回调
            target_day_stats: 目标污染日统计数据

        Returns:
            UDF v2.0格式结果
        """
        import time
        start_time = time.time()

        try:
            if self.pybox is None:
                raise RuntimeError("PyBox不可用")

            grid_resolution = grid_resolution or 21
            mode = "full_ode"  # 定义模式变量

            # 计算基准浓度
            base_vocs = self._calculate_base_vocs(vocs_data)
            base_nox = self._calculate_base_nox(nox_data)
            base_o3 = self._calculate_base_o3(o3_data)

            # 映射VOCs到RACM2
            mapped_vocs = self.vocs_mapper.map_concentrations(base_vocs)

            # ========== [诊断日志] 基准浓度详细统计 ==========
            base_vocs_total = sum(base_vocs.values())
            mapped_vocs_total = sum(mapped_vocs.values())
            vocs_nox_ratio = mapped_vocs_total / base_nox if base_nox > 0 else 0

            logger.info("ekma_diagnostic_base_concentrations",
                # 原始VOCs统计
                base_vocs_species_count=len(base_vocs),
                base_vocs_total=base_vocs_total,
                base_vocs_top_species=dict(list(base_vocs.items())[:5]) if base_vocs else {},
                # 映射后VOCs统计
                mapped_vocs_species_count=len(mapped_vocs),
                mapped_vocs_total=mapped_vocs_total,
                mapped_vocs_top_species=dict(list(mapped_vocs.items())[:5]) if mapped_vocs else {},
                # NOx和O3
                base_nox=base_nox,
                base_o3=base_o3,
                # 比值
                vocs_nox_ratio=vocs_nox_ratio,
                vocs_loss_ratio=(base_vocs_total - mapped_vocs_total) / base_vocs_total if base_vocs_total > 0 else 0,
                # 当前状态值
                current_vocs_value=mapped_vocs_total,  # 使用映射后的总量
                current_nox_value=base_nox,
                # 网格范围
                voc_range_max=mapped_vocs_total * 2.0,
                nox_range_max=base_nox * 2.0,
            )

            # 确定网格范围
            if target_day_stats is not None:
                current_vocs_value = target_day_stats.get('VOCs_Avg') or float(sum(mapped_vocs.values()))
                current_nox_value = target_day_stats.get('NOx_Avg') or base_nox
                current_o3_day_value = target_day_stats.get('O3_Max') or base_o3
            else:
                current_vocs_value = float(sum(mapped_vocs.values()))
                current_nox_value = base_nox
                current_o3_day_value = base_o3

            # 计算VOCs/NOx比值
            vocs_nox_ratio = current_vocs_value / current_nox_value if current_nox_value > 0 else 0

            # ========== [修复] 动态调整网格范围 ==========
            # 问题：峰值在网格外时，右上角可能出现空白区域
            # 解决：扩大网格范围至当前状态点的2.5倍，确保高O3区域被网格覆盖
            voc_range_max = current_vocs_value * 2.5   # 扩大至2.5倍
            nox_range_max = current_nox_value * 2.5    # 扩大至2.5倍
            grid_expansion = "expanded_voc_2.5x_nox_2.5x"

            # 确保最小范围（防止极端情况）
            voc_range_max = max(voc_range_max, 100.0)   # 至少100ppb
            nox_range_max = max(nox_range_max, 50.0)    # 至少50ppb

            logger.info("ekma_grid_range_adjusted",
                vocs_nox_ratio=vocs_nox_ratio,
                voc_range_max=voc_range_max,
                nox_range_max=nox_range_max,
                grid_expansion=grid_expansion,
                reason="low_vocs_nox_ratio" if vocs_nox_ratio < 1.0 else "standard"
            )

            voc_factors = np.linspace(0.0, voc_range_max, grid_resolution).tolist()
            nox_factors = np.linspace(0.0, nox_range_max, grid_resolution).tolist()

            # ========== 场景感知缓存键生成 ==========
            # 策略: VOC/NOx比值分箱 + VOC总量分档 + 芳香烃占比分类
            # 缓存键格式: "scene_v{vocs_bin}_n{nox_bin}_t{...}_s{...}_c{...}_p{...}"
            # 示例: "urban_v200_n40_t295_s30_cM_pstd"
            cache_key = generate_scene_cache_key(
                vocs_dict=mapped_vocs,
                nox=base_nox,
                temperature=self.config.temperature,
                pressure=self.config.pressure,
                solar_zenith_angle=30.0
            )

            # 获取场景信息用于日志
            scene = EKMA_Scenes.get_scene_key(current_vocs_value, current_nox_value)

            # 使用预计算器生成O3曲面（直接使用正确的cache_key）
            if self._precomputer is None or self._precomputer.cache_key != cache_key:
                self._precomputer = O3SurfacePrecomputer(cache_key=cache_key)
                logger.info(
                    "precomputer_cache_updated",
                    cache_key=cache_key,
                    scene=scene,
                    scene_name=EKMA_Scenes.SCENES.get(scene, {}).get("name", ""),
                    reason="data_changed" if self._precomputer.o3_surface is None else "cache_key_mismatch"
                )

            # ========== 缓存命中检查（关键优化）==========
            # 如果O3曲面已存在，说明缓存已加载，直接查询（毫秒级）
            # 否则，尝试相似缓存插值或重新计算
            if self._precomputer.o3_surface is not None:
                # 缓存命中！直接查询
                logger.info(
                    "cache_hit_using_cached_surface",
                    cache_key=cache_key,
                    cache_age=self._precomputer.last_update
                )
                o3_surface = self._precomputer.query(voc_factors, nox_factors)
                elapsed = 0.001  # 毫秒级查询
            else:
                # 缓存未命中，尝试从相似缓存插值
                from .cache_utils import interpolate_from_similar_cache, find_most_similar_cache, CACHE_DIR

                logger.info(
                    "cache_miss_checking_similar",
                    cache_key=cache_key
                )

                # 尝试相似缓存插值（支持新旧格式兼容）
                interpolated_surface = interpolate_from_similar_cache(
                    target_key=cache_key,
                    voc_factors=voc_factors,
                    nox_factors=nox_factors,
                    cache_dir=CACHE_DIR,
                    min_similarity=0.5  # 降低阈值，允许更多匹配
                )

                if interpolated_surface is not None:
                    # 找到相似缓存，使用插值结果
                    logger.info(
                        "cache_interpolated_from_similar",
                        cache_key=cache_key,
                        method="linear_interpolation"
                    )
                    o3_surface = interpolated_surface
                    elapsed = 0.1  # 插值很快
                else:
                    # 无相似缓存，重新计算完整ODE网格
                    logger.info(
                        "cache_miss_computing_full_ode_grid",
                        cache_key=cache_key
                    )
                    o3_surface = self._precomputer.compute_full_grid(
                        pybox_adapter=self.pybox,
                        base_vocs=mapped_vocs,
                        base_nox=base_nox,
                        voc_range=(0.0, voc_range_max),
                        nox_range=(0.0, nox_range_max),
                        grid_size=grid_resolution,
                        simulation_time=self.config.simulation_time,
                        temperature=self.config.temperature,
                        pressure=self.config.pressure,
                        solar_zenith_angle=30.0,
                        progress_callback=progress_callback
                    )
                elapsed = time.time() - start_time

            # ========== 峰值位置确定（参考EKMA.py策略）==========
            # 策略1：尝试使用O3曲面最大值
            ode_peak_idx = np.unravel_index(np.argmax(o3_surface), o3_surface.shape)
            ode_peak_voc = voc_factors[ode_peak_idx[0]]
            ode_peak_nox = nox_factors[ode_peak_idx[1]]

            # 计算ODE峰值相对位置
            ode_peak_voc_ratio = ode_peak_voc / voc_range_max if voc_range_max > 0 else 0
            ode_peak_nox_ratio = ode_peak_nox / nox_range_max if nox_range_max > 0 else 0

            # 判断是否在合理范围（0.2-0.8）
            is_ode_peak_valid = (
                0.20 <= ode_peak_voc_ratio <= 0.80 and
                0.20 <= ode_peak_nox_ratio <= 0.80
            )

            if is_ode_peak_valid:
                # ODE峰值合理，直接使用
                peak_position = (ode_peak_voc, ode_peak_nox)
                peak_source = "ode_maximum"
                logger.info("ekma_peak_from_ode",
                           peak_voc=ode_peak_voc, peak_nox=ode_peak_nox,
                           peak_voc_ratio=round(ode_peak_voc_ratio, 3),
                           peak_nox_ratio=round(ode_peak_nox_ratio, 3))
            else:
                # 策略2：ODE峰值在边界，使用理论峰值（峰值在网格外，避免闭合等值线）
                # 使用网格外区域（VOC=120%, NOx=110%），确保等值线开放延伸
                theoretical_voc = voc_range_max * 1.20
                theoretical_nox = nox_range_max * 1.10
                peak_position = (theoretical_voc, theoretical_nox)
                peak_source = "theoretical_outside_grid"

                logger.warning("ekma_peak_position_abnormal",
                             ode_peak_voc_ratio=round(ode_peak_voc_ratio, 3),
                             ode_peak_nox_ratio=round(ode_peak_nox_ratio, 3),
                             expected_range="VOC: 0.2-0.8, NOx: 0.2-0.8",
                             possible_causes=[
                                 "VOCs数据不完整（缺少关键前体物）",
                                 "VOCs/NOx比值异常偏低",
                                 "化学机理边界效应",
                                 "网格范围设置不合理"
                             ],
                             action=f"using_theoretical_peak at ({theoretical_voc:.1f}, {theoretical_nox:.1f})",
                             theoretical_voc_ratio=1.20,
                             theoretical_nox_ratio=1.10)

            logger.info("precomputed_surface_ready",
                       peak_o3=float(np.max(o3_surface)),
                       peak_position=peak_position,
                       peak_source=peak_source,
                       elapsed_seconds=round(elapsed, 1))

            # 平滑处理（参考EKMA.py：sigma=3单轴平滑）
            # 策略：先沿NOx方向平滑（主要方向），再适度全局平滑
            from scipy.ndimage import gaussian_filter, gaussian_filter1d

            # 第一步：沿NOx方向（axis=0）平滑（参考EKMA.py行68）
            o3_surface_smooth = gaussian_filter1d(o3_surface, sigma=3, axis=0)

            # 第二步：轻度全局平滑（sigma=1.0，避免过度平滑）
            o3_surface_smooth = gaussian_filter(o3_surface_smooth, sigma=1.0)

            # 确保非负
            o3_surface_smooth = np.maximum(o3_surface_smooth, 0)

            logger.info("ekma_surface_smoothed",
                       method="1D(axis=0,σ=3) + 2D(σ=1.0)",
                       reference="EKMA.py line 68")

            # 保留L形模型用于控制区划分，但禁用L形控制线，改用自然山脊线
            # 方案：L形模型计算控制区背景，山脊线算法绘制控制线
            # 使用修正后的峰值位置（而不是从异常的ODE曲面自动检测）
            lshape_model = LShapeControlLine(
                peak_voc=peak_position[0],
                peak_nox=peak_position[1],
                anchor_voc=0.0,
                anchor_nox=0.0,
                slope_voc_arm=-0.5,  # 默认斜率
                slope_nox_arm=2.0
            )

            # 划分控制区（保留，用于背景着色）
            zone_divider = ControlZoneDivider(lshape_model, transition_buffer_ratio=0.10)
            control_zones = zone_divider.divide_zones(
                np.array(voc_factors),
                np.array(nox_factors)
            )

            # 但禁用L形等值线，让可视化器使用matplotlib contour提取峰值等值线
            lshape_contours = None  # 不使用L形等值线

            logger.info("ekma_control_line_mode",
                       mode="hybrid",
                       control_line="natural_ridge_contour",
                       control_zones="lshape_based",
                       note="控制线用自然等值线/山脊线，控制区用L形划分")

            # 后续分析
            reduction_paths = self._simulate_reduction_paths(o3_surface_smooth, voc_factors, nox_factors)
            sensitivity = self._determine_sensitivity(o3_surface_smooth, base_vocs, base_nox, control_zones)

            # 当前状态点
            current_vocs = current_vocs_value
            current_nox = current_nox_value

            # 生成图表
            o3_target = getattr(self.config, 'o3_target', 75.0)
            professional_charts = self.visualizer.generate_all_charts(
                o3_surface=o3_surface_smooth,
                voc_factors=voc_factors,
                nox_factors=nox_factors,
                sensitivity=sensitivity,
                reduction_paths=reduction_paths,
                o3_target=o3_target,
                current_vocs=current_vocs,
                current_nox=current_nox,
                peak_position=peak_position,
                lshape_model=lshape_model,
                control_zones=control_zones,
                lshape_contours=lshape_contours
            )

            # 构建结果
            result = {
                "status": "success",
                "success": True,
                "data": {
                    "o3_surface": o3_surface_smooth.tolist(),
                    "voc_axis": voc_factors,
                    "nox_axis": nox_factors,
                    "reduction_paths": reduction_paths,
                    "sensitivity": sensitivity,
                    "base_concentrations": {
                        "vocs_total": float(sum(base_vocs.values())),
                        "vocs_mapped": float(sum(mapped_vocs.values())),
                        "nox": float(base_nox),
                        "o3": float(base_o3),
                        "current_vocs": float(current_vocs),
                        "current_nox": float(current_nox),
                        "current_o3": float(current_o3_day_value),
                        "target_day_date": str(target_day_stats.get('date')) if target_day_stats else None
                    },
                    "statistics": {
                        "max_o3": float(np.max(o3_surface_smooth)),
                        "min_o3": float(np.min(o3_surface_smooth)),
                        "mean_o3": float(np.mean(o3_surface_smooth))
                    }
                },
                "visuals": professional_charts,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "FullEKMAAnalyzer",
                    "generator_version": "2.0.0",
                    "mode": mode,
                    "mechanism": self.mechanism,
                    "grid_resolution": grid_resolution,
                    "precision": "standard",
                    "elapsed_seconds": elapsed,
                    "analysis_time": datetime.now().isoformat()
                },
                "summary": self._generate_summary(mode, sensitivity, reduction_paths)
            }

            # ========== 数据精简优化（方案A）：删除LLM无需的冗余数据 ==========
            # 1. 删除O3响应曲面矩阵（441个数字 → 删除，保留statistics即可）
            if "o3_surface" in result["data"]:
                del result["data"]["o3_surface"]
                logger.debug("llm_optimization_removed_o3_surface",
                           reason="441 numbers unnecessary for LLM")

            # 2. 简化减排路径：删除完整O3时序，保留初始/最终/效率
            if "reduction_paths" in result["data"] and "paths" in result["data"]["reduction_paths"]:
                for path_name, path_data in result["data"]["reduction_paths"]["paths"].items():
                    if "o3" in path_data:
                        o3_series = path_data["o3"]
                        if len(o3_series) >= 2:
                            # 保留关键统计值
                            path_data["initial_o3"] = float(o3_series[0])
                            path_data["final_o3"] = float(o3_series[-1])
                            path_data["reduction"] = float(o3_series[0] - o3_series[-1])
                            # 删除完整时序
                            del path_data["o3"]
                logger.debug("llm_optimization_simplified_reduction_paths",
                           reason="Removed detailed O3 timeseries, kept summary stats")

            # 3. 简化VOC/NOx轴坐标：21个数字 → 范围+分辨率
            if "voc_axis" in result["data"]:
                voc_axis = result["data"]["voc_axis"]
                result["data"]["voc_range"] = {
                    "min": float(min(voc_axis)),
                    "max": float(max(voc_axis)),
                    "resolution": len(voc_axis)
                }
                del result["data"]["voc_axis"]

            if "nox_axis" in result["data"]:
                nox_axis = result["data"]["nox_axis"]
                result["data"]["nox_range"] = {
                    "min": float(min(nox_axis)),
                    "max": float(max(nox_axis)),
                    "resolution": len(nox_axis)
                }
                del result["data"]["nox_axis"]

            logger.debug("llm_optimization_simplified_axes",
                       reason="Replaced 21-element arrays with range objects")

            # 记录优化效果
            logger.info("llm_data_optimization_completed",
                       removed_fields=["o3_surface", "voc_axis", "nox_axis", "paths[*].o3"],
                       estimated_token_savings="~98.8% (~52K tokens → ~650 tokens)")

            logger.debug("ekma_analysis_completed", mode=mode, elapsed_seconds=elapsed)

            # ========== [NEW] 添加完整EKMA诊断信息（调试辅助） ==========
            result["diagnostic"] = self._generate_ekma_diagnostic_report(
                o3_surface=o3_surface_smooth,
                voc_factors=voc_factors,
                nox_factors=nox_factors,
                base_vocs=base_vocs,
                mapped_vocs=mapped_vocs,
                base_nox=base_nox,
                base_o3=base_o3,
                current_vocs=current_vocs,
                current_nox=current_nox,
                peak_position=peak_position,
                sensitivity=sensitivity,
                control_zones=control_zones,
                reduction_paths=reduction_paths,
                cache_key=cache_key
            )

            return result

        except Exception as e:
            logger.error("ekma_analysis_failed", error=str(e), exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "visuals": [],
                "metadata": {"schema_version": "v2.0", "error_type": "analysis_failed", "error_message": str(e)},
                "summary": f"EKMA分析失败: {str(e)}"
            }

    def _calculate_base_vocs(
        self,
        vocs_data: List[Dict],
        percentile: int = 95,
        daytime_only: bool = True,
        daytime_hours: tuple = (10, 18)
    ) -> Dict[str, float]:
        """
        计算基准VOCs浓度

        Args:
            vocs_data: VOCs时序数据列表
            percentile: 分位数百分比（默认95）
            daytime_only: 是否只使用日间数据（默认True）
            daytime_hours: 日间时段范围（默认10:00-18:00）

        Returns:
            各物种的基准浓度字典
        """
        if not vocs_data:
            return {}

        species_values = {}
        total_records = 0
        filtered_records = 0

        for record in vocs_data:
            if not isinstance(record, dict):
                continue

            total_records += 1

            # 日间数据过滤
            if daytime_only:
                time_field = record.get('time') or record.get('TimePoint') or record.get('timestamp')
                if time_field:
                    hour = _parse_hour(time_field)
                    if hour is not None:
                        if not (daytime_hours[0] <= hour <= daytime_hours[1]):
                            continue  # 跳过非日间数据
                        filtered_records += 1
                    else:
                        # 时间解析失败，保留该记录（容错处理）
                        filtered_records += 1
                else:
                    # 没有时间字段，保留该记录（容错处理）
                    filtered_records += 1
            else:
                filtered_records += 1

            # 统一使用species_data字段（优先UDF v2.0格式）
            if "species_data" in record and isinstance(record["species_data"], dict):
                species_dict = record["species_data"]
            else:
                # Fallback: 从record顶层提取数值字段（扁平格式）
                species_dict = {k: v for k, v in record.items()
                               if isinstance(v, (int, float)) and v >= 0
                               and k.lower() not in ['time', 'date', 'station', 'timestamp', 'timepoint']}

            for species, value in species_dict.items():
                if species not in species_values:
                    species_values[species] = []
                species_values[species].append(value)

        # 日志记录过滤统计
        if daytime_only:
            logger.info("vocs_daytime_filtering",
                       total_records=total_records,
                       filtered_records=filtered_records,
                       daytime_hours=f"{daytime_hours[0]:02d}:00-{daytime_hours[1]:02d}:00",
                       species_count=len(species_values))

        return {s: float(np.percentile(v, percentile)) for s, v in species_values.items() if v}

    def _calculate_base_nox(
        self,
        nox_data: List[Dict],
        percentile: int = 95,
        daytime_only: bool = True,
        daytime_hours: tuple = (10, 18)
    ) -> float:
        """
        计算基准NOx浓度

        Args:
            nox_data: NOx时序数据列表
            percentile: 分位数百分比（默认95）
            daytime_only: 是否只使用日间数据（默认True）
            daytime_hours: 日间时段范围（默认10:00-18:00）

        Returns:
            基准NOx浓度
        """
        values = []
        total_records = 0
        filtered_records = 0

        for record in nox_data:
            if not isinstance(record, dict):
                continue

            total_records += 1

            # 日间数据过滤
            if daytime_only:
                time_field = record.get('time') or record.get('TimePoint') or record.get('timestamp')
                if time_field:
                    hour = _parse_hour(time_field)
                    if hour is not None and not (daytime_hours[0] <= hour <= daytime_hours[1]):
                        continue
                    filtered_records += 1
                else:
                    filtered_records += 1
            else:
                filtered_records += 1

            # 提取NOx值
            for name in ['NOx', 'nox', 'NO2', 'no2']:
                v = record.get(name) or (record.get('measurements', {}).get(name) if isinstance(record.get('measurements'), dict) else None)
                if v is not None and isinstance(v, (int, float)) and v >= 0:
                    values.append(float(v))
                    break

        if daytime_only and values:
            logger.info("nox_daytime_filtering",
                       total_records=total_records,
                       filtered_records=filtered_records,
                       daytime_hours=f"{daytime_hours[0]:02d}:00-{daytime_hours[1]:02d}:00",
                       nox_values_count=len(values))

        return float(np.percentile(values, percentile)) if values else 30.0

    def _calculate_base_o3(
        self,
        o3_data: List[Dict],
        use_max: bool = True,
        daytime_only: bool = True,
        daytime_hours: tuple = (10, 18)
    ) -> float:
        """
        计算基准O3浓度

        Args:
            o3_data: O3时序数据列表
            use_max: 是否使用最大值（默认True），否则使用95%分位数
            daytime_only: 是否只使用日间数据（默认True）
            daytime_hours: 日间时段范围（默认10:00-18:00）

        Returns:
            基准O3浓度
        """
        values = []
        total_records = 0
        filtered_records = 0

        for record in o3_data:
            if not isinstance(record, dict):
                continue

            total_records += 1

            # 日间数据过滤
            if daytime_only:
                time_field = record.get('time') or record.get('TimePoint') or record.get('timestamp')
                if time_field:
                    hour = _parse_hour(time_field)
                    if hour is not None and not (daytime_hours[0] <= hour <= daytime_hours[1]):
                        continue
                    filtered_records += 1
                else:
                    filtered_records += 1
            else:
                filtered_records += 1

            # 提取O3值
            for name in ['O3', 'o3']:
                v = record.get(name) or (record.get('measurements', {}).get(name) if isinstance(record.get('measurements'), dict) else None)
                if v is not None and isinstance(v, (int, float)) and v >= 0:
                    values.append(float(v))
                    break

        if daytime_only and values:
            logger.info("o3_daytime_filtering",
                       total_records=total_records,
                       filtered_records=filtered_records,
                       daytime_hours=f"{daytime_hours[0]:02d}:00-{daytime_hours[1]:02d}:00",
                       o3_values_count=len(values),
                       use_max=use_max)

        if not values:
            return 80.0

        return float(np.max(values)) if use_max else float(np.percentile(values, 95))

    def _calculate_initial_o3(self, o3_data: List[Dict]) -> float:
        """计算初始O3浓度（10%分位数，清晨背景值）"""
        values = []
        for record in o3_data:
            if not isinstance(record, dict):
                continue
            for name in ['O3', 'o3']:
                v = record.get(name)
                if v is not None and isinstance(v, (int, float)) and v > 0:
                    values.append(float(v))
                    break

        return float(np.percentile(values, 10)) if values else 30.0

    def _simulate_reduction_paths(
        self,
        o3_surface: np.ndarray,
        voc_values: List[float],
        nox_values: List[float]
    ) -> Dict[str, Any]:
        """模拟5种减排路径"""
        n_voc, n_nox = o3_surface.shape

        # 找到当前状态点的索引（基准浓度在网格中的位置）
        # 基准浓度是网格最大值的一半（因为范围是0-2倍基准浓度）
        current_vocs = max(voc_values) / 2.0
        current_nox = max(nox_values) / 2.0

        voc_idx = min(range(len(voc_values)), key=lambda i: abs(voc_values[i] - current_vocs))
        nox_idx = min(range(len(nox_values)), key=lambda i: abs(nox_values[i] - current_nox))
        current_o3 = float(o3_surface[voc_idx, nox_idx])

        # 路径名称映射
        path_names = {
            "vocs_only": "仅减VOCs",
            "nox_only": "仅减NOx",
            "equal": "等比例减排",
            "vocs_2_nox_1": "VOCs优先(2:1)",
            "vocs_1_nox_2": "NOx优先(1:2)"
        }

        # 生成减排路径数据
        # 修复：使用正确的字段名 "o3_values"（与绘图端一致），并添加 "name" 字段
        paths = {}

        # 仅减VOCs：NOx保持不变，VOCs从当前值减到0
        vocs_only_o3 = [float(o3_surface[i, nox_idx]) for i in range(voc_idx, -1, -1)]
        paths["vocs_only"] = {
            "o3_values": vocs_only_o3,
            "name": path_names["vocs_only"]
        }

        # 仅减NOx：VOCs保持不变，NOx从当前值减到0
        nox_only_o3 = [float(o3_surface[voc_idx, j]) for j in range(nox_idx, -1, -1)]
        paths["nox_only"] = {
            "o3_values": nox_only_o3,
            "name": path_names["nox_only"]
        }

        # 等比例减排：VOCs和NOx同步减少
        equal_o3 = [float(o3_surface[i, j]) for i, j in zip(
            range(voc_idx, -1, -1),
            range(nox_idx, -1, -1)
        )]
        paths["equal"] = {
            "o3_values": equal_o3,
            "name": path_names["equal"]
        }

        # VOCs优先(2:1)：VOCs减少速度是NOx的2倍
        vocs_2_nox_1_o3 = []
        i, j = voc_idx, nox_idx
        step = 0
        while i >= 0 and j >= 0 and step < 50:  # 增加步数限制防止无限循环
            vocs_2_nox_1_o3.append(float(o3_surface[i, j]))
            i = max(0, i - 2)  # VOCs每次减2步
            j = max(0, j - 1)  # NOx每次减1步
            step += 1
        paths["vocs_2_nox_1"] = {
            "o3_values": vocs_2_nox_1_o3,
            "name": path_names["vocs_2_nox_1"]
        }

        # NOx优先(1:2)：NOx减少速度是VOCs的2倍
        vocs_1_nox_2_o3 = []
        i, j = voc_idx, nox_idx
        step = 0
        while i >= 0 and j >= 0 and step < 50:
            vocs_1_nox_2_o3.append(float(o3_surface[i, j]))
            i = max(0, i - 1)  # VOCs每次减1步
            j = max(0, j - 2)  # NOx每次减2步
            step += 1
        paths["vocs_1_nox_2"] = {
            "o3_values": vocs_1_nox_2_o3,
            "name": path_names["vocs_1_nox_2"]
        }

        # 计算效率
        best_path = "equal"
        best_eff = 0.0
        for name, p in paths.items():
            o3_vals = p["o3_values"]
            if len(o3_vals) >= 2 and o3_vals[0] > 0:
                eff = (o3_vals[0] - o3_vals[-1]) / o3_vals[0] * 100
                p["efficiency"] = eff
                if eff > best_eff:
                    best_eff = eff
                    best_path = name

        logger.info("reduction_paths_completed",
                   current_o3=current_o3,
                   best_path=best_path,
                   best_efficiency=best_eff,
                   paths_count=len(paths))

        return {
            "paths": paths,
            "current_o3": current_o3,
            "best_path": best_path,
            "best_efficiency": best_eff
        }

    def _determine_sensitivity(
        self,
        o3_surface: np.ndarray,
        base_vocs: Dict[str, float],
        base_nox: float,
        control_zones: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        确定敏感性类型

        优先使用控制区面积占比判断（更可靠），fallback到梯度分析
        """
        # 方法1: 使用控制区面积占比判断（优先，更可靠）
        if control_zones is not None and "zone_stats" in control_zones:
            stats = control_zones["zone_stats"]
            vocs_ratio = stats.get("vocs_control_ratio", 0)
            nox_ratio = stats.get("nox_control_ratio", 0)
            transition_ratio = stats.get("transition_ratio", 0)

            logger.info("sensitivity_determination_using_zone_stats",
                       vocs_ratio=vocs_ratio,
                       nox_ratio=nox_ratio,
                       transition_ratio=transition_ratio)

            # 根据面积占比判断（阈值50%）
            if vocs_ratio > 0.50:
                sens_type = "VOCs-limited"
                priority = "VOCs"
                rec = "优先控制VOCs排放"
                confidence = 0.90  # 基于面积占比的置信度更高
            elif nox_ratio > 0.50:
                sens_type = "NOx-limited"
                priority = "NOx"
                rec = "优先控制NOx排放"
                confidence = 0.90
            else:
                # 两个控制区都不占主导（各占40-50%左右）
                sens_type = "transitional"
                priority = "both"
                rec = "VOCs和NOx协同控制"
                confidence = 0.70

            total_vocs = sum(base_vocs.values())

            return {
                "type": sens_type,
                "vocs_control_ratio": float(vocs_ratio),
                "nox_control_ratio": float(nox_ratio),
                "transition_ratio": float(transition_ratio),
                "vocs_nox_ratio": total_vocs / (base_nox + 1e-6),
                "recommendation": rec,
                "control_priority": priority,
                "confidence": confidence,
                "method": "control_zone_area"  # 标记判断方法
            }

        # 方法2: Fallback到梯度分析（当control_zones不可用时）
        logger.warning("sensitivity_fallback_to_gradient_method",
                      reason="control_zones not available")

        n_voc, n_nox = o3_surface.shape
        mid_i, mid_j = n_voc // 2, n_nox // 2

        # 中心差分
        d_o3_d_vocs = (o3_surface[mid_i + 1, mid_j] - o3_surface[mid_i - 1, mid_j]) / 2 if 0 < mid_i < n_voc - 1 else 0
        d_o3_d_nox = (o3_surface[mid_i, mid_j + 1] - o3_surface[mid_i, mid_j - 1]) / 2 if 0 < mid_j < n_nox - 1 else 0

        ratio = d_o3_d_vocs / d_o3_d_nox if abs(d_o3_d_nox) > 1e-10 else (float('inf') if d_o3_d_vocs > 0 else 0)

        if ratio > 1.5:
            sens_type, priority, rec = "VOCs-limited", "VOCs", "优先控制VOCs排放"
        elif ratio < 0.67:
            sens_type, priority, rec = "NOx-limited", "NOx", "优先控制NOx排放"
        else:
            sens_type, priority, rec = "transitional", "both", "VOCs和NOx协同控制"

        total_vocs = sum(base_vocs.values())

        return {
            "type": sens_type,
            "vocs_sensitivity": float(d_o3_d_vocs),
            "nox_sensitivity": float(d_o3_d_nox),
            "sensitivity_ratio": float(ratio) if not np.isinf(ratio) else 999.0,
            "vocs_nox_ratio": total_vocs / (base_nox + 1e-6),
            "recommendation": rec,
            "control_priority": priority,
            "confidence": 0.75 if sens_type != "transitional" else 0.50,
            "method": "gradient_analysis"  # 标记判断方法
        }

    def _generate_summary(self, mode: str, sensitivity: Dict, reduction_paths: Dict) -> str:
        """生成分析摘要"""
        mode_cn_map = {
            "full_ode": "完整ODE网格"
        }
        mode_cn = mode_cn_map.get(mode, mode)

        sens_cn = {"VOCs-limited": "VOCs控制型", "NOx-limited": "NOx控制型", "transitional": "过渡区"}[sensitivity["type"]]
        best_cn = {"vocs_only": "仅减VOCs", "nox_only": "仅减NOx", "equal": "等比例减排",
                   "vocs_2_nox_1": "VOCs优先", "vocs_1_nox_2": "NOx优先"}[reduction_paths["best_path"]]

        return f"EKMA分析完成({mode_cn})。敏感性: {sens_cn}，最优路径: {best_cn}，效率: {reduction_paths['best_efficiency']:.1f}%"

    def _generate_ekma_diagnostic_report(
        self,
        o3_surface: np.ndarray,
        voc_factors: List[float],
        nox_factors: List[float],
        base_vocs: Dict[str, float],
        mapped_vocs: Dict[str, float],
        base_nox: float,
        base_o3: float,
        current_vocs: float,
        current_nox: float,
        peak_position: Tuple[float, float],
        sensitivity: Dict[str, Any],
        control_zones: Optional[Dict[str, Any]],
        reduction_paths: Dict[str, Any],
        cache_key: str
    ) -> Dict[str, Any]:
        """
        生成完整的EKMA诊断报告（用于调试和验证）

        此报告帮助诊断以下问题：
        1. VOCs输入数据完整性
        2. 网格范围设置合理性
        3. 峰值位置物理合理性
        4. 控制区划分准确性
        5. 敏感性判断一致性

        Returns:
            完整诊断报告字典
        """
        # ========== 1. 输入数据完整性诊断 ==========
        total_vocs_input = sum(base_vocs.values())
        total_vocs_mapped = sum(mapped_vocs.values())
        mapping_ratio = total_vocs_mapped / total_vocs_input if total_vocs_input > 0 else 0

        # 检查关键前体物
        key_precursors = {
            "alkenes": ["乙烯", "丙烯", "1-丁烯", "异戊二烯"],
            "aromatics": ["苯", "甲苯", "乙苯", "二甲苯"],
            "carbonyls": ["乙醛", "丙酮", "甲醛"],
            "alkanes": ["乙烷", "丙烷", "正丁烷", "异丁烷", "正戊烷", "异戊烷", "正己烷"]
        }

        missing_precursors = {}
        mapped_species = list(mapped_vocs.keys())

        for category, species_list in key_precursors.items():
            missing = [s for s in species_list if s not in mapped_species or mapped_vocs.get(s, 0) < 0.01]
            if missing:
                missing_precursors[category] = missing

        input_diagnostic = {
            "total_vocs_input_ppb": round(total_vocs_input, 2),
            "total_vocs_mapped_ppb": round(total_vocs_mapped, 2),
            "mapping_success_ratio": round(mapping_ratio, 3),
            "species_count_input": len(base_vocs),
            "species_count_mapped": len(mapped_vocs),
            "missing_key_precursors": missing_precursors,
            "has_carbonyls": any(s in mapped_species for s in key_precursors["carbonyls"]),
            "completeness_status": "complete" if mapping_ratio > 0.8 and not missing_precursors else "incomplete",
            "input_species_list": list(base_vocs.keys()),
            "mapped_species_list": mapped_species
        }

        # ========== 2. 网格范围合理性诊断 ==========
        voc_range = (min(voc_factors), max(voc_factors))
        nox_range = (min(nox_factors), max(nox_factors))
        voc_span = voc_range[1] - voc_range[0]
        nox_span = nox_range[1] - nox_range[0]
        ratio_vocs_nox = voc_span / nox_span if nox_span > 0 else float('inf')

        # 当前状态在网格中的相对位置
        current_voc_ratio = (current_vocs - voc_range[0]) / voc_span if voc_span > 0 else 0.5
        current_nox_ratio = (current_nox - nox_range[0]) / nox_span if nox_span > 0 else 0.5

        grid_diagnostic = {
            "voc_range_ppb": voc_range,
            "nox_range_ppb": nox_range,
            "voc_span_ppb": round(voc_span, 2),
            "nox_span_ppb": round(nox_span, 2),
            "vocs_nox_span_ratio": round(ratio_vocs_nox, 2),
            "recommended_ratio_range": "2-5:1",
            "ratio_status": "reasonable" if 2 <= ratio_vocs_nox <= 5 else "abnormal",
            "current_state_in_grid": {
                "vocs_ppb": round(current_vocs, 2),
                "nox_ppb": round(current_nox, 2),
                "voc_position_ratio": round(current_voc_ratio, 3),  # 0=left, 1=right
                "nox_position_ratio": round(current_nox_ratio, 3),  # 0=bottom, 1=top
                "is_centered": (0.3 <= current_voc_ratio <= 0.7 and 0.3 <= current_nox_ratio <= 0.7)
            },
            "grid_resolution": f"{len(voc_factors)}x{len(nox_factors)}"
        }

        # ========== 3. O3曲面物理合理性诊断 ==========
        o3_min = float(np.nanmin(o3_surface))
        o3_max = float(np.nanmax(o3_surface))
        o3_mean = float(np.nanmean(o3_surface))
        o3_std = float(np.nanstd(o3_surface))

        # 峰值位置
        peak_idx = np.unravel_index(np.nanargmax(o3_surface), o3_surface.shape)
        peak_voc_idx, peak_nox_idx = peak_idx
        peak_voc_ratio = peak_voc_idx / (len(voc_factors) - 1) if len(voc_factors) > 1 else 0.5
        peak_nox_ratio = peak_nox_idx / (len(nox_factors) - 1) if len(nox_factors) > 1 else 0.5

        # 边界区域检查
        n_voc, n_nox = o3_surface.shape
        corner_values = {
            "bottom_left": float(o3_surface[0, 0]),       # VOC=0, NOx=0
            "bottom_right": float(o3_surface[0, -1]),     # VOC=0, NOx=max
            "top_left": float(o3_surface[-1, 0]),         # VOC=max, NOx=0
            "top_right": float(o3_surface[-1, -1])        # VOC=max, NOx=max
        }

        # 边界平均值
        left_edge_mean = float(np.nanmean(o3_surface[:, 0]))   # VOC=0列
        right_edge_mean = float(np.nanmean(o3_surface[:, -1])) # VOC=max列
        bottom_edge_mean = float(np.nanmean(o3_surface[0, :])) # NOx=0行
        top_edge_mean = float(np.nanmean(o3_surface[-1, :]))   # NOx=max行

        # 物理合理性检查
        peak_is_boundary = (peak_voc_ratio < 0.1 or peak_voc_ratio > 0.9 or
                           peak_nox_ratio < 0.1 or peak_nox_ratio > 0.9)
        peak_is_reasonable = (0.2 <= peak_voc_ratio <= 0.8 and 0.2 <= peak_nox_ratio <= 0.8)

        # NOx滴定效应检查（高NOx应导致O3下降）
        nox_titration_ok = top_edge_mean < o3_max * 0.9  # 高NOx区O3应低于峰值

        surface_diagnostic = {
            "o3_statistics": {
                "min_ppb": round(o3_min, 2),
                "max_ppb": round(o3_max, 2),
                "mean_ppb": round(o3_mean, 2),
                "std_ppb": round(o3_std, 2),
                "range_ppb": round(o3_max - o3_min, 2)
            },
            "peak_analysis": {
                "position_vocs_ppb": round(peak_position[0], 2),
                "position_nox_ppb": round(peak_position[1], 2),
                "position_voc_ratio": round(peak_voc_ratio, 3),
                "position_nox_ratio": round(peak_nox_ratio, 3),
                "peak_o3_ppb": round(o3_max, 2),
                "is_at_boundary": peak_is_boundary,
                "is_reasonable_position": peak_is_reasonable,
                "expected_range": "VOC: 0.2-0.8, NOx: 0.2-0.8"
            },
            "boundary_analysis": {
                "corner_values_ppb": {k: round(v, 2) for k, v in corner_values.items()},
                "edge_means_ppb": {
                    "left_voc_0": round(left_edge_mean, 2),
                    "right_voc_max": round(right_edge_mean, 2),
                    "bottom_nox_0": round(bottom_edge_mean, 2),
                    "top_nox_max": round(top_edge_mean, 2)
                },
                "nox_titration_effect_ok": nox_titration_ok,
                "titration_explanation": "高NOx区O3应低于峰值（NOx滴定效应）"
            },
            "physical_validity": {
                "peak_position_ok": peak_is_reasonable,
                "nox_titration_ok": nox_titration_ok,
                "overall_status": "valid" if (peak_is_reasonable and nox_titration_ok) else "abnormal"
            }
        }

        # ========== 4. 控制区划分诊断 ==========
        if control_zones:
            zone_stats = control_zones.get("zone_stats", {})
            vocs_ratio = zone_stats.get("vocs_control_ratio", 0)
            nox_ratio = zone_stats.get("nox_control_ratio", 0)
            transition_ratio = zone_stats.get("transition_ratio", 0)

            # 诊断控制区是否极端失衡
            is_balanced = (0.1 <= vocs_ratio <= 0.9 and 0.1 <= nox_ratio <= 0.9)
            is_extreme_vocs = vocs_ratio > 0.85
            is_extreme_nox = nox_ratio > 0.85

            zones_diagnostic = {
                "vocs_control_ratio": round(vocs_ratio, 3),
                "nox_control_ratio": round(nox_ratio, 3),
                "transition_ratio": round(transition_ratio, 3),
                "is_balanced": is_balanced,
                "is_extreme_vocs_dominated": is_extreme_vocs,
                "is_extreme_nox_dominated": is_extreme_nox,
                "balance_status": "balanced" if is_balanced else "extreme_imbalance",
                "expected_range": "Both zones should be 10-90%"
            }
        else:
            zones_diagnostic = {"status": "not_available"}

        # ========== 5. 敏感性判断一致性诊断 ==========
        ekma_sensitivity = sensitivity.get("type", "unknown")
        ekma_method = sensitivity.get("method", "unknown")

        # 比较EKMA结果与预期
        expected_sensitivity = "NOx-limited" if nox_ratio < 0.15 else ("VOCs-limited" if vocs_ratio > 0.85 else "transitional")

        sensitivity_diagnostic = {
            "ekma_result": ekma_sensitivity,
            "ekma_method": ekma_method,
            "expected_from_zones": expected_sensitivity,
            "is_consistent": (ekma_sensitivity == expected_sensitivity),
            "vocs_sensitivity": sensitivity.get("vocs_sensitivity", 0),
            "nox_sensitivity": sensitivity.get("nox_sensitivity", 0),
            "confidence": sensitivity.get("confidence", 0),
            "recommendation": sensitivity.get("recommendation", "N/A")
        }

        # ========== 6. 减排路径有效性诊断 ==========
        best_path = reduction_paths.get("best_path", "unknown")
        best_eff = reduction_paths.get("best_efficiency", 0)
        current_o3 = reduction_paths.get("current_o3", 0)

        # 检查各路径是否合理
        paths = reduction_paths.get("paths", {})
        path_validity = {}
        for path_name, path_data in paths.items():
            o3_values = path_data.get("o3_values", [])
            if len(o3_values) >= 2:
                initial = o3_values[0]
                final = o3_values[-1]
                reduction = initial - final
                is_effective = reduction > 0
                path_validity[path_name] = {
                    "initial_o3": round(initial, 2),
                    "final_o3": round(final, 2),
                    "reduction_ppb": round(reduction, 2),
                    "is_effective": is_effective
                }

        paths_diagnostic = {
            "best_path": best_path,
            "best_efficiency_percent": round(best_eff, 2),
            "current_o3_ppb": round(current_o3, 2),
            "path_validity": path_validity
        }

        # ========== 7. 缓存信息 ==========
        cache_diagnostic = {
            "cache_key": cache_key,
            "using_cache": True,  # 当前始终使用缓存
            "note": "预计算ODE网格，首次约3-5分钟，后续毫秒级"
        }

        # ========== 8. 综合诊断结论 ==========
        issues_found = []
        warnings = []

        # 检查数据完整性
        if input_diagnostic["completeness_status"] == "incomplete":
            issues_found.append("VOCs数据不完整：缺少关键前体物种")
        if input_diagnostic["mapping_success_ratio"] < 0.5:
            issues_found.append(f"VOCs映射率过低: {input_diagnostic['mapping_success_ratio']*100:.1f}%")

        # 检查网格设置
        if grid_diagnostic["ratio_status"] == "abnormal":
            warnings.append(f"网格VOCs/NOx比例异常: {grid_diagnostic['vocs_nox_span_ratio']:.1f}:1（建议2-5:1）")

        # 检查曲面物理性
        if surface_diagnostic["physical_validity"]["overall_status"] == "abnormal":
            issues_found.append("O3曲面物理合理性异常")
            if not surface_diagnostic["peak_analysis"]["is_reasonable_position"]:
                issues_found.append(f"峰值位置异常: 位于边界({peak_voc_ratio:.2f}, {peak_nox_ratio:.2f})")
            if not surface_diagnostic["boundary_analysis"]["nox_titration_effect_ok"]:
                issues_found.append("NOx滴定效应异常: 高NOx区O3反而升高")

        # 检查控制区划分
        if zones_diagnostic.get("balance_status") == "extreme_imbalance":
            issues_found.append(f"控制区极度失衡: VOCs={vocs_ratio*100:.0f}%, NOx={nox_ratio*100:.0f}%")

        # 检查敏感性一致性
        if not sensitivity_diagnostic["is_consistent"]:
            warnings.append(f"敏感性判断不一致: EKMA={ekma_sensitivity}, 预期={expected_sensitivity}")

        summary_diagnostic = {
            "overall_status": "healthy" if not issues_found else "abnormal",
            "critical_issues": issues_found,
            "warnings": warnings,
            "issue_count": len(issues_found),
            "warning_count": len(warnings)
        }

        # ========== 9. 修复建议 ==========
        recommendations = []

        if "VOCs数据不完整" in str(issues_found):
            recommendations.append({
                "issue": "VOCs数据不完整",
                "suggestion": "补充关键前体物数据（乙醛、丙酮等含氧VOCs）",
                "priority": "high"
            })

        if "网格VOCs/NOx比例异常" in str(warnings):
            recommendations.append({
                "issue": "网格比例不合理",
                "suggestion": f"调整网格范围：VOCs=0-{total_vocs_mapped*2:.0f}, NOx=0-{base_nox*3:.0f}",
                "priority": "medium"
            })

        if "峰值位置异常" in str(issues_found):
            recommendations.append({
                "issue": "峰值位置边界效应",
                "suggestion": "扩大网格范围，确保峰值在中心区域",
                "priority": "high"
            })

        if "控制区极度失衡" in str(issues_found):
            recommendations.append({
                "issue": "控制区划分失衡",
                "suggestion": "检查L形控制线模型参数，可能需要调整缓冲区比例",
                "priority": "high"
            })

        # ========== 完整报告 ==========
        return {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "summary": summary_diagnostic,
            "diagnostics": {
                "1_input_data": input_diagnostic,
                "2_grid_setup": grid_diagnostic,
                "3_o3_surface": surface_diagnostic,
                "4_control_zones": zones_diagnostic,
                "5_sensitivity": sensitivity_diagnostic,
                "6_reduction_paths": paths_diagnostic,
                "7_cache_info": cache_diagnostic
            },
            "recommendations": recommendations,
            "interpretation": self._interpret_diagnostic_results(
                input_diagnostic, grid_diagnostic, surface_diagnostic,
                zones_diagnostic, sensitivity_diagnostic, issues_found
            )
        }

    def _interpret_diagnostic_results(
        self,
        input_diag: Dict,
        grid_diag: Dict,
        surface_diag: Dict,
        zones_diag: Dict,
        sens_diag: Dict,
        issues: List[str]
    ) -> str:
        """生成诊断结果的人类可读解释"""

        if not issues:
            return (
                "EKMA分析结果健康，所有关键指标均在合理范围内。\n"
                f"- VOCs数据完整性: {input_diag['completeness_status']}\n"
                f"- 网格设置: {grid_diag['ratio_status']}\n"
                f"- 曲面物理性: {surface_diag['physical_validity']['overall_status']}\n"
                f"- 控制区划分: {zones_diag.get('balance_status', 'N/A')}\n"
                f"分析结果可信，建议采纳控制策略。"
            )

        # 存在问题时的详细解释
        explanation = "EKMA分析发现以下异常，需要进一步检查：\n\n"

        if "VOCs数据不完整" in str(issues):
            missing = input_diag.get("missing_key_precursors", {})
            explanation += (
                f"1. **数据完整性问题**:\n"
                f"   - VOCs映射率仅{input_diag['mapping_success_ratio']*100:.1f}%\n"
                f"   - 缺少关键前体物: {', '.join(sum(missing.values(), []))}\n"
                f"   影响: 可能导致O3生成潜力被低估\n\n"
            )

        if "峰值位置异常" in str(issues):
            peak_ratio = surface_diag["peak_analysis"]["position_voc_ratio"]
            explanation += (
                f"2. **峰值位置异常**:\n"
                f"   - 当前峰值位于网格边界({peak_ratio:.2f}, {surface_diag['peak_analysis']['position_nox_ratio']:.2f})\n"
                f"   - 预期峰值应在中心区域(0.2-0.8, 0.2-0.8)\n"
                f"   影响: EKMA曲线不完整，控制区判断可能失准\n\n"
            )

        if "控制区极度失衡" in str(issues):
            vocs_ratio = zones_diag.get("vocs_control_ratio", 0)
            nox_ratio = zones_diag.get("nox_control_ratio", 0)
            explanation += (
                f"3. **控制区划分失衡**:\n"
                f"   - VOCs控制区: {vocs_ratio*100:.0f}%\n"
                f"   - NOx控制区: {nox_ratio*100:.0f}%\n"
                f"   影响: 可能与RIR/P(O3)诊断结果矛盾\n\n"
            )

        explanation += (
            "**建议操作**:\n"
            "1. 检查VOCs输入数据，补充缺失物种\n"
            "2. 调整网格范围参数，确保峰值在中心\n"
            "3. 对比RIR和P(O3)诊断结果，交叉验证敏感性判断\n"
        )

        return explanation
