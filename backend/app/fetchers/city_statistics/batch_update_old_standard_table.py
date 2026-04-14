"""
批量回填city_168_statistics_old_standard表

从city_168_statistics_new_standard表读取数据，使用旧标准限值规则重新计算并保存到city_168_statistics_old_standard表。

关键区别：
1. 污染物浓度修约规则：使用final_output规则（CO保留1位，其他取整）
2. 计算综合指数时使用修约后的浓度值

执行日期: 2026-04-09
"""

import pyodbc
from decimal import Decimal
from datetime import datetime

# 数据库连接配置
DB_CONFIG = {
    'host': '180.184.30.94',
    'port': 1433,
    'database': 'XcAiDb',
    'user': 'sa',
    'password': "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"
}

# HJ 663-2013 旧标准限值
ANNUAL_STANDARD_LIMITS_2013 = {
    'SO2': 60,
    'NO2': 40,
    'PM10': 70,
    'PM2_5': 35,
    'CO': 4,
    'O3_8h': 160
}

# 新标准综合指数权重
WEIGHTS_NEW_ALGO = {
    'SO2': 1,
    'NO2': 2,
    'PM10': 1,
    'PM2_5': 3,
    'CO': 1,
    'O3_8h': 2
}

# 旧标准综合指数权重
WEIGHTS_OLD_ALGO = {
    'SO2': 1,
    'NO2': 1,
    'PM10': 1,
    'PM2_5': 1,
    'CO': 1,
    'O3_8h': 1
}


def build_connection_string():
    """构建ODBC连接字符串"""
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_CONFIG['host']},{DB_CONFIG['port']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['user']};"
        f"PWD={{{DB_CONFIG['password']}}};"
        f"TrustServerCertificate=yes;"
    )


def safe_round(value, precision):
    """修约函数（四舍六入五成双）"""
    if value is None:
        return None
    try:
        value_str = format(value, f'.{precision + 5}f').rstrip('0').rstrip('.')
        decimal_value = Decimal(value_str)
        quantize_unit = Decimal('0.' + '0' * precision) if precision > 0 else Decimal('1')
        rounded = decimal_value.quantize(quantize_unit, rounding='ROUND_HALF_EVEN')
        return float(rounded)
    except (ValueError, TypeError):
        return None


def apply_final_output_rounding(value, pollutant):
    """应用最终输出修约规则（CO保留1位，其他取整）"""
    if value is None:
        return None

    final_output_precision = {
        'PM2_5': 0,      # 取整
        'CO': 1,         # 保留1位小数
        'SO2': 0,        # 取整
        'NO2': 0,        # 取整
        'PM10': 0,       # 取整
        'O3_8h': 0,      # 取整
    }

    precision = final_output_precision.get(pollutant, 0)
    return safe_round(value, precision)


