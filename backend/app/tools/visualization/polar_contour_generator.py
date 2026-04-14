"""
极坐标热力型污染玫瑰图生成器 - 双模式支持

支持两种技术方案：
1. Matplotlib方案：平滑静态图（适合报告生成）
2. ECharts方案：交互式图表（适合数据探索）
"""

from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
import base64
from io import BytesIO
import json
import structlog
import os
from pathlib import Path

logger = structlog.get_logger()

# 导入6色阶支持
try:
    from app.tools.visualization.pollutant_color_scales import (
        create_custom_colormap,
        get_pollutant_thresholds,
        SIX_LEVEL_COLORS
    )
    SIX_LEVEL_SUPPORT = True
except ImportError:
    SIX_LEVEL_SUPPORT = False
    logger.warning("pollutant_color_scales_not_available", six_level_mode=False)


def aggregate_by_time(
    timestamps: List[str],
    wind_directions: List[float],
    wind_speeds: List[float],
    concentrations: List[float],
    resolution: str = "hour"
) -> Tuple[List[float], List[float], List[float]]:
    """
    按时间分辨率聚合数据

    关键统计方法：
    - 风向：矢量平均（分解为u, v分量，平均后再合成）
    - 风速：算术平均
    - 浓度：算术平均

    Args:
        timestamps: 时间戳列表（格式：YYYY-MM-DD HH:MM:SS）
        wind_directions: 风向列表（度数，0-360）
        wind_speeds: 风速列表（m/s）
        concentrations: 浓度列表
        resolution: 时间分辨率（5min/hour/day）

    Returns:
        (聚合后的风向, 风速, 浓度) 元组
    """
    import pandas as pd

    if resolution == "5min":
        # 不需要聚合
        return wind_directions, wind_speeds, concentrations

    # 创建DataFrame
    df = pd.DataFrame({
        'time': pd.to_datetime(timestamps),
        'wind_dir': wind_directions,
        'wind_speed': wind_speeds,
        'concentration': concentrations
    })

    # 分解风向为u, v分量（用于矢量平均）
    df['u'] = np.cos(np.radians(df['wind_dir']))
    df['v'] = np.sin(np.radians(df['wind_dir']))

    # 按时间分辨率分组
    if resolution == "hour":
        df['time_group'] = df['time'].dt.floor('H')
    elif resolution == "day":
        df['time_group'] = df['time'].dt.floor('D')
    else:
        logger.warning("unknown_time_resolution", resolution=resolution, fallback="no_aggregation")
        return wind_directions, wind_speeds, concentrations

    # 聚合统计
    grouped = df.groupby('time_group').agg({
        'u': 'mean',           # u分量平均
        'v': 'mean',           # v分量平均
        'wind_speed': 'mean',  # 风速平均
        'concentration': 'mean'  # 浓度平均
    })

    # 重新合成风向（从平均的u, v分量）
    avg_wind_dir = np.degrees(np.arctan2(grouped['v'], grouped['u'])) % 360
    avg_wind_speed = grouped['wind_speed'].values
    avg_concentration = grouped['concentration'].values

    logger.info(
        "time_aggregation_completed",
        resolution=resolution,
        original_count=len(timestamps),
        aggregated_count=len(avg_wind_dir),
        data_reduction=f"{len(avg_wind_dir) / len(timestamps) * 100:.1f}%"
    )

    return avg_wind_dir.tolist(), avg_wind_speed.tolist(), avg_concentration.tolist()


def load_data_from_id(data_id: str, data_dir: str = None) -> List[Dict]:
    """
    从 data_id 加载数据

    Args:
        data_id: 数据ID（如：air_quality_5min:v1:xxx）
        data_dir: 数据目录路径（默认使用项目标准路径）

    Returns:
        数据记录列表

    Raises:
        FileNotFoundError: 数据文件不存在
    """
    if data_dir is None:
        # 使用项目标准数据目录
        data_dir = "/home/xckj/suyuan/backend/backend_data_registry/datasets"

    # 将 data_id 中的冒号替换为下划线（文件命名规则）
    filename = f"{data_id.replace(':', '_')}.json"
    filepath = os.path.join(data_dir, filename)

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"数据文件不存在：{filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    logger.info(
        "data_loaded_from_id",
        data_id=data_id,
        filepath=filepath,
        record_count=len(data)
    )

    return data


