"""
RIR (Relative Incremental Reactivity) Analyzer

相对增量反应性分析器 - 评估各VOC物种对O3生成的贡献。

原理:
RIR(i) = [ΔP(O3) / P(O3)] / [ΔC(i) / C(i)]
通过扰动法计算各物种/组分的相对增量反应性。

功能:
1. 计算各VOC物种的RIR值
2. 识别关键控制物种
3. 评估减排优先级
4. 诊断敏感性区域

参考:
- D:\溯源\参考\OBM-deliver_20200901\rir_v0\
- Carter, W.P.L. (1994) Development of Ozone Reactivity Scales
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


class RIRVisualizer:
    """RIR可视化器"""

    def __init__(self, figure_size: tuple = (14, 6), dpi: int = 150):
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

    def generate_species_rir_chart(self, result: "RIRResult", base_vocs: Dict[str, float]) -> Dict[str, Any]:
        """生成关键VOC物种RIR贡献图"""
        try:
            fig, ax = plt.subplots(figsize=(12, 6), dpi=self.dpi)

            # 准备数据 - top_species 是 List[Tuple[str, float]]，不是 List[Dict]
            # Tuple: (species_name, rir_value)
            species_names = [item[0] for item in result.top_species]
            rir_values = [item[1] for item in result.top_species]
            # 修复: 直接使用RIR值（无量纲），不乘以浓度
            plot_values = [abs(rir) for rir in rir_values]

            # 绘制柱状图
            colors = ['#4CAF50' if r > 0 else '#F44336' for r in rir_values]
            bars = ax.barh(range(len(species_names)), plot_values, color=colors, alpha=0.8)

            # 添加浓度标注（如果浓度已知）
            for i, (bar, sp, rir) in enumerate(zip(bars, species_names, rir_values)):
                conc = base_vocs.get(sp, 0)
                if conc > 0:
                    ax.text(bar.get_width() + 0.001, bar.get_y() + bar.get_height()/2,
                           f'{conc:.2f}ppb', va='center', fontsize=8, alpha=0.7)

            ax.set_yticks(range(len(species_names)))
            ax.set_yticklabels(species_names)
            ax.set_xlabel('RIR值（无量纲）', fontsize=12)
            ax.set_title('关键VOC物种RIR贡献排名', fontsize=14, fontweight='bold', pad=15)

            # 敏感性信息
            regime_text = {
                "VOC-limited": "VOCs控制型",
                "NOx-limited": "NOx控制型",
                "transition": "过渡区"
            }.get(result.regime, result.regime)

            info_text = (
                f"敏感性类型: {regime_text}\n"
                f"NOx RIR: {result.nox_rir:.3f}\n"
                f"总VOCs RIR: {result.total_vocs_rir:.3f}"
            )
            ax.text(0.98, 0.02, info_text, transform=ax.transAxes,
                   horizontalalignment='right', verticalalignment='bottom',
                   bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9),
                   fontsize=10)

            ax.grid(True, alpha=0.3, axis='x')
            ax.invert_yaxis()

            plt.tight_layout()

            # 生成图片URL
            img_base64 = self._fig_to_base64(fig)
            saved_image_id = _save_image_to_cache(img_base64, "rir_species")
            image_url = f"/api/image/{saved_image_id}"

            return {
                "id": saved_image_id,
                "type": "chart",
                "schema": "chart_config",
                "payload": {
                    "id": saved_image_id,
                    "type": "image",
                    "title": "关键VOC物种RIR贡献排名",
                    "data": f"[IMAGE:{saved_image_id}]",
                    "image_id": saved_image_id,
                    "image_url": image_url,
                    "markdown_image": f"![关键VOC物种RIR贡献排名]({image_url})",
                    "meta": {
                        "schema_version": "3.1",
                        "generator": "RIRVisualizer",
                        "scenario": "rir_analysis",
                        "regime": result.regime,
                        "nox_rir": result.nox_rir,
                        "total_vocs_rir": result.total_vocs_rir
                    }
                },
                "meta": {
                    "schema_version": "v2.0",
                    "generator": "RIRVisualizer",
                    "scenario": "rir_analysis",
                    "image_id": saved_image_id,
                    "image_url": image_url,
                    "markdown_image": f"![关键VOC物种RIR贡献排名]({image_url})"
                }
            }

        except Exception as e:
            logger.error("rir_species_chart_generation_failed", error=str(e), exc_info=True)
            return {"error": str(e)}

    def generate_group_rir_chart(self, result: "RIRResult") -> Dict[str, Any]:
        """生成VOC分组RIR贡献饼图"""
        try:
            fig, ax = plt.subplots(figsize=(8, 8), dpi=self.dpi)

            # 准备数据
            group_data = [
                {"name": self._translate_group(g), "value": round(abs(rir) * 100, 1)}
                for g, rir in result.group_rir.items()
                if rir != 0
            ]

            if not group_data:
                return {"error": "无有效分组数据"}

            labels = [item["name"] for item in group_data]
            values = [item["value"] for item in group_data]

            # 颜色映射
            color_map = {
                "烷烃": "#2196F3",
                "烯烃": "#4CAF50",
                "芳香烃": "#FF9800",
                "醛酮类": "#9C27B0",
                "其他": "#607D8B"
            }
            colors = [color_map.get(name, "#999999") for name in labels]

            # 绘制饼图
            wedges, texts, autotexts = ax.pie(
                values, labels=labels, colors=colors,
                autopct='%1.1f%%', startangle=90,
                textprops={'fontsize': 11}
            )
            ax.set_title('VOC分组RIR贡献占比', fontsize=14, fontweight='bold', pad=20)

            # 敏感性信息
            regime_text = {
                "VOC-limited": "VOCs控制型",
                "NOx-limited": "NOx控制型",
                "transition": "过渡区"
            }.get(result.regime, result.regime)

            info_text = f"敏感性类型: {regime_text}"
            ax.text(0.5, -0.1, info_text, transform=ax.transAxes,
                   horizontalalignment='center',
                   bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9),
                   fontsize=10)

            plt.tight_layout()

            # 生成图片URL
            img_base64 = self._fig_to_base64(fig)
            saved_image_id = _save_image_to_cache(img_base64, "rir_group")
            image_url = f"/api/image/{saved_image_id}"

            return {
                "id": saved_image_id,
                "type": "chart",
                "schema": "chart_config",
                "payload": {
                    "id": saved_image_id,
                    "type": "image",
                    "title": "VOC分组RIR贡献占比",
                    "data": f"[IMAGE:{saved_image_id}]",
                    "image_id": saved_image_id,
                    "image_url": image_url,
                    "markdown_image": f"![VOC分组RIR贡献占比]({image_url})",
                    "meta": {
                        "schema_version": "3.1",
                        "generator": "RIRVisualizer",
                        "scenario": "rir_analysis",
                        "regime": result.regime
                    }
                },
                "meta": {
                    "schema_version": "v2.0",
                    "generator": "RIRVisualizer",
                    "scenario": "rir_analysis",
                    "image_id": saved_image_id,
                    "image_url": image_url,
                    "markdown_image": f"![VOC分组RIR贡献占比]({image_url})"
                }
            }

        except Exception as e:
            logger.error("rir_group_chart_generation_failed", error=str(e))
            return {"error": str(e)}

    def _translate_group(self, group: str) -> str:
        """翻译分组名"""
        translations = {
            "alkanes": "烷烃",
            "alkenes": "烯烃",
            "aromatics": "芳香烃",
            "carbonyls": "醛酮类",
            "others": "其他"
        }
        return translations.get(group, group)


@dataclass
class RIRResult:
    """RIR分析结果"""
    species_rir: Dict[str, float]  # 物种RIR值
    group_rir: Dict[str, float]  # 分组RIR值
    nox_rir: float  # NOx的RIR值
    total_vocs_rir: float  # 总VOCs的RIR值
    top_species: List[Tuple[str, float]]  # 前10关键物种
    regime: str  # 敏感性区域
    ln_ratio: float  # ln([HCHO]/[NOy]) 或 ln([H2O2]/[HNO3])


# VOC分组定义
VOC_GROUPS = {
    "alkanes": ["甲烷", "乙烷", "丙烷", "正丁烷", "异丁烷", "正戊烷", "异戊烷", 
                "正己烷", "正庚烷", "正辛烷", "2-甲基戊烷", "3-甲基戊烷",
                "2,2-二甲基丁烷", "2,3-二甲基丁烷", "2-甲基己烷", "3-甲基己烷",
                "环戊烷", "甲基环戊烷", "环己烷", "甲基环己烷"],
    "alkenes": ["乙烯", "丙烯", "1-丁烯", "反-2-丁烯", "顺-2-丁烯", "1-戊烯",
                "反-2-戊烯", "顺-2-戊烯", "异戊二烯", "1,3-丁二烯",
                "1-己烯", "异丁烯"],
    "aromatics": ["苯", "甲苯", "乙苯", "邻二甲苯", "间二甲苯", "对二甲苯",
                  "苯乙烯", "1,2,3-三甲苯", "1,2,4-三甲苯", "1,3,5-三甲苯",
                  "异丙苯", "正丙苯"],
    "carbonyls": ["甲醛", "乙醛", "丙醛", "丁醛", "戊醛", "丙酮", "丁酮",
                  "甲基乙基酮", "苯甲醛"],
    "others": ["乙炔", "MTBE", "氯甲烷", "二氯甲烷", "三氯甲烷", "四氯化碳",
               "1,2-二氯乙烷", "三氯乙烯", "四氯乙烯"]
}

# MIR系数 (Carter, 2010)
MIR_COEFFICIENTS = {
    "乙烯": 9.0, "丙烯": 11.66, "1-丁烯": 9.73, "异戊二烯": 10.61,
    "甲苯": 4.0, "邻二甲苯": 7.64, "间二甲苯": 9.75, "对二甲苯": 5.84,
    "乙苯": 3.04, "苯乙烯": 1.73, "苯": 0.72,
    "甲醛": 9.46, "乙醛": 6.54, "丙酮": 0.36,
    "乙烷": 0.28, "丙烷": 0.49, "正丁烷": 1.15, "异丁烷": 1.23,
    "正戊烷": 1.31, "异戊烷": 1.45, "正己烷": 1.24,
    "乙炔": 0.95
}


class RIRAnalyzer:
    """
    相对增量反应性(RIR)分析器
    
    通过扰动法评估各VOC物种对O3生成的相对贡献。
    
    使用:
        analyzer = RIRAnalyzer()
        result = analyzer.analyze(vocs_data, nox_data, o3_data)
    """
    
    # 扰动比例
    PERTURBATION_RATIO = 0.1  # 10%扰动
    
    def __init__(self, pybox_adapter=None):
        """
        初始化分析器
        
        Args:
            pybox_adapter: PyBox适配器 (可选，用于完整化学模拟)
        """
        self.pybox = pybox_adapter
        self.use_full_chemistry = pybox_adapter is not None
        
        logger.info(
            "rir_analyzer_initialized",
            mode="full_chemistry" if self.use_full_chemistry else "empirical"
        )
    
    def analyze(
        self,
        vocs_data: List[Dict],
        nox_data: List[Dict],
        o3_data: List[Dict],
        species_list: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        执行RIR分析
        
        Args:
            vocs_data: VOCs数据列表
            nox_data: NOx数据列表
            o3_data: O3数据列表
            species_list: 指定分析的物种列表 (可选)
        
        Returns:
            分析结果字典
        """
        try:
            # 提取基准浓度
            base_vocs = self._calculate_base_vocs(vocs_data)
            base_nox = self._calculate_base_nox(nox_data)
            base_o3 = self._calculate_base_o3(o3_data)
            
            if not base_vocs:
                return self._empty_result("无有效VOCs数据")
            
            # 计算基准O3生成潜势
            base_ofp = self._calculate_ofp(base_vocs, base_nox)
            
            if base_ofp <= 0:
                return self._empty_result("基准OFP为零")
            
            # 计算各物种RIR
            species_rir = {}
            for species, conc in base_vocs.items():
                if conc > 0 and species in MIR_COEFFICIENTS:
                    rir = self._calculate_species_rir(
                        species, conc, base_vocs, base_nox, base_ofp
                    )
                    species_rir[species] = rir
            
            # 计算分组RIR
            group_rir = self._calculate_group_rir(base_vocs, base_nox, base_ofp)
            
            # 计算NOx RIR
            nox_rir = self._calculate_nox_rir(base_vocs, base_nox, base_ofp)
            
            # 计算总VOCs RIR
            total_vocs_rir = sum(
                rir * base_vocs.get(sp, 0) / sum(base_vocs.values())
                for sp, rir in species_rir.items()
            )
            
            # 排序获取前10物种
            sorted_species = sorted(
                species_rir.items(), 
                key=lambda x: abs(x[1] * base_vocs.get(x[0], 0)),
                reverse=True
            )[:10]
            
            # 判断敏感性区域
            regime, ln_ratio = self._diagnose_regime(
                species_rir, nox_rir, total_vocs_rir, base_vocs, base_nox
            )
            
            result = RIRResult(
                species_rir=species_rir,
                group_rir=group_rir,
                nox_rir=nox_rir,
                total_vocs_rir=total_vocs_rir,
                top_species=sorted_species,
                regime=regime,
                ln_ratio=ln_ratio
            )
            
            logger.info(
                "rir_analysis_complete",
                species_count=len(species_rir),
                regime=regime,
                nox_rir=round(nox_rir, 4),
                vocs_rir=round(total_vocs_rir, 4)
            )
            
            return self._format_result(result, base_vocs)
            
        except Exception as e:
            logger.error("rir_analysis_failed", error=str(e))
            return self._empty_result(str(e))
    
    def _calculate_base_vocs(self, vocs_data: List[Dict]) -> Dict[str, float]:
        """计算基准VOCs浓度"""
        species_values = {}
        
        for record in vocs_data:
            # 处理species_data嵌套格式
            if "species_data" in record and isinstance(record["species_data"], dict):
                species = record["species_data"]
            else:
                skip_keys = {"timestamp", "time", "station_code", "station_name", 
                           "metadata", "unit", "qc_flag"}
                species = {k: v for k, v in record.items() 
                          if k.lower() not in skip_keys and isinstance(v, (int, float))}
            
            for sp, value in species.items():
                if isinstance(value, (int, float)) and value >= 0:
                    if sp not in species_values:
                        species_values[sp] = []
                    species_values[sp].append(value)
        
        # 使用均值
        base_vocs = {}
        for sp, values in species_values.items():
            if values:
                base_vocs[sp] = float(np.mean(values))
        
        return base_vocs
    
    def _calculate_base_nox(self, nox_data: List[Dict]) -> float:
        """计算基准NOx浓度"""
        nox_values = []
        
        for record in nox_data:
            value = self._extract_pollutant(record, ["NOx", "nox", "NO2", "no2"])
            if value is not None:
                nox_values.append(value)
        
        return float(np.mean(nox_values)) if nox_values else 30.0
    
    def _calculate_base_o3(self, o3_data: List[Dict]) -> float:
        """计算基准O3浓度"""
        o3_values = []
        
        for record in o3_data:
            value = self._extract_pollutant(record, ["O3", "o3", "Ozone"])
            if value is not None:
                o3_values.append(value)
        
        return float(np.mean(o3_values)) if o3_values else 80.0
    
    def _extract_pollutant(self, record: Dict, field_names: List[str]) -> Optional[float]:
        """提取污染物值"""
        for name in field_names:
            value = record.get(name)
            if value is not None and isinstance(value, (int, float)):
                return float(value)
        
        if "measurements" in record and isinstance(record["measurements"], dict):
            m = record["measurements"]
            for name in field_names:
                value = m.get(name)
                if value is not None and isinstance(value, (int, float)):
                    return float(value)
        
        return None
    
    def _calculate_ofp(self, vocs: Dict[str, float], nox: float) -> float:
        """计算O3生成潜势(OFP)"""
        ofp = 0.0
        for species, conc in vocs.items():
            mir = MIR_COEFFICIENTS.get(species, 1.0)
            ofp += conc * mir
        
        # NOx限制因子
        total_vocs = sum(vocs.values())
        vocs_nox_ratio = total_vocs / max(nox, 0.1)
        
        if vocs_nox_ratio < 4:
            # VOC-limited: OFP随VOCs线性增加
            nox_factor = 1.0
        elif vocs_nox_ratio > 15:
            # NOx-limited: OFP随NOx变化更敏感
            nox_factor = 0.5
        else:
            # 过渡区
            nox_factor = 1.0 - 0.5 * (vocs_nox_ratio - 4) / 11
        
        return ofp * nox_factor
    
    def _calculate_species_rir(
        self,
        species: str,
        conc: float,
        base_vocs: Dict[str, float],
        base_nox: float,
        base_ofp: float
    ) -> float:
        """计算单个物种的RIR"""
        # 扰动后浓度
        delta_conc = conc * self.PERTURBATION_RATIO
        
        # 创建扰动后的VOCs字典
        perturbed_vocs = base_vocs.copy()
        perturbed_vocs[species] = conc - delta_conc
        
        # 计算扰动后OFP
        perturbed_ofp = self._calculate_ofp(perturbed_vocs, base_nox)
        
        # 计算RIR
        delta_ofp = base_ofp - perturbed_ofp
        relative_delta_ofp = delta_ofp / base_ofp if base_ofp > 0 else 0
        relative_delta_conc = delta_conc / conc if conc > 0 else 0
        
        rir = relative_delta_ofp / relative_delta_conc if relative_delta_conc > 0 else 0
        
        return rir
    
    def _calculate_group_rir(
        self,
        base_vocs: Dict[str, float],
        base_nox: float,
        base_ofp: float
    ) -> Dict[str, float]:
        """计算分组RIR"""
        group_rir = {}
        
        for group_name, species_list in VOC_GROUPS.items():
            # 获取该组的物种
            group_species = {sp: base_vocs.get(sp, 0) for sp in species_list 
                           if sp in base_vocs and base_vocs[sp] > 0}
            
            if not group_species:
                group_rir[group_name] = 0.0
                continue
            
            # 扰动整组
            total_group = sum(group_species.values())
            delta_group = total_group * self.PERTURBATION_RATIO
            
            perturbed_vocs = base_vocs.copy()
            for sp in group_species:
                ratio = group_species[sp] / total_group
                perturbed_vocs[sp] = base_vocs[sp] - delta_group * ratio
            
            perturbed_ofp = self._calculate_ofp(perturbed_vocs, base_nox)
            
            delta_ofp = base_ofp - perturbed_ofp
            relative_delta_ofp = delta_ofp / base_ofp if base_ofp > 0 else 0
            relative_delta_conc = delta_group / total_group if total_group > 0 else 0
            
            rir = relative_delta_ofp / relative_delta_conc if relative_delta_conc > 0 else 0
            group_rir[group_name] = rir
        
        return group_rir
    
    def _calculate_nox_rir(
        self,
        base_vocs: Dict[str, float],
        base_nox: float,
        base_ofp: float
    ) -> float:
        """计算NOx的RIR"""
        delta_nox = base_nox * self.PERTURBATION_RATIO
        perturbed_nox = base_nox - delta_nox
        
        perturbed_ofp = self._calculate_ofp(base_vocs, perturbed_nox)
        
        delta_ofp = base_ofp - perturbed_ofp
        relative_delta_ofp = delta_ofp / base_ofp if base_ofp > 0 else 0
        relative_delta_nox = delta_nox / base_nox if base_nox > 0 else 0
        
        rir = relative_delta_ofp / relative_delta_nox if relative_delta_nox > 0 else 0
        
        return rir
    
    def _diagnose_regime(
        self,
        species_rir: Dict[str, float],
        nox_rir: float,
        total_vocs_rir: float,
        base_vocs: Dict[str, float],
        base_nox: float
    ) -> Tuple[str, float]:
        """诊断敏感性区域"""
        # 计算ln([HCHO]/[NOy]) 近似使用NOx
        hcho = base_vocs.get("甲醛", 0) or base_vocs.get("HCHO", 0)
        if hcho > 0 and base_nox > 0:
            ln_ratio = np.log(hcho / base_nox)
        else:
            # 使用VOCs/NOx比值代替
            total_vocs = sum(base_vocs.values())
            ln_ratio = np.log(total_vocs / max(base_nox, 0.1))
        
        # 基于RIR判断
        if nox_rir < 0:
            # NOx RIR为负说明减少NOx会增加O3，即VOC-limited
            regime = "VOC-limited"
        elif total_vocs_rir < nox_rir * 0.5:
            regime = "NOx-limited"
        elif total_vocs_rir > nox_rir * 2:
            regime = "VOC-limited"
        else:
            regime = "transition"
        
        return regime, ln_ratio
    
    def _format_result(self, result: RIRResult, base_vocs: Dict[str, float]) -> Dict[str, Any]:
        """格式化输出结果"""
        # 生成图片URL
        visualizer = RIRVisualizer()
        species_chart = visualizer.generate_species_rir_chart(result, base_vocs)
        group_chart = visualizer.generate_group_rir_chart(result)

        visuals = []
        if "error" not in species_chart:
            visuals.append(species_chart)
        if "error" not in group_chart:
            visuals.append(group_chart)

        return {
            "status": "success",
            "success": True,
            "data": {
                "species_rir": {k: round(v, 4) for k, v in result.species_rir.items()},
                "group_rir": {k: round(v, 4) for k, v in result.group_rir.items()},
                "nox_rir": round(result.nox_rir, 4),
                "total_vocs_rir": round(result.total_vocs_rir, 4),
                "top_species": [
                    {
                        "species": sp,
                        "rir": round(rir, 4),
                        "contribution": round(abs(rir * base_vocs.get(sp, 0)), 2)
                    }
                    for sp, rir in result.top_species
                ],
                "regime": result.regime,
                "ln_ratio": round(result.ln_ratio, 2),
                "interpretation": self._generate_interpretation(result)
            },
            "visuals": visuals,
            "metadata": {
                "schema_version": "v2.0",
                "generator": "RIRAnalyzer",
                "analysis_type": "rir",
                "species_count": len(result.species_rir),
                "regime": result.regime
            }
        }
    
    def _translate_group(self, group: str) -> str:
        """翻译分组名"""
        translations = {
            "alkanes": "烷烃",
            "alkenes": "烯烃",
            "aromatics": "芳香烃",
            "carbonyls": "醛酮类",
            "others": "其他"
        }
        return translations.get(group, group)
    
    def _generate_interpretation(self, result: RIRResult) -> str:
        """生成结果解读"""
        regime_text = {
            "VOC-limited": "VOCs控制区",
            "NOx-limited": "NOx控制区",
            "transition": "过渡区"
        }
        
        top3 = result.top_species[:3]
        top_species_text = "、".join([f"{sp}({round(rir, 2)})" for sp, rir in top3])
        
        if result.regime == "VOC-limited":
            advice = "建议优先控制VOCs排放，特别是高反应性物种"
        elif result.regime == "NOx-limited":
            advice = "建议优先控制NOx排放"
        else:
            advice = "建议VOCs和NOx协同控制"
        
        return (
            f"RIR分析表明当前处于{regime_text[result.regime]}。"
            f"NOx的RIR值为{result.nox_rir:.3f}，总VOCs的RIR值为{result.total_vocs_rir:.3f}。"
            f"关键控制物种为{top_species_text}。{advice}。"
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
                "generator": "RIRAnalyzer",
                "error": error
            },
            "summary": f"RIR分析失败: {error}"
        }
