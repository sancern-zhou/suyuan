"""
清除所有统计数据脚本

功能：
- 清除 city_168_statistics_new_standard 表中的所有数据
- 清除 province_statistics_new_standard 表中的所有数据

使用方法：
    python backend/clear_all_statistics.py

作者：Claude Code
日期：2026-04-18

注意：
清除后请运行 manual_update_2026_statistics.py 重新计算数据
新的stat_type命名：
- ytd_to_month: 年初到某月累计
- month_current: 当月累计（进行中）
- year_to_date: 年初至今累计
- month_complete: 完整月数据（已结束）
"""

import sys
import pyodbc
from pathlib import Path

# 添加backend目录到Python路径
script_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(script_dir))

# 导入配置
from app.fetchers.city_statistics.city_statistics_fetcher import SQLServerClient


def clear_all_statistics():
    """清除所有统计数据"""

    print("\n" + "="*80)
    print("清除所有统计数据脚本")
    print("="*80 + "\n")

    # 创建数据库连接
    sql_client = SQLServerClient()

    print("数据库连接信息：")
    print(f"  服务器: {sql_client.host}:{sql_client.port}")
    print(f"  数据库: {sql_client.database}")
    print(f"  用户: {sql_client.user}")
    print()

    try:
        conn = pyodbc.connect(sql_client.connection_string, timeout=30)
        cursor = conn.cursor()

        # 统计删除前的数据量
        print("正在统计删除前的数据量...")

        cursor.execute("SELECT COUNT(*) FROM city_168_statistics_new_standard")
        city_count_before = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM province_statistics_new_standard")
        province_count_before = cursor.fetchone()[0]

        print(f"\n删除前数据量：")
        print(f"  城市统计表: {city_count_before:,} 条")
        print(f"  省级统计表: {province_count_before:,} 条")
        print(f"  总计: {city_count_before + province_count_before:,} 条")
        print()

        # 确认删除
        confirm = input("确认要删除所有数据吗？此操作不可恢复！(yes/no): ")
        if confirm.lower() != 'yes':
            print("\n已取消删除操作")
            conn.close()
            return

        print("\n开始删除数据...")
        print("-"*80)

        # 删除城市统计数据
        print("正在删除城市统计数据...")
        cursor.execute("DELETE FROM city_168_statistics_new_standard")
        city_deleted = cursor.rowcount
        print(f"✓ 城市统计数据已删除: {city_deleted:,} 条")

        # 删除省级统计数据
        print("正在删除省级统计数据...")
        cursor.execute("DELETE FROM province_statistics_new_standard")
        province_deleted = cursor.rowcount
        print(f"✓ 省级统计数据已删除: {province_deleted:,} 条")

        # 提交事务
        conn.commit()

        print("-"*80)

        # 验证删除结果
        print("\n正在验证删除结果...")

        cursor.execute("SELECT COUNT(*) FROM city_168_statistics_new_standard")
        city_count_after = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM province_statistics_new_standard")
        province_count_after = cursor.fetchone()[0]

        print(f"\n删除后数据量：")
        print(f"  城市统计表: {city_count_after:,} 条")
        print(f"  省级统计表: {province_count_after:,} 条")

        if city_count_after == 0 and province_count_after == 0:
            print("\n" + "="*80)
            print("✓ 所有数据已成功清除！")
            print("="*80)
            print("\n下一步：运行以下命令重新计算数据")
            print("  python backend/manual_update_2026_statistics.py")
            print()
        else:
            print("\n" + "="*80)
            print("⚠ 警告：数据清除不完全，请检查！")
            print("="*80 + "\n")

        cursor.close()
        conn.close()

    except pyodbc.Error as e:
        print(f"\n✗ 数据库操作失败: {str(e)}")
        print(f"  SQLState: {e.args[0] if e.args else 'N/A'}")
        print(f"  错误信息: {e.args[1] if len(e.args) > 1 else 'N/A'}")
        sys.exit(1)


if __name__ == "__main__":
    clear_all_statistics()
