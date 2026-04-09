"""
执行数据库迁移脚本
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
    """构建ODBC连接字符串"""
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_CONFIG['host']},{DB_CONFIG['port']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['user']};"
        f"PWD={{{DB_CONFIG['password']}}};"
        f"TrustServerCertificate=yes;"
    )

def execute_migration():
    """执行迁移"""
    conn_str = build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    # 城市数据表迁移
    print("正在迁移城市数据表...")

    sql_statements = [
        "ALTER TABLE city_168_statistics ADD comprehensive_index_new_limit_old_algo decimal(10, 3) NULL",
        "ALTER TABLE city_168_statistics ADD comprehensive_index_rank_new_limit_old_algo int NULL",
        "ALTER TABLE city_168_statistics ADD comprehensive_index_old_limit_new_algo decimal(10, 3) NULL",
        "ALTER TABLE city_168_statistics ADD comprehensive_index_rank_old_limit_new_algo int NULL",
        "ALTER TABLE province_statistics ADD comprehensive_index_new_limit_old_algo decimal(10, 3) NULL",
        "ALTER TABLE province_statistics ADD comprehensive_index_rank_new_limit_old_algo int NULL",
        "ALTER TABLE province_statistics ADD comprehensive_index_old_limit_new_algo decimal(10, 3) NULL",
        "ALTER TABLE province_statistics ADD comprehensive_index_rank_old_limit_new_algo int NULL",
    ]

    for sql in sql_statements:
        try:
            cursor.execute(sql)
            print(f"执行成功: {sql[:80]}...")
        except Exception as e:
            if 'already exists' in str(e) or 'duplicate column name' in str(e).lower():
                print(f"字段已存在，跳过: {sql[:80]}...")
            else:
                print(f"执行失败: {sql[:80]}...")
                print(f"错误: {str(e)}")

    conn.commit()
    cursor.close()
    conn.close()

    print("数据库迁移完成！")

if __name__ == '__main__':
    execute_migration()
