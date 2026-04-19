"""
修改数据库表字段类型脚本

功能：
- 将整数字段（SO2、NO2、PM10、O3-8h）改为INT类型
- 将小数字段（PM2.5、CO）改为DECIMAL(5,1)类型

使用方法：
    python backend/alter_table_columns.py

作者：Claude Code
日期：2026-04-18
"""

import sys
import pyodbc
from pathlib import Path

# 添加backend目录到Python路径
script_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(script_dir))

# 导入配置
from app.fetchers.city_statistics.city_statistics_fetcher import SQLServerClient


def alter_table_columns():
    """修改表字段类型"""

    print("\n" + "="*80)
    print("修改数据库表字段类型")
    print("="*80 + "\n")

    # 创建数据库连接
    sql_client = SQLServerClient()

    print("数据库连接信息：")
    print(f"  服务器: {sql_client.host}:{sql_client.port}")
    print(f"  数据库: {sql_client.database}")
    print(f"  用户: {sql_client.user}")
    print()

    # 显示修改计划
    print("【修改计划】")
    print("\n城市统计表 (city_168_statistics_new_standard):")
    print("  - so2_concentration:  decimal(5,2) → INT")
    print("  - no2_concentration:  decimal(5,2) → INT")
    print("  - pm10_concentration: decimal(5,2) → INT")
    print("  - o3_8h_concentration: decimal(5,2) → INT")
    print("  - pm2_5_concentration: decimal(5,2) → DECIMAL(5,1)")
    print("  - co_concentration:  decimal(6,3) → DECIMAL(5,1)")

    print("\n省级统计表 (province_statistics_new_standard):")
    print("  - so2_concentration:  decimal(5,2) → INT")
    print("  - no2_concentration:  decimal(5,2) → INT")
    print("  - pm10_concentration: decimal(5,2) → INT")
    print("  - o3_8h_concentration: decimal(5,2) → INT")
    print("  - pm2_5_concentration: decimal(5,2) → DECIMAL(5,1)")
    print("  - co_concentration:  decimal(6,3) → DECIMAL(5,1)")

    print("\n注意：")
    print("  ⚠ 修改字段类型会清空表中的所有数据")
    print("  ⚠ 修改后需要重新计算所有统计数据")
    print()

    # 确认
    confirm = input("确认要修改字段类型吗？此操作不可恢复！(yes/no): ")
    if confirm.lower() != 'yes':
        print("\n已取消修改")
        return

    try:
        conn = pyodbc.connect(sql_client.connection_string, timeout=30)
        cursor = conn.cursor()

        print("\n开始修改字段类型...")
        print("-"*80)

        # 修改城市统计表
        print("\n正在修改城市统计表...")

        # 整数字段改为INT
        print("  [1/6] so2_concentration → INT")
        cursor.execute("ALTER TABLE city_168_statistics_new_standard ALTER COLUMN so2_concentration INT")

        print("  [2/6] no2_concentration → INT")
        cursor.execute("ALTER TABLE city_168_statistics_new_standard ALTER COLUMN no2_concentration INT")

        print("  [3/6] pm10_concentration → INT")
        cursor.execute("ALTER TABLE city_168_statistics_new_standard ALTER COLUMN pm10_concentration INT")

        print("  [4/6] o3_8h_concentration → INT")
        cursor.execute("ALTER TABLE city_168_statistics_new_standard ALTER COLUMN o3_8h_concentration INT")

        # 小数字段调整为1位小数
        print("  [5/6] pm2_5_concentration → DECIMAL(5,1)")
        cursor.execute("ALTER TABLE city_168_statistics_new_standard ALTER COLUMN pm2_5_concentration DECIMAL(5,1)")

        print("  [6/6] co_concentration → DECIMAL(5,1)")
        cursor.execute("ALTER TABLE city_168_statistics_new_standard ALTER COLUMN co_concentration DECIMAL(5,1)")

        print("\n✓ 城市统计表字段类型修改完成")

        # 修改省级统计表
        print("\n正在修改省级统计表...")

        # 整数字段改为INT
        print("  [1/6] so2_concentration → INT")
        cursor.execute("ALTER TABLE province_statistics_new_standard ALTER COLUMN so2_concentration INT")

        print("  [2/6] no2_concentration → INT")
        cursor.execute("ALTER TABLE province_statistics_new_standard ALTER COLUMN no2_concentration INT")

        print("  [3/6] pm10_concentration → INT")
        cursor.execute("ALTER TABLE province_statistics_new_standard ALTER COLUMN pm10_concentration INT")

        print("  [4/6] o3_8h_concentration → INT")
        cursor.execute("ALTER TABLE province_statistics_new_standard ALTER COLUMN o3_8h_concentration INT")

        # 小数字段调整为1位小数
        print("  [5/6] pm2_5_concentration → DECIMAL(5,1)")
        cursor.execute("ALTER TABLE province_statistics_new_standard ALTER COLUMN pm2_5_concentration DECIMAL(5,1)")

        print("  [6/6] co_concentration → DECIMAL(5,1)")
        cursor.execute("ALTER TABLE province_statistics_new_standard ALTER COLUMN co_concentration DECIMAL(5,1)")

        print("\n✓ 省级统计表字段类型修改完成")

        conn.commit()
        cursor.close()
        conn.close()

        print("-"*80)
        print("\n" + "="*80)
        print("✓ 字段类型修改完成！")
        print("="*80)
        print("\n新字段类型：")
        print("  - SO2、NO2、PM10、O3-8h: INT (整数)")
        print("  - PM2.5、CO: DECIMAL(5,1) (1位小数)")
        print()
        print("下一步操作：")
        print("  1. 清除所有数据: python clear_all_statistics.py")
        print("  2. 重新计算数据: python manual_update_2026_statistics.py")
        print("  3. 验证数据: python verify_statistics_update.py")
        print()

    except pyodbc.Error as e:
        print(f"\n✗ 数据库操作失败: {str(e)}")
        print(f"  SQLState: {e.args[0] if e.args else 'N/A'}")
        print(f"  错误信息: {e.args[1] if len(e.args) > 1 else 'N/A'}")
        sys.exit(1)


if __name__ == "__main__":
    alter_table_columns()
