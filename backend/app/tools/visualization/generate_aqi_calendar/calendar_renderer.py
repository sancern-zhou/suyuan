"""
AQI日历图渲染器

使用matplotlib生成AQI日历热力图，支持：
- 单城市和多城市展示（最多21个）
- AQI及6项污染物指标
- 根据国家空气质量标准渲染颜色
"""

import math
import calendar
from io import BytesIO
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import matplotlib.font_manager as fm
import base64
import structlog

logger = structlog.get_logger()

# IAQI断点表（HJ 633-2026新标准）
IAQI_BREAKPOINTS_NEW = {
    'SO2': [(0, 0), (50, 50), (150, 100), (475, 150), (800, 200), (1600, 300), (2100, 400), (2620, 500)],
    'NO2': [(0, 0), (40, 50), (80, 100), (180, 150), (280, 200), (565, 300), (750, 400), (940, 500)],
    'PM10': [(0, 0), (50, 50), (150, 100), (250, 150), (350, 200), (420, 300), (500, 400), (600, 500)],
    'CO': [(0, 0), (2, 50), (4, 100), (14, 150), (24, 200), (36, 300), (48, 400), (60, 500)],
    'O3_8h': [(0, 0), (100, 50), (160, 100), (215, 150), (265, 200), (800, 300)],
    'PM2_5': [(0, 0), (35, 50), (75, 100), (115, 150), (150, 200), (250, 300), (350, 400), (500, 500)]
}

# 颜色等级映射（中等浅度版本）
AQI_COLOR_MAP = {
    'excellent': '#4CFF4C',    # 0-50: 优（中浅绿色）
    'good': '#FFFF66',         # 51-100: 良（中浅黄色）
    'lightly': '#FF9933',      # 101-150: 轻度污染（中浅橙色）
    'moderately': '#FF6666',   # 151-200: 中度污染（中浅红色）
    'heavily': '#B33366',      # 201-300: 重度污染（中浅紫色）
    'severely': '#993333',     # 301-500: 严重污染（中浅褐红色）
    'missing': '#DDDDDD'       # 缺失数据（中浅灰色）
}

# 广东省21个城市
GUANGDONG_CITIES = [
    '广州', '深圳', '珠海', '汕头', '佛山', '韶关', '湛江', '肇庆',
    '江门', '茂名', '惠州', '梅州', '汕尾', '河源', '阳江', '清远',
    '东莞', '中山', '潮州', '揭阳', '云浮'
]


def calculate_iaqi(concentration: float, pollutant: str) -> int:
    """计算污染物IAQI（基于HJ 633-2026新标准）

    Args:
        concentration: 污染物浓度值（μg/m³，CO为mg/m³）
        pollutant: 污染物名称

    Returns:
        IAQI值（整数）
    """
    if concentration is None or concentration <= 0:
        return 0

    # 特殊处理：O3_8h > 800时，IAQI固定为300
    if pollutant == 'O3_8h' and concentration > 800:
        return 300

    breakpoints = IAQI_BREAKPOINTS_NEW.get(pollutant, [])
    if not breakpoints:
        return 0

    # 分段线性插值
    for i in range(len(breakpoints) - 1):
        bp_lo, iaqi_lo = breakpoints[i]
        bp_hi, iaqi_hi = breakpoints[i + 1]

        if bp_lo <= concentration <= bp_hi:
            if bp_hi == bp_lo:
                return iaqi_hi
            iaqi = (iaqi_hi - iaqi_lo) / (bp_hi - bp_lo) * (concentration - bp_lo) + iaqi_lo
            import math
            return math.ceil(iaqi)

    return breakpoints[-1][1]


def get_aqi_color(aqi_value: Optional[int]) -> str:
    """根据AQI/IAQI值获取颜色

    Args:
        aqi_value: AQI/IAQI值，None表示缺失数据

    Returns:
        颜色代码（十六进制）
    """
    if aqi_value is None:
        return AQI_COLOR_MAP['missing']

    if aqi_value <= 50:
        return AQI_COLOR_MAP['excellent']
    elif aqi_value <= 100:
        return AQI_COLOR_MAP['good']
    elif aqi_value <= 150:
        return AQI_COLOR_MAP['lightly']
    elif aqi_value <= 200:
        return AQI_COLOR_MAP['moderately']
    elif aqi_value <= 300:
        return AQI_COLOR_MAP['heavily']
    else:
        return AQI_COLOR_MAP['severely']


