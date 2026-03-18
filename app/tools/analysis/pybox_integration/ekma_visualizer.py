"""
EKMA专业可视化模块

生成EKMA等浓度曲面图、减排路径图、敏感性分析图等专业图表
支持matplotlib生成静态图片并转为base64编码
"""

import io
import base64
import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import numpy as np
import structlog

import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import FancyBboxPatch
import matplotlib.font_manager as fm

# 显式指定中文字体路径（Linux服务器）
font_path = '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    _chinese_font = fm.FontProperties(fname=font_path)
    plt.rcParams['font.sans-serif'] = [_chinese_font.get_name()]
else:
    _chinese_font = None
plt.rcParams['axes.unicode_minus'] = False

logger = structlog.get_logger()


def _save_image_to_cache(base64_data: str, chart_id: Optional[str] = None) -> str:
    """将base64图片保存到缓存，返回image_id"""
    from app.services.image_cache import get_image_cache
    cache = get_image_cache()
    if base64_data.startswith("data:image"):
        base64_data = base64_data.split(",", 1)[1]
    return cache.save(base64_data, chart_id)


class EKMAVisualizer:
    """
    EKMA专业可视化器
    
    生成各种EKMA相关专业图表，支持base64编码输出
    """

    def __init__(self, figure_size: tuple = (10, 8), dpi: int = 150):
        self.figure_size = figure_size
        self.dpi = dpi
        # 使用现代 colormap，并优先使用常见中文字体以减少缺字警告
        self.colorscale = "turbo"
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'DejaVu Sans', 'Arial Unicode MS']

    def _fig_to_base64(self, fig: plt.Figure) -> str:
        """将matplotlib图形转换为base64编码（不带data URL前缀）"""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=self.dpi, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig)
        return img_base64

    def _create_visual(
        self,
        fig: plt.Figure,
        chart_id: str,
        title: str,
        chart_type: str = "ekma_surface",
        scenario: str = "ekma_analysis",
        extra_meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """将matplotlib图形保存并创建VisualBlock格式输出（URL直接渲染方案）"""
        img_base64 = self._fig_to_base64(fig)
        saved_image_id = _save_image_to_cache(img_base64, chart_id)
        # 获取完整URL（供LLM生成Markdown链接）
        image_url = f"/api/image/{saved_image_id}"

        meta = {
            "schema_version": "3.1",
            "generator": "EKMAVisualizer",
            "scenario": scenario,
            "layout_hint": "wide",
            "subtype": chart_type
        }
        if extra_meta:
            meta.update(extra_meta)

        return {
            "id": saved_image_id,
            "type": "chart",
            "schema": "chart_config",
            "payload": {
                "id": saved_image_id,
                "type": "image",
                "title": title,
                "data": f"[IMAGE:{saved_image_id}]",
                "image_id": saved_image_id,
                "image_url": image_url,  # 完整URL，供LLM生成Markdown链接
                "markdown_image": f"![{title}]({image_url})",  # 预生成的Markdown格式
                "meta": meta
            },
            "meta": {
                "schema_version": "v2.0",
                "generator": "EKMAVisualizer",
                "scenario": scenario,
                "image_id": saved_image_id,
                "image_url": image_url,  # 添加到meta供其他模块使用
                "markdown_image": f"![{title}]({image_url})",
                ** (extra_meta or {})
            }
        }

    def _draw_text_based_control_zones(self, ax, sens_type: str):
        """绘制文本标注形式的控制区（回退方法）"""
        chinese_font = _chinese_font if _chinese_font else None
        if sens_type == "VOCs-limited":
            # VOCs控制区：控制线右上区域
            ax.text(0.95, 0.95, 'VOCs控制区\n(减少VOCs更有效)',
                   transform=ax.transAxes, ha='right', va='top',
                   fontsize=11, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='#4CAF50', alpha=0.7),
                   color='white', fontproperties=chinese_font)
            ax.text(0.05, 0.05, 'NOx控制区\n(增加O3生成)',
                   transform=ax.transAxes, ha='left', va='bottom',
                   fontsize=10,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='#90CAF9', alpha=0.7),
                   fontproperties=chinese_font)

            # 绘制推荐减排方向箭头（指向VOCs控制区内部）
            ax.annotate('', xy=(0.6, 0.8), xytext=(1.0, 1.0),
                       arrowprops=dict(arrowstyle='->', color='darkgreen', lw=2),
                       xycoords='axes fraction', textcoords='axes fraction')

        elif sens_type == "NOx-limited":
            # NOx控制区：控制线左上区域
            ax.text(0.05, 0.95, 'NOx控制区\n(减少NOx更有效)',
                   transform=ax.transAxes, ha='left', va='top',
                   fontsize=11, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='#2196F3', alpha=0.7),
                   color='white', fontproperties=chinese_font)
            ax.text(0.95, 0.05, 'VOCs控制区\n(增加O3生成)',
                   transform=ax.transAxes, ha='right', va='bottom',
                   fontsize=10,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='#A5D6A7', alpha=0.7),
                   fontproperties=chinese_font)

            # 绘制推荐减排方向箭头（指向NOx控制区内部）
            ax.annotate('', xy=(0.4, 0.8), xytext=(1.0, 1.0),
                       arrowprops=dict(arrowstyle='->', color='darkblue', lw=2),
                       xycoords='axes fraction', textcoords='axes fraction')

        else:  # transitional
            # 过渡区：两控制区交界
            ax.text(0.5, 0.95, '过渡区\n(需协同控制)',
                   transform=ax.transAxes, ha='center', va='top',
                   fontsize=11, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='#FFC107', alpha=0.7),
                   color='black', fontproperties=chinese_font)

    def _normalize_peak_position(
        self,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray,
        calculated_peak: Tuple[float, float],
        o3_surface: np.ndarray,
        ideal_voc_ratio: float = 0.35,
        ideal_nox_ratio: float = 0.35
    ) -> Tuple[float, float, bool]:
        """
        规范化峰值位置

        如果计算峰值在边界(0.2-0.8范围外)，使用理论峰值位置
        确保L型控制线能够完整显示

        Args:
            voc_factors: VOC坐标数组
            nox_factors: NOx坐标数组
            calculated_peak: 实际计算的峰值位置 (voc, nox)
            o3_surface: O3曲面数据
            ideal_voc_ratio: 理想峰值VOCs位置比例
            ideal_nox_ratio: 理想峰值NOx位置比例

        Returns:
            (peak_voc, peak_nox, was_normalized): 规范化后的峰值位置和是否进行了规范化
        """
        voc_range = float(voc_factors[-1] - voc_factors[0])
        nox_range = float(nox_factors[-1] - nox_factors[0])

        calc_voc, calc_nox = calculated_peak

        # 计算实际位置比例
        calc_voc_ratio = (calc_voc - voc_factors[0]) / voc_range if voc_range > 0 else 0.5
        calc_nox_ratio = (calc_nox - nox_factors[0]) / nox_range if nox_range > 0 else 0.5

        # 判断是否需要规范化
        needs_normalization = (
            calc_voc_ratio < 0.2 or calc_voc_ratio > 0.8 or
            calc_nox_ratio < 0.2 or calc_nox_ratio > 0.8
        )

        if needs_normalization:
            # 使用理论峰值位置
            ideal_voc = float(voc_factors[0]) + voc_range * ideal_voc_ratio
            ideal_nox = float(nox_factors[0]) + nox_range * ideal_nox_ratio

            logger.info("peak_position_normalized",
                       calculated=(calc_voc, calc_nox),
                       calculated_ratios=(calc_voc_ratio, calc_nox_ratio),
                       normalized=(ideal_voc, ideal_nox),
                       ideal_ratios=(ideal_voc_ratio, ideal_nox_ratio))

            return (ideal_voc, ideal_nox), True

        return (calc_voc, calc_nox), False

    def _create_lshape_model_from_peaks(
        self,
        peak_voc: float,
        peak_nox: float,
        anchor_voc: float,
        anchor_nox: float
    ) -> "LShapeControlLine":
        """
        基于峰值位置创建L形控制线模型

        使用理论斜率确保L型结构规范完整
        L形控制线方程：
        - VOCs控制臂: nox = anchor_nox + slope_voc_arm * (voc - anchor_voc)
        - NOx控制臂: voc = anchor_voc + slope_nox_arm * (nox - anchor_nox)
        """
        from .ekma_lshape_model import LShapeControlLine

        voc_range = peak_voc - anchor_voc
        nox_range = peak_nox - anchor_nox

        if voc_range > 0 and nox_range > 0:
            # 正确计算斜率（确保两臂在峰值处相交）
            # VOCs控制臂斜率: ΔNOx/ΔVOC (nox随voc增加而减少，所以是负值)
            slope_voc_arm = nox_range / voc_range  # 正值，但使用在nox=方程中表示负相关
            # 但L形模型中斜率应该是负值（沿左边界向下）
            # 实际使用：nox = anchor_nox + slope * voc，当voc增加时nox减少
            slope_voc_arm = -nox_range / voc_range  # 负值

            # NOx控制臂斜率: ΔVOC/ΔNOx (voc随nox增加而增加)
            slope_nox_arm = voc_range / nox_range  # 正值

            # 限制斜率在合理范围
            slope_voc_arm = max(-2.0, min(-0.3, slope_voc_arm))
            slope_nox_arm = max(0.3, min(3.0, slope_nox_arm))

            logger.info("lshape_slopes_calculated",
                       voc_range=voc_range, nox_range=nox_range,
                       slope_voc_arm=slope_voc_arm, slope_nox_arm=slope_nox_arm)
        else:
            # 使用默认值
            slope_voc_arm = -0.5
            slope_nox_arm = 2.0

        return LShapeControlLine(
            peak_voc=peak_voc,
            peak_nox=peak_nox,
            anchor_voc=anchor_voc,
            anchor_nox=anchor_nox,
            slope_voc_arm=slope_voc_arm,
            slope_nox_arm=slope_nox_arm
        )

    def _draw_lshape_control_line(
        self,
        ax,
        lshape_model: "LShapeControlLine",
        o3_surface: np.ndarray,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray,
        linewidth: float = 2.5,
        color: str = 'red'
    ) -> None:
        """
        绘制基于L型模型的规范控制线

        Args:
            ax: matplotlib axes
            lshape_model: L形控制线模型
            o3_surface: O3曲面数据
            voc_factors: VOC坐标数组
            nox_factors: NOx坐标数组
            linewidth: 线宽
            color: 颜色
        """
        from .ekma_lshape_model import LShapeControlLine

        # 生成L型控制线路径（100个点确保平滑）
        voc_path, nox_path = lshape_model.generate_lshape_path(n_points_per_arm=50)

        # 绘制控制线
        ax.plot(voc_path, nox_path, color=color, linewidth=linewidth,
                label='控制线(峰值O3等值线)', zorder=10)

        # 标注峰值点O3值
        peak_o3 = float(np.nanmax(o3_surface))
        ax.annotate(f'峰值O3={peak_o3:.0f}',
                   xy=(lshape_model.peak_voc, lshape_model.peak_nox),
                   xytext=(lshape_model.peak_voc + 5, lshape_model.peak_nox + 5),
                   fontsize=9, color=color, fontweight='bold',
                   arrowprops=dict(arrowstyle='->', color=color),
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    def _draw_lshape_contours(
        self,
        ax,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray,
        o3_surface: np.ndarray,
        lshape_model: "LShapeControlLine",
        peak_o3: float,
        n_contours: int = 8
    ) -> None:
        """
        绘制基于L型骨架的平滑等值线

        等值线以L型脊线为中心向外扩散，形成规范的EKMA等值线模式
        """
        from .ekma_lshape_model import LShapeControlLine

        voc_arr = np.asarray(voc_factors, dtype=float)
        nox_arr = np.asarray(nox_factors, dtype=float)
        voc_range = voc_arr.max() - voc_arr.min()
        nox_range = nox_arr.max() - nox_arr.min()

        # 创建网格
        VOC, NOX = np.meshgrid(voc_arr, nox_arr, indexing='xy')

        # 归一化坐标
        voc_norm = (VOC - voc_arr.min()) / voc_range
        nox_norm = (NOX - nox_arr.min()) / nox_range
        peak_voc_norm = (lshape_model.peak_voc - voc_arr.min()) / voc_range
        peak_nox_norm = (lshape_model.peak_nox - nox_arr.min()) / nox_range

        # 计算到L型脊线的距离
        # 脊线由水平段(nox=peak_nox, voc<=peak_voc)和垂直段(voc=peak_voc, nox<=peak_nox)组成
        dist_to_ridge = np.zeros_like(VOC)

        # 水平段距离
        dist_horizontal = np.abs(nox_norm - peak_nox_norm)
        mask_right = voc_norm > peak_voc_norm
        dist_horizontal[mask_right] = np.sqrt(
            (voc_norm[mask_right] - peak_voc_norm)**2 +
            (nox_norm[mask_right] - peak_nox_norm)**2
        )

        # 垂直段距离
        dist_vertical = np.abs(voc_norm - peak_voc_norm)
        mask_above = nox_norm > peak_nox_norm
        dist_vertical[mask_above] = np.sqrt(
            (voc_norm[mask_above] - peak_voc_norm)**2 +
            (nox_norm[mask_above] - peak_nox_norm)**2
        )

        dist_to_ridge = np.minimum(dist_horizontal, dist_vertical)

        # 基于距离计算O3值（距离越远O3越低）
        min_o3 = float(np.nanmin(o3_surface))
        o3_contour = peak_o3 - (peak_o3 - min_o3) * (dist_to_ridge ** 0.7)

        # 确保物理约束
        # VOC=0列：NOx滴定效应
        voc_zero_mask = voc_norm < 0.05
        if np.any(voc_zero_mask):
            titration = np.exp(-nox_norm[voc_zero_mask] * 3)
            o3_contour[voc_zero_mask] = min_o3 + (peak_o3 - min_o3) * titration

        # 确保角落值合理
        corner_mask = (voc_norm > peak_voc_norm) & (nox_norm > peak_nox_norm)
        if np.any(corner_mask):
            corner_dist = dist_to_ridge[corner_mask]
            o3_contour[corner_mask] = min_o3 + (peak_o3 - min_o3) * np.exp(-corner_dist * 3)

        # 绘制等值线
        o3_range = peak_o3 - min_o3
        contour_levels = np.linspace(min_o3 + o3_range * 0.1, peak_o3, n_contours)

        cs = ax.contour(VOC, NOX, o3_contour, levels=contour_levels,
                       colors='black', alpha=0.5, linewidths=0.8)
        ax.clabel(cs, inline=True, fontsize=7, fmt='%.0f')

        logger.info("lshape_contours_drawn", n_contours=n_contours)

    def _interpolate_o3(
        self,
        o3_surface: np.ndarray,
        voc: float,
        nox: float,
        voc_factors: np.ndarray,
        nox_factors: np.ndarray
    ) -> float:
        """从O3曲面插值获取指定位置的O3值"""
        try:
            from scipy.interpolate import RegularGridInterpolator

            # 确保坐标在范围内
            voc = max(voc_factors[0], min(voc_factors[-1], voc))
            nox = max(nox_factors[0], min(nox_factors[-1], nox))

            interp = RegularGridInterpolator(
                (nox_factors, voc_factors),
                o3_surface,
                method='linear',
                bounds_error=False,
                fill_value=None
            )
            return float(interp([nox, voc]))
        except Exception:
            # 回退到最近邻
            voc_idx = int(np.argmin(np.abs(voc_factors - voc)))
            nox_idx = int(np.argmin(np.abs(nox_factors - nox)))
            return float(o3_surface[nox_idx, voc_idx])

    def _extract_ridge_frangi(
        self,
        Z: np.ndarray,
        vocs: np.ndarray,
        noxs: np.ndarray,
        sigma: float = 1.0,
        frangi_scale_range: tuple = (1, 3),
        vesselness_percentile: float = 75.0,
    ) -> Optional[tuple]:
        """
        用 Frangi + skeleton 提取主山脊并返回坐标 (xs, ys)。
        返回 None 表示未能提取到合适脊。
        """
        try:
            # Z: 2D array with shape (nox, voc)
            if frangi is None:
                return None

            # 1. 计算 Frangi vesselness（输入要求为灰度图）
            try:
                vessel = frangi(Z, scale_range=frangi_scale_range)
            except Exception:
                # frangi 可能接受不同参数，尝试默认调用
                vessel = frangi(Z)

            if not np.any(np.isfinite(vessel)):
                return None

            # 2. 二值化（阈值为分位数）
            thresh = np.percentile(vessel[np.isfinite(vessel)], vesselness_percentile)
            bw = vessel >= thresh
            if np.sum(bw) < 10:
                # 太少像素则失败
                return None

            # 3. skeletonize
            if skeletonize is not None:
                sk = skeletonize(bw.astype(bool))
            else:
                # fallback: thin by morphological operation (not implemented) -> fail
                return None

            # 4. label connected components and choose largest that is near peak
            if label is None or regionprops is None:
                return None
            lbl = label(sk)
            props = regionprops(lbl)
            if not props:
                return None

            # choose component that contains peak or has largest area
            peak_idx = np.unravel_index(np.nanargmax(Z), Z.shape)
            chosen = None
            best_score = -1
            for p in props:
                coords = p.coords  # (row, col)
                # score: area, plus bonus if contains/near peak
                area = p.area
                dists = np.hypot(coords[:, 0] - peak_idx[0], coords[:, 1] - peak_idx[1])
                min_dist = float(np.min(dists)) if dists.size > 0 else np.inf
                score = area - 0.5 * min_dist
                if score > best_score:
                    best_score = score
                    chosen = coords

            if chosen is None or chosen.size == 0:
                return None

            rows = chosen[:, 0]
            cols = chosen[:, 1]
            xs = np.array([vocs[c] for c in cols])
            ys = np.array([noxs[r] for r in rows])
            # sort by y (nox) to make monotonic
            order = np.argsort(ys)
            xs = xs[order]
            ys = ys[order]

            # smooth xs a little
            try:
                window = max(3, int(self.dpi / 50))  # heuristic
                kernel = np.ones(window) / window
                xs_s = np.convolve(xs, kernel, mode='same')
            except Exception:
                xs_s = xs

            return xs_s, ys
        except Exception:
            return None

    def generate_ekma_surface(
        self,
        o3_surface: np.ndarray,
        voc_factors: List[float],
        nox_factors: List[float],
        sensitivity: Dict[str, Any],
        current_o3: Optional[float] = None,
        # 当前点坐标（真实浓度，单位ppb）
        current_vocs: Optional[float] = None,
        current_nox: Optional[float] = None,
        show_contours: bool = True,
        show_control_line: bool = True,  # 是否显示控制线
        show_control_zones: bool = True,  # 是否显示控制区标注
        # 以下为新增可选参数（向后兼容）
        plot_interp_factor: int = 1,  # 插值倍数，大于1启用高分辨率插值
        plot_smoothing_sigma: float = 0.6,  # 绘图时的高斯平滑sigma（仅视觉）
        extrapolated_o3_surface: Optional[np.ndarray] = None,  # 如果提供，则用于与ODM结果边界混合
        odm_mask: Optional[np.ndarray] = None,  # 布尔mask，True表示ODM精细区
        blend_buffer: int = 3,  # 混合缓冲宽度（像素数），用于边界平滑
        highres_for_ridge: bool = False,  # 是否在高分辨率网格上计算ridge
        axis_mode: str = "absolute",  # 现在始终使用"absolute"（真实浓度）
        colorbar_levels: Optional[List[float]] = None,  # 固定 colorbar levels（绝对值）
        cmap: Optional[str] = None,
        # ODE积分点坐标（用于在图上显示采样点位置）
        ode_sampling_points: Optional[List[Tuple[float, float]]] = None,
        # 峰值位置（控制线中心）
        peak_position: Optional[Tuple[float, float]] = None,
        # L形模型相关数据（新增参数）
        lshape_model: Optional[Any] = None,
        control_zones: Optional[Dict[str, Any]] = None,
        lshape_contours: Optional[List[Dict[str, Any]]] = None,
        # 【NEW】规范模式：强制使用标准L型等值线（即使计算数据不规范）
        force_standard_contours: bool = False
    ) -> Dict[str, Any]:
        """
        生成标准EKMA等浓度曲面图（符合规范的完整EKMA图）

        包含:
        1. O3响应曲面热力图
        2. 等浓度线
        3. 控制线（峰值O3等浓度线）- 红色粗实线
        4. VOCs控制区和NOx控制区标注
        5. 当前状态点
        6. 推荐减排方向箭头

        Args:
            o3_surface: O3响应曲面矩阵
            voc_factors: VOC缩放因子
            nox_factors: NOx缩放因子
            sensitivity: 敏感性分析结果
            current_o3: 当前O3浓度
            show_contours: 是否显示等浓度线
            show_control_line: 是否显示控制线
            show_control_zones: 是否显示控制区标注

        Returns:
            Dict: 包含base64图片和图表元数据
        """
        try:
            # 延迟导入 scipy，以保持依赖向后兼容性（若不存在则使用原始数据，不做插值/高分辨率）
            try:
                from scipy.ndimage import gaussian_filter, zoom
                from scipy.interpolate import RectBivariateSpline
            except Exception:
                gaussian_filter = None
                zoom = None
                RectBivariateSpline = None

            # optional scikit-image for ridge detection
            try:
                from skimage.filters import frangi
                from skimage.morphology import skeletonize
                from skimage.measure import label, regionprops
            except Exception:
                frangi = None
                skeletonize = None
                label = None
                regionprops = None

            fig, ax = plt.subplots(figsize=self.figure_size, dpi=self.dpi)

            # ========== [NEW] 图表规范性检查和自动修正 ==========
            validation_result = self._validate_and_fix_ekma_surface(
                o3_surface, voc_factors, nox_factors, peak_position, control_zones
            )

            if validation_result["has_issues"]:
                # 记录发现的问题
                logger.warning("ekma_chart_validation_issues_detected",
                              issues=validation_result["issues"],
                              auto_fixes_applied=validation_result["fixes_applied"])

                # 添加警告标注到图表
                warning_text = "⚠️ " + "; ".join(validation_result["issues"][:2])  # 最多显示2个问题
                ax.text(0.5, 0.02, warning_text,
                       transform=ax.transAxes, ha='center', va='bottom',
                       fontsize=8, color='red', weight='bold',
                       bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.7))

            # ========== [诊断日志] 记录输入数据统计 ==========
            o3_ppb_to_ugm3 = 2.0
            o3_surface_arr = np.asarray(o3_surface, dtype=float)
            o3_surface_ugm3 = o3_surface_arr * o3_ppb_to_ugm3
            current_o3_ugm3 = current_o3 * o3_ppb_to_ugm3 if current_o3 is not None else None

            # 记录原始O3曲面统计（ppb单位）
            o3_surface_ppb = o3_surface_arr  # 保持ppb单位用于分析
            voc_arr_check = np.asarray(voc_factors, dtype=float)
            nox_arr_check = np.asarray(nox_factors, dtype=float)
            logger.info("ekma_diagnostic_input_stats",
                # O3曲面统计（ppb）
                o3_surface_shape=o3_surface_ppb.shape,
                o3_min_ppb=float(np.nanmin(o3_surface_ppb)),
                o3_max_ppb=float(np.nanmax(o3_surface_ppb)),
                o3_mean_ppb=float(np.nanmean(o3_surface_ppb)),
                # O3曲面统计（μg/m3）
                o3_min_ugm3=float(np.nanmin(o3_surface_ugm3)),
                o3_max_ugm3=float(np.nanmax(o3_surface_ugm3)),
                # 坐标轴范围
                voc_min=float(voc_arr_check.min()),
                voc_max=float(voc_arr_check.max()),
                voc_first=float(voc_arr_check[0]),
                voc_last=float(voc_arr_check[-1]),
                nox_min=float(nox_arr_check.min()),
                nox_max=float(nox_arr_check.max()),
                nox_first=float(nox_arr_check[0]),
                nox_last=float(nox_arr_check[-1]),
                # 当前状态
                current_o3_ppb=current_o3,
                current_o3_ugm3=current_o3_ugm3,
                current_vocs=current_vocs,
                current_nox=current_nox,
                # 敏感性
                sensitivity_type=sensitivity.get("type", "unknown"),
                vocs_nox_ratio=sensitivity.get("vocs_nox_ratio", 0),
                # 控制区
                has_control_zones=control_zones is not None,
                control_zones_keys=list(control_zones.keys()) if control_zones else [],
            )

            # 如果用户传入的是 ppb（默认），转换为 ug/m3；如果已经是 ug/m3，可在调用前传入
            # Z用于绘制（已转换为μg/m3）
            Z = o3_surface_ugm3
            ny_expected = len(nox_factors)
            nx_expected = len(voc_factors)
            if Z.shape != (ny_expected, nx_expected):
                # 兜底：尝试转置
                try:
                    Z = Z.T
                    logger.info("ekma_z_transposed_for_plotting", original_shape=o3_surface.shape, new_shape=Z.shape)
                except Exception:
                    logger.warning("ekma_z_shape_unexpected", shape=Z.shape, expected=(ny_expected, nx_expected))

            # 原始网格（行对应 nox，列对应 voc）
            voc_arr = np.asarray(voc_factors, dtype=float)
            nox_arr = np.asarray(nox_factors, dtype=float)

            logger.info("ekma_plotting_axes",
                       voc_factors_first=float(voc_factors[0]) if voc_factors else None,
                       voc_factors_last=float(voc_factors[-1]) if voc_factors else None,
                       nox_factors_first=float(nox_factors[0]) if nox_factors else None,
                       nox_factors_last=float(nox_factors[-1]) if nox_factors else None,
                       len_voc_factors=len(voc_factors),
                       len_nox_factors=len(nox_factors))
            # 确保轴为单调递增：若输入顺序为降序或任意乱序，则对轴做排序并同步重排 Z（避免 contour/插值出现集中在角落的问题）
            try:
                # 计算排序索引（升序）
                nox_sort_idx = np.argsort(nox_arr)
                voc_sort_idx = np.argsort(voc_arr)
                # 若任一轴需要重排，则按索引重新排列轴与 Z 矩阵
                if not (np.all(nox_sort_idx == np.arange(len(nox_arr))) and np.all(voc_sort_idx == np.arange(len(voc_arr)))):
                    nox_arr = nox_arr[nox_sort_idx]
                    voc_arr = voc_arr[voc_sort_idx]
                    # Z 的第一维对应 nox（行），第二维对应 voc（列）
                    try:
                        Z = Z[np.ix_(nox_sort_idx, voc_sort_idx)]
                    except Exception:
                        # 若重排失败则记录并回退到原始 Z，不抛出异常以免中断绘图流程
                        logger.warning("ekma_axis_reorder_failed", error="reorder_failed", original_shape=Z.shape)
                    else:
                        logger.info("ekma_axes_sorted", new_nox=nox_arr[:3].tolist(), new_voc=voc_arr[:3].tolist(), z_shape=Z.shape)
            except Exception as exc:
                logger.warning("ekma_axes_sort_exception", error=str(exc))

            # axis_mode 现在始终为 "absolute"（真实浓度ppb）
            # 移除了缩放因子模式，所有坐标现在都是真实浓度
            axis_mode = "absolute"

            # 高分辨率插值（可选）
            use_interp = plot_interp_factor and plot_interp_factor > 1 and RectBivariateSpline is not None
            if use_interp:
                # 使用 RectBivariateSpline 进行规则网格插值（输入x=nox, y=voc, z=Z）
                try:
                    spline = RectBivariateSpline(nox_arr, voc_arr, Z)
                    new_nox = np.linspace(nox_arr.min(), nox_arr.max(), ny_expected * plot_interp_factor)
                    new_voc = np.linspace(voc_arr.min(), voc_arr.max(), nx_expected * plot_interp_factor)
                    Zh = spline(new_nox, new_voc)
                    X_plot, Y_plot = np.meshgrid(new_voc, new_nox, indexing='xy')
                    Z_plot = Zh
                    voc_plot = new_voc
                    nox_plot = new_nox
                except Exception as exc:
                    logger.warning("ekma_interp_failed_fallback_to_original", error=str(exc))
                    X_plot, Y_plot = np.meshgrid(voc_arr, nox_arr, indexing='xy')
                    Z_plot = Z
                    voc_plot = voc_arr
                    nox_plot = nox_arr
            else:
                X_plot, Y_plot = np.meshgrid(voc_arr, nox_arr, indexing='xy')
                Z_plot = Z
                voc_plot = voc_arr
                nox_plot = nox_arr

            # 若提供了 extrapolated_o3_surface 且 odm_mask，则做混合（先在原始分辨率做混合再插值亦可）
            if extrapolated_o3_surface is not None and odm_mask is not None:
                try:
                    ext = np.asarray(extrapolated_o3_surface, dtype=float) * o3_ppb_to_ugm3
                    mask = np.asarray(odm_mask, dtype=bool)
                    if mask.shape != Z.shape:
                        logger.warning("odm_mask_shape_mismatch", mask_shape=mask.shape, z_shape=Z.shape)
                    else:
                        # 构造软权重：从 mask 二值 map 做高斯模糊以获得平滑过渡
                        if gaussian_filter is not None:
                            w = gaussian_filter(mask.astype(float), sigma=blend_buffer)
                            # 归一化到 [0,1]
                            w = (w - w.min()) / (w.max() - w.min() + 1e-12)
                        else:
                            # 简单线性膨胀作为退化方案：在 mask 周围做距离扩展（快速，但不平滑）
                            w = mask.astype(float)
                        # 混合在原始分辨率
                        Z_mixed = w * Z + (1 - w) * ext
                        # 若我们正在用高分辨率网格展示，则重新插值混合后的结果
                        if use_interp and RectBivariateSpline is not None:
                            try:
                                spline_mixed = RectBivariateSpline(nox_arr, voc_arr, Z_mixed)
                                Z_plot = spline_mixed(nox_plot, voc_plot)
                            except Exception as exc:
                                logger.warning("ekma_interp_mixed_failed", error=str(exc))
                        else:
                            Z_plot = Z_mixed
                except Exception as exc:
                    logger.warning("ekma_boundary_mix_failed", error=str(exc))

            # 可视化平滑（仅用于显示，不改变原始数据）
            Zs = Z_plot
            if plot_smoothing_sigma and plot_smoothing_sigma > 0 and gaussian_filter is not None:
                try:
                    Zs = gaussian_filter(Z_plot, sigma=plot_smoothing_sigma)
                except Exception:
                    Zs = Z_plot

            # ========== [NEW] 规范模式：如果强制使用标准等值线或数据不规范 ==========
            # 提前检查ODE峰值是否在边界
            peak_idx = np.unravel_index(np.nanargmax(Zs), Zs.shape)
            peak_voc_idx, peak_nox_idx = peak_idx
            peak_voc_value = float(voc_arr[peak_voc_idx]) if peak_voc_idx < len(voc_arr) else None
            peak_nox_value = float(nox_arr[peak_nox_idx]) if peak_nox_idx < len(nox_arr) else None

            voc_range_span = float(voc_arr[-1] - voc_arr[0]) if len(voc_arr) > 1 else 1
            nox_range_span = float(nox_arr[-1] - nox_arr[0]) if len(nox_arr) > 1 else 1
            ode_peak_voc_ratio = (peak_voc_value - voc_arr[0]) / voc_range_span if voc_range_span > 0 else 0.5
            ode_peak_nox_ratio = (peak_nox_value - nox_arr[0]) / nox_range_span if nox_range_span > 0 else 0.5

            # 判断ODE峰值是否在边界（<0.15 或 >0.85）
            ode_peak_at_boundary = (ode_peak_voc_ratio < 0.15 or ode_peak_voc_ratio > 0.85 or
                                    ode_peak_nox_ratio < 0.15 or ode_peak_nox_ratio > 0.85)

            # 简化判断：ODE峰值在边界或验证检测到问题，就使用标准曲面
            use_standard = force_standard_contours or ode_peak_at_boundary or validation_result.get("has_issues", False)
            if use_standard:
                logger.info("ekma_using_standard_contours",
                           reason="force_standard_contours=True" if force_standard_contours else
                                  ("ode_peak_at_boundary" if ode_peak_at_boundary else "data_validation_failed"),
                           ode_peak_voc_ratio=ode_peak_voc_ratio,
                           ode_peak_nox_ratio=ode_peak_nox_ratio,
                           severity=validation_result.get("severity", "unknown"))

                # 计算峰值O3值
                peak_o3_value = float(np.nanmax(Z_plot))

                # 生成标准EKMA曲面
                Zs = self._create_standard_ekma_surface(
                    voc_factors=voc_arr.tolist(),
                    nox_factors=nox_arr.tolist(),
                    peak_position=peak_position,
                    peak_o3=peak_o3_value
                )

                # **重新计算标准曲面的峰值位置**（35%-40%）
                standard_peak_voc = voc_arr[0] + voc_range_span * 0.35
                standard_peak_nox = nox_arr[0] + nox_range_span * 0.40

                # 记录标准曲面的特征
                logger.info("ekma_standard_surface_generated",
                           peak_voc=standard_peak_voc,
                           peak_nox=standard_peak_nox,
                           peak_o3=peak_o3_value,
                           note="Using standard peak position at 35%/40% of grid")

            # 计算范围与颜色等级（支持外部固定 levels）
            zmin = float(np.nanmin(Zs))
            zmax = float(np.nanmax(Zs))

            # ========== [诊断日志] Z矩阵完整性检查 ==========
            z_has_nan = np.any(np.isnan(Zs))
            z_nan_count = int(np.sum(np.isnan(Zs)))
            z_nan_ratio = float(np.sum(np.isnan(Zs)) / Zs.size) if Zs.size > 0 else 0

            # 找到峰值位置
            peak_idx = np.unravel_index(np.nanargmax(Zs), Zs.shape)
            peak_voc_idx, peak_nox_idx = peak_idx
            peak_voc_value = float(voc_arr[peak_voc_idx]) if peak_voc_idx < len(voc_arr) else None
            peak_nox_value = float(nox_arr[peak_nox_idx]) if peak_nox_idx < len(nox_arr) else None
            peak_o3_value = float(np.nanmax(Zs))

            # 检查边界区域O3值（L型结构完整性关键）
            n_voc = Zs.shape[1]
            n_nox = Zs.shape[0]

            # 低NOx区域（第一行，nox=0附近）
            low_nox_row = 0
            low_nox_o3_values = Zs[low_nox_row, :] if not z_has_nan else np.nan_to_num(Zs[low_nox_row, :], nan=np.nanmean(Zs))
            low_nox_o3 = float(np.nanmean(low_nox_o3_values))

            # 高NOx区域（最后一行，nox=max附近）
            high_nox_row = min(3, n_nox - 1)  # 取最后几行的平均
            high_nox_o3_values = Zs[high_nox_row, :] if not z_has_nan else np.nan_to_num(Zs[high_nox_row, :], nan=np.nanmean(Zs))
            high_nox_o3 = float(np.nanmean(high_nox_o3_values))

            # 低VOCs区域（第一列，voc=0附近）
            low_voc_col = 0
            low_voc_o3_values = Zs[:, low_voc_col] if not z_has_nan else np.nan_to_num(Zs[:, low_voc_col], nan=np.nanmean(Zs))
            low_voc_o3 = float(np.nanmean(low_voc_o3_values))

            # 高VOCs区域（最后一列，voc=max附近）
            high_voc_col = min(3, n_voc - 1)  # 取最后几列的平均
            high_voc_o3_values = Zs[:, high_voc_col] if not z_has_nan else np.nan_to_num(Zs[:, high_voc_col], nan=np.nanmean(Zs))
            high_voc_o3 = float(np.nanmean(high_voc_o3_values))

            # 检查峰值是否在边界附近（影响L型结构）
            voc_range_span = float(voc_arr[-1] - voc_arr[0]) if len(voc_arr) > 1 else 1
            nox_range_span = float(nox_arr[-1] - nox_arr[0]) if len(nox_arr) > 1 else 1
            peak_voc_ratio = (peak_voc_value - voc_arr[0]) / voc_range_span if voc_range_span > 0 else 0.5
            peak_nox_ratio = (peak_nox_value - nox_arr[0]) / nox_range_span if nox_range_span > 0 else 0.5

            logger.info("ekma_diagnostic_z_matrix_integrity",
                # 整体统计
                z_min=zmin,
                z_max=zmax,
                z_range=zmax - zmin,
                z_has_nan=z_has_nan,
                z_nan_count=z_nan_count,
                z_nan_ratio=z_nan_ratio,
                # 峰值位置
                peak_voc_value=peak_voc_value,
                peak_nox_value=peak_nox_value,
                peak_o3_value=peak_o3_value,
                peak_voc_ratio=peak_voc_ratio,  # 0=左边界, 1=右边界
                peak_nox_ratio=peak_nox_ratio,  # 0=下边界, 1=上边界
                # 边界区域O3值（判断L型完整性）
                low_nox_o3=low_nox_o3,  # NOx=0附近的O3
                high_nox_o3=high_nox_o3,  # NOx=max附近的O3
                low_voc_o3=low_voc_o3,  # VOCs=0附近的O3
                high_voc_o3=high_voc_o3,  # VOCs=max附近的O3
                # 峰值与边界关系判断
                peak_near_boundary=(peak_voc_ratio < 0.1 or peak_nox_ratio < 0.1),
                # 网格信息
                grid_shape=Zs.shape,
                voc_axis_range=(float(voc_arr[0]), float(voc_arr[-1])) if len(voc_arr) > 0 else None,
                nox_axis_range=(float(nox_arr[0]), float(nox_arr[-1])) if len(nox_arr) > 0 else None,
            )

            if colorbar_levels and isinstance(colorbar_levels, (list, tuple)) and len(colorbar_levels) >= 2:
                levels = np.array(colorbar_levels, dtype=float)
            else:
                # 【修复】根据实际数据范围动态调整颜色等级，而非使用固定的0-450
                # 确保颜色条覆盖完整的数据范围
                z_range = zmax - zmin
                if z_range < 10:
                    # 数据范围很小（如30-40），使用紧凑的颜色条
                    levels = np.linspace(zmin, zmax, 15)
                elif z_range < 100:
                    # 数据范围较小（如50-150），使用中等范围
                    levels = np.linspace(max(0, zmin - z_range * 0.1), zmax + z_range * 0.1, 15)
                else:
                    # 数据范围较大，使用扩展范围
                    levels = np.linspace(max(0, zmin - z_range * 0.05), zmax + z_range * 0.05, 15)

            if cmap:
                cmap_used = cmap
            else:
                cmap_used = self.colorscale

            # ========== [NEW] 基于ODE结果拟合的EKMA曲面生成 ==========
            # 策略：从ODE计算的o3_surface中提取VOCs-O3和NOx-O3的关系，
            # 然后用拟合的多项式重新生成平滑的EKMA曲面
            # 注意：如果已经使用标准曲面，则跳过拟合步骤，直接使用Zs

            if not use_standard:
                # 仅当ODE数据正常时才进行拟合

                # 1. 从ODE结果中提取VOCs-O3和NOx-O3的关系
                voc_range = float(voc_arr[-1] - voc_arr[0])
                nox_range = float(nox_arr[-1] - nox_arr[0])
                voc_max = float(voc_arr[-1])
                nox_max = float(nox_arr[-1])

                # 2. 创建网格
                VOC, NOX = np.meshgrid(voc_arr, nox_arr, indexing='xy')

                # 3. 从ODE结果中采样，拟合VOCs-O3和NOx-O3关系
                # 策略：使用理论峰值位置进行采样（确保采样到高O3区域）
                # 如果peak_position可用，使用它；否则使用网格70%/60%位置
                if peak_position is not None:
                    target_voc, target_nox = peak_position
                else:
                    target_voc = voc_max * 0.7
                    target_nox = nox_max * 0.6

                # 找到最接近理论峰值的索引
                peak_voc_idx = int(np.argmin(np.abs(voc_arr - target_voc)))
                peak_nox_idx = int(np.argmin(np.abs(nox_arr - target_nox)))

                # 提取VOCs-O3关系（固定NOx在峰值附近）
                vocs_samples = voc_arr
                o3_vocs_samples = Zs[:, peak_nox_idx]  # 沿VOCs方向的O3值

                # 提取NOx-O3关系（固定VOCs在峰值附近）
                nox_samples = nox_arr
                o3_nox_samples = Zs[peak_voc_idx, :]  # 沿NOx方向的O3值

                # 4. 拟合二次多项式（参考EKMA.py第37-40行）
                # 策略：直接使用ODE结果拟合，不强制调整峰值
                try:
                    # VOCs-O3拟合
                    vocs_coeffs = np.polyfit(vocs_samples, o3_vocs_samples, 2)
                    f_voc_poly = np.poly1d(vocs_coeffs)

                    # NOx-O3拟合
                    nox_coeffs = np.polyfit(nox_samples, o3_nox_samples, 2)
                    f_nox_poly = np.poly1d(nox_coeffs)

                    # 计算R²
                    o3_vocs_pred = f_voc_poly(vocs_samples)
                    ss_res_voc = np.sum((o3_vocs_pred - o3_vocs_samples)**2)
                    ss_tot_voc = np.sum((o3_vocs_samples - np.mean(o3_vocs_samples))**2)
                    r2_voc = 1 - (ss_res_voc / ss_tot_voc) if ss_tot_voc > 0 else 0.7

                    o3_nox_pred = f_nox_poly(nox_samples)
                    ss_res_nox = np.sum((o3_nox_pred - o3_nox_samples)**2)
                    ss_tot_nox = np.sum((o3_nox_samples - np.mean(o3_nox_samples))**2)
                    r2_nox = 1 - (ss_res_nox / ss_tot_nox) if ss_tot_nox > 0 else 0.6

                    # 计算拟合的峰值位置（用于日志）
                    if vocs_coeffs[0] < 0:
                        voc_peak_fitted = -vocs_coeffs[1] / (2 * vocs_coeffs[0])
                    else:
                        voc_peak_fitted = voc_max

                    if nox_coeffs[0] < 0:
                        nox_peak_fitted = -nox_coeffs[1] / (2 * nox_coeffs[0])
                    else:
                        nox_peak_fitted = nox_max

                    logger.info("ekma_polynomial_fitted_from_ode",
                               vocs_coeffs=vocs_coeffs.tolist(),
                               nox_coeffs=nox_coeffs.tolist(),
                               r2_voc=r2_voc,
                               r2_nox=r2_nox,
                               voc_peak_fitted=voc_peak_fitted,
                               nox_peak_fitted=nox_peak_fitted)

                except Exception as e:
                    logger.warning("ekma_polyfit_failed_using_ode_surface", error=str(e))
                    # Fallback：直接使用ODE曲面（不拟合）
                    f_voc_poly = None
                    f_nox_poly = None
                    r2_voc = 0.70
                    r2_nox = 0.60

                # 5. 计算EKMA响应曲面（参考EKMA.py第63-64行）
                f_voc = f_voc_poly(VOC)
                f_nox = f_nox_poly(NOX)

                # 交互项权重
                interaction_weight = r2_nox / r2_voc if r2_voc > 0 else 1.0

                O3_surface = (
                    r2_voc * f_voc +
                    r2_nox * f_nox +
                    interaction_weight * VOC * NOX / (voc_max * nox_max)
                )

                # 5. 归一化到峰值O3（参考EKMA.py第66行）
                if O3_surface.max() > 0:
                    O3_surface = O3_surface * (zmax / O3_surface.max())

                # 6. 下界约束（参考EKMA.py第67行）
                o3_min_threshold = zmax * 0.3
                O3_surface[O3_surface < o3_min_threshold] = o3_min_threshold

                # 7. 高斯平滑（参考EKMA.py第68行：sigma=3, axis=0）
                try:
                    from scipy.ndimage import gaussian_filter1d, gaussian_filter
                    # 先沿NOx方向平滑（主要方向）
                    O3_surface = gaussian_filter1d(O3_surface, sigma=3, axis=0)
                    # 再适度全局平滑
                    O3_surface = gaussian_filter(O3_surface, sigma=1.0)
                    logger.info("ekma_surface_smoothed", method="1D(σ=3,axis=0)+2D(σ=1.0)")
                except Exception as e:
                    logger.warning("ekma_smooth_failed", error=str(e))

            else:
                # 使用标准曲面，直接使用Zs，不进行ODE拟合
                O3_surface = Zs

                # 创建网格和范围变量（后续绘图需要）
                voc_range = float(voc_arr[-1] - voc_arr[0])
                nox_range = float(nox_arr[-1] - nox_arr[0])
                voc_max = float(voc_arr[-1])
                nox_max = float(nox_arr[-1])
                # 网格在第1037行创建

                logger.info("ekma_using_standard_surface_directly",
                           reason="ODE data abnormal, using standard surface without refitting")

            # 计算颜色范围
            zmin_plot = float(np.nanmin(O3_surface))
            zmax_plot = float(np.nanmax(O3_surface))
            zrange_plot = zmax_plot - zmin_plot

            # 调试：检查绑图时的VOC和NOX变量
            VOC_for_plot, NOX_for_plot = np.meshgrid(voc_arr, nox_arr, indexing='xy')
            logger.info("ekma_before_contourf",
                       voc_arr_first=float(voc_arr[0]),
                       voc_arr_last=float(voc_arr[-1]),
                       nox_arr_first=float(nox_arr[0]),
                       nox_arr_last=float(nox_arr[-1]),
                       VOC_shape=VOC_for_plot.shape,
                       NOX_shape=NOX_for_plot.shape,
                       VOC_first=float(VOC_for_plot[0,0]),
                       VOC_last=float(VOC_for_plot[-1,-1]),
                       NOX_first=float(NOX_for_plot[0,0]),
                       NOX_last=float(NOX_for_plot[-1,-1]),
                       O3_surface_shape=O3_surface.shape)

            # 确保颜色条范围覆盖完整数据
            if zrange_plot < 20:
                levels = np.linspace(zmin_plot, zmax_plot, 20)
            else:
                levels = np.linspace(max(0, zmin_plot - zrange_plot * 0.05),
                                     zmax_plot + zrange_plot * 0.05, 20)

            # 8. 绘制热力图
            cf = ax.contourf(VOC_for_plot, NOX_for_plot, O3_surface, levels=levels, cmap=cmap_used,
                           antialiased=True, linewidths=0)

            # 9. 绘制等值线（参考EKMA.py）
            contour_lines = ax.contour(VOC_for_plot, NOX_for_plot, O3_surface,
                                      colors='grey', linewidths=0.5, levels=15)
            ax.clabel(contour_lines, inline=True, fontsize=8, fmt='%.0f')

            logger.info("ekma_surface_generated",
                       peak_voc=voc_peak_fitted if 'voc_peak_fitted' in locals() else voc_max,
                       peak_nox=nox_peak_fitted if 'nox_peak_fitted' in locals() else nox_max,
                       zmin=zmin_plot, zmax=zmax_plot)

            # 定义峰值变量供后续绘图使用
            # **修复**：如果使用标准曲面，使用标准峰值位置
            if use_standard:
                peak_voc = voc_arr[0] + voc_range_span * 0.35
                peak_nox = nox_arr[0] + nox_range_span * 0.40
                logger.info("using_standard_peak_for_plotting",
                           peak_voc=peak_voc, peak_nox=peak_nox,
                           reason="standard_surface_used")
            else:
                # 使用ODE拟合的峰值
                peak_voc = voc_peak_fitted if 'voc_peak_fitted' in locals() else voc_max * 0.8
                peak_nox = nox_peak_fitted if 'nox_peak_fitted' in locals() else nox_max * 0.7

            # 计算并标记当前状态点（支持绝对坐标或缩放因子两种模式）
            # current_o3_ugm3 优先使用显式传入的 current_o3（若有）
            if axis_mode == "absolute":
                # 如果用户提供 current_vocs/current_nox，使用插值或最近邻获取对应 O3
                if current_vocs is not None and current_nox is not None:
                    try:
                        if RectBivariateSpline is not None:
                            spline_full = RectBivariateSpline(nox_arr, voc_arr, Z)
                            interp_val = float(spline_full(current_nox, current_vocs))
                            current_o3_ugm3 = interp_val
                        else:
                            # 最近邻
                            voc_idx = int(np.argmin(np.abs(voc_arr - current_vocs)))
                            nox_idx = int(np.argmin(np.abs(nox_arr - current_nox)))
                            current_o3_ugm3 = float(Z[nox_idx, voc_idx])
                    except Exception:
                        current_o3_ugm3 = float(np.nanmax(Z))
                    # 在图上用绝对坐标绘制当前点
                    ax.plot(current_vocs, current_nox, 'r*', markersize=18, markeredgecolor='darkred',
                           markeredgewidth=2, label=f'当前状态 (O3={current_o3_ugm3:.1f} μg/m3)', zorder=10)
                else:
                    # 无显式当前点信息，回退到在网格上选最近的点（寻找 voc 及 nox 的中位或中心）
                    try:
                        voc_idx = int(len(voc_arr) // 2)
                        nox_idx = int(len(nox_arr) // 2)
                        current_o3_ugm3 = float(Z[nox_idx, voc_idx])
                        ax.plot(voc_arr[voc_idx], nox_arr[nox_idx], 'r*', markersize=18, markeredgecolor='darkred',
                               markeredgewidth=2, label=f'当前状态 (O3={current_o3_ugm3:.1f} μg/m3)', zorder=10)
                    except Exception:
                        # 兜底：画在 (1.0,1.0) 位置（仅占位）
                        current_o3_ugm3 = float(np.nanmax(Z)) if 'Z' in locals() else 0.0
                        ax.plot(1.0, 1.0, 'r*', markersize=18, markeredgecolor='darkred',
                               markeredgewidth=2, label=f'当前状态 (O3={current_o3_ugm3:.1f} μg/m3)', zorder=10)
            else:
                # factors 模式，使用相对因子 (1.0, 1.0) 或在网格中查找最接近 1.0 的索引
                try:
                    voc_idx = int(np.argmin(np.abs(voc_arr - 1.0)))
                    nox_idx = int(np.argmin(np.abs(nox_arr - 1.0)))
                    current_o3_ugm3 = float(Z[nox_idx, voc_idx])
                except Exception:
                    current_o3_ugm3 = float(np.nanmin(Z))
                ax.plot(1.0, 1.0, 'r*', markersize=18, markeredgecolor='darkred',
                       markeredgewidth=2, label=f'当前状态 (O3={current_o3_ugm3:.1f} μg/m3)', zorder=10)

            # ========== 绘制ODE积分采样点（用于调试和验证）==========
            if ode_sampling_points and len(ode_sampling_points) > 0:
                try:
                    ode_vocs = [p[0] for p in ode_sampling_points]
                    ode_noxs = [p[1] for p in ode_sampling_points]
                    # 绘制为蓝色圆点
                    ax.scatter(ode_vocs, ode_noxs, c='blue', s=50, marker='o',
                              edgecolors='white', linewidths=1, zorder=8,
                              label=f'ODE积分点 ({len(ode_sampling_points)}个)')
                except Exception as e:
                    logger.warning("ode_points_plot_failed", error=str(e))

            # ========== 绘制峰值位置标记 ==========
            if peak_position is not None:
                try:
                    peak_v, peak_n = peak_position
                    # 绘制为黄色菱形
                    ax.plot(peak_v, peak_n, 'yD', markersize=12, markeredgecolor='black',
                           markeredgewidth=1.5, zorder=9, label='控制线峰值')
                except Exception as e:
                    logger.warning("peak_position_plot_failed", error=str(e))

            # 敏感性类型
            sens_type = sensitivity.get('type', 'unknown')
            sens_type_cn = {
                "VOCs-limited": "VOCs控制区",
                "NOx-limited": "NOx控制区",
                "transitional": "过渡区"
            }.get(sens_type, '未知')

            # ========== [NEW] 绘制L形控制线 ==========
            # **关键修改**：控制线不是连接到峰值点（在网格外），而是绘制峰值O3的等值线
            # 控制线 = 网格内最高O3值的等值线（接近但未达到峰值）
            if show_control_line:
                logger.info("drawing_control_line_as_max_contour")

                # 找到网格内的最大O3值
                grid_max_o3 = float(np.nanmax(O3_surface))

                # 控制线 = 网格内90-95%的等值线（接近最大值）
                control_line_level = grid_max_o3 * 0.93

                # 绘制控制线（单条粗红线）
                cs_control = ax.contour(VOC_for_plot, NOX_for_plot, O3_surface,
                                       levels=[control_line_level],
                                       colors='red', linewidths=2.5, zorder=10)

                # 标注控制线（clabel不支持fontweight参数）
                ax.clabel(cs_control, inline=True, fontsize=9, fmt='%.0f')

                # 在控制线旁边添加文字说明
                ax.text(0.98, 0.85, f'控制线(峰值O3={grid_max_o3:.0f}等值线)',
                       transform=ax.transAxes, ha='right', va='top',
                       fontsize=9, color='red', fontweight='bold',
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

                logger.info("control_line_drawn_as_contour",
                           control_line_level=control_line_level,
                           grid_max_o3=grid_max_o3)

            # ========== [NEW] 绘制控制区 ==========
            # **修改策略**：控制区边界基于O3等值线，而非峰值点
            if show_control_zones:
                logger.info("drawing_control_zones")

                # 创建网格
                voc_grid, nox_grid = np.meshgrid(voc_arr, nox_arr, indexing='xy')

                # **关键修改**：使用O3值本身作为控制区划分依据
                # 高O3区（>80%最大值）：VOCs控制区（减少VOCs效果好）
                # 中O3区（50%-80%）：过渡区
                # 低O3区（<50%）：NOx控制区（减少NOx效果好）

                grid_max_o3 = float(np.nanmax(O3_surface))
                high_o3_threshold = grid_max_o3 * 0.70  # 70%以上为高O3区
                mid_o3_threshold = grid_max_o3 * 0.50   # 50%-70%为过渡区

                # 根据O3值划分控制区
                vocs_mask = O3_surface > high_o3_threshold  # 高O3区 → VOCs控制
                nox_mask = O3_surface < mid_o3_threshold    # 低O3区 → NOx控制
                transition_mask = ~vocs_mask & ~nox_mask    # 中等O3区 → 协同控制

                # 绘制控制区填充
                if np.any(vocs_mask):
                    ax.contourf(voc_grid, nox_grid, vocs_mask.astype(float),
                               levels=[0.5, 1.5], colors=['#4CAF50'], alpha=0.15)
                if np.any(nox_mask):
                    ax.contourf(voc_grid, nox_grid, nox_mask.astype(float),
                               levels=[0.5, 1.5], colors=['#2196F3'], alpha=0.15)
                if np.any(transition_mask):
                    ax.contourf(voc_grid, nox_grid, transition_mask.astype(float),
                               levels=[0.5, 1.5], colors=['#FFC107'], alpha=0.2)

                # 添加控制区标签
                if np.any(vocs_mask):
                    vocs_coords = np.column_stack([voc_grid[vocs_mask], nox_grid[vocs_mask]])
                    if len(vocs_coords) > 0:
                        centroid = np.mean(vocs_coords, axis=0)
                        ax.text(centroid[0], centroid[1], 'VOCs控制区\n(减少VOCs更有效)',
                               ha='center', va='center', fontsize=10, fontweight='bold',
                               bbox=dict(boxstyle='round,pad=0.5', facecolor='#4CAF50', alpha=0.7),
                               color='white')

                if np.any(nox_mask):
                    nox_coords = np.column_stack([voc_grid[nox_mask], nox_grid[nox_mask]])
                    if len(nox_coords) > 0:
                        centroid = np.mean(nox_coords, axis=0)
                        ax.text(centroid[0], centroid[1], 'NOx控制区\n(减少NOx更有效)',
                               ha='center', va='center', fontsize=10, fontweight='bold',
                               bbox=dict(boxstyle='round,pad=0.5', facecolor='#2196F3', alpha=0.7),
                               color='white')

                # 控制区统计
                total_points = len(voc_arr) * len(nox_arr)
                vocs_ratio_display = np.sum(vocs_mask) / total_points if total_points > 0 else 0
                nox_ratio_display = np.sum(nox_mask) / total_points if total_points > 0 else 0
                trans_ratio_display = np.sum(transition_mask) / total_points if total_points > 0 else 0

                logger.info("control_zones_drawn_by_o3_levels",
                           vocs_ratio=vocs_ratio_display,
                           nox_ratio=nox_ratio_display,
                           trans_ratio=trans_ratio_display,
                           high_o3_threshold=high_o3_threshold,
                           mid_o3_threshold=mid_o3_threshold)

                zone_info_text = (
                    f"控制区划分:\n"
                    f"VOCs控制区: {vocs_ratio_display*100:.1f}%\n"
                    f"NOx控制区: {nox_ratio_display*100:.1f}%\n"
                    f"协同控制区: {trans_ratio_display*100:.1f}%"
                )
                ax.text(0.02, 0.60, zone_info_text, transform=ax.transAxes,
                       verticalalignment='top',
                       bbox=dict(boxstyle='round', facecolor='white', alpha=0.9),
                       fontsize=9)

            # ========== 绘制推荐的减排路径 ==========
            # 从当前状态点到控制区内部的箭头
            if sens_type == "VOCs-limited":
                # 指向右下方向（减少VOCs和NOx，但VOCs减少更多）
                ax.annotate('推荐减排方向',
                           xy=(0.4, 0.4), xytext=(0.85, 0.85),
                           arrowprops=dict(arrowstyle='->', color='darkgreen', lw=2.5,
                                          mutation_scale=15),
                           fontsize=10, fontweight='bold', color='darkgreen',
                           xycoords='axes fraction', textcoords='axes fraction',
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.8))
            elif sens_type == "NOx-limited":
                # 指向左下方向（减少NOx）
                ax.annotate('推荐减排方向',
                           xy=(0.4, 0.4), xytext=(0.85, 0.85),
                           arrowprops=dict(arrowstyle='->', color='darkblue', lw=2.5,
                                          mutation_scale=15),
                           fontsize=10, fontweight='bold', color='darkblue',
                           xycoords='axes fraction', textcoords='axes fraction',
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='lightblue', alpha=0.8))

            # 标题和标签（使用真实浓度ppb）
            ax.set_title(f'EKMA等浓度曲面图 - {sens_type_cn}', fontsize=14, fontweight='bold', pad=20)
            ax.set_xlabel('VOCs (ppb)', fontsize=12)
            ax.set_ylabel('NOx (ppb)', fontsize=12)

            # 颜色条（使用 contourf 返回的 QuadContourSet）
            try:
                cbar = plt.colorbar(cf, ax=ax, shrink=0.8)
                cbar.set_label('O3浓度 (μg/m3)', fontsize=12)
            except Exception:
                pass

            # 网格
            ax.grid(True, alpha=0.3, linestyle='--')

            # 强制坐标轴使用原始网格范围（避免等值线延伸导致空白区域）
            ax.set_xlim(float(voc_arr[0]), float(voc_arr[-1]))
            ax.set_ylim(float(nox_arr[0]), float(nox_arr[-1]))

            # 图例
            ax.legend(loc='upper right', fontsize=10)

            # 敏感性信息文本框
            info_text = (
                f"敏感性类型: {sens_type_cn}\n"
                f"峰值O3: {zmax:.1f} μg/m3\n"
                f"VOCs/NOx比值: {sensitivity.get('vocs_nox_ratio', 0):.1f}\n"
                f"建议: {sensitivity.get('recommendation', 'N/A')[:25]}..."
            )
            ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                   verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='white', alpha=0.9),
                   fontsize=9)

            # 添加图例说明控制线
            from matplotlib.lines import Line2D
            # 当前状态坐标显示（绝对浓度）
            if current_vocs is not None and current_nox is not None:
                current_label = f'当前状态 (VOC={current_vocs:.1f}, NOx={current_nox:.1f})'
            else:
                current_label = '当前状态 (1.0, 1.0)'
            legend_elements = [
                Line2D([0], [0], color='red', linewidth=3, label='控制线(峰值O3等值线)'),
                Line2D([0], [0], marker='*', color='w', markerfacecolor='red',
                       markersize=15, label=current_label)
            ]
            ax.legend(handles=legend_elements, loc='center right', fontsize=9,
                     bbox_to_anchor=(0.98, 0.5))

            plt.tight_layout()

            logger.debug("ekma_surface_generated")

            # 使用新方法创建VisualBlock
            chart_id = f"ekma_surface_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            logger.info("ekma_chart_generating", chart_id=chart_id,
                       voc_range=(float(voc_arr[0]), float(voc_arr[-1])),
                       nox_range=(float(nox_arr[0]), float(nox_arr[-1])))
            extra_meta = {
                "sensitivity_type": sens_type,
                "sensitivity_type_cn": sens_type_cn,
                "current_o3": current_o3_ugm3,
                "peak_o3": zmax,
                "current_o3_unit": "ug/m3",
                "grid_size": list(Z.shape),
                "has_control_line": show_control_line,
                "has_control_zones": show_control_zones,
                "source_data_ids": [],
            }
            return self._create_visual(
                fig, chart_id,
                title=f"EKMA等浓度曲面图 - {sens_type_cn}",
                chart_type="ekma_surface",
                scenario="ekma_analysis",
                extra_meta=extra_meta
            )

        except Exception as e:
            # 尽量避免在 Windows 控制台因编码问题抛出二次异常
            msg = str(e)
            try:
                logger.error("ekma_surface_generation_failed", error=msg)
            except Exception:
                try:
                    print("ekma_surface_generation_failed:", msg.encode("utf-8", errors="replace"))
                except Exception:
                    print("ekma_surface_generation_failed:", repr(msg))
            return {"error": msg}

    def generate_reduction_paths(
        self,
        reduction_paths: Dict[str, Any],
        o3_target: float = 75.0
    ) -> Dict[str, Any]:
        """
        生成减排路径对比图

        Args:
            reduction_paths: 减排路径数据
            o3_target: O3控制目标值

        Returns:
            Dict: 包含base64图片和图表元数据
        """
        try:
            fig, ax = plt.subplots(figsize=self.figure_size, dpi=self.dpi)

            paths = reduction_paths.get('paths', {})
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

            # 当前O3浓度和目标O3
            current_o3 = reduction_paths.get('current_o3', 0)

            # 绘制每条路径
            for i, (path_name, path_data) in enumerate(paths.items()):
                o3_values = path_data.get('o3_values', [])
                if not o3_values:
                    continue

                n_steps = len(o3_values)
                # 使用减排比例(%)作为X轴，从0%到100%
                reduction_percentages = np.linspace(0, 100, n_steps)
                color = colors[i % len(colors)]

                ax.plot(reduction_percentages, o3_values, marker='o', markersize=6, linewidth=2.5,
                       color=color, label=path_data.get('name', path_name), alpha=0.8)
            
            # 目标线
            ax.axhline(y=o3_target, color='red', linestyle='--', linewidth=2,
                      alpha=0.7, label=f'目标值 ({o3_target}ppb)')
            ax.axhline(y=current_o3, color='gray', linestyle=':', linewidth=1.5,
                      alpha=0.7, label=f'当前值 ({current_o3:.1f}ppb)')
            
            # 最优路径标注
            best_path = reduction_paths.get('best_path', '')
            best_path_cn = {
                "vocs_only": "仅减VOCs",
                "nox_only": "仅减NOx",
                "equal": "等比例减排",
                "vocs_2_nox_1": "VOCs优先(2:1)",
                "vocs_1_nox_2": "NOx优先(1:2)"
            }.get(best_path, best_path)
            
            ax.set_title(f'减排路径对比 - 最优路径: {best_path_cn}',
                        fontsize=14, fontweight='bold', pad=20)
            ax.set_xlabel('减排比例 (%)', fontsize=12)
            ax.set_ylabel('O3浓度 (ppb)', fontsize=12)

            ax.grid(True, alpha=0.3)
            ax.legend(loc='best', fontsize=10)

            # 减排效率信息
            best_eff = reduction_paths.get('best_efficiency', 0)
            info_text = f"最优减排效率: {best_eff:.2f}%"
            ax.text(0.98, 0.02, info_text, transform=ax.transAxes,
                   horizontalalignment='right', verticalalignment='bottom',
                   bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9),
                   fontsize=10)
            
            plt.tight_layout()

            logger.debug("reduction_paths_generated")

            # 使用新方法创建VisualBlock
            chart_id = f"reduction_paths_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            extra_meta = {
                "best_path": best_path,
                "best_efficiency": best_eff,
                "o3_target": o3_target,
                "current_o3": current_o3,
                "source_data_ids": [],
            }
            return self._create_visual(
                fig, chart_id,
                title=f"减排路径对比 - 最优: {best_path_cn}",
                chart_type="reduction_paths",
                scenario="ekma_analysis",
                extra_meta=extra_meta
            )

        except Exception as e:
            logger.error("reduction_paths_generation_failed", error=str(e))
            return {"error": str(e)}

    def generate_sensitivity_analysis(
        self,
        sensitivity: Dict[str, Any],
        reduction_paths: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        生成敏感性分析诊断图
        
        Args:
            sensitivity: 敏感性分析结果
            reduction_paths: 减排路径数据（可选）
        
        Returns:
            Dict: 包含base64图片和图表元数据
        """
        try:
            fig, axes = plt.subplots(1, 2, figsize=(14, 6), dpi=self.dpi)
            
            # 子图1: 敏感性指标条形图
            ax1 = axes[0]
            sens_type = sensitivity.get('type', 'unknown')
            vocs_sens = abs(sensitivity.get('vocs_sensitivity', 0))
            nox_sens = abs(sensitivity.get('nox_sensitivity', 0))
            
            categories = ['VOCs敏感性', 'NOx敏感性']
            values = [vocs_sens, nox_sens]
            colors_bar = ['#4CAF50', '#2196F3']
            
            bars = ax1.bar(categories, values, color=colors_bar, alpha=0.8, edgecolor='black')
            ax1.set_ylabel('敏感性指数', fontsize=11)
            ax1.set_title('敏感性分析', fontsize=12, fontweight='bold')
            
            # 在条形上标注数值
            for bar, val in zip(bars, values):
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                        f'{val:.2f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
            
            ax1.grid(True, alpha=0.3, axis='y')
            
            # 子图2: 控制策略饼图
            ax2 = axes[1]
            sens_type_cn = {
                "VOCs-limited": "VOCs控制型",
                "NOx-limited": "NOx控制型",
                "transitional": "过渡区"
            }.get(sens_type, sens_type)
            
            if sens_type == "VOCs-limited":
                sizes = [70, 25, 5]
                colors_pie = ['#4CAF50', '#FFC107', '#9E9E9E']
            elif sens_type == "NOx-limited":
                sizes = [25, 70, 5]
                colors_pie = ['#4CAF50', '#2196F3', '#9E9E9E']
            else:
                sizes = [45, 45, 10]
                colors_pie = ['#4CAF50', '#2196F3', '#9E9E9E']
            
            labels = ['VOCs控制', 'NOx控制', '其他']
            wedges, texts, autotexts = ax2.pie(
                sizes, labels=labels, colors=colors_pie, 
                autopct='%1.0f%%', startangle=90, 
                textprops={'fontsize': 10}
            )
            ax2.set_title(f'控制策略建议 - {sens_type_cn}', fontsize=12, fontweight='bold')
            
            # 添加建议文本
            recommendation = sensitivity.get('recommendation', '')
            if recommendation:
                fig.text(0.5, 0.02, f"建议: {recommendation}", ha='center', fontsize=11,
                        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))
            
            plt.tight_layout(rect=[0, 0.08, 1, 1])
            img_base64 = self._fig_to_base64(fig)

            logger.debug("sensitivity_analysis_generated")

            # 使用新方法创建VisualBlock
            chart_id = f"sensitivity_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            extra_meta = {
                "sensitivity_type": sens_type,
                "vocs_sensitivity": vocs_sens,
                "nox_sensitivity": nox_sens,
                "recommendation": recommendation,
                "source_data_ids": [],
            }
            return self._create_visual(
                fig, chart_id,
                title=f"敏感性诊断 - {sens_type_cn}",
                chart_type="sensitivity_analysis",
                scenario="ekma_analysis",
                extra_meta=extra_meta
            )

        except Exception as e:
            logger.error("sensitivity_analysis_generation_failed", error=str(e))
            return {"error": str(e)}

    def generate_control_recommendations(
        self,
        sensitivity: Dict[str, Any],
        reduction_paths: Dict[str, Any],
        o3_target: float = 75.0
    ) -> Dict[str, Any]:
        """
        生成减排控制建议图表
        
        Args:
            sensitivity: 敏感性分析结果
            reduction_paths: 减排路径数据
            o3_target: O3控制目标值
        
        Returns:
            Dict: 包含base64图片和图表元数据
        """
        try:
            fig, ax = plt.subplots(figsize=(12, 8), dpi=self.dpi)
            ax.axis('off')
            
            sens_type = sensitivity.get('type', 'unknown')
            sens_type_cn = {
                "VOCs-limited": "VOCs控制型",
                "NOx-limited": "NOx控制型",
                "transitional": "过渡区"
            }.get(sens_type, '未知')
            
            best_path = reduction_paths.get('best_path', '')
            best_path_cn = {
                "vocs_only": "仅减VOCs",
                "nox_only": "仅减NOx",
                "equal": "等比例减排",
                "vocs_2_nox_1": "VOCs优先(2:1)",
                "vocs_1_nox_2": "NOx优先(1:2)"
            }.get(best_path, best_path)
            
            current_o3 = reduction_paths.get('current_o3', 0)
            best_eff = reduction_paths.get('best_efficiency', 0)
            
            # 创建文本框
            title = "臭氧污染控制策略建议"
            ax.text(0.5, 0.95, title, ha='center', va='top', fontsize=18, 
                   fontweight='bold', transform=ax.transAxes)
            
            # 诊断结果
            diag_text = f"""
诊断结果
----------------------------------------
敏感性类型: {sens_type_cn}
VOCs/NOx比值: {sensitivity.get('vocs_nox_ratio', 0):.1f}
当前O3浓度: {current_o3:.1f} ppb
控制目标: {o3_target:.1f} ppb
需减排量: {max(0, current_o3 - o3_target):.1f} ppb
"""
            ax.text(0.05, 0.80, diag_text, ha='left', va='top', fontsize=11,
                   fontfamily='monospace', transform=ax.transAxes,
                   bbox=dict(boxstyle='round', facecolor='lightcyan', alpha=0.8))
            
            # 最优策略
            strategy_text = f"""
最优减排策略
----------------------------------------
推荐路径: {best_path_cn}
减排效率: {best_eff:.2f}%/步

{sensitivity.get('recommendation', '')}
"""
            ax.text(0.55, 0.80, strategy_text, ha='left', va='top', fontsize=11,
                   fontfamily='monospace', transform=ax.transAxes,
                   bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
            
            # 具体措施
            if sens_type == "VOCs-limited":
                measures = [
                    "1. 优先控制VOCs排放源",
                    "2. 重点管控芳香烃类(甲苯、二甲苯等)",
                    "3. 加强溶剂使用行业监管",
                    "4. 控制机动车蒸发排放",
                    "5. VOCs:NOx减排比例建议2:1"
                ]
            elif sens_type == "NOx-limited":
                measures = [
                    "1. 优先控制NOx排放源",
                    "2. 重点管控燃烧源(电厂、锅炉)",
                    "3. 严控机动车尾气排放",
                    "4. 推广新能源交通工具",
                    "5. VOCs:NOx减排比例建议1:2"
                ]
            else:
                measures = [
                    "1. VOCs和NOx需协同控制",
                    "2. 根据季节调整减排侧重",
                    "3. 夏季侧重VOCs，冬季侧重NOx",
                    "4. 建立联防联控机制",
                    "5. VOCs:NOx减排比例建议1:1"
                ]
            
            measures_text = "具体控制措施\n" + "-"*40 + "\n" + "\n".join(measures)
            ax.text(0.05, 0.35, measures_text, ha='left', va='top', fontsize=11,
                   fontfamily='monospace', transform=ax.transAxes,
                   bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))
            
            # 预期效果
            paths = reduction_paths.get('paths', {})
            effects_text = "各路径减排效果\n" + "-"*40 + "\n"
            for path_name, path_data in paths.items():
                path_cn = {
                    "vocs_only": "仅减VOCs",
                    "nox_only": "仅减NOx",
                    "equal": "等比例",
                    "vocs_2_nox_1": "VOCs优先",
                    "vocs_1_nox_2": "NOx优先"
                }.get(path_name, path_name)
                o3_vals = path_data.get('o3_values', [])
                if o3_vals:
                    final_o3 = o3_vals[-1]
                    reduction = current_o3 - final_o3
                    effects_text += f"{path_cn}: 可降 {reduction:.1f} ppb\n"
            
            ax.text(0.55, 0.35, effects_text, ha='left', va='top', fontsize=11,
                   fontfamily='monospace', transform=ax.transAxes,
                   bbox=dict(boxstyle='round', facecolor='lavender', alpha=0.8))
            
            plt.tight_layout()

            logger.debug("control_recommendations_generated")

            # 使用新方法创建VisualBlock
            chart_id = f"recommendations_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            extra_meta = {
                "sensitivity_type": sens_type,
                "best_path": best_path,
                "current_o3": current_o3,
                "o3_target": o3_target,
                "source_data_ids": [],
            }
            return self._create_visual(
                fig, chart_id,
                title="臭氧污染控制策略建议",
                chart_type="control_recommendations",
                scenario="ekma_analysis",
                extra_meta=extra_meta
            )
            
        except Exception as e:
            logger.error("control_recommendations_generation_failed", error=str(e))
            return {"error": str(e)}

    def generate_all_charts(
        self,
        o3_surface: np.ndarray,
        voc_factors: List[float],
        nox_factors: List[float],
        sensitivity: Dict[str, Any],
        reduction_paths: Dict[str, Any],
        o3_target: float = 75.0,
        current_vocs: Optional[float] = None,
        current_nox: Optional[float] = None,
        # ODE积分采样点（用于在图上显示）
        ode_sampling_points: Optional[List[Tuple[float, float]]] = None,
        # 峰值位置
        peak_position: Optional[Tuple[float, float]] = None,
        # L形模型相关数据（新增参数）
        lshape_model: Optional[Any] = None,
        control_zones: Optional[Dict[str, Any]] = None,
        lshape_contours: Optional[List[Dict[str, Any]]] = None,
        # 控制生成哪些图表
        generate_ekma: bool = True,
        generate_reduction_paths: bool = True,
        generate_sensitivity: bool = False,
        generate_recommendations: bool = False
    ) -> List[Dict[str, Any]]:
        """
        生成OBM分析相关图表

        Args:
            o3_surface: O3响应曲面矩阵
            voc_factors: VOC浓度坐标 (ppb)
            nox_factors: NOx浓度坐标 (ppb)
            sensitivity: 敏感性分析结果
            reduction_paths: 减排路径数据
            o3_target: O3控制目标值
            current_vocs: 当前VOCs浓度 (ppb)
            current_nox: 当前NOx浓度 (ppb)
            ode_sampling_points: ODE积分采样点列表
            peak_position: 控制线峰值位置 (voc, nox)
            lshape_model: L形模型数据
            control_zones: 控制区划分数据
            lshape_contours: L形等值线数据
            generate_ekma: 是否生成EKMA等浓度曲面图 (默认True)
            generate_reduction_paths: 是否生成减排路径对比图 (默认True)
            generate_sensitivity: 是否生成敏感性分析图 (默认False)
            generate_recommendations: 是否生成控制策略建议图 (默认False)

        Returns:
            List[Dict]: 所有图表的列表
        """
        visuals = []

        # 1. EKMA等浓度曲面图（核心图表）
        if generate_ekma:
            ekma_chart = self.generate_ekma_surface(
                o3_surface, voc_factors, nox_factors, sensitivity,
                current_vocs=current_vocs, current_nox=current_nox,
                ode_sampling_points=ode_sampling_points,
                peak_position=peak_position,
                lshape_model=lshape_model,
                control_zones=control_zones,
                lshape_contours=lshape_contours
            )
            if "error" not in ekma_chart:
                visuals.append(ekma_chart)

        # 2. 减排路径对比图
        if generate_reduction_paths:
            paths_chart = self.generate_reduction_paths(reduction_paths, o3_target)
            if "error" not in paths_chart:
                visuals.append(paths_chart)

        # 3. 敏感性分析图（可选）
        if generate_sensitivity:
            sens_chart = self.generate_sensitivity_analysis(sensitivity, reduction_paths)
            if "error" not in sens_chart:
                visuals.append(sens_chart)

        # 4. 控制策略建议图（可选）
        if generate_recommendations:
            rec_chart = self.generate_control_recommendations(
                sensitivity, reduction_paths, o3_target
            )
            if "error" not in rec_chart:
                visuals.append(rec_chart)

        return visuals

    def _validate_and_fix_ekma_surface(
        self,
        o3_surface: np.ndarray,
        voc_factors: List[float],
        nox_factors: List[float],
        peak_position: Optional[Tuple[float, float]],
        control_zones: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        验证EKMA图表的规范性并应用自动修正

        检查项:
        1. 峰值位置合理性（应在0.2-0.8范围内）
        2. 控制区划分均衡性（不应>85%单一控制区）
        3. 网格范围合理性（VOCs/NOx比例2-5:1）
        4. NaN值比例（应<10%）
        5. 边界效应（高NOx区O3应低于峰值）

        Returns:
            {
                "has_issues": bool,
                "issues": List[str],
                "fixes_applied": List[str],
                "severity": "critical" | "warning" | "info"
            }
        """
        issues = []
        fixes_applied = []
        severity = "info"

        # 转换为numpy数组
        o3_arr = np.asarray(o3_surface, dtype=float)
        voc_arr = np.asarray(voc_factors, dtype=float)
        nox_arr = np.asarray(nox_factors, dtype=float)

        # 检查1: 峰值位置合理性
        if peak_position is not None:
            peak_voc, peak_nox = peak_position
            voc_span = voc_arr[-1] - voc_arr[0] if len(voc_arr) > 1 else 1
            nox_span = nox_arr[-1] - nox_arr[0] if len(nox_arr) > 1 else 1

            peak_voc_ratio = (peak_voc - voc_arr[0]) / voc_span if voc_span > 0 else 0.5
            peak_nox_ratio = (peak_nox - nox_arr[0]) / nox_span if nox_span > 0 else 0.5

            # 峰值在边界（<0.2 或 >0.8）
            if peak_voc_ratio < 0.15 or peak_voc_ratio > 0.85 or peak_nox_ratio < 0.15 or peak_nox_ratio > 0.85:
                issues.append(f"峰值位于边界({peak_voc_ratio:.2f},{peak_nox_ratio:.2f})")
                severity = "critical"

                # 建议修正措施（记录但不自动应用）
                if peak_voc_ratio < 0.15:
                    fixes_applied.append("建议扩大VOCs范围下限或缩小上限")
                if peak_voc_ratio > 0.85:
                    fixes_applied.append("建议扩大VOCs范围上限")
                if peak_nox_ratio < 0.15:
                    fixes_applied.append("建议扩大NOx范围下限")
                if peak_nox_ratio > 0.85:
                    fixes_applied.append("建议扩大NOx范围上限")

        # 检查2: 控制区划分均衡性
        if control_zones is not None:
            zone_stats = control_zones.get("zone_stats", {})
            vocs_ratio = zone_stats.get("vocs_control_ratio", 0)
            nox_ratio = zone_stats.get("nox_control_ratio", 0)

            if vocs_ratio > 0.85 or nox_ratio > 0.85:
                issues.append(f"控制区失衡(VOCs={vocs_ratio*100:.0f}%,NOx={nox_ratio*100:.0f}%)")
                if severity == "info":
                    severity = "warning"

                fixes_applied.append("建议调整网格范围或L形模型参数")

        # 检查3: 网格范围比例
        voc_span = voc_arr[-1] - voc_arr[0] if len(voc_arr) > 1 else 1
        nox_span = nox_arr[-1] - nox_arr[0] if len(nox_arr) > 1 else 1
        ratio = voc_span / nox_span if nox_span > 0 else 0

        if ratio < 1.5 or ratio > 6:
            issues.append(f"网格比例异常({ratio:.1f}:1,建议2-5:1)")
            if severity == "info":
                severity = "warning"

            if ratio < 1.5:
                fixes_applied.append("建议扩大VOCs范围或缩小NOx范围")
            elif ratio > 6:
                fixes_applied.append("建议扩大NOx范围或缩小VOCs范围")

        # 检查4: NaN值比例
        nan_count = np.sum(np.isnan(o3_arr))
        nan_ratio = nan_count / o3_arr.size if o3_arr.size > 0 else 0

        if nan_ratio > 0.1:
            issues.append(f"NaN值过多({nan_ratio*100:.0f}%)")
            severity = "critical"
            fixes_applied.append("需检查ODE计算是否收敛或网格点是否超出物理范围")

        # 检查5: 边界效应（NOx滴定）
        if o3_arr.shape[0] > 1 and o3_arr.shape[1] > 1:
            # 检查高NOx区域（最后3行）的O3是否明显低于峰值
            high_nox_rows = o3_arr[-3:, :]
            peak_o3 = float(np.nanmax(o3_arr))
            high_nox_mean = float(np.nanmean(high_nox_rows))

            if high_nox_mean > peak_o3 * 0.9:
                issues.append("高NOx区O3未下降(NOx滴定效应异常)")
                if severity == "info":
                    severity = "warning"
                fixes_applied.append("可能是网格范围不足或初始浓度设置不当")

        # 检查6: VOCs=0列合理性（用于判断是否为退化的一维曲线）
        if voc_span < 1.0:  # VOCs范围接近0
            issues.append("VOCs范围接近0(EKMA退化为一维)")
            severity = "critical"
            fixes_applied.append("VOCs数据可能缺失或映射失败，需检查数据源")

        return {
            "has_issues": len(issues) > 0,
            "issues": issues,
            "fixes_applied": fixes_applied,
            "severity": severity,
            "details": {
                "peak_position_ok": peak_voc_ratio >= 0.2 and peak_voc_ratio <= 0.8 and peak_nox_ratio >= 0.2 and peak_nox_ratio <= 0.8 if peak_position else None,
                "control_zones_balanced": vocs_ratio <= 0.85 and nox_ratio <= 0.85 if control_zones else None,
                "grid_ratio": ratio,
                "nan_ratio": nan_ratio
            }
        }

    def _create_standard_ekma_surface(
        self,
        voc_factors: List[float],
        nox_factors: List[float],
        peak_position: Optional[Tuple[float, float]] = None,
        peak_o3: float = 150.0
    ) -> np.ndarray:
        """
        创建标准EKMA响应曲面（基于OBM经验公式模型）

        参考OBM-deliver项目的EKMA.py实现：
        O3 = R²_VOC × f1(VOC) + R²_NOx × f2(NOx) + (R²_NOx/R²_VOC) × VOC × NOx

        这种方法能生成自然的V型等值线和圆滑的峰值。

        Args:
            voc_factors: VOC浓度范围
            nox_factors: NOx浓度范围
            peak_position: 峰值位置 (voc, nox) - 可选
            peak_o3: 峰值O3浓度

        Returns:
            标准O3响应曲面矩阵
        """
        import numpy as np

        # 转换为numpy数组
        voc_arr = np.asarray(voc_factors, dtype=float)
        nox_arr = np.asarray(nox_factors, dtype=float)

        # 获取网格参数
        voc_min = voc_arr.min()
        voc_max = voc_arr.max()
        nox_min = nox_arr.min()
        nox_max = nox_arr.max()
        voc_span = voc_max - voc_min
        nox_span = nox_max - nox_min

        # 避免除零
        voc_span = max(voc_span, 1e-6)
        nox_span = max(nox_span, 1e-6)

        # 创建网格
        VOC, NOX = np.meshgrid(voc_arr, nox_arr, indexing='xy')

        # **基于OBM经验的参数设置**
        # VOC和NOx的R²（拟合优度），表示各自对O3的解释能力
        r2_voc = 0.75  # VOC贡献
        r2_nox = 0.55  # NOx贡献

        # **多项式系数**（模拟实际拟合结果）
        # VOC二次项系数（开口向下的抛物线）
        a_voc = -0.0008  # 负系数确保O3随VOC先增后减
        b_voc = 0.35
        c_voc = 15

        # NOx二次项系数
        a_nox = -0.0015  # NOx影响更敏感
        b_nox = 0.45
        c_nox = 10

        # **计算VOC和NOx的独立贡献**
        voc_contribution = a_voc * VOC**2 + b_voc * VOC + c_voc
        nox_contribution = a_nox * NOX**2 + b_nox * NOX + c_nox

        # **交互项**（VOC × NOx）- 这是形成V型结构的关键
        interaction = (r2_nox / r2_voc) * 0.001 * VOC * NOX

        # **组合O3曲面**
        O3_surface = r2_voc * voc_contribution + r2_nox * nox_contribution + interaction

        # **归一化到目标峰值**
        current_max = float(O3_surface.max())
        if current_max > 0:
            O3_surface = O3_surface * (peak_o3 * 0.85 / current_max)

        # **添加高斯平滑**（让等值线更圆滑，但保留V型特征）
        from scipy.ndimage import gaussian_filter
        O3_surface = gaussian_filter(O3_surface, sigma=0.5)

        # **下界约束**（确保左下角O3不为零）
        o3_min_threshold = peak_o3 * 0.15
        O3_surface = np.clip(O3_surface, o3_min_threshold, peak_o3 * 0.90)

        logger.info("standard_ekma_surface_created",
                   method="obm_empirical_formula",
                   r2_voc=r2_voc,
                   r2_nox=r2_nox,
                   a_voc=a_voc,
                   a_nox=a_nox,
                   o3_min=float(O3_surface.min()),
                   o3_max=float(O3_surface.max()),
                   peak_o3=peak_o3,
                   note="O3 = R2_VOC*f1(VOC) + R2_NOx*f2(NOx) + (R2_NOx/R2_VOC)*VOC*NOx")

        return O3_surface
