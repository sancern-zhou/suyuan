"""
批量更新4套标准组合的排名

使用窗口函数提高性能
"""

import pyodbc

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

def update_rankings():
    """批量更新排名"""
    conn_str = build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=120)
    cursor = conn.cursor()

    print("="*70)
    print("开始批量更新排名")
    print("="*70)

    # 更新城市排名 - 新限值+旧算法
    print("\n[1/4] 更新城市排名（新限值+旧算法）...")
    sql = """
    WITH Ranked AS (
        SELECT
            city_name,
            stat_type,
            stat_date,
            ROW_NUMBER() OVER (PARTITION BY stat_type, stat_date ORDER BY comprehensive_index_new_limit_old_algo ASC) as rank_num
        FROM city_168_statistics
        WHERE comprehensive_index_new_limit_old_algo IS NOT NULL
    )
    UPDATE c
    SET c.comprehensive_index_rank_new_limit_old_algo = r.rank_num
    FROM city_168_statistics c
    INNER JOIN Ranked r ON c.city_name = r.city_name AND c.stat_type = r.stat_type AND c.stat_date = r.stat_date
    """
    cursor.execute(sql)
    print(f"影响行数: {cursor.rowcount}")

    # 更新城市排名 - 旧限值+新算法
    print("\n[2/4] 更新城市排名（旧限值+新算法）...")
    sql = """
    WITH Ranked AS (
        SELECT
            city_name,
            stat_type,
            stat_date,
            ROW_NUMBER() OVER (PARTITION BY stat_type, stat_date ORDER BY comprehensive_index_old_limit_new_algo ASC) as rank_num
        FROM city_168_statistics
        WHERE comprehensive_index_old_limit_new_algo IS NOT NULL
    )
    UPDATE c
    SET c.comprehensive_index_rank_old_limit_new_algo = r.rank_num
    FROM city_168_statistics c
    INNER JOIN Ranked r ON c.city_name = r.city_name AND c.stat_type = r.stat_type AND c.stat_date = r.stat_date
    """
    cursor.execute(sql)
    print(f"影响行数: {cursor.rowcount}")

    # 更新省份排名 - 新限值+旧算法
    print("\n[3/4] 更新省份排名（新限值+旧算法）...")
    sql = """
    WITH Ranked AS (
        SELECT
            province_name,
            stat_type,
            stat_date,
            ROW_NUMBER() OVER (PARTITION BY stat_type, stat_date ORDER BY comprehensive_index_new_limit_old_algo ASC) as rank_num
        FROM province_statistics
        WHERE comprehensive_index_new_limit_old_algo IS NOT NULL
    )
    UPDATE p
    SET p.comprehensive_index_rank_new_limit_old_algo = r.rank_num
    FROM province_statistics p
    INNER JOIN Ranked r ON p.province_name = r.province_name AND p.stat_type = r.stat_type AND p.stat_date = r.stat_date
    """
    cursor.execute(sql)
    print(f"影响行数: {cursor.rowcount}")

    # 更新省份排名 - 旧限值+新算法
    print("\n[4/4] 更新省份排名（旧限值+新算法）...")
    sql = """
    WITH Ranked AS (
        SELECT
            province_name,
            stat_type,
            stat_date,
            ROW_NUMBER() OVER (PARTITION BY stat_type, stat_date ORDER BY comprehensive_index_old_limit_new_algo ASC) as rank_num
        FROM province_statistics
        WHERE comprehensive_index_old_limit_new_algo IS NOT NULL
    )
    UPDATE p
    SET p.comprehensive_index_rank_old_limit_new_algo = r.rank_num
    FROM province_statistics p
    INNER JOIN Ranked r ON p.province_name = r.province_name AND p.stat_type = r.stat_type AND p.stat_date = r.stat_date
    """
    cursor.execute(sql)
    print(f"影响行数: {cursor.rowcount}")

    conn.commit()
    cursor.close()
    conn.close()

    print("\n" + "="*70)
    print("排名更新完成！")
    print("="*70)

if __name__ == '__main__':
    try:
        update_rankings()
    except Exception as e:
        print(f"更新失败: {str(e)}")
        import traceback
        traceback.print_exc()
