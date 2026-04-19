"""
重新计算2026年统计数据（使用新的年月格式）

功能：
1. 清空所有历史数据
2. 重新计算2026年1-3月的月度数据
3. 使用新的年月格式（stat_date: VARCHAR(7)）

新的日期格式：
- monthly: "2026-01"（表示2026年1月全月数据）
- current_month: "2026-04"（表示2026年4月当月累计）
- annual_ytd: "2026"（表示2026年年初至今）
"""
import sys
import asyncio
from datetime import date, datetime, timedelta

sys.path.insert(0, '/home/xckj/suyuan/backend')

from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceStatisticsFetcher
from app.fetchers.city_statistics.city_statistics_fetcher import CityStatisticsFetcher


def clear_all_statistics():
    """清空所有统计数据"""
    import pyodbc
    from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient

    print("\n" + "="*80)
    print("步骤1：清空所有历史数据")
    print("="*80)

    sql_client = ProvinceSQLServerClient()
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        # 清空省级统计表
        delete_province = "DELETE FROM province_statistics_new_standard"
        cursor.execute(delete_province)
        province_count = cursor.rowcount
        print(f"  ✓ 已清空省级统计表：{province_count} 条记录")

        # 清空城市统计表
        delete_city = "DELETE FROM city_168_statistics_new_standard"
        cursor.execute(delete_city)
        city_count = cursor.rowcount
        print(f"  ✓ 已清空城市统计表：{city_count} 条记录")

        conn.commit()
        print("\n✓ 数据清空完成！")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ 清空失败: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()


async def calculate_province_monthly(year: int, month: int):
    """计算指定月份的省级统计数据"""
    fetcher = ProvinceStatisticsFetcher()

    # 获取该月的最后一天
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    print(f"\n  计算省级统计：{year}-{month:02d}（1日-{last_day.day}日）")

    # 计算当月累计（模拟该月最后一天）
    await fetcher._calculate_and_store_current_month(last_day)

    # 转换为monthly（模拟下月1日）
    next_month = last_day + timedelta(days=1)
    await fetcher._convert_current_to_monthly(next_month)


async def calculate_city_monthly(year: int, month: int):
    """计算指定月份的城市统计数据"""
    fetcher = CityStatisticsFetcher()

    # 获取该月的最后一天
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    print(f"  计算城市统计：{year}-{month:02d}（1日-{last_day.day}日）")

    # 计算当月累计（模拟该月最后一天）
    await fetcher._calculate_and_store_current_month(last_day)

    # 转换为monthly（模拟下月1日）
    next_month = last_day + timedelta(days=1)
    await fetcher._convert_current_to_monthly(next_month)


async def calculate_annual_ytd(year: int, month: int, day: int):
    """计算年度累计数据"""
    # 省级统计
    province_fetcher = ProvinceStatisticsFetcher()
    calc_date = date(year, month, day)
    print(f"  计算省级年度累计：截至 {calc_date}")
    await province_fetcher._calculate_and_store_annual_ytd(calc_date)

    # 城市统计
    city_fetcher = CityStatisticsFetcher()
    print(f"  计算城市年度累计：截至 {calc_date}")
    await city_fetcher._calculate_and_store_annual_ytd(calc_date)


async def verify_results():
    """验证计算结果"""
    import pyodbc
    from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient

    print("\n" + "="*80)
    print("步骤4：验证计算结果")
    print("="*80)

    sql_client = ProvinceSQLServerClient()
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        # 验证省级统计
        print("\n省级统计表：")
        print("-" * 80)
        check_province = """
        SELECT stat_date, stat_type, COUNT(*) as count
        FROM province_statistics_new_standard
        GROUP BY stat_date, stat_type
        ORDER BY stat_date, stat_type
        """
        cursor.execute(check_province)
        for row in cursor:
            print(f"  {row.stat_date:12} | {row.stat_type:15} | {row.count:3} 条记录")

        # 验证城市统计
        print("\n城市统计表：")
        print("-" * 80)
        check_city = """
        SELECT stat_date, stat_type, COUNT(*) as count
        FROM city_168_statistics_new_standard
        GROUP BY stat_date, stat_type
        ORDER BY stat_date, stat_type
        """
        cursor.execute(check_city)
        for row in cursor:
            print(f"  {row.stat_date:12} | {row.stat_type:15} | {row.count:3} 条记录")

        # 示例数据检查
        print("\n示例数据（广东省 2026-01 monthly）：")
        print("-" * 80)
        example = """
        SELECT TOP 1
            stat_date, stat_type, province_name,
            pm2_5_concentration, city_count
        FROM province_statistics_new_standard
        WHERE stat_date = '2026-01' AND stat_type = 'monthly' AND province_name = '广东'
        """
        cursor.execute(example)
        row = cursor.fetchone()
        if row:
            print(f"  日期：{row.stat_date}")
            print(f"  类型：{row.stat_type}")
            print(f"  省份：{row.province_name}")
            print(f"  PM2.5：{row.pm2_5_concentration} μg/m³")
            print(f"  城市数：{row.city_count}")
        else:
            print("  ✗ 未找到数据")

    finally:
        cursor.close()
        conn.close()


async def main():
    """主函数"""
    print("="*80)
    print("重新计算2026年统计数据（使用新的年月格式）")
    print("="*80)
    print("\n新的日期格式：")
    print("  - monthly: '2026-01'（表示2026年1月全月数据）")
    print("  - current_month: '2026-04'（表示2026年4月当月累计）")
    print("  - annual_ytd: '2026'（表示2026年年初至今）")

    try:
        # 步骤1：清空所有数据
        clear_all_statistics()

        # 步骤2：计算月度数据
        print("\n" + "="*80)
        print("步骤2：计算月度数据（2026年1-3月）")
        print("="*80)

        months_to_calculate = [1, 2, 3]  # 2026年1-3月

        for month in months_to_calculate:
            print(f"\n--- 计算 2026-{month:02d} ---")

            # 城市统计
            await calculate_city_monthly(2026, month)

            # 省级统计
            await calculate_province_monthly(2026, month)

        # 步骤3：计算年度累计（截至3月31日）
        print("\n" + "="*80)
        print("步骤3：计算年度累计数据（截至2026年3月31日）")
        print("="*80)

        await calculate_annual_ytd(2026, 3, 31)

        # 步骤4：验证结果
        await verify_results()

        print("\n" + "="*80)
        print("✓ 重新计算完成！")
        print("="*80)
        print("\n注意事项：")
        print("  1. 所有历史数据已清空")
        print("  2. 已重新计算2026年1-3月的月度数据")
        print("  3. 日期格式已更新为：VARCHAR(7)")
        print("  4. 请检查验证结果是否正确")

    except Exception as e:
        print(f"\n✗ 执行失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
