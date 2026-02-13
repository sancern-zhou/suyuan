"""
EKMA L形等值线提取算法

从O3响应曲面提取标准的L形等值线。

L形等值线特征：
- 左臂（VOCs控制臂）：沿左边界（低VOCs）向峰值延伸
- 底臂（NOx控制臂）：沿下边界（低NOx）向峰值延伸
- 拐点：两臂交汇点（峰值附近）

算法策略：
1. 方法1（显式生成）：基于L形模型直接生成L形路径，沿路径采样O3值
2. 方法2（约束拟合）：从标准等值线中筛选最接近L形的，用两段直线拟合
"""

from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import structlog

try:
    from .ekma_lshape_model import LShapeControlLine
except ImportError:
    from ekma_lshape_model import LShapeControlLine

logger = structlog.get_logger()


class LShapeContourExtractor:
    """
    L形等值线提取器

    从O3响应曲面提取符合EKMA理论的L形等值线。

    使用：
        extractor = LShapeContourExtractor(lshape_model)
        contours = extractor.extract_lshape_contours(
            o3_surface, voc_factors, nox_factors, levels=[50, 100, 150]
        )
    """

    def __init__(self, lshape_model: LShapeControlLine):
        """
        初始化L形等值线提取器

        Args:
            lshape_model: L形控制线模型
        """
        self.lshape = lshape_model

        logger.info("lshape_contour_extractor_initialized")

    def extract_lshape_contours(
        self,
        o3_surface: np.ndarray,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray,
        levels: Optional[List[float]] = None,
        n_levels: int = 10,
        n_points_per_arm: int = 50
    ) -> List[Dict[str, Any]]:
        """
        提取多条L形等值线

        Args:
            o3_surface: O3响应曲面矩阵 (shape: [n_nox, n_voc])
            voc_factors: VOCs浓度坐标数组
            nox_factors: NOx浓度坐标数组
            levels: 等值线浓度列表（如果为None，则自动生成）
            n_levels: 自动生成时的等值线数量
            n_points_per_arm: 每个臂的采样点数

        Returns:
            L形等值线列表，每条等值线格式：
            {
                "level": O3浓度值,
                "voc_coords": VOCs坐标数组,
                "nox_coords": NOx坐标数组,
                "is_valid": 是否有效的L形,
                "arm_lengths": {"voc_arm": 长度, "nox_arm": 长度}
            }
        """
        # 自动生成等值线浓度
        if levels is None:
            o3_min = float(np.nanmin(o3_surface))
            o3_max = float(np.nanmax(o3_surface))
            levels = np.linspace(o3_min, o3_max, n_levels).tolist()

        contours = []

        for level in levels:
            contour = self._extract_single_lshape_contour(
                o3_surface, voc_factors, nox_factors, level, n_points_per_arm
            )
            contours.append(contour)

        logger.info(
            "lshape_contours_extracted",
            n_contours=len(contours),
            valid_contours=sum(1 for c in contours if c["is_valid"])
        )

        return contours

    def _extract_single_lshape_contour(
        self,
        o3_surface: np.ndarray,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray,
        target_level: float,
        n_points_per_arm: int
    ) -> Dict[str, Any]:
        """
        提取单条L形等值线

        策略：
        1. 沿L形模型的两个臂采样
        2. 对于每个采样点，在垂直方向搜索目标O3浓度
        3. 组合两个臂的坐标形成完整L形

        Args:
            o3_surface: O3曲面
            voc_factors: VOCs坐标
            nox_factors: NOx坐标
            target_level: 目标O3浓度
            n_points_per_arm: 每个臂的采样点数

        Returns:
            L形等值线字典
        """
        try:
            # 创建插值函数（用于查询O3值）
            from scipy.interpolate import RectBivariateSpline

            # 注意：RectBivariateSpline要求输入为(x, y, z)，其中z.shape = (len(x), len(y))
            # 我们的o3_surface.shape = (n_nox, n_voc)
            spline = RectBivariateSpline(nox_factors, voc_factors, o3_surface)

            # VOCs控制臂：从锚点沿左边界向峰值搜索
            voc_arm_coords = self._trace_arm_contour(
                spline,
                arm_type="voc",
                target_level=target_level,
                n_points=n_points_per_arm,
                voc_factors=voc_factors,
                nox_factors=nox_factors
            )

            # NOx控制臂：从锚点沿下边界向峰值搜索
            nox_arm_coords = self._trace_arm_contour(
                spline,
                arm_type="nox",
                target_level=target_level,
                n_points=n_points_per_arm,
                voc_factors=voc_factors,
                nox_factors=nox_factors
            )

            # 合并两个臂（去除锚点重复）
            if voc_arm_coords and nox_arm_coords:
                voc_coords = np.concatenate([
                    nox_arm_coords["voc"][:-1],  # NOx臂（去除最后一个点）
                    voc_arm_coords["voc"]         # VOCs臂
                ])
                nox_coords = np.concatenate([
                    nox_arm_coords["nox"][:-1],
                    voc_arm_coords["nox"]
                ])

                is_valid = True
                arm_lengths = {
                    "voc_arm": len(voc_arm_coords["voc"]),
                    "nox_arm": len(nox_arm_coords["nox"])
                }
            else:
                # 无法提取有效的L形
                voc_coords = np.array([])
                nox_coords = np.array([])
                is_valid = False
                arm_lengths = {"voc_arm": 0, "nox_arm": 0}

            return {
                "level": float(target_level),
                "voc_coords": voc_coords,
                "nox_coords": nox_coords,
                "is_valid": is_valid,
                "arm_lengths": arm_lengths
            }

        except Exception as e:
            logger.warning(
                "lshape_contour_extraction_failed",
                level=target_level,
                error=str(e)
            )
            return {
                "level": float(target_level),
                "voc_coords": np.array([]),
                "nox_coords": np.array([]),
                "is_valid": False,
                "arm_lengths": {"voc_arm": 0, "nox_arm": 0}
            }

    def _trace_arm_contour(
        self,
        spline,
        arm_type: str,
        target_level: float,
        n_points: int,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        追踪单个臂的等值线

        Args:
            spline: O3曲面插值函数
            arm_type: "voc" 或 "nox"
            target_level: 目标O3浓度
            n_points: 采样点数
            voc_factors: VOCs坐标范围
            nox_factors: NOx坐标范围

        Returns:
            臂坐标字典 {"voc": [...], "nox": [...]} 或 None
        """
        voc_coords = []
        nox_coords = []

        if arm_type == "voc":
            # VOCs控制臂：沿VOCs方向（垂直于x轴）搜索
            # 从锚点到峰值，VOCs从小到大
            voc_samples = np.linspace(
                self.lshape.anchor_voc,
                self.lshape.peak_voc,
                n_points
            )

            for voc in voc_samples:
                # 在当前VOCs位置，沿NOx方向搜索目标O3值
                nox = self._search_o3_level_along_nox(
                    spline, voc, target_level, nox_factors
                )
                if nox is not None:
                    voc_coords.append(voc)
                    nox_coords.append(nox)

        elif arm_type == "nox":
            # NOx控制臂：沿NOx方向（垂直于y轴）搜索
            # 从锚点到峰值，NOx从小到大
            nox_samples = np.linspace(
                self.lshape.anchor_nox,
                self.lshape.peak_nox,
                n_points
            )

            for nox in nox_samples:
                # 在当前NOx位置，沿VOCs方向搜索目标O3值
                voc = self._search_o3_level_along_voc(
                    spline, nox, target_level, voc_factors
                )
                if voc is not None:
                    voc_coords.append(voc)
                    nox_coords.append(nox)

        if len(voc_coords) > 0:
            return {
                "voc": np.array(voc_coords),
                "nox": np.array(nox_coords)
            }
        else:
            return None

    def _search_o3_level_along_nox(
        self,
        spline,
        voc_fixed: float,
        target_level: float,
        nox_range: np.ndarray
    ) -> Optional[float]:
        """
        在固定VOCs位置，沿NOx方向搜索目标O3浓度

        Args:
            spline: O3插值函数
            voc_fixed: 固定的VOCs值
            target_level: 目标O3浓度
            nox_range: NOx搜索范围

        Returns:
            对应的NOx值，如果未找到则返回None
        """
        try:
            # 在nox_range内采样，查找O3值最接近target_level的位置
            nox_samples = np.linspace(nox_range[0], nox_range[-1], 100)
            o3_samples = np.array([
                float(spline(nox, voc_fixed)[0, 0])
                for nox in nox_samples
            ])

            # 找到最接近target_level的位置
            idx = np.argmin(np.abs(o3_samples - target_level))
            closest_nox = nox_samples[idx]
            closest_o3 = o3_samples[idx]

            # 如果误差小于10%，则接受
            if abs(closest_o3 - target_level) / target_level < 0.10:
                return float(closest_nox)
            else:
                return None

        except Exception:
            return None

    def _search_o3_level_along_voc(
        self,
        spline,
        nox_fixed: float,
        target_level: float,
        voc_range: np.ndarray
    ) -> Optional[float]:
        """
        在固定NOx位置，沿VOCs方向搜索目标O3浓度

        Args:
            spline: O3插值函数
            nox_fixed: 固定的NOx值
            target_level: 目标O3浓度
            voc_range: VOCs搜索范围

        Returns:
            对应的VOCs值，如果未找到则返回None
        """
        try:
            # 在voc_range内采样，查找O3值最接近target_level的位置
            voc_samples = np.linspace(voc_range[0], voc_range[-1], 100)
            o3_samples = np.array([
                float(spline(nox_fixed, voc)[0, 0])
                for voc in voc_samples
            ])

            # 找到最接近target_level的位置
            idx = np.argmin(np.abs(o3_samples - target_level))
            closest_voc = voc_samples[idx]
            closest_o3 = o3_samples[idx]

            # 如果误差小于10%，则接受
            if abs(closest_o3 - target_level) / target_level < 0.10:
                return float(closest_voc)
            else:
                return None

        except Exception:
            return None

    def validate_lshape(
        self,
        voc_coords: np.ndarray,
        nox_coords: np.ndarray
    ) -> Dict[str, Any]:
        """
        验证等值线是否符合L形特征

        验证标准：
        1. 有两个明显的臂（斜率差异大）
        2. 有明显的拐点
        3. 左臂接近垂直，底臂接近水平

        Args:
            voc_coords: VOCs坐标数组
            nox_coords: NOx坐标数组

        Returns:
            验证结果字典
        """
        if len(voc_coords) < 10:
            return {
                "is_valid": False,
                "reason": "Too few points",
                "score": 0.0
            }

        try:
            # 分段线性拟合（分为两段）
            mid_idx = len(voc_coords) // 2

            # 底臂（NOx控制臂）：前半段
            nox_arm_voc = voc_coords[:mid_idx]
            nox_arm_nox = nox_coords[:mid_idx]

            # 左臂（VOCs控制臂）：后半段
            voc_arm_voc = voc_coords[mid_idx:]
            voc_arm_nox = nox_coords[mid_idx:]

            # 计算斜率
            nox_arm_slope = (nox_arm_nox[-1] - nox_arm_nox[0]) / (nox_arm_voc[-1] - nox_arm_voc[0] + 1e-10)
            voc_arm_slope = (voc_arm_nox[-1] - voc_arm_nox[0]) / (voc_arm_voc[-1] - voc_arm_voc[0] + 1e-10)

            # 理论斜率：NOx臂应接近水平（slope≈0），VOCs臂应较陡（|slope|>1）
            nox_arm_score = 1.0 / (1.0 + abs(nox_arm_slope))  # 越接近0越好
            voc_arm_score = min(1.0, abs(voc_arm_slope) / 2.0)  # 越陡越好（饱和于2.0）

            # 综合评分
            score = (nox_arm_score + voc_arm_score) / 2.0

            is_valid = score > 0.5

            return {
                "is_valid": is_valid,
                "score": float(score),
                "nox_arm_slope": float(nox_arm_slope),
                "voc_arm_slope": float(voc_arm_slope),
                "reason": "Valid L-shape" if is_valid else "Slope mismatch"
            }

        except Exception as e:
            return {
                "is_valid": False,
                "reason": f"Validation error: {str(e)}",
                "score": 0.0
            }
