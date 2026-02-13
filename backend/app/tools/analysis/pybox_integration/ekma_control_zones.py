"""
EKMA控制区划分算法

基于L形控制线模型，将EKMA等浓度曲面划分为三个控制区：
1. VOCs控制区：减少VOCs更有效（控制线右下方，高NOx+低VOCs）
2. NOx控制区：减少NOx更有效（控制线左上方，低NOx+高VOCs）
3. 协同控制区：需要VOCs和NOx协同控制（控制线附近）

算法原理：
- 计算每个网格点到L形控制线的距离
- 根据距离和方位判断所属控制区
- 协同控制区：控制线附近±10%缓冲区
"""

from typing import Dict, Any, Tuple, Optional
import numpy as np
import structlog

try:
    from .ekma_lshape_model import LShapeControlLine
except ImportError:
    from ekma_lshape_model import LShapeControlLine

logger = structlog.get_logger()


class ControlZoneDivider:
    """
    EKMA控制区划分器

    基于L形控制线将网格划分为三个控制区。

    控制区定义：
    - VOCs控制区 (Zone 1)：控制线右下方，减少VOCs更有效
    - NOx控制区 (Zone 2)：控制线左上方，减少NOx更有效
    - 协同控制区 (Zone 3)：控制线附近，需协同控制

    使用：
        divider = ControlZoneDivider(lshape_model)
        zone_map = divider.divide_zones(voc_grid, nox_grid)
    """

    def __init__(
        self,
        lshape_model: LShapeControlLine,
        transition_buffer_ratio: float = 0.10
    ):
        """
        初始化控制区划分器

        Args:
            lshape_model: L形控制线模型
            transition_buffer_ratio: 协同控制区缓冲比例（0.10 = ±10%）
        """
        self.lshape = lshape_model
        self.buffer_ratio = float(transition_buffer_ratio)

        # 计算缓冲区阈值（基于网格范围）
        voc_range = abs(self.lshape.peak_voc - self.lshape.anchor_voc)
        nox_range = abs(self.lshape.peak_nox - self.lshape.anchor_nox)
        self.buffer_threshold = min(voc_range, nox_range) * self.buffer_ratio

        logger.info(
            "control_zone_divider_initialized",
            buffer_threshold=self.buffer_threshold,
            buffer_ratio=self.buffer_ratio
        )

    def divide_zones(
        self,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray
    ) -> Dict[str, Any]:
        """
        将EKMA网格划分为控制区

        Args:
            voc_factors: VOCs浓度坐标数组 (1D)
            nox_factors: NOx浓度坐标数组 (1D)

        Returns:
            控制区划分结果字典：
            {
                "zone_map": 控制区矩阵 (shape: [n_nox, n_voc])
                             值为 1=VOCs控制区, 2=NOx控制区, 3=协同控制区
                "zone_masks": {
                    "vocs_control": 布尔mask,
                    "nox_control": 布尔mask,
                    "transition": 布尔mask
                },
                "zone_stats": {
                    "vocs_control_ratio": VOCs控制区占比,
                    "nox_control_ratio": NOx控制区占比,
                    "transition_ratio": 协同控制区占比
                },
                "zone_boundaries": {
                    "vocs_control": [(voc, nox), ...],  # 边界坐标
                    "nox_control": [(voc, nox), ...],
                    "transition": [(voc, nox), ...]
                }
            }
        """
        n_voc = len(voc_factors)
        n_nox = len(nox_factors)

        # 初始化控制区map（默认为0=未分类）
        zone_map = np.zeros((n_nox, n_voc), dtype=int)

        # 创建网格
        voc_grid, nox_grid = np.meshgrid(voc_factors, nox_factors, indexing='xy')

        # 遍历每个网格点进行分类
        for i in range(n_nox):
            for j in range(n_voc):
                voc = voc_grid[i, j]
                nox = nox_grid[i, j]

                # 使用L形模型分类点
                classification = self.lshape.classify_point(voc, nox)
                zone_type = classification["zone"]
                dist_voc_arm = classification["distance_to_voc_arm"]
                dist_nox_arm = classification["distance_to_nox_arm"]

                # 判断是否在协同控制区（控制线附近）
                min_distance = min(dist_voc_arm, dist_nox_arm)
                is_transition = min_distance < self.buffer_threshold

                if is_transition:
                    zone_map[i, j] = 3  # 协同控制区
                elif zone_type == "vocs_control":
                    zone_map[i, j] = 1  # VOCs控制区
                elif zone_type == "nox_control":
                    zone_map[i, j] = 2  # NOx控制区
                elif zone_type == "peak":
                    zone_map[i, j] = 3  # 峰值区域归为协同控制区
                else:
                    # 过渡区（根据最近臂决定）
                    if classification["closest_arm"] == "voc":
                        zone_map[i, j] = 1
                    else:
                        zone_map[i, j] = 2

        # 创建布尔mask
        zone_masks = {
            "vocs_control": zone_map == 1,
            "nox_control": zone_map == 2,
            "transition": zone_map == 3
        }

        # 计算统计信息
        total_points = n_voc * n_nox
        zone_stats = {
            "vocs_control_ratio": float(np.sum(zone_masks["vocs_control"])) / total_points,
            "nox_control_ratio": float(np.sum(zone_masks["nox_control"])) / total_points,
            "transition_ratio": float(np.sum(zone_masks["transition"])) / total_points
        }

        # 提取边界坐标（用于可视化）
        zone_boundaries = {
            "vocs_control": self._extract_boundary(zone_masks["vocs_control"], voc_grid, nox_grid),
            "nox_control": self._extract_boundary(zone_masks["nox_control"], voc_grid, nox_grid),
            "transition": self._extract_boundary(zone_masks["transition"], voc_grid, nox_grid)
        }

        logger.info(
            "zones_divided",
            vocs_ratio=zone_stats["vocs_control_ratio"],
            nox_ratio=zone_stats["nox_control_ratio"],
            transition_ratio=zone_stats["transition_ratio"]
        )

        return {
            "zone_map": zone_map,
            "zone_masks": zone_masks,
            "zone_stats": zone_stats,
            "zone_boundaries": zone_boundaries
        }

    def _extract_boundary(
        self,
        mask: np.ndarray,
        voc_grid: np.ndarray,
        nox_grid: np.ndarray
    ) -> np.ndarray:
        """
        提取控制区边界坐标

        Args:
            mask: 控制区布尔mask
            voc_grid: VOCs网格坐标
            nox_grid: NOx网格坐标

        Returns:
            边界坐标数组 (shape: [n_points, 2])
        """
        try:
            from scipy.ndimage import binary_erosion

            # 边界 = mask - erosion(mask)
            eroded = binary_erosion(mask)
            boundary = mask & ~eroded

            # 提取边界坐标
            boundary_indices = np.where(boundary)
            boundary_coords = np.column_stack([
                voc_grid[boundary_indices],
                nox_grid[boundary_indices]
            ])

            return boundary_coords
        except Exception as e:
            logger.warning("boundary_extraction_failed", error=str(e))
            # Fallback: 返回mask内所有点
            indices = np.where(mask)
            return np.column_stack([
                voc_grid[indices],
                nox_grid[indices]
            ])

    def get_zone_colors(self) -> Dict[str, str]:
        """
        获取控制区颜色映射（用于可视化）

        Returns:
            颜色字典
        """
        return {
            "vocs_control": "#4CAF50",  # 绿色（VOCs控制区）
            "nox_control": "#2196F3",   # 蓝色（NOx控制区）
            "transition": "#FFC107"     # 黄色（协同控制区）
        }

    def get_zone_labels_cn(self) -> Dict[str, str]:
        """
        获取控制区中文标签

        Returns:
            中文标签字典
        """
        return {
            "vocs_control": "VOCs控制区",
            "nox_control": "NOx控制区",
            "transition": "协同控制区"
        }

    def recommend_control_strategy(
        self,
        current_voc: float,
        current_nox: float,
        zone_divisions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        根据当前状态点位置推荐控制策略

        Args:
            current_voc: 当前VOCs浓度
            current_nox: 当前NOx浓度
            zone_divisions: 控制区划分结果

        Returns:
            控制策略建议字典
        """
        # 分类当前点
        classification = self.lshape.classify_point(current_voc, current_nox)
        zone_type = classification["zone"]

        # 根据所在区域给出建议
        if zone_type == "vocs_control":
            strategy = {
                "primary_control": "VOCs",
                "reduction_ratio": "VOCs:NOx = 2:1",
                "recommendation": "优先控制VOCs排放源，重点管控芳香烃类",
                "confidence": "high"
            }
        elif zone_type == "nox_control":
            strategy = {
                "primary_control": "NOx",
                "reduction_ratio": "VOCs:NOx = 1:2",
                "recommendation": "优先控制NOx排放源，重点管控燃烧源",
                "confidence": "high"
            }
        elif zone_type == "transition" or zone_type == "peak":
            strategy = {
                "primary_control": "Both",
                "reduction_ratio": "VOCs:NOx = 1:1",
                "recommendation": "VOCs和NOx需协同控制，建立联防联控机制",
                "confidence": "medium"
            }
        else:
            strategy = {
                "primary_control": "Unknown",
                "reduction_ratio": "N/A",
                "recommendation": "需进一步分析确定控制策略",
                "confidence": "low"
            }

        # 添加距离信息
        strategy["distance_to_voc_arm"] = classification["distance_to_voc_arm"]
        strategy["distance_to_nox_arm"] = classification["distance_to_nox_arm"]
        strategy["zone_stats"] = zone_divisions["zone_stats"]

        return strategy
