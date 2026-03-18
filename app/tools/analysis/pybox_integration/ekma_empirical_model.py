"""
EKMA经验模型骨架生成器

基于参考实现（D:\溯源\参考\OBM\EKMA.py）的完整复现
核心逻辑：使用VOCs和NOx的二次多项式拟合 + 交互项生成O3响应曲面

参考文献：
- EKMA.py 第51-68行：减排情景模拟
- 坐标系：归一化排放倍数（0-2倍基准排放）
- 峰值：右上角（高VOCs+高NOx）
"""

import numpy as np
from scipy.ndimage import gaussian_filter1d
from typing import Dict, List, Tuple, Optional
import structlog

logger = structlog.get_logger()


class EKMAEmpiricalModel:
    """
    EKMA经验拟合模型

    使用历史观测数据拟合VOCs-O3和NOx-O3的关系，
    生成归一化的EKMA响应曲面（0-2倍基准排放）

    特征：
    - 归一化坐标系（0-2倍）
    - 峰值在右上角
    - 平滑的弧形等值线
    """

    def __init__(
        self,
        base_vocs: float,
        base_nox: float,
        base_o3: float,
        vocs_o3_r2: float = 0.7,
        nox_o3_r2: float = 0.6
    ):
        """
        初始化经验模型

        Args:
            base_vocs: 基准VOCs浓度（ppb，通常为95百分位或平均值）
            base_nox: 基准NOx浓度（ppb）
            base_o3: 基准O3浓度（ppb，通常为最大值）
            vocs_o3_r2: VOCs-O3拟合的R²（默认0.7）
            nox_o3_r2: NOx-O3拟合的R²（默认0.6）
        """
        self.base_vocs = base_vocs
        self.base_nox = base_nox
        self.base_o3 = base_o3
        self.r2_vocs = vocs_o3_r2
        self.r2_nox = nox_o3_r2

        # 多项式拟合系数（将在fit()中更新，或使用默认值）
        self.vocs_poly_coeffs = None  # VOCs的二次多项式系数
        self.nox_poly_coeffs = None   # NOx的二次多项式系数

        logger.info("ekma_empirical_model_initialized",
                   base_vocs=base_vocs, base_nox=base_nox, base_o3=base_o3,
                   r2_vocs=vocs_o3_r2, r2_nox=nox_o3_r2)

    def fit_from_data(
        self,
        vocs_samples: List[float],
        nox_samples: List[float],
        o3_samples: List[float]
    ) -> None:
        """
        从历史观测数据拟合多项式关系

        Args:
            vocs_samples: VOCs观测值列表
            nox_samples: NOx观测值列表
            o3_samples: O3观测值列表
        """
        # 拟合VOCs-O3关系（二次多项式）
        self.vocs_poly_coeffs = np.polyfit(vocs_samples, o3_samples, 2)

        # 拟合NOx-O3关系（二次多项式）
        self.nox_poly_coeffs = np.polyfit(nox_samples, o3_samples, 2)

        # 计算R²
        f_vocs = np.poly1d(self.vocs_poly_coeffs)
        f_nox = np.poly1d(self.nox_poly_coeffs)

        o3_arr = np.array(o3_samples)
        y_pred_vocs = f_vocs(vocs_samples)
        y_pred_nox = f_nox(nox_samples)

        ss_res_vocs = np.sum((y_pred_vocs - o3_arr)**2)
        ss_tot = np.sum((o3_arr - np.mean(o3_arr))**2)
        self.r2_vocs = 1 - (ss_res_vocs / ss_tot)

        ss_res_nox = np.sum((y_pred_nox - o3_arr)**2)
        self.r2_nox = 1 - (ss_res_nox / ss_tot)

        logger.info("ekma_polynomials_fitted",
                   vocs_coeffs=self.vocs_poly_coeffs.tolist(),
                   nox_coeffs=self.nox_poly_coeffs.tolist(),
                   r2_vocs=self.r2_vocs,
                   r2_nox=self.r2_nox)

    def use_default_coefficients(self) -> None:
        """
        使用默认的拟合系数（当无历史数据时）

        默认系数假设：
        - VOCs对O3的二次响应（先增后降）
        - NOx对O3的近线性响应（饱和效应）
        """
        # 默认VOCs多项式：a*x^2 + b*x + c
        # 使假设：VOCs=base_vocs时O3=base_o3，VOCs=0时O3=base_o3*0.5
        vocs_max = self.base_vocs * 2.0
        self.vocs_poly_coeffs = np.array([
            -self.base_o3 / (vocs_max**2),  # a（二次项系数，负值使曲线先增后降）
            2 * self.base_o3 / vocs_max,     # b（一次项系数）
            self.base_o3 * 0.3               # c（常数项）
        ])

        # 默认NOx多项式：a*x^2 + b*x + c
        nox_max = self.base_nox * 2.0
        self.nox_poly_coeffs = np.array([
            -self.base_o3 * 0.3 / (nox_max**2),  # a（轻微二次效应）
            self.base_o3 * 0.8 / nox_max,        # b（主要线性响应）
            self.base_o3 * 0.4                   # c（背景O3）
        ])

        logger.warning("ekma_using_default_coefficients",
                      reason="no_historical_data_available",
                      vocs_coeffs=self.vocs_poly_coeffs.tolist(),
                      nox_coeffs=self.nox_poly_coeffs.tolist())

    def generate_ekma_surface(
        self,
        grid_resolution: int = 201,
        max_multiplier: float = 2.0,
        apply_smoothing: bool = True,
        smoothing_sigma: float = 3.0
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        生成EKMA响应曲面（参考EKMA.py第51-68行）

        Args:
            grid_resolution: 网格分辨率（默认201，参考实现）
            max_multiplier: 最大排放倍数（默认2.0，即0-2倍基准排放）
            apply_smoothing: 是否应用高斯平滑（默认True）
            smoothing_sigma: 平滑参数（默认3.0，参考实现）

        Returns:
            (VOCs_grid, NOx_grid, O3_surface): 归一化网格和O3响应曲面
        """
        # 确保有拟合系数
        if self.vocs_poly_coeffs is None or self.nox_poly_coeffs is None:
            logger.warning("ekma_no_coefficients_using_default")
            self.use_default_coefficients()

        # 1. 创建归一化网格（参考EKMA.py第51-61行）
        vocs_indices = np.arange(grid_resolution)  # 0-200
        nox_indices = np.arange(grid_resolution)

        # 创建2D网格矩阵
        VOCs_grid = np.zeros((grid_resolution, grid_resolution))
        NOx_grid = np.zeros((grid_resolution, grid_resolution))

        vocs_max = self.base_vocs * max_multiplier
        nox_max = self.base_nox * max_multiplier

        # 填充网格（行=VOCs维度，列=NOx维度）
        for i in vocs_indices:
            VOCs_grid[i, :] = vocs_max * (i / (grid_resolution - 1))
        for j in nox_indices:
            NOx_grid[:, j] = nox_max * (j / (grid_resolution - 1))

        logger.info("ekma_grid_created",
                   grid_shape=(grid_resolution, grid_resolution),
                   vocs_range=(0, vocs_max),
                   nox_range=(0, nox_max))

        # 2. 计算O3响应曲面（参考EKMA.py第63-64行）
        f_vocs = np.poly1d(self.vocs_poly_coeffs)
        f_nox = np.poly1d(self.nox_poly_coeffs)

        # 交互项权重（参考实现：r²_nox / r²_vocs）
        interaction_weight = self.r2_nox / self.r2_vocs if self.r2_vocs > 0 else 1.0

        O3_surface = (
            self.r2_vocs * f_vocs(VOCs_grid) +
            self.r2_nox * f_nox(NOx_grid) +
            interaction_weight * VOCs_grid * NOx_grid / (vocs_max * nox_max)  # 归一化交互项
        )

        logger.info("ekma_surface_calculated",
                   interaction_weight=interaction_weight,
                   o3_raw_min=float(np.min(O3_surface)),
                   o3_raw_max=float(np.max(O3_surface)))

        # 3. 归一化到实际观测峰值（参考EKMA.py第66行）
        if O3_surface.max() > 0:
            O3_surface = O3_surface * (self.base_o3 / O3_surface.max())

        # 4. 下界约束（参考EKMA.py第67行）
        o3_min_threshold = self.base_o3 * 0.5
        O3_surface[O3_surface < o3_min_threshold] = o3_min_threshold

        logger.info("ekma_surface_normalized",
                   o3_min_threshold=o3_min_threshold,
                   o3_final_min=float(np.min(O3_surface)),
                   o3_final_max=float(np.max(O3_surface)))

        # 5. 平滑处理（参考EKMA.py第68行）
        if apply_smoothing:
            O3_surface = gaussian_filter1d(O3_surface, sigma=smoothing_sigma, axis=0)
            logger.info("ekma_surface_smoothed",
                       method="gaussian_filter1d",
                       sigma=smoothing_sigma,
                       axis=0)

        return VOCs_grid, NOx_grid, O3_surface

    def get_normalized_coordinates(
        self,
        grid_resolution: int = 201,
        max_multiplier: float = 2.0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        获取归一化坐标轴（0-2倍基准排放）

        用于绘图的X/Y轴坐标

        Returns:
            (vocs_factors, nox_factors): 归一化坐标数组
        """
        vocs_factors = np.linspace(0, max_multiplier, grid_resolution)
        nox_factors = np.linspace(0, max_multiplier, grid_resolution)
        return vocs_factors, nox_factors
