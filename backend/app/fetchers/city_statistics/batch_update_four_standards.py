"""
批量更新4套标准组合的综合指数（优化版）

使用批量更新提高性能
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

def build_connection_string():
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_CONFIG['host']},{DB_CONFIG['port']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['user']};"
        f"PWD={{{DB_CONFIG['password']}}};"
        f"TrustServerCertificate=yes;"
    )

def update_all():
    """批量更新所有数据"""
    conn_str = build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=120)
    cursor = conn.cursor()

    print("="*70)
    print("开始批量更新4套标准组合的综合指数")
    print("="*70)

    # 更新城市数据表 - 新限值+旧算法
    print("\n[1/4] 更新城市数据表（新限值+旧算法）...")
    sql = """
    UPDATE city_168_statistics
    SET comprehensive_index_new_limit_old_algo =
        ROUND(ISNULL(so2_index, 0) * 1.0 +
              ISNULL(no2_index, 0) * 1.0 +
              ISNULL(pm10_index, 0) * 1.0 +
              ISNULL(pm2_5_index, 0) * 1.0 +
              ISNULL(co_index, 0) * 1.0 +
              ISNULL(o3_8h_index, 0) * 1.0, 3)
    WHERE comprehensive_index IS NOT NULL
    """
    cursor.execute(sql)
    print(f"影响行数: {cursor.rowcount}")

    # 更新城市数据表 - 旧限值+新算法
    print("\n[2/4] 更新城市数据表（旧限值+新算法）...")
    sql = """
    UPDATE city_168_statistics
    SET comprehensive_index_old_limit_new_algo =
        ROUND(ISNULL(so2_index, 0) * 1.0 +
              ISNULL(no2_index, 0) * 2.0 +
              ISNULL(pm10_index_old, pm10_index) * 1.0 +
              ISNULL(pm2_5_index_old, pm2_5_index) * 3.0 +
              ISNULL(co_index, 0) * 1.0 +
              ISNULL(o3_8h_index, 0) * 2.0, 3)
    WHERE comprehensive_index IS NOT NULL
    """
    cursor.execute(sql)
    print(f"影响行数: {cursor.rowcount}")

    # 更新省份数据表 - 新限值+旧算法
    print("\n[3/4] 更新省份数据表（新限值+旧算法）...")
    sql = """
    UPDATE province_statistics
    SET comprehensive_index_new_limit_old_algo =
        ROUND(ISNULL(so2_index, 0) * 1.0 +
              ISNULL(no2_index, 0) * 1.0 +
              ISNULL(pm10_index, 0) * 1.0 +
              ISNULL(pm2_5_index, 0) * 1.0 +
              ISNULL(co_index, 0) * 1.0 +
              ISNULL(o3_8h_index, 0) * 1.0, 3)
    WHERE comprehensive_index IS NOT NULL
    """
    cursor.execute(sql)
    print(f"影响行数: {cursor.rowcount}")

    # 更新省份数据表 - 旧限值+新算法
    print("\n[4/4] 更新省份数据表（旧限值+新算法）...")
    sql = """
    UPDATE province_statistics
    SET comprehensive_index_old_limit_new_algo =
        ROUND(ISNULL(so2_index, 0) * 1.0 +
              ISNULL(no2_index, 0) * 2.0 +
              ISNULL(pm10_index_old, pm10_index) * 1.0 +
              ISNULL(pm2_5_index_old, pm2_5_index) * 3.0 +
              ISNULL(co_index, 0) * 1.0 +
              ISNULL(o3_8h_index, 0) * 2.0, 3)
    WHERE comprehensive_index IS NOT NULL
    """
    cursor.execute(sql)
    print(f"影响行数: {cursor.rowcount}")

    conn.commit()
    cursor.close()
    conn.close()

    print("\n" + "="*70)
    print("批量更新完成！")
    print("="*70)

if __name__ == '__main__':
    try:
        update_all()
    except Exception as e:
        print(f"更新失败: {str(e)}")
        import traceback
        traceback.print_exc()
