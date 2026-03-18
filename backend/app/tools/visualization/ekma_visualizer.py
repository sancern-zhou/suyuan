"""
OBM/OFP 分析可视化器

生成 EKMA 等值线图、减排情景模拟、臭氧平衡图
格式统一为 UDF v2.0 + Chart v3.1 规范
"""

import io
import os
import base64
from typing import Dict, List, Any, Optional
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import structlog

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, FormatStrFormatter
from scipy.ndimage import gaussian_filter1d
import matplotlib.font_manager as fm

# 显式指定中文字体路径（Linux服务器）
font_path = '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.sans-serif'] = [fm.FontProperties(fname=font_path).get_name()]
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['mathtext.fontset'] = 'stix'

logger = structlog.get_logger()


class EKMAVisualizer:
    """
    OBM/OFP 分析可视化器

    生成图表：
    1. EKMA 等值线图 - VOCs vs NOx 的臭氧等值线
    2. 减排情景模拟 - 不同减排路线的 O3 变化
    3. 臭氧平衡图 - O3 与前体物关系
    """

    def __init__(self, figure_size: tuple = (12, 9), dpi: int = 150):
        self.figure_size = figure_size
        self.dpi = dpi

    def _fig_to_base64(self, fig: plt.Figure) -> str:
        """将matplotlib图形转换为base64编码"""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=self.dpi, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig)
        return f"data:image/png;base64,{img_base64}"

    def _create_visual(
        self,
        fig: plt.Figure,
        chart_id: str,
        title: str,
        chart_type: str,
        scenario: str,
        extra_meta: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """创建符合前端渲染规范的 visual 结构"""
        from app.services.image_cache import get_image_cache

        img_base64 = self._fig_to_base64(fig)
        cache = get_image_cache()
        saved_image_id = cache.save(img_base64, chart_id)
        image_url = f"/api/image/{saved_image_id}"

        meta = {
            "schema_version": "3.1",
            "generator": "EKMAVisualizer",
            "scenario": scenario,
        }
        if extra_meta:
            meta.update(extra_meta)

        return {
            "id": saved_image_id,
            "type": "image",
            "schema": "chart_config",
            "payload": {
                "type": "image",
                "data": f"[IMAGE:{saved_image_id}]",
                "image_id": saved_image_id,
                "image_url": image_url,
                "markdown_image": f"![{title}]({image_url})",
                "title": title,
                "meta": meta
            },
            "meta": {
                "chart_type": chart_type,
                "scenario": scenario,
                "source_data_ids": [],
                "layout_hint": "wide",
                "image_url": image_url,
                "markdown_image": f"![{title}]({image_url})"
            }
        }

    def generate_ekma_contour(
        self,
        vocs_data: List[Dict],
        o3_data: List[Dict],
        nox_data: Optional[List[Dict]] = None,
        station_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        生成 EKMA 等值线图

        Args:
            vocs_data: VOCs浓度数据列表
            o3_data: O3浓度数据列表
            nox_data: NOx浓度数据列表（可选）
            station_name: 站点名称

        Returns:
            EKMA等值线图 visual
        """
        try:
            # 提取数据
            vocs_values = []
            o3_values = []
            nox_values = []

            for record in vocs_data:
                # 计算总VOCs（ppbv）
                total_voc = 0
                for key, val in record.items():
                    if key != 'time' and key != 'timestamp' and isinstance(val, (int, float)):
                        total_voc += val
                if total_voc > 0:
                    vocs_values.append(total_voc)

            for record in o3_data:
                o3_val = record.get('O3', record.get('o3', 0))
                if isinstance(o3_val, (int, float)) and o3_val > 0:
                    o3_values.append(o3_val)

            if nox_data:
                for record in nox_data:
                    nox_val = record.get('NOx', record.get('NO2', record.get('nox', record.get('no2', 0))))
                    if isinstance(nox_val, (int, float)) and nox_val > 0:
                        nox_values.append(nox_val)

            if len(vocs_values) == 0 or len(o3_values) == 0:
                logger.warning("[EKMAVisualizer] 数据不足，无法生成EKMA图")
                return None

            # 确保数据长度一致
            min_len = min(len(vocs_values), len(o3_values))
            vocs_values = vocs_values[:min_len]
            o3_values = o3_values[:min_len]

            # 获取数据范围
            VOCs_max = np.percentile(vocs_values, 95) if vocs_values else np.max(vocs_values)
            VOCs_min = np.percentile(vocs_values, 5) if vocs_values else np.min(vocs_values)
            O3_max = np.max(o3_values)
            O3_min = np.min(o3_values)

            # 如果没有NOx数据，使用模拟值
            if len(nox_values) == 0:
                nox_values = [v * 0.5 for v in vocs_values]  # 模拟NOx
            NOx_max = np.percentile(nox_values, 95) if nox_values else np.max(nox_values)
            NOx_min = np.percentile(nox_values, 5) if nox_values else np.min(nox_values)

            # 非线性建模 - 简单二次拟合
            x_voc = np.array(vocs_values)
            y_o3 = np.array(o3_values)

            # VOCs-O3 关系
            coeffs_voc = np.polyfit(x_voc, y_o3, 2)
            f_voc = np.poly1d(coeffs_voc)

            # NOx-O3 关系
            x_nox = np.array(nox_values[:min_len])
            coeffs_nox = np.polyfit(x_nox, y_o3, 2)
            f_nox = np.poly1d(coeffs_nox)

            # 计算 R²
            y_pred_voc = f_voc(x_voc)
            ss_res_voc = np.sum((y_o3 - y_pred_voc) ** 2)
            ss_tot_voc = np.sum((y_o3 - np.mean(y_o3)) ** 2)
            r2_voc = 1 - (ss_res_voc / ss_tot_voc) if ss_tot_voc > 0 else 0.5

            y_pred_nox = f_nox(x_nox)
            ss_res_nox = np.sum((y_o3 - y_pred_nox) ** 2)
            ss_tot_nox = np.sum((y_o3 - np.mean(y_o3)) ** 2)
            r2_nox = 1 - (ss_res_nox / ss_tot_nox) if ss_tot_nox > 0 else 0.5

            # 创建减排情景网格
            VOC_rr = np.linspace(0, 100, 101)  # 0-100% 减排
            NOx_rr = np.linspace(0, 100, 101)

            EKMAVOCs, EKMANOx = np.meshgrid(VOC_rr, NOx_rr)

            # 计算 EKMA O3 曲面（简化模型）
            # O3 = R²_VOC * f_VOC(VOCs_max *减排比例) + R²_NOx * f_NOx(NOx_max *减排比例)
            # + 交互项
            EKMAO3 = (
                r2_voc * f_voc(VOCs_max * (1 - EKMAVOCs / 100)) +
                r2_nox * f_nox(NOx_max * (1 - EKMANOx / 100)) +
                0.1 * EKMAVOCs * EKMANOx  # 交互项
            )

            # 归一化到实际O3范围
            EKMAO3 = EKMAO3 * (O3_max / EKMAO3.max()) if EKMAO3.max() > 0 else EKMAO3
            EKMAO3 = np.clip(EKMAO3, O3_min * 0.5, O3_max * 1.1)
            EKMAO3 = gaussian_filter1d(EKMAO3, sigma=3, axis=0)
            EKMAO3 = gaussian_filter1d(EKMAO3, sigma=3, axis=1)

            # 绘制 EKMA 等值线图
            fig, ax = plt.subplots(figsize=(12, 9))

            levels = np.linspace(O3_min, O3_max, 20)

            # 填充等值线
            contourf = ax.contourf(EKMAVOCs, EKMANOx, EKMAO3, levels=levels, alpha=0.9, cmap='jet')

            # 等值线
            contour_lines = ax.contour(EKMAVOCs, EKMANOx, EKMAO3, colors='gray', linewidths=0.8, levels=15)
            ax.clabel(contour_lines, inline=True, fontsize=10, fmt='%.0f')

            # 标注当前排放情景（基于平均值）
            current_voc = np.mean(vocs_values)
            current_nox = np.mean(nox_values[:min_len])
            # 转换为减排百分比坐标
            current_voc_pct = (1 - current_voc / VOCs_max) * 100 if VOCs_max > 0 else 50
            current_nox_pct = (1 - current_nox / NOx_max) * 100 if NOx_max > 0 else 50

            ax.plot(current_voc_pct, current_nox_pct, '*', markersize=20,
                   markerfacecolor='white', markeredgecolor='black', markeredgewidth=2)
            ax.text(current_voc_pct + 3, current_nox_pct + 3, '当前情景', fontsize=12,
                   fontweight='bold', color='white', bbox=dict(boxstyle='round', facecolor='black', alpha=0.7))

            # 设置坐标轴
            ax.set_xlabel('VOCs 减排比例 (%)', fontsize=14, fontweight='bold')
            ax.set_ylabel('NOx 减排比例 (%)', fontsize=14, fontweight='bold')
            ax.set_xlim(0, 100)
            ax.set_ylim(0, 100)

            # 颜色条
            cbar = plt.colorbar(contourf, shrink=0.8)
            cbar.ax.yaxis.set_major_formatter(FormatStrFormatter('%.0f'))
            cbar.set_label('臭氧浓度 (μg/m³)', fontsize=12, fontweight='bold')

            # 标题
            title_text = f'EKMA 臭氧等值线分析 - {station_name}' if station_name else 'EKMA 臭氧等值线分析'
            plt.title(title_text, fontsize=16, fontweight='bold', pad=15)

            # 添加水印和时间戳
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            fig.text(0.5, 0.5, f'OBM Analysis {time_str}', fontsize=14, color='grey',
                    alpha=0.5, ha='center', va='center', rotation=45)

            plt.tight_layout()

            chart_id = f"ekma_contour_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(
                fig, chart_id,
                f'EKMA臭氧等值线分析 - {station_name}',
                "ekma_contour",
                "obm_ekma_analysis",
                {"station_name": station_name, "r2_voc": round(r2_voc, 3), "r2_nox": round(r2_nox, 3)}
            )

        except Exception as e:
            logger.warning(f"生成EKMA等值线图失败: {e}")
            return None

    def generate_emission_reduction_scenarios(
        self,
        vocs_data: List[Dict],
        o3_data: List[Dict],
        nox_data: Optional[List[Dict]] = None,
        station_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        生成减排情景模拟图

        展示不同减排路线下O3浓度的变化：
        1. VOCs:NOx = 1:0（仅VOCs减排）
        2. VOCs:NOx = 0:1（仅NOx减排）
        3. VOCs:NOx = 1:1（同时减排）
        4. VOCs:NOx = 2:1（VOCs减排更多）
        5. VOCs:NOx = 1:2（NOx减排更多）
        """
        try:
            # 提取数据
            vocs_values = []
            o3_values = []
            nox_values = []

            for record in vocs_data:
                total_voc = sum(v for k, v in record.items() if k not in ['time', 'timestamp'] and isinstance(v, (int, float)))
                if total_voc > 0:
                    vocs_values.append(total_voc)

            for record in o3_data:
                o3_val = record.get('O3', record.get('o3', 0))
                if isinstance(o3_val, (int, float)) and o3_val > 0:
                    o3_values.append(o3_val)

            if nox_data:
                for record in nox_data:
                    nox_val = record.get('NOx', record.get('NO2', 0))
                    if isinstance(nox_val, (int, float)) and nox_val > 0:
                        nox_values.append(nox_val)

            if len(vocs_values) == 0 or len(o3_values) == 0:
                return None

            min_len = min(len(vocs_values), len(o3_values))
            vocs_values = vocs_values[:min_len]
            o3_values = o3_values[:min_len]

            O3_current = np.mean(o3_values)

            if len(nox_values) == 0:
                nox_values = [v * 0.5 for v in vocs_values[:min_len]]

            # 计算基准排放（95百分位）
            VOCs_95 = np.percentile(vocs_values, 95)
            NOx_95 = np.percentile(nox_values, 95)

            # 简化模型：O3与减排比例的关系
            reduction_pct = np.arange(0, 101, 2)  # 0-100% 减排

            # 计算各情景的O3响应
            # 使用简单的线性或对数关系模拟
            cases = {}

            # 情景1: VOCs:NOx = 1:0（仅VOCs减排）
            cases['仅VOCs减排'] = O3_current * (1 - 0.3 * (reduction_pct / 100))

            # 情景2: VOCs:NOx = 0:1（仅NOx减排）
            cases['仅NOx减排'] = O3_current * (1 - 0.1 * (reduction_pct / 100))

            # 情景3: VOCs:NOx = 1:1（同时减排）
            cases['协同减排(1:1)'] = O3_current * (1 - 0.25 * (reduction_pct / 100))

            # 情景4: VOCs:NOx = 2:1（VOCs减排更多）
            cases['VOCs优先减排(2:1)'] = O3_current * (1 - 0.28 * (reduction_pct / 100))

            # 情景5: VOCs:NOx = 1:2（NOx减排更多）
            cases['NOx优先减排(1:2)'] = O3_current * (1 - 0.18 * (reduction_pct / 100))

            # 绘制减排情景图
            fig, ax = plt.subplots(figsize=(12, 8))

            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
            linestyles = ['-', '--', '-.', ':', '-']

            for idx, (scenario_name, o3_values_case) in enumerate(cases.items()):
                ax.plot(reduction_pct, o3_values_case,
                       color=colors[idx % len(colors)],
                       linestyle=linestyles[idx % len(linestyles)],
                       linewidth=2.5,
                       label=scenario_name)

            # 绘制当前O3水平线
            ax.axhline(y=O3_current, color='black', linestyle='--', linewidth=2, alpha=0.7, label=f'当前O3水平 ({O3_current:.1f})')

            # 标注达标线（假设75μg/m³为达标线）
            target_75 = 75
            ax.axhline(y=target_75, color='red', linestyle=':', linewidth=1.5, alpha=0.7)
            ax.text(102, target_75, f'达标线({target_75})', fontsize=10, va='center')

            # 设置坐标轴
            ax.set_xlabel('减排比例 (%)', fontsize=14, fontweight='bold')
            ax.set_ylabel('臭氧浓度 (μg/m³)', fontsize=14, fontweight='bold')
            ax.set_xlim(0, 100)

            # O3目标范围
            ax.set_ylim(0, O3_current * 1.1)

            ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=10))
            ax.grid(True, alpha=0.3, linestyle='--')

            ax.legend(loc='upper right', fontsize=10, framealpha=0.9)

            # 标题
            title_text = f'臭氧减排情景模拟 - {station_name}' if station_name else '臭氧减排情景模拟'
            plt.title(title_text, fontsize=16, fontweight='bold', pad=15)

            # 添加水印
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            fig.text(0.5, 0.5, f'OBM Analysis {time_str}', fontsize=14, color='grey',
                    alpha=0.5, ha='center', va='center', rotation=45)

            plt.tight_layout()

            chart_id = f"emission_reduction_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(
                fig, chart_id,
                f'臭氧减排情景模拟 - {station_name}',
                "emission_reduction",
                "obm_reduction_analysis",
                {"station_name": station_name, "current_o3": round(O3_current, 2)}
            )

        except Exception as e:
            logger.warning(f"生成减排情景图失败: {e}")
            return None

    def generate_ozone_balance_chart(
        self,
        vocs_data: List[Dict],
        o3_data: List[Dict],
        nox_data: Optional[List[Dict]] = None,
        station_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        生成臭氧平衡图

        展示O3与前体物（VOCs、NOx）的关系
        """
        try:
            # 提取数据
            vocs_values = []
            o3_values = []
            nox_values = []

            for record in vocs_data:
                total_voc = sum(v for k, v in record.items() if k not in ['time', 'timestamp'] and isinstance(v, (int, float)))
                if total_voc > 0:
                    vocs_values.append(total_voc)

            for record in o3_data:
                o3_val = record.get('O3', record.get('o3', 0))
                if isinstance(o3_val, (int, float)) and o3_val > 0:
                    o3_values.append(o3_val)

            if nox_data:
                for record in nox_data:
                    nox_val = record.get('NOx', record.get('NO2', 0))
                    if isinstance(nox_val, (int, float)) and nox_val > 0:
                        nox_values.append(nox_val)

            if len(vocs_values) == 0 or len(o3_values) == 0:
                return None

            min_len = min(len(vocs_values), len(o3_values))
            vocs_values = vocs_values[:min_len]
            o3_values = o3_values[:min_len]

            if len(nox_values) == 0:
                nox_values = [v * 0.5 for v in vocs_values[:min_len]]
            nox_values = nox_values[:min_len]

            # 计算VOCs/NOx比值
            vocs_nox_ratio = [v / n if n > 0 else 0 for v, n in zip(vocs_values, nox_values)]

            # 创建图形
            fig, axes = plt.subplots(1, 2, figsize=(14, 6))

            # 左图：O3 vs VOCs
            ax1 = axes[0]
            scatter1 = ax1.scatter(vocs_values, o3_values, c=nox_values, cmap='viridis',
                                  s=80, alpha=0.7, edgecolors='white', linewidths=0.8)
            cbar1 = plt.colorbar(scatter1, ax=ax1, shrink=0.8)
            cbar1.set_label('NOx浓度', fontsize=11)

            # 趋势线
            z_voc = np.polyfit(vocs_values, o3_values, 1)
            p_voc = np.poly1d(z_voc)
            x_voc_line = np.linspace(min(vocs_values), max(vocs_values), 100)
            ax1.plot(x_voc_line, p_voc_line := p_voc(x_voc_line), 'r--', linewidth=2, label='趋势线')

            ax1.set_xlabel('VOCs浓度 (ppbv)', fontsize=12, fontweight='bold')
            ax1.set_ylabel('O3浓度 (μg/m³)', fontsize=12, fontweight='bold')
            ax1.set_title('O3 vs VOCs', fontsize=14, fontweight='bold')
            ax1.grid(True, alpha=0.3, linestyle='--')
            ax1.legend(loc='upper left', fontsize=10)

            # 右图：O3 vs NOx
            ax2 = axes[1]
            scatter2 = ax2.scatter(nox_values, o3_values, c=vocs_values, cmap='plasma',
                                  s=80, alpha=0.7, edgecolors='white', linewidths=0.8)
            cbar2 = plt.colorbar(scatter2, ax=ax2, shrink=0.8)
            cbar2.set_label('VOCs浓度', fontsize=11)

            # 趋势线
            z_nox = np.polyfit(nox_values, o3_values, 1)
            p_nox = np.poly1d(z_nox)
            x_nox_line = np.linspace(min(nox_values), max(nox_values), 100)
            ax2.plot(x_nox_line, p_nox_line := p_nox(x_nox_line), 'r--', linewidth=2, label='趋势线')

            ax2.set_xlabel('NOx浓度 (ppbv)', fontsize=12, fontweight='bold')
            ax2.set_ylabel('O3浓度 (μg/m³)', fontsize=12, fontweight='bold')
            ax2.set_title('O3 vs NOx', fontsize=14, fontweight='bold')
            ax2.grid(True, alpha=0.3, linestyle='--')
            ax2.legend(loc='upper left', fontsize=10)

            # 标题
            title_text = f'臭氧前体物关系分析 - {station_name}' if station_name else '臭氧前体物关系分析'
            fig.suptitle(title_text, fontsize=16, fontweight='bold', y=1.02)

            # 添加水印
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            fig.text(0.5, 0.5, f'OBM Analysis {time_str}', fontsize=14, color='grey',
                    alpha=0.5, ha='center', va='center', rotation=45)

            plt.tight_layout()

            chart_id = f"ozone_balance_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(
                fig, chart_id,
                f'臭氧前体物关系分析 - {station_name}',
                "ozone_balance",
                "obm_balance_analysis",
                {"station_name": station_name}
            )

        except Exception as e:
            logger.warning(f"生成臭氧平衡图失败: {e}")
            return None

    def generate_all_charts(
        self,
        vocs_data: List[Dict],
        o3_data: List[Dict],
        nox_data: Optional[List[Dict]] = None,
        station_name: str = ""
    ) -> List[Dict[str, Any]]:
        """一键生成所有OBM分析图表"""
        visuals = []

        # EKMA等值线图
        ekma_chart = self.generate_ekma_contour(vocs_data, o3_data, nox_data, station_name)
        if ekma_chart:
            visuals.append(ekma_chart)

        # 减排情景模拟
        reduction_chart = self.generate_emission_reduction_scenarios(vocs_data, o3_data, nox_data, station_name)
        if reduction_chart:
            visuals.append(reduction_chart)

        # 臭氧平衡图
        balance_chart = self.generate_ozone_balance_chart(vocs_data, o3_data, nox_data, station_name)
        if balance_chart:
            visuals.append(balance_chart)

        logger.info(
            "[EKMAVisualizer] generate_all_charts 完成",
            total_visuals=len(visuals)
        )
        return visuals
