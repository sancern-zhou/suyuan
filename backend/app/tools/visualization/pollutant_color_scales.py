"""
污染物色阶配置 - 基于新标准日平均浓度限值

支持6色阶模式：
1. 绿色 (0,228,0) - 优
2. 黄色 (255,255,0) - 良
3. 橙色 (255,126,0) - 轻度污染
4. 红色 (255,0,0) - 中度污染
5. 紫色 (153,0,76) - 重度污染
6. 褐红色 (126,0,35) - 严重污染
"""

from typing import Dict, Tuple, List
import numpy as np
import matplotlib.colors as mcolors
import structlog

logger = structlog.get_logger()


# 6色阶颜色定义（RGB格式）
SIX_LEVEL_COLORS = [
    (0/255, 228/255, 0/255),    # 绿色：优
    (255/255, 255/255, 0/255),  # 黄色：良
    (255/255, 126/255, 0/255),  # 橙色：轻度污染
    (255/255, 0/255, 0/255),    # 红色：中度污染
    (153/255, 0/255, 76/255),   # 紫色：重度污染
    (126/255, 0/255, 35/255),   # 褐红色：严重污染
]

# 污染物日平均浓度限值（μg/m³，基于新标准）
# 6个界限对应：优-良-轻度-中度-重度-严重
POLLUTANT_THRESHOLDS = {
    'PM2.5': [0, 35, 75, 115, 150, 250],     # PM2.5日均值
    'PM10': [0, 50, 150, 250, 350, 420],      # PM10日均值
    'O3': [0, 100, 160, 215, 265, 800],       # O3日均值（1小时平均）或日均值
    'SO2': [0, 50, 150, 475, 800, 1600],      # SO2日均值
    'NO2': [0, 40, 80, 180, 280, 565],       # NO2日均值
    'CO': [0, 2, 4, 14, 24, 36],              # CO日均值（mg/m³）
    'default': [0, 50, 150, 250, 350, 500]    # 默认阈值
}


def get_six_level_colormap():
    """
    创建6色阶的LinearSegmentedColormap

    Returns:
        matplotlib colormap对象
    """
    return mcolors.LinearSegmentedColormap.from_list(
        'pollution_six_level',
        SIX_LEVEL_COLORS,
        N=256  # 插值到256个颜色级别
    )


def get_pollutant_thresholds(pollutant_name: str) -> List[float]:
    """
    获取污染物的6级阈值

    Args:
        pollutant_name: 污染物名称（如'PM2.5'）

    Returns:
        6个界限值列表
    """
    # 标准化污染物名称
    name_map = {
        'PM2_5': 'PM2.5',
        'PM10': 'PM10',
        'O3': 'O3',
        'SO2': 'SO2',
        'NO2': 'NO2',
        'CO': 'CO'
    }

    standard_name = name_map.get(pollutant_name, pollutant_name)

    thresholds = POLLUTANT_THRESHOLDS.get(standard_name)
    if thresholds is None:
        logger.warning(
            "pollutant_thresholds_not_found",
            pollutant=pollutant_name,
            using_default=True
        )
        thresholds = POLLUTANT_THRESHOLDS['default']

    return thresholds


def get_six_level_norm(pollutant_name: str, data_min: float, data_max: float):
    """
    创建6级归一化对象（用于matplotlib的contourf）

    设计原则：色阶始终显示完整的6级阈值范围，不受数据范围影响。
    即使数据只覆盖部分浓度区间，颜色条仍显示完整的标准限值。

    Args:
        pollutant_name: 污染物名称
        data_min: 数据最小值（仅用于验证，不修改bounds）
        data_max: 数据最大值（仅用于验证，不修改bounds）

    Returns:
        matplotlib.colors.BoundaryNorm对象
    """
    thresholds = get_pollutant_thresholds(pollutant_name)

    # 使用完整的阈值范围，不根据数据范围截断
    # 这样即使数据只覆盖"优"和"良"，颜色条仍显示全部6个等级
    bounds = thresholds[:]

    return mcolors.BoundaryNorm(bounds, ncolors=256)


def get_color_level_info(pollutant_name: str, concentration: float) -> Dict:
    """
    获取特定浓度值对应的等级信息

    Args:
        pollutant_name: 污染物名称
        concentration: 浓度值

    Returns:
        包含等级、颜色、描述的字典
    """
    thresholds = get_pollutant_thresholds(pollutant_name)

    level_names = ['优', '良', '轻度污染', '中度污染', '重度污染', '严重污染']
    color_names = ['绿色', '黄色', '橙色', '红色', '紫色', '褐红色']
    rgb_colors = [
        (0, 228, 0),
        (255, 255, 0),
        (255, 126, 0),
        (255, 0, 0),
        (153, 0, 76),
        (126, 0, 35)
    ]

    # 确定等级
    level = 0
    for i, threshold in enumerate(thresholds[1:], 1):
        if concentration <= threshold:
            level = i - 1
            break
    else:
        level = 5

    return {
        'level': level,
        'level_name': level_names[level],
        'color_name': color_names[level],
        'rgb': rgb_colors[level],
        'thresholds': thresholds
    }


def create_custom_colormap(pollutant_name: str, data_min: float, data_max: float):
    """
    创建针对特定污染物的自定义色阶映射

    Args:
        pollutant_name: 污染物名称
        data_min: 数据最小值
        data_max: 数据最大值

    Returns:
        (colormap, norm) 元组
    """
    cmap = get_six_level_colormap()
    norm = get_six_level_norm(pollutant_name, data_min, data_max)

    logger.info(
        "custom_colormap_created",
        pollutant=pollutant_name,
        data_range=(data_min, data_max),
        thresholds=get_pollutant_thresholds(pollutant_name)
    )

    return cmap, norm


# 为了兼容性，导出一些别名
POLLUTANT_SIX_LEVEL_COLORS = SIX_LEVEL_COLORS
POLLUTANT_SIX_LEVEL_THRESHOLDS = POLLUTANT_THRESHOLDS
