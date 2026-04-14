#!/usr/bin/env python3
"""检查表结构"""
import pyodbc
from config.settings import Settings

def describe_table(table_name: str):
    settings = Settings()
    conn_str = settings.sqlserver_connection_string

    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    # 查询表结构
    sql = f"""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH,
            IS_NULLABLE,
            COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = '{table_name}'
        ORDER BY ORDINAL_POSITION
    """

    cursor.execute(sql)
    columns = cursor.fetchall()

    if not columns:
        print(f"未找到表 '{table_name}' 的结构信息")
        return

    print(f"表名: {table_name}\n")
    print("字段列表:")
    for col in columns:
        col_name, data_type, max_length, is_nullable, col_default = col
        length_str = f"({max_length})" if max_length else ""
        nullable_str = "可空" if is_nullable == "YES" else "非空"
        print(f"  - {col_name} ({data_type}{length_str}, {nullable_str})")

    # 获取1条数据样例
    sample_sql = f"SELECT TOP 1 * FROM {table_name}"
    cursor.execute(sample_sql)
    sample = cursor.fetchone()

    if sample:
        print("\n数据样例:")
        for i, col in enumerate(columns):
            col_name = col[0]
            value = sample[i] if i < len(sample) else "NULL"
            if value and len(str(value)) > 50:
                value = str(value)[:50] + "..."
            print(f"  {col_name}: {value}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    # 检查可能相关的表
    tables_to_check = [
        "CityDayAQIPublishHistory",
        "CityAQIPublishHistory",
        "CurrentAirQuality",
        "dat_station_day",
        "city_168_statistics"
    ]

    for table in tables_to_check:
        print("=" * 80)
        describe_table(table)
        print()
