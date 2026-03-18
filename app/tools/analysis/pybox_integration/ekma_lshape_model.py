"""
EKMA L形控制线数学模型

提供L形控制线的数学建模和几何计算功能。

L形特征（EKMA理论）：
- 峰值点：O3最大值对应的(VOCs, NOx)坐标
- VOCs控制臂（左臂）：从左下角沿左边界向峰值延伸（低VOCs，高NOx）
- NOx控制臂（底臂）：从左下角沿下边界向峰值延伸（低NOx，高VOCs）
- 拐点：峰值点位置

数学表示：
- VOCs控制臂：nox = nox_anchor + slope_voc * (voc - voc_anchor)
- NOx控制臂：voc = voc_anchor + slope_nox * (nox - nox_anchor)
"""

from typing import Tuple, Optional, Dict, Any
import numpy as np
import structlog

logger = structlog.get_logger()


class LShapeControlLine:
    """
    L形控制线模型

    用于描述EKMA等浓度曲面上的L形控制线（峰值O3等值线）。

    属性：
        peak_voc: 峰值点VOCs浓度 (ppb)
        peak_nox: 峰值点NOx浓度 (ppb)
        anchor_voc: L形锚点（左下角）VOCs浓度 (ppb)
        anchor_nox: L形锚点（左下角）NOx浓度 (ppb)
        slope_voc_arm: VOCs控制臂斜率（左臂，沿左边界）
        slope_nox_arm: NOx控制臂斜率（底臂，沿下边界）
    """

    def __init__(
        self,
        peak_voc: float,
        peak_nox: float,
        anchor_voc: float,
        anchor_nox: float,
        slope_voc_arm: float = -1.5,  # 左臂斜率（负值，向下）
        slope_nox_arm: float = 0.3     # 底臂斜率（正值，向右）
    ):
        """
        初始化L形控制线模型

        Args:
            peak_voc: 峰值点VOCs浓度
            peak_nox: 峰值点NOx浓度
            anchor_voc: L形锚点VOCs浓度（通常为网格最小值）
            anchor_nox: L形锚点NOx浓度（通常为网格最小值）
            slope_voc_arm: VOCs控制臂斜率（负数，表示从左下到峰值）
            slope_nox_arm: NOx控制臂斜率（正数，表示从左下到峰值）
        """
        self.peak_voc = float(peak_voc)
        self.peak_nox = float(peak_nox)
        self.anchor_voc = float(anchor_voc)
        self.anchor_nox = float(anchor_nox)
        self.slope_voc_arm = float(slope_voc_arm)
        self.slope_nox_arm = float(slope_nox_arm)

        # 自动计算L形参数
        self._compute_lshape_params()

        logger.info(
            "lshape_model_initialized",
            peak=(self.peak_voc, self.peak_nox),
            anchor=(self.anchor_voc, self.anchor_nox),
            slopes=(self.slope_voc_arm, self.slope_nox_arm)
        )

    def _compute_lshape_params(self):
        """计算L形辅助参数"""
        # VOCs控制臂方程：nox = nox_anchor + slope_voc_arm * (voc - voc_anchor)
        # 计算VOCs控制臂在峰值处的坐标
        self.voc_arm_voc_at_peak = self.peak_voc
        self.voc_arm_nox_at_peak = self.anchor_nox + self.slope_voc_arm * (self.peak_voc - self.anchor_voc)

        # NOx控制臂方程：voc = voc_anchor + slope_nox_arm * (nox - nox_anchor)
        # 计算NOx控制臂在峰值处的坐标
        self.nox_arm_voc_at_peak = self.anchor_voc + self.slope_nox_arm * (self.peak_nox - self.anchor_nox)
        self.nox_arm_nox_at_peak = self.peak_nox

    def point_to_voc_arm_distance(self, voc: float, nox: float) -> Tuple[float, str]:
        """
        计算点到VOCs控制臂的距离

        Args:
            voc: 点的VOCs坐标
            nox: 点的NOx坐标

        Returns:
            distance: 垂直距离（正值表示在臂右侧，负值表示在臂左侧）
            side: "right" 或 "left"
        """
        # VOCs控制臂方程：nox = nox_anchor + slope_voc_arm * (voc - voc_anchor)
        # 点到直线的垂直距离：d = (nox - nox_on_line)
        nox_on_line = self.anchor_nox + self.slope_voc_arm * (voc - self.anchor_voc)
        distance = nox - nox_on_line
        side = "right" if distance > 0 else "left"
        return abs(distance), side

    def point_to_nox_arm_distance(self, voc: float, nox: float) -> Tuple[float, str]:
        """
        计算点到NOx控制臂的距离

        Args:
            voc: 点的VOCs坐标
            nox: 点的NOx坐标

        Returns:
            distance: 垂直距离（正值表示在臂上方，负值表示在臂下方）
            side: "above" 或 "below"
        """
        # NOx控制臂方程：voc = voc_anchor + slope_nox_arm * (nox - nox_anchor)
        # 点到直线的垂直距离：d = (voc - voc_on_line)
        voc_on_line = self.anchor_voc + self.slope_nox_arm * (nox - self.anchor_nox)
        distance = voc - voc_on_line
        side = "above" if distance > 0 else "below"
        return abs(distance), side

    def classify_point(self, voc: float, nox: float) -> Dict[str, Any]:
        """
        分类点相对于L形控制线的位置

        Args:
            voc: 点的VOCs坐标
            nox: 点的NOx坐标

        Returns:
            分类结果字典：
            - zone: "vocs_control" | "nox_control" | "transition" | "peak"
            - distance_to_voc_arm: 到VOCs控制臂的距离
            - distance_to_nox_arm: 到NOx控制臂的距离
            - closest_arm: "voc" | "nox" | "both"
        """
        # 计算到两个臂的距离
        dist_voc_arm, side_voc = self.point_to_voc_arm_distance(voc, nox)
        dist_nox_arm, side_nox = self.point_to_nox_arm_distance(voc, nox)

        # 判断是否在峰值附近（峰值±5%范围）
        voc_range = abs(self.peak_voc - self.anchor_voc)
        nox_range = abs(self.peak_nox - self.anchor_nox)
        is_near_peak = (
            abs(voc - self.peak_voc) < voc_range * 0.05 and
            abs(nox - self.peak_nox) < nox_range * 0.05
        )

        if is_near_peak:
            zone = "peak"
            closest_arm = "both"
        elif side_voc == "right" and side_nox == "below":
            # 在VOCs控制臂右侧且NOx控制臂下方 → VOCs控制区
            zone = "vocs_control"
            closest_arm = "voc" if dist_voc_arm < dist_nox_arm else "nox"
        elif side_voc == "left" and side_nox == "above":
            # 在VOCs控制臂左侧且NOx控制臂上方 → NOx控制区
            zone = "nox_control"
            closest_arm = "nox" if dist_nox_arm < dist_voc_arm else "voc"
        else:
            # 其他情况 → 过渡区
            zone = "transition"
            closest_arm = "voc" if dist_voc_arm < dist_nox_arm else "nox"

        return {
            "zone": zone,
            "distance_to_voc_arm": dist_voc_arm,
            "distance_to_nox_arm": dist_nox_arm,
            "closest_arm": closest_arm,
            "side_voc": side_voc,
            "side_nox": side_nox
        }

    def generate_lshape_path(
        self,
        n_points_per_arm: int = 50
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        生成L形控制线路径坐标

        Args:
            n_points_per_arm: 每个臂的采样点数

        Returns:
            voc_path: VOCs坐标数组
            nox_path: NOx坐标数组
        """
        # VOCs控制臂：从锚点到峰值
        voc_arm_vocs = np.linspace(self.anchor_voc, self.peak_voc, n_points_per_arm)
        voc_arm_noxs = self.anchor_nox + self.slope_voc_arm * (voc_arm_vocs - self.anchor_voc)

        # NOx控制臂：从锚点到峰值
        nox_arm_noxs = np.linspace(self.anchor_nox, self.peak_nox, n_points_per_arm)
        nox_arm_vocs = self.anchor_voc + self.slope_nox_arm * (nox_arm_noxs - self.anchor_nox)

        # 合并两个臂（去除锚点重复）
        voc_path = np.concatenate([nox_arm_vocs[:-1], voc_arm_vocs])
        nox_path = np.concatenate([nox_arm_noxs[:-1], voc_arm_noxs])

        return voc_path, nox_path

    def get_control_line_equation(self) -> str:
        """
        获取控制线方程的文本表示（用于日志和报告）

        Returns:
            方程字符串
        """
        voc_arm_eq = f"VOCs控制臂: NOx = {self.anchor_nox:.2f} + {self.slope_voc_arm:.2f} * (VOCs - {self.anchor_voc:.2f})"
        nox_arm_eq = f"NOx控制臂: VOCs = {self.anchor_voc:.2f} + {self.slope_nox_arm:.2f} * (NOx - {self.anchor_nox:.2f})"
        return f"{voc_arm_eq}\n{nox_arm_eq}"

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式（用于序列化）

        Returns:
            L形模型参数字典
        """
        return {
            "peak": {"voc": self.peak_voc, "nox": self.peak_nox},
            "anchor": {"voc": self.anchor_voc, "nox": self.anchor_nox},
            "slopes": {
                "voc_arm": self.slope_voc_arm,
                "nox_arm": self.slope_nox_arm
            },
            "equation": self.get_control_line_equation()
        }

    @classmethod
    def from_ekma_surface(
        cls,
        o3_surface: np.ndarray,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray,
        auto_detect_slopes: bool = True
    ) -> "LShapeControlLine":
        """
        从EKMA O3曲面自动构建L形模型

        Args:
            o3_surface: O3响应曲面矩阵 (shape: [n_nox, n_voc])
            voc_factors: VOCs浓度坐标数组
            nox_factors: NOx浓度坐标数组
            auto_detect_slopes: 是否自动检测斜率（否则使用默认值）

        Returns:
            LShapeControlLine实例
        """
        # 找到峰值位置
        peak_idx = np.unravel_index(np.nanargmax(o3_surface), o3_surface.shape)
        peak_nox_idx, peak_voc_idx = peak_idx
        peak_voc = float(voc_factors[peak_voc_idx])
        peak_nox = float(nox_factors[peak_nox_idx])

        # 锚点（左下角）
        anchor_voc = float(voc_factors[0])
        anchor_nox = float(nox_factors[0])

        # 自动检测斜率（通过峰值连线）
        if auto_detect_slopes:
            # VOCs控制臂斜率：从锚点到峰值的斜率
            slope_voc_arm = (peak_nox - anchor_nox) / (peak_voc - anchor_voc + 1e-10)

            # NOx控制臂斜率：从锚点到峰值的斜率
            slope_nox_arm = (peak_voc - anchor_voc) / (peak_nox - anchor_nox + 1e-10)

            logger.info(
                "auto_detected_slopes",
                slope_voc_arm=slope_voc_arm,
                slope_nox_arm=slope_nox_arm
            )
        else:
            # 使用理论默认值
            slope_voc_arm = -1.5
            slope_nox_arm = 0.3

        return cls(
            peak_voc=peak_voc,
            peak_nox=peak_nox,
            anchor_voc=anchor_voc,
            anchor_nox=anchor_nox,
            slope_voc_arm=slope_voc_arm,
            slope_nox_arm=slope_nox_arm
        )