def get_text_color(background_color: str) -> str:
    """根据背景颜色选择合适的文字颜色（黑色或白色）

    Args:
        background_color: 背景颜色代码（十六进制）

    Returns:
        文字颜色（'black' 或 'white'）
    """
    light_colors = ['#FFFF00', '#D3D3D3']  # 黄色、灰色用黑色文字
    if background_color in light_colors:
        return 'black'
    return 'white'


def setup_chinese_font():
    """配置中文字体

    字体优先级（从高到低）：
    1. 方正小标宋简体 - 用户安装字体（对"门"等字符显示更好）
    2. Microsoft YaHei - Windows系统字体
    3. Noto Sans CJK SC (Regular) - Google开源字体，系统自带
    4. Noto Sans CJK SC (Bold/Light/Medium) - Noto系列变体
    5. PingFang SC - macOS系统字体
    """
    import os
    from pathlib import Path

    # 构建字体路径列表（按优先级排序）
    font_configs = [
        # 用户安装的方正字体（最高优先级，避免Noto Sans的"门"字显示问题）
        # 使用绝对路径，因为服务可能以root用户运行
        {
            'path': Path('/home/xckj/.local/share/fonts/方正小标宋简.TTF'),
            'name': 'FZXiaoBiaoSong-B05S',
            'fonts': ['FZXiaoBiaoSong-B05S', 'Microsoft YaHei', 'SimHei']
        },
        # Windows Microsoft YaHei
        {
            'path': 'C:\\Windows\\Fonts\\msyh.ttc',
            'name': 'Microsoft YaHei',
            'fonts': ['Microsoft YaHei', 'SimHei']
        },
        # Linux Noto Sans CJK（系统字体）
        {
            'path': '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc',
            'name': 'Noto Sans CJK SC',
            'fonts': ['Noto Sans CJK SC', 'Noto Sans CJK JP', 'Noto Sans CJK TC', 'SimHei']
        },
        {
            'path': '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc',
            'name': 'Noto Sans CJK SC',
            'fonts': ['Noto Sans CJK SC', 'Noto Sans CJK JP', 'Noto Sans CJK TC', 'SimHei']
        },
        {
            'path': '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Medium.ttc',
            'name': 'Noto Sans CJK SC',
            'fonts': ['Noto Sans CJK SC', 'Noto Sans CJK JP', 'Noto Sans CJK TC', 'SimHei']
        },
        {
            'path': '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Light.ttc',
            'name': 'Noto Sans CJK SC',
            'fonts': ['Noto Sans CJK SC Light', 'Noto Sans CJK SC', 'Noto Sans CJK JP', 'SimHei']
        },
        # macOS PingFang
        {
            'path': '/System/Library/Fonts/PingFang.ttc',
            'name': 'PingFang SC',
            'fonts': ['PingFang SC', 'Heiti SC', 'STHeiti']
        }
    ]

    logger.info("setting_up_chinese_font", total_configs=len(font_configs))

    # 调试：输出当前用户和home目录
    import getpass
    current_user = getpass.getuser()
    home_dir = Path.home()
    logger.info("user_info", user=current_user, home_dir=str(home_dir))

    for config in font_configs:
        font_path = config['path']
        font_name = config['name']
        font_list = config['fonts']

        # 调试：输出字体检查信息
        path_exists = os.path.exists(font_path)
        logger.info("checking_font",
                   config_index=font_configs.index(config),
                   font_name=font_name,
                   font_path=str(font_path),
                   exists=path_exists)

        try:
            if os.path.exists(font_path):
                logger.info("found_font_file", path=str(font_path), name=font_name)

                # 添加字体到matplotlib
                fm.fontManager.addfont(str(font_path))

                # 设置字体列表
                plt.rcParams['font.sans-serif'] = font_list + ['DejaVu Sans']
                plt.rcParams['axes.unicode_minus'] = False

                logger.info("chinese_font_configured",
                           font_path=str(font_path),
                           primary_font=font_list[0],
                           font_list=font_list)
                return
        except Exception as e:
            logger.warning("font_load_failed",
                          font_path=str(font_path),
                          font_name=font_name,
                          error=str(e))
            continue

    # 回退到系统默认字体
    logger.warning("chinese_font_setup_failed", error="No suitable font found, using fallback")
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False