def generate_pollution_rose_contour(
    # 新增：支持 data_id 模式（推荐，简化 LLM 调用）
    data_id: str = None,
    time_resolution: str = "hour",  # 新增：时间分辨率（5min/hour/day）

    # 保留：支持直接传数据模式（向后兼容）
    wind_directions: List[float] = None,
    wind_speeds: List[float] = None,
    concentrations: List[float] = None,

    # 其他参数
    title: str = "极坐标热力型污染玫瑰图",
    pollutant_name: str = "PM10",
    unit: str = "μg/m³",
    grid_resolution: int = 100,
    interpolation_method: str = "cubic",
    contour_levels: int = 20,
    color_map: str = "RdYlBu_r",
    value_range: Tuple[float, float] = None,
    use_six_level: bool = True,
    dpi: int = 150
) -> str:
    """
    生成极坐标热力型污染玫瑰图（matplotlib平滑方案）

    图表特征：
    - 方位轴：N/E/S/W四个主方向
    - 径向轴：同心圆1-5 m/s
    - 颜色编码：
        - 默认模式：深蓝（低浓度）→ 深红（高浓度）
        - 6色阶模式：绿→黄→橙→红→紫→褐红（基于新标准）

    Args:
        # ========== 新增：data_id 模式（推荐） ==========
        data_id: 数据ID（如：air_quality_5min:v1:xxx），传入后自动加载和处理数据
        time_resolution: 时间分辨率（5min/hour/day，默认hour）
                        - 5min：使用原始5分钟数据
                        - hour：按小时聚合（风向矢量平均，风速/浓度算术平均）
                        - day：按日聚合（统计方法同hour）

        # ========== 保留：直接传数据模式（向后兼容） ==========
        wind_directions: 风向列表（度数，0-360），仅在 data_id=None 时使用
        wind_speeds: 风速列表（m/s），仅在 data_id=None 时使用
        concentrations: 污染物浓度列表，仅在 data_id=None 时使用

        # ========== 其他参数 ==========
        title: 图表标题
        pollutant_name: 污染物名称（如：PM10, PM2_5, O3, NO2, SO2, CO）
        unit: 浓度单位
        grid_resolution: 网格分辨率（仅在默认模式下使用，6色阶模式下内部固定为100）
        interpolation_method: 插值方法（仅在默认模式下使用，6色阶模式下内部固定为cubic）
        contour_levels: 等值线层数（仅在默认模式下使用）
        color_map: 颜色映射（仅在默认模式下使用，6色阶模式下使用固定的6色阶映射）
        value_range: 浓度范围（min, max），None则自动计算（6色阶模式下内部固定为阈值范围）
        use_six_level: 是否使用6色阶模式（默认True）
                      - True时，内部固定以下参数：grid_resolution=100, interpolation_method="cubic",
                        dpi=150, value_range=阈值范围, color_map=6色阶映射
                      - False时，使用用户传入的参数
        dpi: 图片分辨率（仅在默认模式下使用，6色阶模式下内部固定为150）

    Returns:
        base64编码的PNG图片

    Raises:
        ValueError: 输入数据长度不一致或为空
        FileNotFoundError: data_id 对应的数据文件不存在

    Note:
        6色阶模式下强制显示完整的6色阶图例，即使数据没有覆盖所有浓度范围。
        这确保了图表的可比性和标准化。

    Examples:
        # 推荐用法：使用 data_id
        img = generate_pollution_rose_contour(
            data_id="air_quality_5min:v1:xxx",
            pollutant_name="PM10",
            time_resolution="hour"
        )

        # 传统用法：直接传数据
        img = generate_pollution_rose_contour(
            wind_directions=[...],
            wind_speeds=[...],
            concentrations=[...],
            pollutant_name="PM10"
        )
    """
    # 定义6色阶模式的内部固定参数（降低LLM输入负担）
    FIXED_SIX_LEVEL_PARAMS = {
        "grid_resolution": 100,
        "interpolation_method": "cubic",
        "dpi": 150
    }

    # ========== 阶段1：数据加载和处理 ==========
    if data_id is not None:
        # 使用 data_id 模式（推荐）
        logger.info(
            "using_data_id_mode",
            data_id=data_id,
            time_resolution=time_resolution,
            pollutant_name=pollutant_name
        )

        # 1. 加载数据
        data = load_data_from_id(data_id)

        # 2. 自动提取字段
        try:
            timestamps = [record['timestamp'] for record in data]
            wind_dirs_extracted = [float(record['wind_direction_10m']) for record in data]
            wind_speeds_extracted = [float(record['wind_speed_10m']) for record in data]
            concs_extracted = [float(record[pollutant_name]) for record in data]
        except KeyError as e:
            raise ValueError(
                f"数据文件中缺少必要字段：{e}。"
                f"请确认 pollutant_name='{pollutant_name}' 是否正确。"
                f"可用字段：{list(data[0].keys()) if data else 'N/A'}"
            )

        # 3. 时间聚合（如果需要）
        if time_resolution in ["hour", "day"]:
            wind_dirs_extracted, wind_speeds_extracted, concs_extracted = aggregate_by_time(
                timestamps=timestamps,
                wind_directions=wind_dirs_extracted,
                wind_speeds=wind_speeds_extracted,
                concentrations=concs_extracted,
                resolution=time_resolution
            )

        # 赋值给后续变量
        wind_dirs = np.array(wind_dirs_extracted)
        wind_speeds = np.array(wind_speeds_extracted)
        concs = np.array(concs_extracted)

    else:
        # 使用直接传数据模式（向后兼容）
        logger.info("using_direct_data_mode")

        if wind_directions is None or wind_speeds is None or concentrations is None:
            raise ValueError("必须提供 data_id 或 (wind_directions, wind_speeds, concentrations)")

        if not (len(wind_directions) == len(wind_speeds) == len(concentrations)):
            raise ValueError("风向、风速、浓度数据长度必须一致")
        if len(wind_directions) == 0:
            raise ValueError("输入数据不能为空")

        # 转换为numpy数组
        wind_dirs = np.array(wind_directions)
        wind_speeds = np.array(wind_speeds)
        concs = np.array(concentrations)

    # ========== 阶段2：基础数据验证 ==========
    valid_mask = (
        np.isfinite(wind_dirs) &
        np.isfinite(wind_speeds) &
        np.isfinite(concs) &
        (wind_speeds > 0)  # 风速必须大于0
    )

    if not np.any(valid_mask):
        raise ValueError("没有有效数据（所有数据点都包含NaN或无效风速）")

    wind_dirs = wind_dirs[valid_mask]
    wind_speeds = wind_speeds[valid_mask]
    concs = concs[valid_mask]

    # 保存原始浓度数据用于对比
    original_concs = concs.copy()
    original_count = len(concs)

    logger.info(
        "polar_contour_data_prepared",
        total_points=len(wind_dirs),
        valid_points=len(wind_dirs),
        invalid_points=len(wind_dirs) - len(wind_dirs),
        concentration_range=(float(np.min(concs)), float(np.max(concs)))
    )

    # ========== 阶段2：智能异常值过滤 ==========
    # 步骤1：过滤负值（硬性规则，污染物浓度不能为负）
    negative_mask = concs < 0
    negative_count = np.sum(negative_mask)
    if negative_count > 0:
        logger.warning(
            "polar_contour_negative_values_detected",
            pollutant_name=pollutant_name,
            negative_count=negative_count,
            negative_values=original_concs[negative_mask][:10].tolist()  # 记录前10个负值
        )
        concs[negative_mask] = np.nan

    # 步骤2：使用IQR方法检测极大值（自适应规则）
    # 只对非负数据进行统计
    valid_concs = concs[np.isfinite(concs)]
    if len(valid_concs) > 10:  # 至少需要10个数据点才能做统计
        # 计算四分位数和IQR
        q1 = np.percentile(valid_concs, 25)
        q2 = np.percentile(valid_concs, 50)  # 中位数
        q3 = np.percentile(valid_concs, 75)
        iqr = q3 - q1

        # 计算异常值阈值（使用4倍IQR，比标准的1.5倍更宽松）
        # 这样可以保留更多高浓度值（可能是真实的重污染事件）
        upper_bound = q3 + 4 * iqr

        # 检测超过阈值的极大值
        outlier_mask = (concs > upper_bound) & np.isfinite(concs)
        outlier_count = np.sum(outlier_mask)

        if outlier_count > 0:
            outlier_values = concs[outlier_mask]
            logger.warning(
                "polar_contour_outliers_detected",
                pollutant_name=pollutant_name,
                outlier_count=outlier_count,
                statistics={
                    "q1": float(q1),
                    "median": float(q2),
                    "q3": float(q3),
                    "iqr": float(iqr),
                    "upper_bound": float(upper_bound)
                },
                outlier_info={
                    "min_outlier": float(np.min(outlier_values)),
                    "max_outlier": float(np.max(outlier_values)),
                    "outlier_values": outlier_values[:10].tolist()  # 记录前10个异常值
                },
                message=f"检测到 {outlier_count} 个异常值（>{upper_bound:.1f}），将被过滤"
            )
            concs[outlier_mask] = np.nan
    else:
        # 数据点太少，不做IQR过滤
        logger.info(
            "polar_contour_insufficient_data_for_iqr",
            valid_concs_count=len(valid_concs),
            message="数据点太少（<10），跳过IQR异常值检测"
        )

    # 步骤3：重新过滤（将设为NaN的数据点移除）
    final_valid_mask = np.isfinite(concs)
    final_count = np.sum(final_valid_mask)
    filtered_count = original_count - final_count

    if filtered_count > 0:
        logger.info(
            "polar_contour_data_filtered",
            pollutant_name=pollutant_name,
            original_count=original_count,
            final_count=final_count,
            filtered_count=filtered_count,
            filter_details={
                "negative_filtered": int(negative_count),
                "outlier_filtered": int(filtered_count - negative_count),
                "retention_rate": f"{final_count / original_count * 100:.1f}%"
            },
            concentration_range_before=(
                float(np.min(original_concs)),
                float(np.max(original_concs))
            ),
            concentration_range_after=(
                float(np.min(concs[final_valid_mask])),
                float(np.max(concs[final_valid_mask]))
            )
        )

    # 应用最终过滤
    wind_dirs = wind_dirs[final_valid_mask]
    wind_speeds = wind_speeds[final_valid_mask]
    concs = concs[final_valid_mask]

    # 再次检查过滤后是否还有数据
    if len(concs) == 0:
        raise ValueError(f"数据过滤后无有效数据点。原始数据范围：{np.min(original_concs):.2f} - {np.max(original_concs):.2f}，建议检查数据质量")

    # 转换风向为弧度（数学坐标系，0度在右边，逆时针）
    theta = np.radians(wind_dirs)

    # 自动确定浓度范围
    if value_range is None:
        vmin, vmax = np.percentile(concs, [5, 95])  # 使用5-95分位数避免极值影响
    else:
        vmin, vmax = value_range

    # 创建极坐标网格
    grid_resolution_radial = grid_resolution
    grid_resolution_angular = grid_resolution * 2  # 角度方向使用更多点

    theta_grid = np.linspace(0, 2 * np.pi, grid_resolution_angular)
    r_grid = np.linspace(0, np.max(wind_speeds) * 1.1, grid_resolution_radial)
    Theta, R = np.meshgrid(theta_grid, r_grid)

    # 插值计算网格点的浓度值
    points = np.column_stack([theta, wind_speeds])
    values = concs

    try:
        Conc = griddata(points, values, (Theta, R), method=interpolation_method)

        # 记录插值后的数据范围（裁剪前）
        logger.info(
            "polar_contour_interpolation_raw",
            interpolation_method=interpolation_method,
            grid_shape=Conc.shape,
            raw_range=(float(np.nanmin(Conc)), float(np.nanmax(Conc))),
            intended_range=(vmin, vmax)
        )

        # 裁剪插值结果到[vmin, vmax]范围，避免插值过冲
        # cubic插值可能产生超出原始数据范围的极端值
        np.clip(Conc, vmin, vmax, out=Conc)

        # 记录裁剪后的数据范围
        logger.info(
            "polar_contour_interpolation_clipped",
            clipped_range=(float(np.nanmin(Conc)), float(np.nanmax(Conc))),
            within_bounds=True
        )

    except Exception as e:
        logger.warning("cubic_interpolation_failed", error=str(e), fallback="linear")
        # 如果三次插值失败，回退到线性插值
        Conc = griddata(points, values, (Theta, R), method='linear')
        # 同样需要裁剪
        np.clip(Conc, vmin, vmax, out=Conc)

    # 创建极坐标图（根据模式选择DPI）
    figure_dpi = FIXED_SIX_LEVEL_PARAMS["dpi"] if (use_six_level and SIX_LEVEL_SUPPORT) else dpi
    fig = plt.figure(figsize=(10, 8), dpi=figure_dpi)
    ax = fig.add_subplot(111, projection='polar')

    # ========== 选择色阶模式 ==========
    if use_six_level and SIX_LEVEL_SUPPORT:
        # 6色阶模式：基于新标准日平均浓度限值
        # 内部固定所有参数，降低LLM输入负担
        thresholds = get_pollutant_thresholds(pollutant_name)

        # 强制使用阈值的完整范围作为vmin/vmax，忽略用户传入的value_range
        vmin = thresholds[0]
        vmax = thresholds[-1]

        # 如果用户传入的参数与固定值不同，记录警告
        if (grid_resolution != FIXED_SIX_LEVEL_PARAMS["grid_resolution"] or
            interpolation_method != FIXED_SIX_LEVEL_PARAMS["interpolation_method"] or
            dpi != FIXED_SIX_LEVEL_PARAMS["dpi"]):
            logger.info(
                "polar_contour_six_level_override_parameters",
                mode="six_level",
                original_grid_resolution=grid_resolution,
                fixed_grid_resolution=FIXED_SIX_LEVEL_PARAMS["grid_resolution"],
                original_interpolation_method=interpolation_method,
                fixed_interpolation_method=FIXED_SIX_LEVEL_PARAMS["interpolation_method"],
                original_dpi=dpi,
                fixed_dpi=FIXED_SIX_LEVEL_PARAMS["dpi"],
                message="6色阶模式下使用内部固定参数，用户传入的参数被忽略"
            )

        logger.info(
            "polar_contour_using_six_level_mode",
            pollutant=pollutant_name,
            thresholds=thresholds,
            forced_value_range=(vmin, vmax),
            fixed_parameters=FIXED_SIX_LEVEL_PARAMS
        )

        # 创建自定义colormap和norm
        cmap, norm = create_custom_colormap(pollutant_name, vmin, vmax)

        # 使用自定义colormap和norm，关键：使用levels参数指定阈值边界
        # 这确保了即使数据没有覆盖所有范围，图例也会显示完整的6个色阶
        contour = ax.contourf(
            Theta, R, Conc,
            levels=thresholds,  # 明确使用阈值作为等值线边界
            cmap=cmap,
            norm=norm,
            alpha=0.9,
            extend='both'  # 扩展颜色条两端，确保显示完整范围
        )

        # 添加色阶等级标签到颜色条
        cbar = plt.colorbar(contour, ax=ax, pad=0.1)

        # 设置颜色条刻度：显示完整的浓度限值数值
        # 使用FixedLocator确保刻度位置固定在阈值处
        from matplotlib.ticker import FixedLocator
        cbar.locator = FixedLocator(thresholds)
        cbar.update_ticks()
        cbar.set_ticklabels([str(t) for t in thresholds], fontsize=9)

        logger.info(
            "polar_contour_six_level_colorbar_created",
            pollutant=pollutant_name,
            thresholds=thresholds,
            colorbar_range="full",
            extend_mode="both"
        )

    else:
        # 默认模式：使用连续渐变色阶
        logger.info(
            "polar_contour_using_default_mode",
            color_map=color_map,
            levels=contour_levels,
            vmin=vmin,
            vmax=vmax
        )

        # 绘制填充等值线图
        contour = ax.contourf(
            Theta, R, Conc,
            levels=contour_levels,
            cmap=color_map,
            vmin=vmin,
            vmax=vmax,
            alpha=0.9
        )

        # 添加颜色条
        cbar = plt.colorbar(contour, ax=ax, pad=0.1)

    # 设置颜色条标签
    cbar.set_label(f'{pollutant_name}浓度 ({unit})', fontsize=12)

    # 设置极坐标轴
    ax.set_theta_zero_location('N')  # 0度在北方
    ax.set_theta_direction(-1)  # 顺时针方向

    # 设置径向轴标签（风速）
    max_speed = np.max(wind_speeds)
    tick_speeds = np.linspace(0, max_speed, 5)
    ax.set_yticks(tick_speeds)
    ax.set_yticklabels([f'{s:.1f}' for s in tick_speeds], fontsize=10)
    ax.set_ylabel('风速 (m/s)', fontsize=12, labelpad=20)

    # 设置角度轴标签（方位）
    ax.set_xticks(np.radians([0, 90, 180, 270]))
    ax.set_xticklabels(['N', 'E', 'S', 'W'], fontsize=12)

    # 设置标题
    ax.set_title(title, fontsize=14, pad=20)

    # 调整布局
    plt.tight_layout()

    # 保存为base64（6色阶模式下使用固定DPI）
    save_dpi = FIXED_SIX_LEVEL_PARAMS["dpi"] if (use_six_level and SIX_LEVEL_SUPPORT) else dpi
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=save_dpi, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)

    logger.info(
        "polar_contour_generated",
        title=title,
        size_kb=len(img_base64) / 1024,
        method="matplotlib_contourf"
    )

    return img_base64


