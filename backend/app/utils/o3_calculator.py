"""
O3日最大8小时平均计算模块

从小时O3数据计算日最大8小时滑动平均值
"""

from typing import Optional
import pandas as pd


def calculate_o3_8h_max(
    hourly_data: pd.DataFrame,
    o3_column: str = 'o3',
    time_column: str = 'time_point'
) -> pd.Series:
    """
    计算O3日最大8小时平均浓度

    从小时O3数据使用8小时滑动窗口计算每日最大8小时平均值
    最少需要6个有效小时数据（min_periods=6）

    Args:
        hourly_data: 包含小时O3数据的DataFrame
        o3_column: O3列名
        time_column: 时间列名

    Returns:
        每日O3最大8小时平均浓度Series，索引为日期

    Examples:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     'time_point': pd.date_range('2024-01-01', periods=24, freq='H'),
        ...     'o3': range(24)
        ... })
        >>> result = calculate_o3_8h_max(df)
        >>> print(result)
        2024-01-01    11.5
    """
    df = hourly_data.copy()

    # 确保时间列是datetime类型
    df[time_column] = pd.to_datetime(df[time_column])
    df['date'] = df[time_column].dt.date

    # 按日期分组，计算每日的8小时滑动平均最大值
    daily_results = []
    for date, group in df.groupby('date'):
        group = group.sort_values(time_column)
        # 8小时滑动窗口，最少需要6个有效值
        rolling_8h = group[o3_column].rolling(window=8, min_periods=6).mean()
        daily_max = rolling_8h.max()
        daily_results.append({'date': date, 'o3_8h_max': daily_max})

    if not daily_results:
        return pd.Series(dtype=float)

    result_df = pd.DataFrame(daily_results)
    return result_df.set_index('date')['o3_8h_max']


def calculate_o3_8h_max_for_group(
    group: pd.DataFrame,
    o3_column: str = 'o3',
    time_column: str = 'time_point'
) -> float:
    """
    计算单个分组的O3日最大8小时平均浓度

    用于groupby.apply()场景

    Args:
        group: 单个分组的数据
        o3_column: O3列名
        time_column: 时间列名

    Returns:
        该分组的O3日最大8小时平均浓度
    """
    result = calculate_o3_8h_max(group, o3_column, time_column)
    if result.empty:
        return None
    return result.iloc[0]
