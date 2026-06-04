"""
PO3 (Ozone Production Rate) Analyzer

臭氧生成速率分析器 - 计算O3净生成速率的时序变化。

原理:
P(O3) = k1[HO2][NO] + k2[RO2][NO] - k3[O3][NO] - k4[O3][alkenes]

功能:
1. 计算O3净生成速率时序
2. 分析HO2-NO、RO2-NO贡献
3. 识别O3生成高峰时段
4. 评估光化学活性

参考:
- D:\溯源\参考\OBM-deliver_20200901\po3_v1\
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from datetime import datetime
import structlog
import io
import base64

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

logger = structlog.get_logger()


def _save_image_to_cache(base64_data: str, chart_id: Optional[str] = None) -> str:
    """将base64图片保存到缓存，返回image_id"""
    from app.services.image_cache import get_image_cache
    cache = get_image_cache()
    if base64_data.startswith("data:image"):
        base64_data = base64_data.split(",", 1)[1]
    return cache.save(base64_data, chart_id)


class PO3Visualizer:
    """PO3可视化器"""

    def __init__(self, figure_size: tuple = (12, 6), dpi: int = 150):
        self.figure_size = figure_size
        self.dpi = dpi
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

    def _fig_to_base64(self, fig: plt.Figure) -> str:
        """将matplotlib图形转换为base64编码"""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=self.dpi, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig)
        return img_base64

    def generate_po3_timeseries(self, result: "PO3Result") -> Dict[str, Any]:
        """生成O3生成速率时序图"""
        try:
            fig, ax = plt.subplots(figsize=self.figure_size, dpi=self.dpi)

            # 提取数据
            timestamps = result.timestamps
            po3_net = result.po3_values
            po3_ho2 = result.po3_ho2_no
            po3_ro2 = result.po3_ro2_no

            # 绘制时序图
            ax.plot(timestamps, po3_net, 'r-', linewidth=2.5, label='净P(O3)', marker='o', markersize=4)
            ax.plot(timestamps, po3_ho2, 'b--', linewidth=1.5, label='HO2+NO', alpha=0.8)
            ax.plot(timestamps, po3_ro2, 'g--', linewidth=1.5, label='RO2+NO', alpha=0.8)

            # 标记最大值
            max_idx = np.argmax(po3_net)
            ax.scatter([timestamps[max_idx]], [po3_net[max_idx]], s=150, c='red', marker='*', zorder=5)
            ax.annotate(f'最大值: {result.max_po3:.1f} ppb/h\n{timestamps[max_idx]}',
                       xy=(timestamps[max_idx], po3_net[max_idx]),
                       xytext=(10, 20), textcoords='offset points',
                       fontsize=10, color='red',
                       arrowprops=dict(arrowstyle='->', color='red'))

            # 添加零线
            ax.axhline(y=0, color='gray', linestyle='-', linewidth=1, alpha=0.5)

            # 标题和标签
            ax.set_title('O3生成速率时序变化', fontsize=14, fontweight='bold', pad=15)
            ax.set_xlabel('时间', fontsize=12)
            ax.set_ylabel('P(O3) (ppb/h)', fontsize=12)

            # 敏感性信息
            regime_text = {
                "VOC-limited": "VOCs控制型",
                "NOx-limited": "NOx控制型",
                "transition": "过渡区"
            }.get(result.regime, result.regime)

            info_text = (
                f"敏感性类型: {regime_text}\n"
                f"最大P(O3): {result.max_po3:.1f} ppb/h\n"
                f"日累积生成: {result.daily_integrated:.1f} ppb"
            )
            ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                   verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9),
                   fontsize=10)

            ax.legend(loc='upper right', fontsize=10)
            ax.grid(True, alpha=0.3)

            # x轴标签优化
            if len(timestamps) > 10:
                step = len(timestamps) // 8
                ax.set_xticks(range(0, len(timestamps), step))
                ax.set_xticklabels([timestamps[i] for i in range(0, len(timestamps), step)], rotation=45, ha='right')

            plt.tight_layout()

            # 生成图片URL
            img_base64 = self._fig_to_base64(fig)
            saved_image_id = _save_image_to_cache(img_base64, "po3_timeseries")
            image_url = f"/api/image/{saved_image_id}"

            return {
                "id": saved_image_id,
                "type": "chart",
                "schema": "chart_config",
                "payload": {
                    "id": saved_image_id,
                    "type": "image",
                    "title": "O3生成速率时序变化",
                    "data": f"[IMAGE:{saved_image_id}]",
                    "image_id": saved_image_id,
                    "image_url": image_url,
                    "markdown_image": f"![O3生成速率时序变化]({image_url})",
                    "meta": {
                        "schema_version": "3.1",
                        "generator": "PO3Visualizer",
                        "scenario": "po3_analysis",
                        "max_po3": result.max_po3,
                        "max_time": result.max_po3_time,
                        "regime": result.regime
                    }
                },
                "meta": {
                    "schema_version": "v2.0",
                    "generator": "PO3Visualizer",
                    "scenario": "po3_analysis",
                    "image_id": saved_image_id,
                    "image_url": image_url,
                    "markdown_image": f"![O3生成速率时序变化]({image_url})"
                }
            }

        except Exception as e:
            logger.error("po3_timeseries_generation_failed", error=str(e))
            return {"error": str(e)}


@dataclass
class PO3Result:
    """PO3分析结果"""
    timestamps: List[str]
    po3_values: List[float]  # ppb/h
    po3_ho2_no: List[float]  # HO2+NO贡献
    po3_ro2_no: List[float]  # RO2+NO贡献
    loss_o3_no: List[float]  # O3+NO损失
    loss_o3_vocs: List[float]  # O3+VOCs损失
    max_po3: float
    max_po3_time: str
    daily_integrated: float  # 日累积O3生成量
    regime: str  # VOC-limited / NOx-limited / transition


class PO3Analyzer:
    """
    O3生成速率分析器
    
    计算臭氧的净化学生成速率，诊断光化学污染强度。
    
    使用:
        analyzer = PO3Analyzer()
        result = analyzer.analyze(vocs_data, nox_data, o3_data, meteo_data)
    """
    
    # 反应速率常数 (298K, 1atm)
    # k(HO2+NO) = 8.1e-12 cm3/molecule/s
    K_HO2_NO = 8.1e-12
    # k(CH3O2+NO) = 7.7e-12 cm3/molecule/s (代表RO2)
    K_RO2_NO = 7.7e-12
    # k(O3+NO) = 1.8e-14 cm3/molecule/s
    K_O3_NO = 1.8e-14
    # k(O3+alkene) ~ 1e-17 cm3/molecule/s (平均值)
    K_O3_ALKENE = 1.0e-17
    
    # 单位转换
    PPB_TO_MOLEC_CM3 = 2.46e10  # ppb -> molecules/cm3 at 298K, 1atm

    def __init__(
        self,
        temperature: float = 298.15,
        pressure: float = 1013.25,
        ho2_conc: Optional[float] = None,
        ro2_conc: Optional[float] = None,
        no_ratio: float = 0.3,
        alkene_ratio: float = 0.15
    ):
        """
        初始化分析器

        Args:
            temperature: 温度 (K)
            pressure: 气压 (hPa)
            ho2_conc: 代表性HO2浓度 (ppt)，None表示使用估算值
            ro2_conc: 代表性RO2浓度 (ppt)，None表示使用估算值
            no_ratio: NO/NOx比例，默认0.3
            alkene_ratio: 烯烃占VOCs比例，默认0.15
        """
        self.temperature = temperature
        self.pressure = pressure
        self.ho2_conc = ho2_conc
        self.ro2_conc = ro2_conc
        self.no_ratio = no_ratio
        self.alkene_ratio = alkene_ratio
        self._adjust_rate_constants()

        logger.info(
            "po3_analyzer_initialized",
            temperature=temperature,
            pressure=pressure,
            ho2_conc=ho2_conc,
            ro2_conc=ro2_conc,
            no_ratio=no_ratio,
            alkene_ratio=alkene_ratio
        )
    
    def _adjust_rate_constants(self):
        """根据温度调整速率常数 (Arrhenius方程)"""
        T = self.temperature
        T_ref = 298.15
        
        # 活化能 (J/mol)
        Ea_HO2_NO = -240 * 8.314  # 负活化能，温度升高速率下降
        Ea_RO2_NO = -180 * 8.314
        Ea_O3_NO = 1440 * 8.314
        Ea_O3_ALKENE = 1900 * 8.314
        
        R = 8.314  # J/mol/K
        
        self.k_ho2_no = self.K_HO2_NO * np.exp(-Ea_HO2_NO/R * (1/T - 1/T_ref))
        self.k_ro2_no = self.K_RO2_NO * np.exp(-Ea_RO2_NO/R * (1/T - 1/T_ref))
        self.k_o3_no = self.K_O3_NO * np.exp(-Ea_O3_NO/R * (1/T - 1/T_ref))
        self.k_o3_alkene = self.K_O3_ALKENE * np.exp(-Ea_O3_ALKENE/R * (1/T - 1/T_ref))
    
    def analyze(
        self,
        vocs_data: List[Dict],
        nox_data: List[Dict],
        o3_data: List[Dict],
        meteo_data: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        执行PO3分析
        
        Args:
            vocs_data: VOCs数据列表
            nox_data: NOx数据列表
            o3_data: O3数据列表
            meteo_data: 气象数据列表 (可选)
        
        Returns:
            分析结果字典
        """
        try:
            # 提取时序数据
            timestamps, vocs_ts, nox_ts, o3_ts = self._align_timeseries(
                vocs_data, nox_data, o3_data
            )
            
            if len(timestamps) < 2:
                return self._empty_result("数据点不足")
            
            # 估算自由基浓度
            ho2_ts, ro2_ts = self._estimate_radicals(vocs_ts, nox_ts, o3_ts)
            
            # 计算各项速率
            po3_ho2_no = []
            po3_ro2_no = []
            loss_o3_no = []
            loss_o3_vocs = []
            
            for i in range(len(timestamps)):
                no = nox_ts[i] * self.no_ratio * self.PPB_TO_MOLEC_CM3  # 可配置的NO/NOx比例
                no2 = nox_ts[i] * (1 - self.no_ratio) * self.PPB_TO_MOLEC_CM3
                o3 = o3_ts[i] * self.PPB_TO_MOLEC_CM3
                ho2 = ho2_ts[i] * self.PPB_TO_MOLEC_CM3
                ro2 = ro2_ts[i] * self.PPB_TO_MOLEC_CM3
                alkenes = vocs_ts[i] * self.alkene_ratio * self.PPB_TO_MOLEC_CM3  # 可配置的烯烃占比
                
                # P(O3) = k[HO2][NO] + k[RO2][NO]
                p_ho2 = self.k_ho2_no * ho2 * no / self.PPB_TO_MOLEC_CM3 * 3600  # ppb/h
                p_ro2 = self.k_ro2_no * ro2 * no / self.PPB_TO_MOLEC_CM3 * 3600
                
                # L(O3) = k[O3][NO] + k[O3][alkenes]
                l_no = self.k_o3_no * o3 * no / self.PPB_TO_MOLEC_CM3 * 3600
                l_alkene = self.k_o3_alkene * o3 * alkenes / self.PPB_TO_MOLEC_CM3 * 3600
                
                po3_ho2_no.append(float(p_ho2))
                po3_ro2_no.append(float(p_ro2))
                loss_o3_no.append(float(l_no))
                loss_o3_vocs.append(float(l_alkene))
            
            # 计算净PO3
            po3_net = [
                po3_ho2_no[i] + po3_ro2_no[i] - loss_o3_no[i] - loss_o3_vocs[i]
                for i in range(len(timestamps))
            ]
            
            # 统计指标
            max_idx = np.argmax(po3_net)
            max_po3 = po3_net[max_idx]
            max_po3_time = timestamps[max_idx]
            
            # 日累积 (简单积分)
            daily_integrated = sum(po3_net) / len(po3_net) * 24  # 假设均匀分布
            
            # 判断敏感性区域
            avg_vocs = np.mean(vocs_ts)
            avg_nox = np.mean(nox_ts)
            vocs_nox_ratio = avg_vocs / max(avg_nox, 0.1)
            
            if vocs_nox_ratio < 4:
                regime = "VOC-limited"
            elif vocs_nox_ratio > 15:
                regime = "NOx-limited"
            else:
                regime = "transition"
            
            result = PO3Result(
                timestamps=timestamps,
                po3_values=po3_net,
                po3_ho2_no=po3_ho2_no,
                po3_ro2_no=po3_ro2_no,
                loss_o3_no=loss_o3_no,
                loss_o3_vocs=loss_o3_vocs,
                max_po3=max_po3,
                max_po3_time=max_po3_time,
                daily_integrated=daily_integrated,
                regime=regime
            )
            
            logger.info(
                "po3_analysis_complete",
                max_po3=max_po3,
                max_time=max_po3_time,
                regime=regime,
                daily_integrated=daily_integrated
            )
            
            return self._format_result(result)
            
        except Exception as e:
            logger.error("po3_analysis_failed", error=str(e))
            return self._empty_result(str(e))
    
    def _align_timeseries(
        self,
        vocs_data: List[Dict],
        nox_data: List[Dict],
        o3_data: List[Dict]
    ) -> Tuple[List[str], List[float], List[float], List[float]]:
        """对齐时序数据"""
        # 提取VOCs总量时序
        vocs_dict = {}
        for record in vocs_data:
            ts = record.get("timestamp") or record.get("time") or record.get("TimePoint")
            if ts:
                ts_str = str(ts)[:19]
                total = self._extract_total_vocs(record)
                vocs_dict[ts_str] = total
        
        # 提取NOx时序
        nox_dict = {}
        for record in nox_data:
            ts = record.get("timestamp") or record.get("time")
            if ts:
                ts_str = str(ts)[:19]
                nox = self._extract_pollutant(record, ["NOx", "nox", "NO2", "no2"])
                if nox is not None:
                    nox_dict[ts_str] = nox
        
        # 提取O3时序
        o3_dict = {}
        for record in o3_data:
            ts = record.get("timestamp") or record.get("time")
            if ts:
                ts_str = str(ts)[:19]
                o3 = self._extract_pollutant(record, ["O3", "o3", "Ozone"])
                if o3 is not None:
                    o3_dict[ts_str] = o3
        
        # 找公共时间戳
        common_ts = sorted(set(vocs_dict.keys()) & set(nox_dict.keys()) & set(o3_dict.keys()))
        
        timestamps = []
        vocs_ts = []
        nox_ts = []
        o3_ts = []
        
        for ts in common_ts:
            timestamps.append(ts)
            vocs_ts.append(vocs_dict[ts])
            nox_ts.append(nox_dict[ts])
            o3_ts.append(o3_dict[ts])
        
        return timestamps, vocs_ts, nox_ts, o3_ts
    
    def _extract_total_vocs(self, record: Dict) -> float:
        """提取VOCs总量"""
        # 处理species_data嵌套格式
        if "species_data" in record and isinstance(record["species_data"], dict):
            species = record["species_data"]
        else:
            skip_keys = {"timestamp", "time", "station_code", "station_name", "metadata", "unit"}
            species = {k: v for k, v in record.items() 
                      if k.lower() not in skip_keys and isinstance(v, (int, float))}
        
        total = sum(v for v in species.values() if isinstance(v, (int, float)) and v >= 0)
        return total
    
    def _extract_pollutant(self, record: Dict, field_names: List[str]) -> Optional[float]:
        """提取污染物值"""
        # 直接提取
        for name in field_names:
            value = record.get(name)
            if value is not None and isinstance(value, (int, float)):
                return float(value)
        
        # 从measurements提取
        if "measurements" in record and isinstance(record["measurements"], dict):
            m = record["measurements"]
            for name in field_names:
                value = m.get(name)
                if value is not None and isinstance(value, (int, float)):
                    return float(value)
        
        return None
    
    def _estimate_radicals(
        self,
        vocs_ts: List[float],
        nox_ts: List[float],
        o3_ts: List[float]
    ) -> Tuple[List[float], List[float]]:
        """
        估算HO2和RO2自由基浓度

        使用简化的光化学稳态假设(PSS):
        [HO2] ≈ f([O3], [NOx], J_values)

        如果用户提供了代表性浓度(ho2_conc/ro2_conc)，则直接使用该值
        否则使用经验关系估算
        """
        ho2_ts = []
        ro2_ts = []

        # 如果用户提供了代表性浓度，使用固定值
        if self.ho2_conc is not None:
            ho2_ts = [self.ho2_conc] * len(vocs_ts)
        else:
            # 使用经验公式估算
            for i in range(len(vocs_ts)):
                vocs = vocs_ts[i]
                nox = nox_ts[i]
                o3 = o3_ts[i]

                # 简化估算 (基于典型观测关系)
                # [HO2] ~ 10-50 ppt, 与O3和VOCs正相关，与NOx负相关
                if nox > 0:
                    ho2 = 0.02 * (o3 ** 0.5) * (vocs ** 0.3) / (nox ** 0.2)  # ppt
                else:
                    ho2 = 0.05

                # 限制范围 (5-100 ppt)
                ho2 = max(0.005, min(0.1, ho2))
                ho2_ts.append(ho2)

        if self.ro2_conc is not None:
            ro2_ts = [self.ro2_conc] * len(vocs_ts)
        else:
            # 使用经验公式估算
            for i in range(len(vocs_ts)):
                vocs = vocs_ts[i]
                nox = nox_ts[i]

                if nox > 0:
                    ro2 = 0.015 * (vocs ** 0.5) / (nox ** 0.3)  # ppt
                else:
                    ro2 = 0.03

                # 限制范围 (3-80 ppt)
                ro2 = max(0.003, min(0.08, ro2))
                ro2_ts.append(ro2)

        return ho2_ts, ro2_ts
    
    def _format_result(self, result: PO3Result) -> Dict[str, Any]:
        """格式化输出结果"""
        # 生成图片URL
        visualizer = PO3Visualizer()
        po3_chart = visualizer.generate_po3_timeseries(result)

        return {
            "status": "success",
            "success": True,
            "data": {
                "timeseries": {
                    "timestamps": result.timestamps,
                    "po3_net": result.po3_values,
                    "po3_ho2_no": result.po3_ho2_no,
                    "po3_ro2_no": result.po3_ro2_no,
                    "loss_o3_no": result.loss_o3_no,
                    "loss_o3_vocs": result.loss_o3_vocs
                },
                "statistics": {
                    "max_po3": round(result.max_po3, 2),
                    "max_po3_time": result.max_po3_time,
                    "daily_integrated": round(result.daily_integrated, 2),
                    "regime": result.regime
                },
                "interpretation": self._generate_interpretation(result)
            },
            "visuals": [po3_chart] if "error" not in po3_chart else [],
            "metadata": {
                "schema_version": "v2.0",
                "generator": "PO3Analyzer",
                "analysis_type": "po3",
                "record_count": len(result.timestamps)
            }
        }
    
    def _generate_interpretation(self, result: PO3Result) -> str:
        """生成结果解读"""
        regime_text = {
            "VOC-limited": "VOCs控制区，减少VOCs排放更有效",
            "NOx-limited": "NOx控制区，减少NOx排放更有效",
            "transition": "过渡区，需要VOCs和NOx协同控制"
        }
        
        if result.max_po3 > 20:
            intensity = "高强度光化学污染"
        elif result.max_po3 > 10:
            intensity = "中等强度光化学污染"
        elif result.max_po3 > 5:
            intensity = "轻度光化学污染"
        else:
            intensity = "光化学活性较低"
        
        return (
            f"分析结果显示{intensity}，最大O3生成速率为{result.max_po3:.1f} ppb/h，"
            f"出现在{result.max_po3_time}。日累积O3生成量约{result.daily_integrated:.1f} ppb。"
            f"敏感性诊断表明当前处于{result.regime}（{regime_text[result.regime]}）。"
        )
    
    def _empty_result(self, error: str) -> Dict[str, Any]:
        """返回空结果"""
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "visuals": [],
            "metadata": {
                "schema_version": "v2.0",
                "generator": "PO3Analyzer",
                "error": error
            },
            "summary": f"PO3分析失败: {error}"
        }
