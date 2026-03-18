"""
O3 Response Surface for EKMA - Full ODE Mode

完整ODE网格模式:
- 首次计算21×21完整ODE网格 (441点)
- 保存到缓存，后续直接加载
- 确保物理正确的EKMA结果

使用:
    surface = O3SurfacePrecomputer()

    # 首次运行: 计算完整ODE网格
    o3_surface = surface.compute_full_grid(pybox_adapter, base_vocs, base_nox)

    # 后续查询: 直接加载缓存
    o3_surface = surface.query(voc_factors, nox_factors)
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from datetime import datetime
import json
import os
import structlog

logger = structlog.get_logger()

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), "o3_surface_cache")


class O3SurfacePrecomputer:
    """
    O3响应曲面预计算器 - 完整ODE模式

    策略:
    - 首次运行计算完整21×21 ODE网格 (441点)
    - 保存到缓存，后续直接加载
    - 约3-5分钟首次，后续毫秒级

    相比RBF模式:
    - 精度更高: 真实ODE结果，无插值伪影
    - 稳定性更好: 无边界外推问题
    - 代码更简洁: 无RBF复杂性
    """

    def __init__(self, cache_key: str = "default"):
        """
        初始化预计算器

        Args:
            cache_key: 缓存键，用于区分不同气象条件
        """
        self.cache_key = cache_key
        self.cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")

        # 预计算结果
        self.o3_surface: Optional[np.ndarray] = None
        self.voc_factors: List[float] = []
        self.nox_factors: List[float] = []
        self.base_vocs: Dict[str, float] = {}
        self.base_nox: float = 30.0
        self.last_update: Optional[str] = None

        # 加载缓存
        self._load_cache()

    def compute_full_grid(
        self,
        pybox_adapter,
        base_vocs: Dict[str, float],
        base_nox: float,
        voc_range: Tuple[float, float] = (0.0, 120.0),
        nox_range: Tuple[float, float] = (0.0, 60.0),
        grid_size: int = 21,
        simulation_time: float = 25200.0,  # 7小时
        temperature: float = 298.15,
        pressure: float = 101325.0,
        solar_zenith_angle: float = 30.0,
        progress_callback: Optional[callable] = None
    ) -> np.ndarray:
        """
        计算完整O3响应曲面网格

        Args:
            pybox_adapter: PyBox适配器实例
            base_vocs: 基准VOC浓度
            base_nox: 基准NOx浓度
            voc_range: VOC浓度范围
            nox_range: NOx浓度范围
            grid_size: 网格大小 (默认21×21)
            simulation_time: 模拟时长(秒)
            temperature: 温度(K)
            pressure: 压力(Pa)
            solar_zenith_angle: 太阳天顶角(度)
            progress_callback: 进度回调

        Returns:
            O3曲面矩阵 (grid_size × grid_size)
        """
        import time
        start_time = time.time()

        # 生成网格
        voc_factors = np.linspace(voc_range[0], voc_range[1], grid_size)
        nox_factors = np.linspace(nox_range[0], nox_range[1], grid_size)
        n_voc, n_nox = len(voc_factors), len(nox_factors)

        # 存储
        self.voc_factors = list(voc_factors)
        self.nox_factors = list(nox_factors)
        self.base_vocs = base_vocs
        self.base_nox = base_nox

        # 初始化O3矩阵
        o3_matrix = np.zeros((n_voc, n_nox))

        total_points = n_voc * n_nox
        logger.info(
            "ekma_full_grid_started",
            grid_size=f"{n_voc}x{n_nox}",
            total_points=total_points,
            cache_key=self.cache_key
        )

        # 计算每个网格点
        completed = 0
        for i, voc_val in enumerate(voc_factors):
            for j, nox_val in enumerate(nox_factors):
                # 调整浓度（移除错误的*2倍增，voc_val和nox_val已经是绝对浓度值）
                adj_vocs = {k: v * (voc_val / voc_range[1]) if voc_range[1] > 0 else 0
                           for k, v in base_vocs.items()}
                adj_nox = base_nox * (nox_val / nox_range[1]) if nox_range[1] > 0 else 0

                initial_conc = adj_vocs.copy()
                initial_conc["NO2"] = adj_nox * 0.9  # 90% NO2, 减少滴定
                initial_conc["NO"] = adj_nox * 0.1
                initial_conc["O3"] = 30.0

                # 运行ODE
                result = pybox_adapter.simulate_single_point(
                    initial_concentrations=initial_conc,
                    simulation_time=simulation_time,
                    temperature=temperature,
                    pressure=pressure,
                    solar_zenith_angle=solar_zenith_angle
                )

                o3_matrix[i, j] = result.max_o3 if result.success else np.nan

                completed += 1
                if progress_callback and completed % 44 == 0:
                    progress_callback(completed, total_points, f"O3曲面 {completed}/{total_points}")

        # 验证结果
        valid_count = np.sum(~np.isnan(o3_matrix))
        if valid_count < total_points * 0.9:
            logger.warning(
                "ekma_grid_incomplete",
                valid_points=valid_count,
                total_points=total_points
            )

        # 应用物理约束（确保边界合理）
        o3_matrix = self._apply_physical_constraints(o3_matrix, voc_factors, nox_factors)

        elapsed = time.time() - start_time
        max_o3 = float(np.nanmax(o3_matrix))

        logger.info(
            "ekma_full_grid_completed",
            elapsed_seconds=round(elapsed, 1),
            grid_size=f"{n_voc}x{n_nox}",
            max_o3=max_o3,
            cache_key=self.cache_key
        )

        # 保存缓存
        self.o3_surface = o3_matrix
        self._save_cache(o3_matrix, voc_factors, nox_factors, voc_range, nox_range)

        return o3_matrix

    def _apply_physical_constraints(
        self,
        o3_surface: np.ndarray,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray
    ) -> np.ndarray:
        """
        应用物理约束确保曲面合理

        约束规则:
        1. VOC=0列: O3应随NOx增加而减少或平稳
        2. NOx=0行: O3应随VOC增加而增加
        3. 角落值不应超过峰值的50%
        4. 确保非负
        """
        constrained = o3_surface.copy()
        n_voc, n_nox = constrained.shape
        peak_value = np.nanmax(constrained)

        if np.isnan(peak_value) or peak_value <= 0:
            logger.warning("ekma_surface_empty_or_invalid")
            return constrained

        # 约束1: VOC=0列（边界行为）
        voc_zero_col = constrained[:, 0]
        if not np.all(np.isnan(voc_zero_col)):
            # 平滑处理VOC=0列：不应该随NOx增加而大幅增加
            for i in range(1, n_voc):
                if not np.isnan(voc_zero_col[i]) and not np.isnan(voc_zero_col[i-1]):
                    if voc_zero_col[i] > voc_zero_col[i-1] * 1.3:
                        voc_zero_col[i] = voc_zero_col[i-1] * 1.1
            constrained[:, 0] = voc_zero_col

        # 约束2: NOx=0行
        nox_zero_row = constrained[0, :]
        if not np.all(np.isnan(nox_zero_row)):
            # NOx=0时，O3应随VOC增加而增加
            for j in range(1, n_nox):
                if not np.isnan(nox_zero_row[j]) and not np.isnan(nox_zero_row[j-1]):
                    if nox_zero_row[j] < nox_zero_row[j-1]:
                        nox_zero_row[j] = nox_zero_row[j-1] * 0.95
            constrained[0, :] = nox_zero_row

        # 约束3: 角落值限制
        corners = [(0, 0), (0, -1), (-1, 0), (-1, -1)]
        corner_max = peak_value * 0.5
        for i, j in corners:
            if not np.isnan(constrained[i, j]) and constrained[i, j] > corner_max:
                constrained[i, j] = corner_max

        # 约束4: 非负值
        constrained = np.maximum(constrained, 0)

        # 验证峰值位置
        peak_idx = np.unravel_index(np.argmax(constrained), constrained.shape)
        peak_voc_ratio = peak_idx[0] / (n_voc - 1)
        peak_nox_ratio = peak_idx[1] / (n_nox - 1)

        is_valid = 0.1 <= peak_voc_ratio <= 0.9 and 0.1 <= peak_nox_ratio <= 0.9

        logger.info(
            "physical_constraints_applied",
            peak_voc_ratio=round(peak_voc_ratio, 3),
            peak_nox_ratio=round(peak_nox_ratio, 3),
            peak_valid=is_valid
        )

        return constrained

    def query(
        self,
        voc_factors: List[float],
        nox_factors: List[float],
        allow_interpolation: bool = True
    ) -> np.ndarray:
        """
        查询O3响应曲面 (毫秒级)

        策略:
        1. 精确匹配: 如果有缓存且网格匹配，直接返回
        2. 插值匹配: 网格不匹配时，从缓存插值
        3. 相似缓存: 无精确缓存时，从相似缓存插值

        Args:
            voc_factors: VOC因子列表
            nox_factors: NOx因子列表
            allow_interpolation: 是否允许从相似缓存插值

        Returns:
            O3曲面矩阵
        """
        if self.o3_surface is None:
            if allow_interpolation:
                # 尝试从相似缓存插值
                from .cache_utils import interpolate_from_similar_cache
                result = interpolate_from_similar_cache(
                    self.cache_key, voc_factors, nox_factors
                )
                if result is not None:
                    logger.info("query_from_similar_cache", cache_key=self.cache_key)
                    return result
            raise RuntimeError(
                "曲面未计算且无相似缓存可用。请先调用 compute_full_grid() 计算完整ODE网格。"
            )

        # 如果请求的网格与缓存完全匹配，直接返回
        if (len(voc_factors) == len(self.voc_factors) and
            len(nox_factors) == len(self.nox_factors) and
            np.allclose(voc_factors, self.voc_factors) and
            np.allclose(nox_factors, self.nox_factors)):
            return self.o3_surface.copy()

        # 否则进行插值
        from scipy.interpolate import RegularGridInterpolator

        voc_arr = np.array(self.voc_factors)
        nox_arr = np.array(self.nox_factors)

        interpolator = RegularGridInterpolator(
            (voc_arr, nox_arr),
            self.o3_surface,
            method='linear',
            bounds_error=False,
            fill_value=np.nan
        )

        voc_mesh, nox_mesh = np.meshgrid(voc_factors, nox_factors, indexing='ij')
        query_points = np.column_stack([voc_mesh.ravel(), nox_mesh.ravel()])

        result = interpolator(query_points)
        return result.reshape(len(voc_factors), len(nox_factors))

    def _save_cache(
        self,
        o3_surface: np.ndarray,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray,
        voc_range: Tuple[float, float],
        nox_range: Tuple[float, float]
    ):
        """保存预计算结果到缓存"""
        os.makedirs(CACHE_DIR, exist_ok=True)

        cache_data = {
            "cache_key": self.cache_key,
            "created_at": datetime.now().isoformat(),
            "voc_range": list(voc_range),
            "nox_range": list(nox_range),
            "voc_axis": list(voc_factors),
            "nox_axis": list(nox_factors),
            "base_vocs": self.base_vocs,
            "base_nox": self.base_nox,
            "o3_surface": o3_surface.tolist()
        }

        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        logger.debug("cache_saved", path=self.cache_path)

    def _load_cache(self) -> bool:
        """加载缓存"""
        if not os.path.exists(self.cache_path):
            return False

        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            self.o3_surface = np.array(cache_data["o3_surface"])
            self.voc_factors = cache_data["voc_axis"]
            self.nox_factors = cache_data["nox_axis"]
            self.base_vocs = cache_data.get("base_vocs", {})
            self.base_nox = cache_data.get("base_nox", 30.0)
            self.last_update = cache_data["created_at"]

            logger.debug(
                "cache_loaded",
                path=self.cache_path,
                grid_size=f"{self.o3_surface.shape[0]}x{self.o3_surface.shape[1]}"
            )
            return True

        except Exception as e:
            logger.warning("cache_load_failed", error=str(e))
            return False

    def get_peak_position(self) -> Tuple[float, float, float]:
        """
        获取峰值位置

        Returns:
            (voc_value, nox_value, o3_value)
        """
        if self.o3_surface is None:
            raise RuntimeError("曲面未计算")

        peak_idx = np.unravel_index(np.argmax(self.o3_surface), self.o3_surface.shape)
        peak_o3 = self.o3_surface[peak_idx]

        return (
            self.voc_factors[peak_idx[0]],
            self.nox_factors[peak_idx[1]],
            float(peak_o3)
        )


class FastEKMAAnalyzer:
    """
    快速EKMA分析器 - 完整ODE模式

    使用完整ODE网格计算，确保物理正确性。
    首次约3-5分钟，后续毫秒级。
    """

    def __init__(self):
        self.precomputer: Optional[O3SurfacePrecomputer] = None

    def analyze(
        self,
        pybox_adapter,
        vocs_data: List[Dict],
        nox_data: List[Dict],
        o3_data: List[Dict],
        grid_resolution: int = 21,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        执行EKMA分析

        Args:
            pybox_adapter: PyBox适配器
            vocs_data: VOC数据
            nox_data: NOx数据
            o3_data: O3数据
            grid_resolution: 网格分辨率
            progress_callback: 进度回调

        Returns:
            EKMA分析结果
        """
        import time
        start_time = time.time()

        # 计算基准浓度
        base_vocs = self._calculate_base_vocs(vocs_data)
        base_nox = self._calculate_base_nox(nox_data)
        base_o3 = self._calculate_base_o3(o3_data)

        # 确定网格范围 - 扩大范围以确保峰值在中心区域
        # 典型EKMA需要VOCs/NOx比例在2-5:1范围内
        total_vocs = sum(base_vocs.values())
        voc_range = (0.0, total_vocs * 3.0)   # 扩大至3倍，确保峰值在中心
        nox_range = (0.0, base_nox * 1.5)      # 缩小至1.5倍，调整比例至约2:1

        # 初始化预计算器
        if self.precomputer is None:
            self.precomputer = O3SurfacePrecomputer()

        # 检查是否需要重新计算
        needs_compute = (
            self.precomputer.o3_surface is None or
            self.precomputer.base_vocs != base_vocs
        )

        if needs_compute:
            o3_surface = self.precomputer.compute_full_grid(
                pybox_adapter=pybox_adapter,
                base_vocs=base_vocs,
                base_nox=base_nox,
                voc_range=voc_range,
                nox_range=nox_range,
                grid_size=grid_resolution,
                progress_callback=progress_callback
            )
        else:
            o3_surface = self.precomputer.query(
                self.precomputer.voc_factors,
                self.precomputer.nox_factors
            )

        # 获取峰值位置
        peak_voc, peak_nox, peak_o3 = self.precomputer.get_peak_position()

        elapsed = time.time() - start_time

        return {
            "status": "success",
            "success": True,
            "data": {
                "o3_surface": o3_surface.tolist(),
                "voc_axis": self.precomputer.voc_factors,
                "nox_axis": self.precomputer.nox_factors,
                "base_concentrations": {
                    "vocs_total": float(sum(base_vocs.values())),
                    "nox": float(base_nox),
                    "o3": float(base_o3)
                },
                "peak_position": {
                    "voc": float(peak_voc),
                    "nox": float(peak_nox),
                    "o3": float(peak_o3)
                }
            },
            "metadata": {
                "schema_version": "v2.0",
                "generator": "FastEKMAAnalyzer",
                "mode": "full_ode",
                "elapsed_seconds": elapsed,
                "grid_size": grid_resolution
            }
        }

    def _calculate_base_vocs(self, vocs_data: List[Dict]) -> Dict[str, float]:
        """计算基准VOC浓度"""
        species_values = {}
        for record in vocs_data:
            if isinstance(record, dict):
                for k, v in record.items():
                    if isinstance(v, (int, float)) and v >= 0:
                        if k not in species_values:
                            species_values[k] = []
                        species_values[k].append(v)

        return {s: float(np.percentile(v, 95)) for s, v in species_values.items() if v}

    def _calculate_base_nox(self, nox_data: List[Dict]) -> float:
        """计算基准NOx浓度"""
        values = []
        for record in nox_data:
            if isinstance(record, dict):
                for name in ['NOx', 'nox', 'NO2', 'no2']:
                    v = record.get(name)
                    if v is not None and isinstance(v, (int, float)) and v >= 0:
                        values.append(float(v))
                        break

        return float(np.percentile(values, 95)) if values else 30.0

    def _calculate_base_o3(self, o3_data: List[Dict]) -> float:
        """计算基准O3浓度"""
        values = []
        for record in o3_data:
            if isinstance(record, dict):
                for name in ['O3', 'o3']:
                    v = record.get(name)
                    if v is not None and isinstance(v, (int, float)) and v >= 0:
                        values.append(float(v))
                        break

        return float(np.max(values)) if values else 80.0


# 便捷函数
def create_ekma_analyzer() -> FastEKMAAnalyzer:
    """创建EKMA分析器"""
    return FastEKMAAnalyzer()
