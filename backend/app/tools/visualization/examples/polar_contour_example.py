"""
极坐标等值线图生成器（平滑版本）

解决ECharts极坐标图扇区边界问题，使用matplotlib contourf实现完全平滑的极坐标等值线图。

使用方法：
    from app.tools.visualization.examples.polar_contour_example import generate_smooth_polar_contour

    # 示例数据
    wind_directions = [0, 45, 90, 135, 180, 225, 270, 315]
    wind_speeds = [2.5, 3.0, 2.8, 3.2, 2.6, 2.9, 3.1, 2.7]
    concentrations = [35.2, 42.1, 38.5, 45.3, 32.8, 40.2, 43.6, 37.9]

    # 生成平滑等值线图
    img_base64 = generate_smooth_polar_contour(
        wind_directions=wind_directions,
        wind_speeds=wind_speeds,
        concentrations=concentrations,
        title="PM10浓度极坐标等值线图（广雅中学，2026-03-01）",
        pollutant_name="PM10",
        unit="μg/m³"
    )

    # 返回给前端
    result = {
        "visuals": [{
            "id": "polar_contour_smooth",
            "type": "image",
            "title": "PM10浓度极坐标等值线图（平滑版）",
            "image_url": f"data:image/png;base64,{img_base64}",
            "meta": {
                "generator": "polar_contour_generator",
                "smooth_mode": true,
                "interpolation_method": "cubic"
            }
        }]
    }
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')  # 使用无GUI后端
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
import base64
from io import BytesIO
from typing import List, Tuple, Optional


def generate_smooth_polar_contour(
    wind_directions: List[float],
    wind_speeds: List[float],
    concentrations: List[float],
    title: str = "极坐标等值线图",
    pollutant_name: str = "PM10",
    unit: str = "μg/m³",
    grid_resolution: int = 100,
    interpolation_method: str = "cubic",
    contour_levels: int = 20,
    color_map: str = "RdYlBu_r",
    show_contour_lines: bool = True,
    dpi: int = 150
) -> str:
    """
    生成平滑的极坐标等值线图（无扇区边界）

    参数：
    ---
    wind_directions : List[float]
        风向角度（0-360度，0度为北）
    wind_speeds : List[float]
        风速（m/s）
    concentrations : List[float]
        污染物浓度值
    title : str
        图表标题
    pollutant_name : str
        污染物名称（用于颜色轴标签）
    unit : str
        浓度单位
    grid_resolution : int
        网格分辨率（默认100，越大越平滑但越慢）
    interpolation_method : str
        插值方法：'linear'（线性）、'cubic'（三次样条）、'nearest'（最近邻）
        推荐使用'cubic'获得最平滑效果
    contour_levels : int
        等值线层数（默认20，越多越平滑）
    color_map : str
        颜色映射（默认'RdYlBu_r'红-黄-蓝反转）
    show_contour_lines : bool
        是否显示等值线边界（增强可读性）
    dpi : int
        图片分辨率（默认150）

    返回：
    ---
    str : base64编码的PNG图片

    示例：
    ---
    >>> wind_dirs = [0, 45, 90, 135, 180, 225, 270, 315]
    >>> wind_spds = [2.5, 3.0, 2.8, 3.2, 2.6, 2.9, 3.1, 2.7]
    >>> concs = [35.2, 42.1, 38.5, 45.3, 32.8, 40.2, 43.6, 37.9]
    >>> img_b64 = generate_smooth_polar_contour(wind_dirs, wind_spds, concs)
    """
    # 输入验证
    if not (len(wind_directions) == len(wind_speeds) == len(concentrations)):
        raise ValueError("wind_directions, wind_speeds, concentrations 必须长度相同")

    if len(wind_directions) < 3:
        raise ValueError("至少需要3个数据点才能进行插值")

    # 转换为numpy数组
    wind_directions = np.array(wind_directions)
    wind_speeds = np.array(wind_speeds)
    concentrations = np.array(concentrations)

    # 1. 转换为笛卡尔坐标
    theta_rad = np.radians(wind_directions)
    x = wind_speeds * np.cos(theta_rad)
    y = wind_speeds * np.sin(theta_rad)

    # 2. 创建高分辨率网格（关键：网格越密，越平滑）
    x_min, x_max = x.min(), x.max()
    y_min, y_max = y.min(), y.max()

    # 扩展边界（避免边缘截断）
    x_padding = (x_max - x_min) * 0.1
    y_padding = (y_max - y_min) * 0.1

    xi = np.linspace(x_min - x_padding, x_max + x_padding, grid_resolution)
    yi = np.linspace(y_min - y_padding, y_max + y_padding, grid_resolution)
    xi, yi = np.meshgrid(xi, yi)

    # 3. 插值平滑（关键步骤）
    try:
        zi = griddata((x, y), concentrations, (xi, yi), method=interpolation_method)
    except Exception as e:
        # 如果三次样条插值失败，降级为线性插值
        if interpolation_method == 'cubic':
            print(f"警告：三次样条插值失败 ({e})，降级为线性插值")
            zi = griddata((x, y), concentrations, (xi, yi), method='linear')
        else:
            raise e

    # 处理NaN值（插值无法覆盖的区域）
    if np.any(np.isnan(zi)):
        print("警告：存在NaN值，使用最近邻插值填充")
        zi_nan = np.isnan(zi)
        zi[zi_nan] = griddata((x, y), concentrations, (xi[zi_nan], yi[zi_nan]), method='nearest')

    # 4. 转换回极坐标网格
    ri = np.sqrt(xi**2 + yi**2)
    thetai = np.arctan2(yi, xi)

    # 5. 创建极坐标图（关键：使用projection='polar'）
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111, projection='polar')

    # 6. 绘制等值线填充图（关键：contourf实现平滑渐变）
    contour = ax.contourf(
        thetai, ri, zi,
        levels=contour_levels,
        cmap=color_map,
        alpha=0.8
    )

    # 7. 添加等值线（可选，增强可读性）
    if show_contour_lines:
        ax.contour(
            thetai, ri, zi,
            levels=contour_levels,
            colors='black',
            linewidths=0.5,
            alpha=0.3
        )

    # 8. 添加颜色条
    cbar = plt.colorbar(contour, ax=ax, pad=0.1, shrink=0.8)
    cbar.set_label(f'{pollutant_name}浓度 ({unit})', rotation=270, labelpad=20, fontsize=12)

    # 9. 设置极坐标轴
    ax.set_theta_zero_location('N')  # 0度指向北
    ax.set_theta_direction(-1)        # 顺时针方向
    ax.set_xlabel('风速 (m/s)', fontsize=11)
    ax.set_title(title, pad=20, fontsize=14, weight='bold')

    # 10. 优化布局
    plt.tight_layout()

    # 11. 保存为base64
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    return img_base64


def generate_wind_rose_contour(
    wind_directions: List[float],
    wind_speeds: List[float],
    concentrations: List[float],
    title: str = "污染玫瑰图（等值线版）",
    pollutant_name: str = "PM10",
    unit: str = "μg/m³",
    **kwargs
) -> str:
    """
    生成污染玫瑰图（等值线版本）

    这是 `generate_smooth_polar_contour` 的别名，专门用于污染玫瑰图场景。

    参数同 `generate_smooth_polar_contour`

    示例：
    ---
    >>> # 生成污染玫瑰图
    >>> img_b64 = generate_wind_rose_contour(wind_dirs, wind_spds, concs)
    """
    return generate_smooth_polar_contour(
        wind_directions=wind_directions,
        wind_speeds=wind_speeds,
        concentrations=concentrations,
        title=title,
        pollutant_name=pollutant_name,
        unit=unit,
        **kwargs
    )


# ============================================
# 使用示例（可直接在execute_python_tool中调用）
# ============================================

if __name__ == "__main__":
    # 示例1：基本用法
    print("示例1：生成平滑极坐标等值线图")

    wind_dirs = [0, 45, 90, 135, 180, 225, 270, 315]
    wind_spds = [2.5, 3.0, 2.8, 3.2, 2.6, 2.9, 3.1, 2.7]
    concs = [35.2, 42.1, 38.5, 45.3, 32.8, 40.2, 43.6, 37.9]

    img_b64 = generate_smooth_polar_contour(
        wind_directions=wind_dirs,
        wind_speeds=wind_spds,
        concentrations=concs,
        title="PM10浓度极坐标等值线图（广雅中学，2026-03-01）",
        pollutant_name="PM10",
        unit="μg/m³",
        grid_resolution=100,
        interpolation_method="cubic",
        contour_levels=20
    )

    print(f"✅ 生成成功！Base64长度: {len(img_b64)}")
    print(f"✅ 可用于 <img src=\"data:image/png;base64,{img_b64[:50]}...\">")

    # 示例2：对比测试（不同插值方法）
    print("\n示例2：对比不同插值方法")

    methods = ['linear', 'cubic']
    for method in methods:
        print(f"  测试 {method} 插值...")
        try:
            img = generate_smooth_polar_contour(
                wind_directions=wind_dirs,
                wind_speeds=wind_spds,
                concentrations=concs,
                interpolation_method=method,
                title=f"PM10浓度图（{method}插值）"
            )
            print(f"  ✅ {method} 插值成功")
        except Exception as e:
            print(f"  ❌ {method} 插值失败: {e}")