class AQICalendarRenderer:
    """AQI日历图渲染器"""

    def __init__(self):
        """初始化渲染器"""
        setup_chinese_font()

    def draw_matrix_heatmap(
        self,
        ax: plt.Axes,
        city_data_map: Dict[str, Dict[int, int]],
        year: int,
        month: int,
        pollutant: str
    ) -> None:
        """绘制矩阵热力图

        布局：
        - 第一行：日期（只显示有数据的日期）
        - 左侧：城市名（竖排）
        - 中间：热力图网格
        - 右侧：城市名（竖排，可选）

        Args:
            ax: matplotlib子图axes
            city_data_map: {city_name: {day: aqi_value}} 字典
            year: 年份
            month: 月份
            pollutant: 污染物指标
        """
        import calendar

        cities = list(city_data_map.keys())
        n_cities = len(cities)

        # 收集所有有数据的日期（至少有一个城市有数据的日期）
        days_with_data = set()
        for city in cities:
            days_with_data.update(city_data_map[city].keys())

        # 排序日期
        sorted_days = sorted(days_with_data)
        n_days = len(sorted_days)

        # 如果没有数据，返回
        if n_days == 0:
            logger.warning("no_data_to_display", cities=cities)
            return

        # 计算布局参数
        left_margin = 0.5  # 左侧城市名空间
        right_margin = 0.5  # 右侧城市名空间
        top_margin = 0.8    # 顶部日期行空间
        bottom_margin = 0.3

        # 网格区域
        grid_width = n_days
        grid_height = n_cities

        # 固定色块高度（12点）
        fixed_cell_height_pt = 12

        # 获取图形的DPI和尺寸（英寸）
        fig = ax.figure
        dpi = fig.dpi
        fig_height_inch = fig.get_size_inches()[1]

        # 计算固定高度在数据坐标系统中的对应值
        # 12点 = 12/72英寸 = 12/72 * dpi像素
        # 转换为数据坐标：(12/72 * dpi) / (fig_height_inch * dpi) * data_height
        # 简化：data_height = fig.get_ylim()[1]
        total_data_height = top_margin + grid_height + bottom_margin
        fixed_cell_height_data = (fixed_cell_height_pt / 72) * dpi / (fig_height_inch * dpi) * total_data_height
        fixed_cell_height_data = (fixed_cell_height_pt / 72) / fig_height_inch * total_data_height

        # 单元格大小
        cell_width = 1.0
        cell_height = fixed_cell_height_data

        # 调试日志：输出布局参数
        logger.info(
            "layout_parameters",
            n_cities=n_cities,
            n_days=n_days,
            sorted_days=sorted_days,
            left_margin=left_margin,
            right_margin=right_margin,
            top_margin=top_margin,
            bottom_margin=bottom_margin,
            grid_width=grid_width,
            grid_height=grid_height,
            fixed_cell_height_pt=fixed_cell_height_pt,
            cell_height_data=cell_height,
            dpi=dpi,
            fig_height_inch=fig_height_inch
        )

        # 设置子图范围（根据固定高度计算）
        ax.set_xlim(0, left_margin + grid_width * cell_width + right_margin)
        ax.set_ylim(0, top_margin + grid_height * cell_height + bottom_margin)
        ax.axis('off')

        # 调试日志：输出坐标范围
        logger.info(
            "axes_limits",
            xlim=ax.get_xlim(),
            ylim=ax.get_ylim(),
            xbound=ax.get_xbound(),
            ybound=ax.get_ybound()
        )

        # 绘制日期（第一行）- 只显示有数据的日期
        date_font_size = 12

        for idx, day in enumerate(sorted_days):
            x = left_margin + idx * cell_width + cell_width / 2
            y = top_margin + grid_height * cell_height + 0.3
            ax.text(x, y, str(day),
                   ha='center', va='bottom',
                   fontsize=date_font_size,
                   color='black')

        # 绘制城市名（左侧和右侧）
        for i, city in enumerate(cities):
            # 左侧城市名
            x_left = left_margin - 0.2
            y = top_margin + (n_cities - 1 - i) * cell_height + cell_height / 2

            # 城市名始终横向显示（rotation=0），通过y坐标控制竖排效果
            # 字体大小与网格高度一致（cell_height=1.0，转换为点数约12）
            ax.text(x_left, y, city,
                   ha='right', va='center',
                   fontsize=12,  # 与网格高度一致
                   color='black',
                   rotation=0)  # 始终横向显示，不旋转文字，使用默认sans-serif字体

            # 如果城市较多，右侧也显示城市名（辅助识别）
            if n_cities > 10:
                x_right = left_margin + grid_width * cell_width + 0.2
                ax.text(x_right, y, city,
                       ha='left', va='center',
                       fontsize=12,  # 与网格高度一致
                       color='black',
                       rotation=0)  # 横向显示，不旋转文字，使用默认sans-serif字体

        # 绘制热力图网格（只显示有数据的日期）
        for i, city in enumerate(cities):
            for idx, day in enumerate(sorted_days):
                # 计算位置（从上到下）
                x = left_margin + idx * cell_width
                y = top_margin + (n_cities - 1 - i) * cell_height

                # 获取AQI值和颜色
                aqi_value = city_data_map[city].get(day)
                color = get_aqi_color(aqi_value)

                # 绘制矩形
                rect = Rectangle((x, y), cell_width * 0.95, cell_height * 0.95,
                                facecolor=color, edgecolor='white', linewidth=0.5)
                ax.add_patch(rect)

                # 在每个网格中显示AQI值（移除单元格大小限制）
                if aqi_value is not None:
                    # 统一使用黑色，与城市名称字体一致（默认sans-serif字体）
                    font_size = 12  # 与网格高度一致
                    ax.text(x + cell_width/2, y + cell_height/2, str(aqi_value),
                           ha='center', va='center',
                           fontsize=font_size, color='black', weight='normal')

    def add_color_legend(self, fig: plt.Figure) -> None:
        """添加右侧垂直颜色图例

        格式：
        - 位置：表格主体右侧，垂直居中对齐
        - 结构：从上到下依次为「AQI」标题、6个分级色块+文字
        - 布局：每个分级横向显示「色块（含文字）+ 区间文字」
        - 顺序：严格按照AQI从低到高排列（优→良→轻度→中度→重度→严重）
        """
        # 图例数据（从低到高）
        legend_data = [
            ('优', '0-50', AQI_COLOR_MAP['excellent']),
            ('良', '51-100', AQI_COLOR_MAP['good']),
            ('轻度', '101-150', AQI_COLOR_MAP['lightly']),
            ('中度', '151-200', AQI_COLOR_MAP['moderately']),
            ('重度', '201-300', AQI_COLOR_MAP['heavily']),
            ('严重', '301-500', AQI_COLOR_MAP['severely'])
        ]

        # 创建右侧图例子图（位置在右侧，垂直布局，高度缩减为原来的一半）
        # [left, bottom, width, height] - 高度从0.6缩减到0.3，同时调整bottom保持垂直居中
        legend_ax = fig.add_axes([0.91, 0.35, 0.08, 0.3])
        legend_ax.axis('off')

        # 图例字体大小（使用已配置的中文字体）
        legend_font_size = 12
        legend_title_font_size = 14

        # 绘制AQI标题
        legend_ax.text(0.5, 0.95, 'AQI',
                      ha='center', va='top',
                      fontsize=legend_title_font_size,
                      weight='bold',
                      color='black')

        # 绘制色块和标签（垂直布局，紧密排列无间距）
        n_items = len(legend_data)
        item_height = 0.85 / n_items  # 每个项的高度

        for i, (label, range_text, color) in enumerate(legend_data):
            # 从上到下紧密排列
            y_top = 0.85 - i * item_height
            y_bottom = y_top - item_height

            # 色块（填满整个item_height，无间距）
            rect = Rectangle((0.05, y_bottom),
                            0.8, item_height,  # 高度等于item_height
                            facecolor=color, edgecolor='black', linewidth=0.5)
            legend_ax.add_patch(rect)

            # 色块内显示数字范围（0-50等），垂直居中
            y_center = (y_top + y_bottom) / 2
            legend_ax.text(0.45, y_center, range_text,
                          ha='center', va='center',
                          fontsize=legend_font_size,
                          color='black')

    def render_calendar(
        self,
        city_data_map: Dict[str, Dict[int, int]],
        year: int,
        month: int,
        pollutant: str
    ) -> str:
        """渲染完整的AQI日历图

        Args:
            city_data_map: {city_name: {day: aqi_value}} 字典
            year: 年份
            month: 月份
            pollutant: 污染物指标

        Returns:
            base64编码的图片数据
        """
        n_cities = len(city_data_map)

        # 调试日志
        logger.info(
            "render_calendar_start",
            n_cities=n_cities,
            city_names=list(city_data_map.keys()),
            year=year,
            month=month,
            pollutant=pollutant
        )

        # 收集所有有数据的日期（至少有一个城市有数据的日期）
        days_with_data = set()
        for city_data in city_data_map.values():
            days_with_data.update(city_data.keys())

        # 排序日期
        sorted_days = sorted(days_with_data)
        n_days_with_data = len(sorted_days)

        # 如果没有数据，返回错误
        if n_days_with_data == 0:
            raise ValueError("没有数据可用于渲染日历图")

        # 创建图形（矩阵热力图布局）
        # 宽度根据有数据的天数自适应，高度基于固定色块高度（12点）
        fixed_cell_height_pt = 12  # 每个色块固定12点
        fixed_cell_height_inch = fixed_cell_height_pt / 72  # 转换为英寸（1点=1/72英寸）

        # 计算图形尺寸
        fig_width = max(12, n_days_with_data * 0.4 + 3)  # 每天约0.4英寸

        # 高度计算：固定色块高度 * 城市数 + 边距
        # top_margin + bottom_margin ≈ 1.1英寸（标题0.8 + 底部0.3）
        margin_height_inch = 1.1
        fig_height = max(4, n_cities * fixed_cell_height_inch + margin_height_inch + 1)  # +1英寸作为额外边距

        logger.info(
            "figure_layout",
            fig_width=fig_width,
            fig_height=fig_height,
            n_cities=n_cities,
            n_days_with_data=n_days_with_data,
            sorted_days=sorted_days,
            fixed_cell_height_pt=fixed_cell_height_pt,
            fixed_cell_height_inch=fixed_cell_height_inch,
            margin_height_inch=margin_height_inch
        )

        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        # 添加总标题（使用已配置的中文字体）
        pollutant_name = self._get_pollutant_name(pollutant)
        title = f'{year}年{month}月 广东省{pollutant_name}日历'

        ax.set_title(title, fontsize=24, pad=20)

        logger.info("title_set", title=title)

        # 绘制矩阵热力图
        self.draw_matrix_heatmap(ax, city_data_map, year, month, pollutant)

        # 添加颜色图例
        self.add_color_legend(fig)

        # 调整布局：给右侧图例留出空间
        plt.tight_layout(rect=[0, 0.08, 0.9, 0.95])

        # 保存到BytesIO
        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=120, bbox_inches='tight')

        # 在关闭fig之前读取buffer内容
        image_bytes = buffer.getvalue()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        plt.close(fig)
        buffer.close()

        return image_base64

    def _get_pollutant_name(self, pollutant: str) -> str:
        """获取污染物的中文名称（使用 LaTeX 下标）"""
        # matplotlib 支持 LaTeX 格式的下标
        name_map = {
            'AQI': 'AQI',
            'SO2': r'SO$_2$',  # LaTeX 下标格式
            'NO2': r'NO$_2$',
            'CO': 'CO',
            'O3_8h': r'O$_3$ 8h',
            'PM2_5': 'PM2.5',
            'PM10': 'PM10'
        }
        return name_map.get(pollutant, pollutant)