def generate_pollution_rose_echarts(
    wind_directions: List[float],
    wind_speeds: List[float],
    concentrations: List[float],
    title: str = "极坐标热力型污染玫瑰图（交互式）",
    pollutant_name: str = "PM10",
    unit: str = "μg/m³",
    grid_angles: int = 360,
    grid_radii: int = 50,
    color_range: Tuple[float, float] = (31, 49),
    blur: int = 10
) -> dict:
    """
    生成交互式极坐标热力型污染玫瑰图（ECharts方案）

    使用极坐标热力图实现交互式可视化

    Args:
        wind_directions: 风向列表（度数，0-360）
        wind_speeds: 风速列表（m/s）
        concentrations: 污染物浓度列表
        title: 图表标题
        pollutant_name: 污染物名称
        unit: 浓度单位
        grid_angles: 角度网格数（默认360，即每度一个点）
        grid_radii: 径向网格数（默认50）
        color_range: 浓度颜色范围（min, max）
        blur: 模糊程度（越大越平滑）

    Returns:
        ECharts配置对象（JSON，包含series字段）

    Raises:
        ValueError: 输入数据长度不一致或为空
    """
    # 参数验证
    if not (len(wind_directions) == len(wind_speeds) == len(concentrations)):
        raise ValueError("风向、风速、浓度数据长度必须一致")
    if len(wind_directions) == 0:
        raise ValueError("输入数据不能为空")

    # 转换为numpy数组
    wind_dirs = np.array(wind_directions)
    wind_speeds = np.array(wind_speeds)
    concs = np.array(concentrations)

    # 过滤无效数据
    valid_mask = (
        np.isfinite(wind_dirs) &
        np.isfinite(wind_speeds) &
        np.isfinite(concs) &
        (wind_speeds > 0)
    )

    if not np.any(valid_mask):
        raise ValueError("没有有效数据（所有数据点都包含NaN或无效风速）")

    wind_dirs = wind_dirs[valid_mask]
    wind_speeds = wind_speeds[valid_mask]
    concs = concs[valid_mask]

    # 自动确定浓度范围
    if color_range is None:
        vmin, vmax = np.percentile(concs, [5, 95])
    else:
        vmin, vmax = color_range

    max_speed = float(np.max(wind_speeds))

    # 构建热力图数据（直接使用原始数据点）
    data = []
    for wd, ws, c in zip(wind_dirs, wind_speeds, concs):
        # 归一化浓度到0-100范围（用于visualMap）
        if vmax > vmin:
            normalized_value = float((c - vmin) / (vmax - vmin) * 100)
        else:
            normalized_value = 50.0

        data.append([float(wd), float(ws), normalized_value, float(c)])

    logger.info(
        "polar_echarts_data_prepared",
        total_points=len(wind_directions),
        valid_points=len(wind_dirs),
        concentration_range=(vmin, vmax),
        max_speed=max_speed
    )

    # 构建ECharts配置
    echarts_option = {
        "title": {
            "text": title,
            "left": "center",
            "textStyle": {
                "fontSize": 16
            }
        },
        "tooltip": {
            "trigger": "item",
            "formatter": function_formatter(
                pollutant_name, unit
            ),
            "textStyle": {
                "fontSize": 12
            }
        },
        "visualMap": {
            "min": 0,
            "max": 100,
            "text": ["高", "低"],
            "calculable": True,
            "inRange": {
                "color": [
                    "#313695", "#4575b4", "#74add1", "#abd9e9",
                    "#e0f3f8", "#ffffbf", "#fee090", "#fdae61",
                    "#f46d43", "#d73027", "#a50026"
                ]
            },
            "textStyle": {
                "color": "#333"
            },
            "left": "right",
            "top": "center"
        },
        "polar": {
            "radius": [0, max_speed * 1.1]
        },
        "angleAxis": {
            "type": "value",
            "startAngle": 90,  # 北方在顶部
            "min": 0,
            "max": 360,
            "axisLine": {
                "lineStyle": {
                    "color": "#999"
                }
            },
            "axisLabel": {
                "formatter": "{value}°",
                "color": "#666"
            },
            "splitLine": {
                "lineStyle": {
                    "color": "#ddd",
                    "type": "dashed"
                }
            }
        },
        "radiusAxis": {
            "type": "value",
            "name": f"风速 (m/s)",
            "nameLocation": "middle",
            "nameTextStyle": {
                "padding": [0, 0, 20, 0]
            },
            "axisLine": {
                "lineStyle": {
                    "color": "#999"
                }
            },
            "axisLabel": {
                "formatter": "{value}",
                "color": "#666"
            },
            "splitLine": {
                "lineStyle": {
                    "color": "#ddd",
                    "type": "dashed"
                }
            }
        },
        "series": [
            {
                "type": "heatmap",
                "coordinateSystem": "polar",
                "data": data,
                "blur": blur,
                "itemStyle": {
                    "emphasis": {
                        "shadowBlur": 10,
                        "shadowColor": "rgba(0, 0, 0, 0.5)"
                    }
                },
                "progressive": 1000,
                "animation": False
            }
        ]
    }

    logger.info(
        "polar_echarts_generated",
        title=title,
        data_points=len(data),
        method="echarts_polar_heatmap"
    )

    return echarts_option


