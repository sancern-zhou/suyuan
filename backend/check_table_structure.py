"""
检查统计数据表结构

使用方法：
    python backend/check_table_structure.py
"""

import sys
import pyodbc
from pathlib import Path

# 添加backend目录到Python路径
script_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(script_dir))

from app.fetchers.city_statistics.city_statistics_fetcher import SQLServerClient


def check_table_structure():
    """检查表结构"""

    sql_client = SQLServerClient()

    try:
        conn = pyodbc.connect(sql_client.connection_string, timeout=30)
        cursor = conn.cursor()

        print("\n" + "="*80)
        print("城市统计表结构 (city_168_statistics_new_standard)")
        print("="*80 + "\n")

        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                   NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'city_168_statistics_new_standard'
            AND COLUMN_NAME IN ('so2_concentration', 'no2_concentration',
                               'pm10_concentration', 'pm2_5_concentration',
                               'co_concentration', 'o3_8h_concentration')
            ORDER BY ORDINAL_POSITION
        """)

        print(f"{'字段名':<25} {'数据类型':<20} {'精度':<10} {'小数位':<10} {'可空':<10}")
        print("-"*80)
        for row in cursor:
            data_type = row.DATA_TYPE
            precision = str(row.NUMERIC_PRECISION) if row.NUMERIC_PRECISION else 'N/A'
            scale = str(row.NUMERIC_SCALE) if row.NUMERIC_SCALE else 'N/A'
            print(f"{row.COLUMN_NAME:<25} {data_type:<20} {precision:<10} {scale:<10} {row.IS_NULLABLE:<10}")

        print("\n" + "="*80)
        print("省级统计表结构 (province_statistics_new_standard)")
        print("="*80 + "\n")

        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                   NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'province_statistics_new_standard'
            AND COLUMN_NAME IN ('so2_concentration', 'no2_concentration',
                               'pm10_concentration', 'pm2_5_concentration',
                               'co_concentration', 'o3_8h_concentration')
            ORDER BY ORDINAL_POSITION
        """)

        print(f"{'字段名':<25} {'数据类型':<20} {'精度':<10} {'小数位':<10} {'可空':<10}")
        print("-"*80)
        for row in cursor:
            data_type = row.DATA_TYPE
            precision = str(row.NUMERIC_PRECISION) if row.NUMERIC_PRECISION else 'N/A'
            scale = str(row.NUMERIC_SCALE) if row.NUMERIC_SCALE else 'N/A'
            print(f"{row.COLUMN_NAME:<25} {data_type:<20} {precision:<10} {scale:<10} {row.IS_NULLABLE:<10}")

        print("\n" + "="*80)
        print("分析")
        print("="*80 + "\n")

        print("当前字段类型分析：")
        print("  - 如果字段类型是 decimal 或 numeric，且 scale=2，")
        print("    即使Python传入整数，数据库也会存储为 14.00")
        print("\n解决方案：")
        print("  方案1: 修改数据库字段类型（整数字段改为 INT）")
        print("  方案2: 接受当前格式（功能正确，只是显示为 14.00）")
        print("\n推荐：方案2")
        print("  - 数据值是正确的（14.00 = 14）")
        print("  - 只是在显示时有小数位，不影响计算")
        print("  - 前端显示时可以格式化为整数")
        print()

        cursor.close()
        conn.close()

    except pyodbc.Error as e:
        print(f"\n✗ 数据库查询失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    check_table_structure()
