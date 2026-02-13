"""
测试SQL Server连接和CityAQIPublishHistory表查询
"""
import pyodbc
import os
from datetime import datetime, timedelta

# SQL Server 连接配置
sql_server_config = {
    'driver': '{ODBC Driver 18 for SQL Server}',
    'server': '180.184.30.94',
    'port': 1433,
    'database': 'XcAiDb',
    'uid': 'sa',
    'pwd': '#Ph981,6J2bOkWYT7p?5slH$I~g_0itR'
}

print("=" * 60)
print("SQL Server 连接测试")
print("=" * 60)
print(f"服务器: {sql_server_config['server']}:{sql_server_config['port']}")
print(f"数据库: {sql_server_config['database']}")
print(f"用户: {sql_server_config['uid']}")
print()

conn = None
cursor = None

try:
    # 构建连接字符串
    conn_str = (
        f"DRIVER={sql_server_config['driver']};"
        f"SERVER={sql_server_config['server']},{sql_server_config['port']};"
        f"DATABASE={sql_server_config['database']};"
        f"UID={sql_server_config['uid']};"
        f"PWD={sql_server_config['pwd']};"
        f"TrustServerCertificate=yes;"
    )

    print("正在连接数据库...")
    conn = pyodbc.connect(conn_str, timeout=10)
    cursor = conn.cursor()
    print("连接成功!")

    # 1. 检查表是否存在
    print("\n" + "=" * 60)
    print("检查 CityAQIPublishHistory 表")
    print("=" * 60)
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = 'CityAQIPublishHistory'
    """)
    table_exists = cursor.fetchone()[0]
    print(f"表存在: {'是' if table_exists > 0 else '否'}")

    if not table_exists:
        print("错误: CityAQIPublishHistory 表不存在!")
        exit(1)

    # 2. 查询表结构
    print("\n" + "=" * 60)
    print("表结构")
    print("=" * 60)
    cursor.execute("""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'CityAQIPublishHistory'
        ORDER BY ORDINAL_POSITION
    """)
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[0]:<25} {col[1]:<20} {col[2]}")

    # 3. 查询总记录数
    print("\n" + "=" * 60)
    print("总记录数")
    print("=" * 60)
    cursor.execute("SELECT COUNT(*) FROM CityAQIPublishHistory")
    total_count = cursor.fetchone()[0]
    print(f"总记录数: {total_count}")

    # 4. 查询所有城市
    print("\n" + "=" * 60)
    print("所有城市 (按记录数排序)")
    print("=" * 60)
    cursor.execute("""
        SELECT Area, COUNT(*) as cnt
        FROM CityAQIPublishHistory
        GROUP BY Area
        ORDER BY cnt DESC
    """)
    cities = cursor.fetchall()
    print(f"共 {len(cities)} 个城市:")
    for city, cnt in cities[:20]:  # 只显示前20个
        print(f"  {city}: {cnt} 条记录")

    # 5. 查询济宁相关数据
    print("\n" + "=" * 60)
    print("济宁相关数据")
    print("=" * 60)
    jining_cities = ["济宁市", "济宁"]
    for city_name in jining_cities:
        cursor.execute("""
            SELECT COUNT(*)
            FROM CityAQIPublishHistory
            WHERE Area = ?
        """, city_name)
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"  {city_name}: {count} 条记录")

    # 6. 查询时间范围
    print("\n" + "=" * 60)
    print("数据时间范围")
    print("=" * 60)
    cursor.execute("""
        SELECT MIN(TimePoint) as min_time, MAX(TimePoint) as max_time
        FROM CityAQIPublishHistory
    """)
    time_range = cursor.fetchone()
    print(f"最早时间: {time_range[0]}")
    print(f"最新时间: {time_range[1]}")

    # 7. 查询最新数据
    print("\n" + "=" * 60)
    print("最新5条数据")
    print("=" * 60)
    cursor.execute("""
        SELECT TOP 5
            TimePoint, Area, CityCode,
            CO, NO2, O3, PM10, PM2_5, SO2,
            AQI, PrimaryPollutant, Quality
        FROM CityAQIPublishHistory
        ORDER BY TimePoint DESC
    """)
    latest_data = cursor.fetchall()
    for row in latest_data:
        print(f"  时间: {row[0]}, 城市: {row[1]}, AQI: {row[10]}")

    # 8. 测试周边12小时查询
    print("\n" + "=" * 60)
    print("测试周边12小时查询 (济宁及周边城市)")
    print("=" * 60)
    cities = ["济宁市", "菏泽市", "枣庄市", "临沂市", "泰安市", "徐州市", "商丘市", "开封市"]
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=12)

    city_placeholders = ','.join(['?' for _ in cities])
    sql_query = f"""
        SELECT
            TimePoint, Area, CityCode,
            CO, NO2, O3, PM10, PM2_5, SO2,
            AQI, PrimaryPollutant, Quality
        FROM CityAQIPublishHistory WITH (NOLOCK)
        WHERE Area IN ({city_placeholders})
            AND TimePoint >= ?
            AND TimePoint <= ?
        ORDER BY TimePoint DESC
    """

    params = cities + [start_time, end_time]
    cursor.execute(sql_query, params)

    # 获取列名
    columns = [column[0] for column in cursor.description]
    print(f"\n查询字段: {', '.join(columns)}")

    history_data = cursor.fetchall()

    print(f"查询时间范围: {start_time} ~ {end_time}")
    print(f"查询城市: {', '.join(cities)}")
    print(f"找到 {len(history_data)} 条记录")

    if history_data:
        print("\n示例数据 (前3条):")
        for row in history_data[:3]:
            row_dict = dict(zip(columns, row))
            print(f"  时间: {row_dict['TimePoint']}")
            print(f"  城市: {row_dict['Area']} (代码: {row_dict['CityCode']})")
            print(f"  AQI: {row_dict['AQI']}")
            print(f"  首要污染物: {row_dict['PrimaryPollutant']}")
            print(f"  等级: {row_dict['Quality']}")
            print(f"  PM2.5: {row_dict['PM2_5']}, PM10: {row_dict['PM10']}, O3: {row_dict['O3']}")
            print(f"  NO2: {row_dict['NO2']}, SO2: {row_dict['SO2']}, CO: {row_dict['CO']}")
            print()

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

except pyodbc.Error as e:
    print(f"\nSQL Server 错误:")
    print(f"  错误类型: {type(e).__name__}")
    print(f"  错误信息: {e}")
    import traceback
    traceback.print_exc()

except Exception as e:
    print(f"\n其他错误:")
    print(f"  错误类型: {type(e).__name__}")
    print(f"  错误信息: {e}")
    import traceback
    traceback.print_exc()

finally:
    # 关闭连接
    if cursor:
        cursor.close()
    if conn:
        conn.close()
        print("\n数据库连接已关闭")
