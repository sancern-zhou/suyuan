"""
更新4套标准组合的综合指数

为city_168_statistics和province_statistics表中的现有数据
计算新增的两套综合指数组合：
1. 新限值+旧算法
2. 旧限值+新算法

执行日期: 2026-04-09
"""

import pyodbc
from decimal import Decimal

# 数据库连接配置
DB_CONFIG = {
    'host': '180.184.30.94',
    'port': 1433,
    'database': 'XcAiDb',
    'user': 'sa',
    'password': "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"
}

# 新旧标准权重（使用float类型）
WEIGHTS_NEW_ALGO = {
    'SO2': 1.0,
    'NO2': 2.0,
    'PM10': 1.0,
    'PM2_5': 3.0,
    'CO': 1.0,
    'O3_8h': 2.0
}

WEIGHTS_OLD_ALGO = {
    'SO2': 1.0,
    'NO2': 1.0,
    'PM10': 1.0,
    'PM2_5': 1.0,
    'CO': 1.0,
    'O3_8h': 1.0
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
    """修约函数"""
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


def update_city_statistics():
    """更新城市统计数据"""
    conn_str = build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    print("正在查询城市统计数据...")
    cursor.execute("""
        SELECT id, city_name, stat_date, stat_type,
               so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
               pm10_index_old, pm2_5_index_old
        FROM city_168_statistics
        WHERE comprehensive_index IS NOT NULL
    """)

    rows = cursor.fetchall()
    print(f"找到 {len(rows)} 条城市统计记录")

    updated_count = 0
    for row in rows:
        record_id = row.id
        so2_index = row.so2_index
        no2_index = row.no2_index
        pm10_index = row.pm10_index
        pm2_5_index = row.pm2_5_index
        co_index = row.co_index
        o3_8h_index = row.o3_8h_index
        pm10_index_old = row.pm10_index_old
        pm2_5_index_old = row.pm2_5_index_old

        # 计算新限值+旧算法综合指数
        comprehensive_index_new_limit_old_algo = 0.0
        if so2_index is not None:
            comprehensive_index_new_limit_old_algo += float(so2_index) * WEIGHTS_OLD_ALGO['SO2']
        if no2_index is not None:
            comprehensive_index_new_limit_old_algo += float(no2_index) * WEIGHTS_OLD_ALGO['NO2']
        if pm10_index is not None:
            comprehensive_index_new_limit_old_algo += float(pm10_index) * WEIGHTS_OLD_ALGO['PM10']
        if pm2_5_index is not None:
            comprehensive_index_new_limit_old_algo += float(pm2_5_index) * WEIGHTS_OLD_ALGO['PM2_5']
        if co_index is not None:
            comprehensive_index_new_limit_old_algo += float(co_index) * WEIGHTS_OLD_ALGO['CO']
        if o3_8h_index is not None:
            comprehensive_index_new_limit_old_algo += float(o3_8h_index) * WEIGHTS_OLD_ALGO['O3_8h']

        comprehensive_index_new_limit_old_algo = safe_round(comprehensive_index_new_limit_old_algo, 3)

        # 计算旧限值+新算法综合指数
        comprehensive_index_old_limit_new_algo = 0.0
        if so2_index is not None:
            comprehensive_index_old_limit_new_algo += float(so2_index) * WEIGHTS_NEW_ALGO['SO2']
        if no2_index is not None:
            comprehensive_index_old_limit_new_algo += float(no2_index) * WEIGHTS_NEW_ALGO['NO2']
        if pm10_index_old is not None:
            comprehensive_index_old_limit_new_algo += float(pm10_index_old) * WEIGHTS_NEW_ALGO['PM10']
        else:
            if pm10_index is not None:
                # 如果没有旧指数，使用新指数计算
                comprehensive_index_old_limit_new_algo += float(pm10_index) * WEIGHTS_NEW_ALGO['PM10']
        if pm2_5_index_old is not None:
            comprehensive_index_old_limit_new_algo += float(pm2_5_index_old) * WEIGHTS_NEW_ALGO['PM2_5']
        else:
            if pm2_5_index is not None:
                comprehensive_index_old_limit_new_algo += float(pm2_5_index) * WEIGHTS_NEW_ALGO['PM2_5']
        if co_index is not None:
            comprehensive_index_old_limit_new_algo += float(co_index) * WEIGHTS_NEW_ALGO['CO']
        if o3_8h_index is not None:
            comprehensive_index_old_limit_new_algo += float(o3_8h_index) * WEIGHTS_NEW_ALGO['O3_8h']

        comprehensive_index_old_limit_new_algo = safe_round(comprehensive_index_old_limit_new_algo, 3)

        # 更新数据库
        cursor.execute("""
            UPDATE city_168_statistics
            SET comprehensive_index_new_limit_old_algo = ?,
                comprehensive_index_old_limit_new_algo = ?
            WHERE id = ?
        """, [comprehensive_index_new_limit_old_algo, comprehensive_index_old_limit_new_algo, record_id])

        updated_count += 1
        if updated_count % 100 == 0:
            print(f"已更新 {updated_count} 条记录...")

    conn.commit()
    cursor.close()
    conn.close()

    print(f"城市统计数据更新完成，共更新 {updated_count} 条记录")


def update_province_statistics():
    """更新省份统计数据"""
    conn_str = build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    print("正在查询省份统计数据...")
    cursor.execute("""
        SELECT id, province_name, stat_date, stat_type,
               so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
               pm10_index_old, pm2_5_index_old
        FROM province_statistics
        WHERE comprehensive_index IS NOT NULL
    """)

    rows = cursor.fetchall()
    print(f"找到 {len(rows)} 条省份统计记录")

    updated_count = 0
    for row in rows:
        record_id = row.id
        so2_index = row.so2_index
        no2_index = row.no2_index
        pm10_index = row.pm10_index
        pm2_5_index = row.pm2_5_index
        co_index = row.co_index
        o3_8h_index = row.o3_8h_index
        pm10_index_old = row.pm10_index_old
        pm2_5_index_old = row.pm2_5_index_old

        # 计算新限值+旧算法综合指数
        comprehensive_index_new_limit_old_algo = 0.0
        if so2_index is not None:
            comprehensive_index_new_limit_old_algo += float(so2_index) * WEIGHTS_OLD_ALGO['SO2']
        if no2_index is not None:
            comprehensive_index_new_limit_old_algo += float(no2_index) * WEIGHTS_OLD_ALGO['NO2']
        if pm10_index is not None:
            comprehensive_index_new_limit_old_algo += float(pm10_index) * WEIGHTS_OLD_ALGO['PM10']
        if pm2_5_index is not None:
            comprehensive_index_new_limit_old_algo += float(pm2_5_index) * WEIGHTS_OLD_ALGO['PM2_5']
        if co_index is not None:
            comprehensive_index_new_limit_old_algo += float(co_index) * WEIGHTS_OLD_ALGO['CO']
        if o3_8h_index is not None:
            comprehensive_index_new_limit_old_algo += float(o3_8h_index) * WEIGHTS_OLD_ALGO['O3_8h']

        comprehensive_index_new_limit_old_algo = safe_round(comprehensive_index_new_limit_old_algo, 3)

        # 计算旧限值+新算法综合指数
        comprehensive_index_old_limit_new_algo = 0.0
        if so2_index is not None:
            comprehensive_index_old_limit_new_algo += float(so2_index) * WEIGHTS_NEW_ALGO['SO2']
        if no2_index is not None:
            comprehensive_index_old_limit_new_algo += float(no2_index) * WEIGHTS_NEW_ALGO['NO2']
        if pm10_index_old is not None:
            comprehensive_index_old_limit_new_algo += float(pm10_index_old) * WEIGHTS_NEW_ALGO['PM10']
        else:
            if pm10_index is not None:
                comprehensive_index_old_limit_new_algo += float(pm10_index) * WEIGHTS_NEW_ALGO['PM10']
        if pm2_5_index_old is not None:
            comprehensive_index_old_limit_new_algo += float(pm2_5_index_old) * WEIGHTS_NEW_ALGO['PM2_5']
        else:
            if pm2_5_index is not None:
                comprehensive_index_old_limit_new_algo += float(pm2_5_index) * WEIGHTS_NEW_ALGO['PM2_5']
        if co_index is not None:
            comprehensive_index_old_limit_new_algo += float(co_index) * WEIGHTS_NEW_ALGO['CO']
        if o3_8h_index is not None:
            comprehensive_index_old_limit_new_algo += float(o3_8h_index) * WEIGHTS_NEW_ALGO['O3_8h']

        comprehensive_index_old_limit_new_algo = safe_round(comprehensive_index_old_limit_new_algo, 3)

        # 更新数据库
        cursor.execute("""
            UPDATE province_statistics
            SET comprehensive_index_new_limit_old_algo = ?,
                comprehensive_index_old_limit_new_algo = ?
            WHERE id = ?
        """, [comprehensive_index_new_limit_old_algo, comprehensive_index_old_limit_new_algo, record_id])

        updated_count += 1
        if updated_count % 10 == 0:
            print(f"已更新 {updated_count} 条记录...")

    conn.commit()
    cursor.close()
    conn.close()

    print(f"省份统计数据更新完成，共更新 {updated_count} 条记录")


def update_city_rankings():
    """更新城市排名"""
    conn_str = build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    print("正在更新城市排名（新限值+旧算法）...")
    cursor.execute("""
        SELECT stat_type, stat_date, city_name, comprehensive_index_new_limit_old_algo
        FROM city_168_statistics
        WHERE comprehensive_index_new_limit_old_algo IS NOT NULL
        ORDER BY stat_type, stat_date, comprehensive_index_new_limit_old_algo
    """)

    rows = cursor.fetchall()
    current_stat_type = None
    current_stat_date = None
    rank = 1

    for row in rows:
        if row.stat_type != current_stat_type or row.stat_date != current_stat_date:
            current_stat_type = row.stat_type
            current_stat_date = row.stat_date
            rank = 1

        cursor.execute("""
            UPDATE city_168_statistics
            SET comprehensive_index_rank_new_limit_old_algo = ?
            WHERE stat_type = ? AND stat_date = ? AND city_name = ?
        """, [rank, row.stat_type, row.stat_date, row.city_name])

        rank += 1

    print("正在更新城市排名（旧限值+新算法）...")
    cursor.execute("""
        SELECT stat_type, stat_date, city_name, comprehensive_index_old_limit_new_algo
        FROM city_168_statistics
        WHERE comprehensive_index_old_limit_new_algo IS NOT NULL
        ORDER BY stat_type, stat_date, comprehensive_index_old_limit_new_algo
    """)

    rows = cursor.fetchall()
    current_stat_type = None
    current_stat_date = None
    rank = 1

    for row in rows:
        if row.stat_type != current_stat_type or row.stat_date != current_stat_date:
            current_stat_type = row.stat_type
            current_stat_date = row.stat_date
            rank = 1

        cursor.execute("""
            UPDATE city_168_statistics
            SET comprehensive_index_rank_old_limit_new_algo = ?
            WHERE stat_type = ? AND stat_date = ? AND city_name = ?
        """, [rank, row.stat_type, row.stat_date, row.city_name])

        rank += 1

    conn.commit()
    cursor.close()
    conn.close()

    print("城市排名更新完成")


def update_province_rankings():
    """更新省份排名"""
    conn_str = build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    print("正在更新省份排名（新限值+旧算法）...")
    cursor.execute("""
        SELECT stat_type, stat_date, province_name, comprehensive_index_new_limit_old_algo
        FROM province_statistics
        WHERE comprehensive_index_new_limit_old_algo IS NOT NULL
        ORDER BY stat_type, stat_date, comprehensive_index_new_limit_old_algo
    """)

    rows = cursor.fetchall()
    current_stat_type = None
    current_stat_date = None
    rank = 1

    for row in rows:
        if row.stat_type != current_stat_type or row.stat_date != current_stat_date:
            current_stat_type = row.stat_type
            current_stat_date = row.stat_date
            rank = 1

        cursor.execute("""
            UPDATE province_statistics
            SET comprehensive_index_rank_new_limit_old_algo = ?
            WHERE stat_type = ? AND stat_date = ? AND province_name = ?
        """, [rank, row.stat_type, row.stat_date, row.province_name])

        rank += 1

    print("正在更新省份排名（旧限值+新算法）...")
    cursor.execute("""
        SELECT stat_type, stat_date, province_name, comprehensive_index_old_limit_new_algo
        FROM province_statistics
        WHERE comprehensive_index_old_limit_new_algo IS NOT NULL
        ORDER BY stat_type, stat_date, comprehensive_index_old_limit_new_algo
    """)

    rows = cursor.fetchall()
    current_stat_type = None
    current_stat_date = None
    rank = 1

    for row in rows:
        if row.stat_type != current_stat_type or row.stat_date != current_stat_date:
            current_stat_type = row.stat_type
            current_stat_date = row.stat_date
            rank = 1

        cursor.execute("""
            UPDATE province_statistics
            SET comprehensive_index_rank_old_limit_new_algo = ?
            WHERE stat_type = ? AND stat_date = ? AND province_name = ?
        """, [rank, row.stat_type, row.stat_date, row.province_name])

        rank += 1

    conn.commit()
    cursor.close()
    conn.close()

    print("省份排名更新完成")


if __name__ == '__main__':
    print("="*70)
    print("开始更新4套标准组合的综合指数")
    print("="*70)

    try:
        # 1. 更新城市统计数据
        update_city_statistics()

        # 2. 更新省份统计数据
        update_province_statistics()

        # 3. 更新城市排名
        update_city_rankings()

        # 4. 更新省份排名
        update_province_rankings()

        print("="*70)
        print("所有数据更新完成！")
        print("="*70)

    except Exception as e:
        print(f"更新失败: {str(e)}")
        import traceback
        traceback.print_exc()