def process_and_save_data():
    """处理并保存数据"""
    conn_str = build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    print("正在查询city_168_statistics_new_standard表数据...")
    cursor.execute("""
        SELECT stat_date, stat_type, city_name,
               so2_concentration, no2_concentration, pm10_concentration,
               pm2_5_concentration, co_concentration, o3_8h_concentration,
               data_days, sample_coverage, region, province
        FROM city_168_statistics_new_standard
        ORDER BY stat_date, stat_type, city_name
    """)

    rows = cursor.fetchall()
    print(f"找到 {len(rows)} 条记录")

    if not rows:
        print("没有数据需要处理")
        conn.close()
        return

    # 处理每条记录
    processed_count = 0
    for row in rows:
        stat_date = row.stat_date
        stat_type = row.stat_type
        city_name = row.city_name

        # 获取原始浓度值
        so2_conc = row.so2_concentration
        no2_conc = row.no2_concentration
        pm10_conc = row.pm10_concentration
        pm25_conc = row.pm2_5_concentration
        co_conc = row.co_concentration
        o3_8h_conc = row.o3_8h_concentration

        # 应用final_output修约规则
        so2_conc_rounded = apply_final_output_rounding(so2_conc, 'SO2')
        no2_conc_rounded = apply_final_output_rounding(no2_conc, 'NO2')
        pm10_conc_rounded = apply_final_output_rounding(pm10_conc, 'PM10')
        pm25_conc_rounded = apply_final_output_rounding(pm25_conc, 'PM2_5')
        co_conc_rounded = apply_final_output_rounding(co_conc, 'CO')
        o3_8h_conc_rounded = apply_final_output_rounding(o3_8h_conc, 'O3_8h')

        # 计算单项指数（使用旧限值）= 修约后浓度 / 旧限值
        so2_index = safe_round(so2_conc_rounded / ANNUAL_STANDARD_LIMITS_2013['SO2'], 3) if so2_conc_rounded is not None else None
        no2_index = safe_round(no2_conc_rounded / ANNUAL_STANDARD_LIMITS_2013['NO2'], 3) if no2_conc_rounded is not None else None
        pm10_index = safe_round(pm10_conc_rounded / ANNUAL_STANDARD_LIMITS_2013['PM10'], 3) if pm10_conc_rounded is not None else None
        pm25_index = safe_round(pm25_conc_rounded / ANNUAL_STANDARD_LIMITS_2013['PM2_5'], 3) if pm25_conc_rounded is not None else None
        co_index = safe_round(co_conc_rounded / ANNUAL_STANDARD_LIMITS_2013['CO'], 3) if co_conc_rounded is not None else None
        o3_8h_index = safe_round(o3_8h_conc_rounded / ANNUAL_STANDARD_LIMITS_2013['O3_8h'], 3) if o3_8h_conc_rounded is not None else None

        # 计算综合指数（旧限值+新算法）
        comprehensive_index_new_algo = 0.0
        valid_indices = 0

        if so2_index is not None:
            comprehensive_index_new_algo += so2_index * WEIGHTS_NEW_ALGO['SO2']
            valid_indices += 1
        if no2_index is not None:
            comprehensive_index_new_algo += no2_index * WEIGHTS_NEW_ALGO['NO2']
            valid_indices += 1
        if pm10_index is not None:
            comprehensive_index_new_algo += pm10_index * WEIGHTS_NEW_ALGO['PM10']
            valid_indices += 1
        if pm25_index is not None:
            comprehensive_index_new_algo += pm25_index * WEIGHTS_NEW_ALGO['PM2_5']
            valid_indices += 1
        if co_index is not None:
            comprehensive_index_new_algo += co_index * WEIGHTS_NEW_ALGO['CO']
            valid_indices += 1
        if o3_8h_index is not None:
            comprehensive_index_new_algo += o3_8h_index * WEIGHTS_NEW_ALGO['O3_8h']
            valid_indices += 1

        comprehensive_index_new_algo = safe_round(comprehensive_index_new_algo, 3) if valid_indices > 0 else None

        # 计算综合指数（旧限值+旧算法）
        comprehensive_index_old_algo = 0.0
        valid_indices = 0

        if so2_index is not None:
            comprehensive_index_old_algo += so2_index * WEIGHTS_OLD_ALGO['SO2']
            valid_indices += 1
        if no2_index is not None:
            comprehensive_index_old_algo += no2_index * WEIGHTS_OLD_ALGO['NO2']
            valid_indices += 1
        if pm10_index is not None:
            comprehensive_index_old_algo += pm10_index * WEIGHTS_OLD_ALGO['PM10']
            valid_indices += 1
        if pm25_index is not None:
            comprehensive_index_old_algo += pm25_index * WEIGHTS_OLD_ALGO['PM2_5']
            valid_indices += 1
        if co_index is not None:
            comprehensive_index_old_algo += co_index * WEIGHTS_OLD_ALGO['CO']
            valid_indices += 1
        if o3_8h_index is not None:
            comprehensive_index_old_algo += o3_8h_index * WEIGHTS_OLD_ALGO['O3_8h']
            valid_indices += 1

        comprehensive_index_old_algo = safe_round(comprehensive_index_old_algo, 3) if valid_indices > 0 else None

        # 删除旧数据并插入新数据
        cursor.execute("""
            DELETE FROM city_168_statistics_old_standard
            WHERE city_name = ? AND stat_date = ? AND stat_type = ?
        """, [city_name, stat_date, stat_type])

        cursor.execute("""
            INSERT INTO city_168_statistics_old_standard (
                stat_date, stat_type, city_name, city_code,
                so2_concentration, no2_concentration, pm10_concentration,
                pm2_5_concentration, co_concentration, o3_8h_concentration,
                so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                comprehensive_index_new_algo, comprehensive_index_old_algo,
                data_days, sample_coverage, region, province
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            stat_date, stat_type, city_name, None,
            so2_conc_rounded, no2_conc_rounded, pm10_conc_rounded,
            pm25_conc_rounded, co_conc_rounded, o3_8h_conc_rounded,
            so2_index, no2_index, pm10_index, pm25_index, co_index, o3_8h_index,
            comprehensive_index_new_algo, comprehensive_index_old_algo,
            row.data_days, row.sample_coverage, row.region, row.province
        ])

        processed_count += 1
        if processed_count % 100 == 0:
            print(f"已处理 {processed_count} 条记录...")

    conn.commit()
    cursor.close()
    conn.close()

    print(f"数据回填完成，共处理 {processed_count} 条记录")


def update_rankings():
    """更新排名"""
    conn_str = build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    print("正在获取所有唯一的stat_date和stat_type组合...")
    cursor.execute("""
        SELECT DISTINCT stat_date, stat_type
        FROM city_168_statistics_old_standard
        ORDER BY stat_date, stat_type
    """)

    date_type_combinations = cursor.fetchall()
    print(f"找到 {len(date_type_combinations)} 个日期-类型组合")

    for combination in date_type_combinations:
        stat_date = combination.stat_date
        stat_type = combination.stat_type

        print(f"正在更新排名: {stat_date} - {stat_type}")

        # 更新旧限值+新算法排名
        cursor.execute("""
            SELECT city_name, comprehensive_index_new_algo
            FROM city_168_statistics_old_standard
            WHERE stat_date = ? AND stat_type = ?
              AND comprehensive_index_new_algo IS NOT NULL
            ORDER BY comprehensive_index_new_algo
        """, [stat_date, stat_type])

        rows = cursor.fetchall()
        for rank, row in enumerate(rows, start=1):
            cursor.execute("""
                UPDATE city_168_statistics_old_standard
                SET comprehensive_index_rank_new_algo = ?
                WHERE city_name = ? AND stat_date = ? AND stat_type = ?
            """, [rank, row.city_name, stat_date, stat_type])

        # 更新旧限值+旧算法排名
        cursor.execute("""
            SELECT city_name, comprehensive_index_old_algo
            FROM city_168_statistics_old_standard
            WHERE stat_date = ? AND stat_type = ?
              AND comprehensive_index_old_algo IS NOT NULL
            ORDER BY comprehensive_index_old_algo
        """, [stat_date, stat_type])

        rows = cursor.fetchall()
        for rank, row in enumerate(rows, start=1):
            cursor.execute("""
                UPDATE city_168_statistics_old_standard
                SET comprehensive_index_rank_old_algo = ?
                WHERE city_name = ? AND stat_date = ? AND stat_type = ?
            """, [rank, row.city_name, stat_date, stat_type])

    conn.commit()
    cursor.close()
    conn.close()

    print("排名更新完成")


if __name__ == '__main__':
    print("="*70)
    print("批量回填city_168_statistics_old_standard表")
    print("="*70)
    print()

    try:
        # 1. 处理并保存数据
        print("步骤1: 处理并保存数据")
        process_and_save_data()
        print()

        # 2. 更新排名
        print("步骤2: 更新排名")
        update_rankings()
        print()

        print("="*70)
        print("所有数据更新完成！")
        print("="*70)

    except Exception as e:
        print(f"更新失败: {str(e)}")
        import traceback
        traceback.print_exc()
