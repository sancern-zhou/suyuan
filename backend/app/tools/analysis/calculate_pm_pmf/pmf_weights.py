"""
PMF权重配置模块

根据规范6.1.2设置颗粒物和VOCs的PMF计算权重：
- 关键标识组分：权重=1.0（强）
- 非关键标识组分：权重=0.5（弱）
- 基于数据质量调整权重
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
import structlog

logger = structlog.get_logger()


# ==================== 颗粒物组分权重配置 ====================

# 关键标识组分（规范6.1.2）
PM_KEY_COMPONENTS = {
    # 水溶性离子
    "SO4": "硫酸盐",
    "SO4²⁻": "硫酸盐",
    "sulfate": "硫酸盐",
    "NO3": "硝酸盐",
    "NO3⁻": "硝酸盐",
    "nitrate": "硝酸盐",
    "NH4": "铵盐",
    "NH4⁺": "铵盐",
    "ammonium": "铵盐",
    "Cl": "氯离子",
    "Cl⁻": "氯离子",
    "chloride": "氯离子",
    # 碳组分
    "OC": "有机碳",
    "EC": "元素碳",
    # 地壳元素
    "Al": "铝",
    "Si": "硅",
    "Ca": "钙",
    "K": "钾",
    "Fe": "铁",
    "Ti": "钛",
}

# 非关键标识组分（规范6.1.2）
PM_SECONDARY_COMPONENTS = {
    "Na": "钠",
    "Mg": "镁",
    "Mn": "锰",
    "Cu": "铜",
    "Zn": "锌",
    "As": "砷",
    "Cd": "镉",
    "Pb": "铅",
    "Cr": "铬",
    "Ni": "镍",
    "V": "钒",
    "Ba": "钡",
    "Co": "钴",
    "Se": "硒",
    "Sr": "锶",
    "Br": "溴",
}


# ==================== VOCs组分权重配置 ====================

# VOCs关键标识组分（臭氧前体物特征物种）
VOCs_KEY_SPECIES = {
    # 乙烯丙烯（机动车尾气特征）
    "C2H4": "乙烯",
    " ethylene": "乙烯",
    "C2H6": "乙烷",
    " ethane": "乙烷",
    "C3H6": "丙烯",
    " propylene": "丙烯",
    "C3H8": "丙烷",
    " propane": "丙烷",
    # 芳烃（工业/溶剂源特征）
    "C6H6": "苯",
    " benzene": "苯",
    "C7H8": "甲苯",
    " toluene": "甲苯",
    "C8H10": "二甲苯/乙苯",
    " xylene": "二甲苯",
    " ethylbenzene": "乙苯",
    # 异戊二烯（生物源）
    "C5H8": "异戊二ene",
    " isoprene": "异戊二ene",
}

# VOCs非关键组分
VOCs_SECONDARY_SPECIES = {
    "propadiene": "丙二ene",
    "acetylene": "乙炔",
    "butane": "正丁烷",
    "isobutane": "异丁烷",
    "pentane": "正戊烷",
    "isopentane": "异戊烷",
    "cyclopentane": "环戊烷",
    "hexane": "正己烷",
    "2-methylpentane": "2-甲基戊烷",
    "3-methylpentane": "3-甲基戊烷",
    "2,2-dimethylbutane": "2,2-二甲基丁烷",
    "2,3-dimethylbutane": "2,3-二甲基丁烷",
    "methylcyclopentane": "甲基环戊烷",
    "cyclohexane": "环己ane",
    "heptane": "正庚烷",
    "2-methylhexane": "2-甲基己烷",
    "3-methylhexane": "3-甲基己烷",
    "2,2,4-trimethylpentane": "2,2,4-三甲基戊烷",
    "2,3,4-trimethylpentane": "2,3,4-三甲基戊烷",
    "styrene": "苯乙烯",
    "m-xylene": "间二甲苯",
    "o-xylene": "邻二甲苯",
    "p-xylene": "对二甲苯",
    "benzaldehyde": "苯甲醛",
}


@dataclass
class ComponentQuality:
    """组分数据质量指标"""
    component: str
    mean: float = 0.0
    std: float = 0.0
    cv: float = 0.0  # 变异系数
    missing_rate: float = 0.0  # 缺失率
    detection_rate: float = 1.0  # 检出率
    count: int = 0  # 有效数据数量


@dataclass
class PMFWeights:
    """PMF计算权重配置"""
    # 基础权重（1.0=强，0.5=弱）
    base_weights: Dict[str, float] = field(default_factory=dict)
    # 质量调整因子（0-1）
    quality_factors: Dict[str, float] = field(default_factory=dict)
    # 最终权重
    weights: Dict[str, float] = field(default_factory=dict)
    # 排除的组分
    excluded: List[str] = field(default_factory=list)
    # 关键组分列表
    key_components: List[str] = field(default_factory=list)
    # 数据质量统计
    quality_stats: Dict[str, ComponentQuality] = field(default_factory=dict)


class PMFWeightCalculator:
    """PMF权重计算器"""

    def __init__(self, pollutant_type: str = "PM"):
        """
        初始化权重计算器

        Args:
            pollutant_type: 污染物类型 ("PM" or "VOCs")
        """
        self.pollutant_type = pollutant_type
        self.key_components = PM_KEY_COMPONENTS if pollutant_type == "PM" else VOCs_KEY_SPECIES
        self.secondary_components = PM_SECONDARY_COMPONENTS if pollutant_type == "PM" else VOCs_SECONDARY_SPECIES

        logger.info(
            "pmf_weight_calculator_init",
            pollutant_type=pollutant_type,
            key_count=len(self.key_components),
            secondary_count=len(self.secondary_components)
        )

    def calculate_weights(
        self,
        component_data: List[Dict],
        component_mapping: Dict[str, str] = None
    ) -> PMFWeights:
        """
        计算PMF权重配置

        Args:
            component_data: 组分数据列表
            component_mapping: 字段映射（标准化后的字段名）

        Returns:
            PMFWeights对象
        """
        # Step 1: 计算各组分数据质量
        quality_stats = self._calculate_quality(component_data, component_mapping)

        # Step 2: 设置基础权重
        base_weights = self._set_base_weights(quality_stats)

        # Step 3: 计算质量调整因子
        quality_factors = self._calculate_quality_factors(quality_stats)

        # Step 4: 计算最终权重
        weights = {}
        for comp in base_weights:
            if comp in quality_stats:
                stats = quality_stats[comp]
                # 缺失率 > 20% 排除该组分
                if stats.missing_rate > 0.2:
                    continue
                # 权重 = 基础权重 × 质量因子
                weights[comp] = base_weights[comp] * quality_factors.get(comp, 1.0)
            else:
                weights[comp] = base_weights[comp]

        # Step 5: 识别关键组分
        key_components = [c for c in weights.keys() if base_weights.get(c, 0) >= 1.0]

        # Step 6: 确定排除的组分
        excluded = [c for c, q in quality_stats.items() if q.missing_rate > 0.2]

        result = PMFWeights(
            base_weights=base_weights,
            quality_factors=quality_factors,
            weights=weights,
            excluded=excluded,
            key_components=key_components,
            quality_stats=quality_stats
        )

        logger.info(
            "pmf_weights_calculated",
            total_components=len(weights),
            key_components=len(key_components),
            excluded=len(excluded)
        )

        return result

    def _calculate_quality(
        self,
        component_data: List[Dict],
        component_mapping: Dict[str, str] = None
    ) -> Dict[str, ComponentQuality]:
        """计算各组分数据质量"""
        quality_stats = {}

        # 收集所有组分值
        component_values = {}
        for record in component_data:
            if not isinstance(record, dict):
                continue

            # 遍历记录中的数值字段
            for key, value in record.items():
                if key in ("time", "timestamp", "station_name", "station_code"):
                    continue

                # 标准化字段名
                std_key = component_mapping.get(key, key) if component_mapping else key

                if std_key not in component_values:
                    component_values[std_key] = []

                if isinstance(value, (int, float)) and not np.isnan(value):
                    component_values[std_key].append(float(value))

        # 计算质量指标
        for comp, values in component_values.items():
            if len(values) < 3:
                continue

            arr = np.array(values)
            mean_val = np.mean(arr)
            std_val = np.std(arr)
            cv = std_val / (mean_val + 1e-10) if mean_val > 0 else 0

            quality_stats[comp] = ComponentQuality(
                component=comp,
                mean=mean_val,
                std=std_val,
                cv=cv,
                missing_rate=0.0,
                detection_rate=1.0,
                count=len(values)
            )

        # 计算缺失率（基于总样本数）
        total_samples = len(component_data)
        for comp in quality_stats:
            quality_stats[comp].missing_rate = 1.0 - quality_stats[comp].detection_rate

        return quality_stats

    def _set_base_weights(self, quality_stats: Dict[str, ComponentQuality]) -> Dict[str, float]:
        """设置基础权重"""
        base_weights = {}

        for comp in quality_stats.keys():
            # 关键组分权重=1.0
            if comp in self.key_components or comp in self.key_components.values():
                base_weights[comp] = 1.0
            # 非关键组分权重=0.5
            elif comp in self.secondary_components or comp in self.secondary_components.values():
                base_weights[comp] = 0.5
            # 默认权重
            else:
                base_weights[comp] = 0.5

        return base_weights

    def _calculate_quality_factors(self, quality_stats: Dict[str, ComponentQuality]) -> Dict[str, float]:
        """计算质量调整因子"""
        quality_factors = {}

        for comp, stats in quality_stats.items():
            if stats.count < 10:
                quality_factors[comp] = 1.0
                continue

            # 基于CV调整
            if stats.cv < 0.3:
                # CV < 30%，数据稳定，质量因子=1.0
                qf = 1.0
            elif stats.cv < 0.5:
                # 30% ≤ CV < 50%，质量因子=0.8
                qf = 0.8
            else:
                # CV ≥ 50%，不确定性高，质量因子=0.5
                qf = 0.5

            # 基于缺失率调整
            if stats.missing_rate > 0.2:
                qf = 0.0  # 排除

            quality_factors[comp] = qf

        return quality_factors

    def get_weights_for_nimfa(self, weights: PMFWeights) -> Tuple[np.ndarray, List[str]]:
        """
        转换为NIMFA需要的权重格式

        Returns:
            weight_matrix: 权重矩阵 (n_samples, n_components)
            component_names: 组分名称列表
        """
        if not weights.weights:
            return None, []

        component_names = list(weights.weights.keys())
        weight_values = list(weights.weights.values())

        # 构建权重矩阵（对角矩阵，每个组分一个权重）
        n_components = len(component_names)
        weight_matrix = np.diag(weight_values)

        return weight_matrix, component_names

    def generate_summary(self, weights: PMFWeights) -> str:
        """生成权重配置摘要"""
        lines = [
            "PMF权重配置摘要",
            "=" * 40,
            f"污染物类型: {self.pollutant_type}",
            f"总组分数: {len(weights.weights)}",
            f"关键组分数: {len(weights.key_components)}",
            f"排除组分数: {len(weights.excluded)}",
            "",
            "关键组分 (权重=1.0):",
        ]

        for comp in weights.key_components:
            w = weights.weights.get(comp, 0)
            stats = weights.quality_stats.get(comp)
            cv_str = f", CV={stats.cv:.2f}" if stats else ""
            lines.append(f"  - {comp}: {w:.1f}{cv_str}")

        if weights.excluded:
            lines.extend([
                "",
                "排除的组分 (缺失率>20%):",
            ])
            for comp in weights.excluded:
                lines.append(f"  - {comp}")

        return "\n".join(lines)


def calculate_pmf_weights(
    component_data: List[Dict],
    pollutant_type: str = "PM",
    component_mapping: Dict[str, str] = None
) -> PMFWeights:
    """
    便捷函数：计算PMF权重配置

    Args:
        component_data: 组分数据列表
        pollutant_type: 污染物类型 ("PM" or "VOCs")
        component_mapping: 字段映射

    Returns:
        PMFWeights对象
    """
    calculator = PMFWeightCalculator(pollutant_type)
    return calculator.calculate_weights(component_data, component_mapping)
