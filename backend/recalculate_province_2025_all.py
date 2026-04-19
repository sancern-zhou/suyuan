"""
重新计算2025年省级统计数据

功能：
1. 清空2025年省级统计数据
2. 重新计算2025年1月至指定月份的省级统计数据
3. 包含月度统计(monthly)、当月累计(current_month)、年度累计(annual_ytd)

用法：
    python recalculate_province_2025_all.py [月份]

示例：
    python recalculate_province_2025_all.py 12    # 重算1-12月（全年）
    python recalculate_province_2025_all.py 6     # 重算1-6月
    python recalculate_province_2025_all.py       # 默认重算1-12月
"""
import sys
import asyncio
from datetime import date, timedelta

sys.path.insert(0, '/home/xckj/suyuan/backend')

import pyodbc
from app.fetchers.city_statistics.province_statistics_fetcher import (
    ProvinceStatisticsFetcher,
    ProvinceSQLServerClient
)


def clear_2025_province_statistics():
    """清空2025年所有省级统计数据"""
    print("\n" + "="*80)
    print("步骤1：清空2025年省级统计数据")
    print("="*80)

    sql_client = ProvinceSQLServerClient()
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        # 删除2025年的所有省级统计数据
        delete_sql = """
        DELETE FROM province_statistics_new_standard
        WHERE stat_date LIKE '2025%'
        """
        cursor.execute(delete_sql)
        deleted_count = cursor.rowcount

        conn.commit()
        print(f"  已删除2025年省级统计数据：{deleted_count} 条记录")

    except Exception as e:
        conn.rollback()
        print(f"\n清空失败: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()


async def calculate_province_current_month(year: int, month: int, day: int):
    """计算指定日期的当月累计统计"""
    fetcher = ProvinceStatisticsFetcher()
    calc_date = date(year, month, day)

    print(f"\n  计算当月累计：{calc_date}")
    await fetcher._calculate_and_store_current_month(calc_date)


async def convert_to_monthly(year: int, month: int):
    """将当月累计转换为月度统计"""
    fetcher = ProvinceStatisticsFetcher()

    # 获取下月第一天用于触发转换
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)

    print(f"  转换为月度统计：{year}-{month:02d}")
    await fetcher._convert_current_to_monthly(next_month)


async def calculate_province_annual_ytd(year: int, month: int, day: int):
    """计算年度累计统计"""
    fetcher = ProvinceStatisticsFetcher()
    calc_date = date(year, month, day)

    print(f"\n  计算年度累计：截至 {calc_date}")
    await fetcher._calculate_and_store_annual_ytd(calc_date)


def verify_results():
    """验证计算结果"""
    print("\n" + "="*80)
    print("步骤4：验证计算结果")
    print("="*80)

    sql_client = ProvinceSQLServerClient()
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        # 验证省级统计
        print("\n省级统计表（2025年）：")
        print("-" * 80)
        check_sql = """
        SELECT stat_date, stat_type, COUNT(*) as count,
               AVG(city_count) as avg_cities,
               MIN(city_count) as min_cities,
               MAX(city_count) as max_cities
        FROM province_statistics_new_standard
        WHERE stat_date LIKE '2025%'
        GROUP BY stat_date, stat_type
        ORDER BY stat_date, stat_type
        """
        cursor.execute(check_sql)

        rows = cursor.fetchall()
        if not rows:
            print("  未找到2025年数据")
            return

        for row in rows:
            print(f"  {row.stat_date:12} | {row.stat_type:15} | {row.count:3} 省份 | "
                  f"平均{row.avg_cities:.1f}城市 (范围:{row.min_cities}-{row.max_cities})")

        # 查询每个省份的城市名单（2025-01 monthly）
        print("\n各省份城市名单（2025-01 monthly，按城市数量排序）：")
        print("-" * 80)

        cursor.execute("""
            SELECT province_name, city_count, city_names
            FROM province_statistics_new_standard
            WHERE stat_date = '2025-01' AND stat_type = 'monthly'
            ORDER BY city_count DESC, province_name
        """)

        rows = cursor.fetchall()
        for row in rows:
            cities = row.city_names.split(',') if row.city_names else []
            print(f"\n  {row.province_name} ({row.city_count}个城市)：")
            # 每行显示5个城市
            for i in range(0, len(cities), 5):
                city_group = cities[i:i+5]
                print(f"    {', '.join(city_group)}")

    finally:
        cursor.close()
        conn.close()


async def main():
    """主函数"""
    # 获取要计算的月份（默认12月，即全年）
    end_month = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    end_month = max(1, min(12, end_month))  # 限制在1-12范围内

    print("="*80)
    print("重新计算2025年省级统计数据")
    print("="*80)
    print(f"\n计算范围：2025年1月至{end_month}月")
    print("\n统计范围：全国所有地级市、州、盟")

    try:
        # 步骤1：清空2025年数据
        clear_2025_province_statistics()

        # 步骤2：按月计算统计数据
        print("\n" + "="*80)
        print("步骤2：计算月度统计数据")
        print("="*80)

        for month in range(1, end_month + 1):
            print(f"\n--- 计算 2025-{month:02d} ---")

            # 获取该月最后一天
            if month == 12:
                last_day = date(2026, 1, 1) - timedelta(days=1)
            else:
                last_day = date(2025, month + 1, 1) - timedelta(days=1)

            # 计算当月累计
            await calculate_province_current_month(2025, month, last_day.day)

            # 转换为月度统计
            await convert_to_monthly(2025, month)

        # 计算年度累计（截至最后一个月的月底）
        print("\n" + "="*80)
        print("步骤3：计算年度累计数据")
        print("="*80)

        if end_month == 12:
            last_day = date(2025, 12, 31)
        else:
            last_day = date(2025, end_month + 1, 1) - timedelta(days=1)

        await calculate_province_annual_ytd(2025, last_day.month, last_day.day)

        # 验证结果
        verify_results()

        print("\n" + "="*80)
        print("重新计算完成！")
        print("="*80)
        print(f"\n已重新计算2025年1-{end_month}月的省级统计数据")
        print("数据范围：全国所有地级市、州、盟")

    except Exception as e:
        print(f"\n执行失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