def function_formatter(pollutant_name: str, unit: str) -> str:
    """
    生成ECharts tooltip格式化函数

    Args:
        pollutant_name: 污染物名称
        unit: 浓度单位

    Returns:
        JavaScript函数字符串
    """
    return f"""function(params) {{
    const wd = params.value[0].toFixed(0);
    const ws = params.value[1].toFixed(1);
    const conc = params.value[3].toFixed(1);
    const dir = getDirection(wd);
    return '风向: ' + dir + ' (' + wd + '°)<br/>' +
           '风速: ' + ws + ' m/s<br/>' +
           '{pollutant_name}浓度: ' + conc + ' {unit}';
}}

function getDirection(wd) {{
    const directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                        'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
    const index = Math.round(wd / 22.5) % 16;
    return directions[index];
}}"""


# 便捷函数：从data_id加载数据并生成图表
def generate_from_data_id(
    data_id: str,
    data_dir: str = "/home/xckj/suyuan/backend_data_registry/data_registry",
    method: str = "matplotlib",
    **kwargs
) -> Any:
    """
    从data_id加载数据并生成图表

    Args:
        data_id: 数据ID
        data_dir: 数据目录路径
        method: 生成方法（matplotlib/echarts）
        **kwargs: 传递给生成函数的其他参数

    Returns:
        matplotlib方法：base64编码的PNG图片
        echarts方法：ECharts配置对象

    Raises:
        FileNotFoundError: 数据文件不存在
        KeyError: 数据文件缺少必要字段
    """
    import json
    import os

    # 构建数据文件路径
    data_file = os.path.join(data_dir, f"{data_id}.json")

    if not os.path.exists(data_file):
        raise FileNotFoundError(f"数据文件不存在：{data_file}")

    # 加载数据
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 提取字段（支持多种字段名）
    def extract_field(record, possible_names):
        for name in possible_names:
            if name in record:
                return record[name]
        raise KeyError(f"字段不存在：{possible_names}")

    # 提取风向、风速、浓度
    wind_dirs = []
    wind_speeds = []
    concentrations = []

    for record in data:
        try:
            wd = extract_field(record, ['WD', 'wind_direction', 'direction', '风向'])
            ws = extract_field(record, ['WS', 'wind_speed', 'speed', '风速'])

            # 浓度字段：从kwargs获取pollutant_name，默认为PM10
            pollutant_name = kwargs.get('pollutant_name', 'PM10')
            possible_conc_names = [
                pollutant_name,
                pollutant_name.replace('.', ''),
                'concentration',
                'conc',
                '浓度'
            ]
            conc = extract_field(record, possible_conc_names)

            wind_dirs.append(float(wd))
            wind_speeds.append(float(ws))
            concentrations.append(float(conc))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("skip_invalid_record", record=record, error=str(e))
            continue

    if len(wind_dirs) == 0:
        raise ValueError("没有有效数据记录")

    # 根据方法生成图表
    if method == "matplotlib":
        return generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            **kwargs
        )
    elif method == "echarts":
        return generate_pollution_rose_echarts(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            **kwargs
        )
    else:
        raise ValueError(f"不支持的生成方法：{method}（支持：matplotlib/echarts）")
