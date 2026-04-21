"""
重新计算2026年省级统计数据（完整版）

功能：
1. 清空2026年省级统计数据
2. 重新计算2026年所有类型的省级统计数据（新标准和旧标准）：
   - ytd_to_month: 年初到某月累计（1-1月、1-2月、...）
   - month_current: 当月累计
   - month_complete: 完整月统计
   - year_to_date: 年初至今累计
3. 包含达标率字段（exceed_days, valid_days, compliance_rate, exceed_rate）

用法：
    conda activate /root/miniconda3/envs/backend_py311
    cd /home/xckj/suyuan/backend
    python recalculate_2026_province_full.py [月份]

示例：
    python recalculate_2026_province_full.py       # 默认计算到当前月份
    python recalculate_2026_province_full.py 4     # 计算到4月份

注意：
    - 本脚本使用修改后的代码（日修约→统计修约）
    - 云南省将只包含8个地级市，不包含8个自治州
    - 修约规则已更新：新标准统计修约保留1位小数，旧标准取整
"""
import sys
import asyncio
from datetime import date, timedelta, datetime

sys.path.insert(0, '/home/xckj/suyuan/backend')

import pyodbc
from app.fetchers.city_statistics.province_statistics_fetcher import (
    ProvinceStatisticsFetcher,
    ProvinceSQLServerClient
)
from app.fetchers.city_statistics.province_statistics_old_standard_fetcher import (
    ProvinceStatisticsOldStandardFetcher,
    ProvinceOldStandardSQLServerClient
)


def clear_2026_province_statistics():
    """清空2026年所有省级统计数据（新标准和旧标准）"""
    print("\n" + "="*80)
    print("步骤1：清空2026年省级统计数据")
    print("="*80)

    # 清空新标准表
    print("  清空新标准表...")
    sql_client = ProvinceSQLServerClient()
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        delete_sql = """
        DELETE FROM province_statistics_new_standard
        WHERE stat_date LIKE '2026%'
        """
        cursor.execute(delete_sql)
        deleted_count_new = cursor.rowcount

        conn.commit()
        print(f"    新标准表：已删除 {deleted_count_new} 条记录")

    except Exception as e:
        conn.rollback()
        print(f"\n清空新标准表失败: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

    # 清空旧标准表
    print("  清空旧标准表...")
    old_sql_client = ProvinceOldStandardSQLServerClient()
    conn = pyodbc.connect(old_sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        delete_sql = """
        DELETE FROM province_statistics_old_standard
        WHERE stat_date LIKE '2026%'
        """
        cursor.execute(delete_sql)
        deleted_count_old = cursor.rowcount

        conn.commit()
        print(f"    旧标准表：已删除 {deleted_count_old} 条记录")

    except Exception as e:
        conn.rollback()
        print(f"\n清空旧标准表失败: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

    print(f"  总计：已删除 {deleted_count_new + deleted_count_old} 条记录")


async def calculate_ytd_to_month(year: int, end_month: int):
    """
    计算年初到各月累计统计（ytd_to_month）

    例如4月份时，计算：
    - 1月累计（stat_date='2026-01'）
    - 1-2月累计（stat_date='2026-02'）
    - 1-3月累计（stat_date='2026-03'）
    """
    fetcher = ProvinceStatisticsFetcher()

    print(f"\n  计算年初到各月累计（1月至{end_month}月）...")

    for month in range(1, end_month + 1):
        stat_date = f"{year}-{month:02d}"
        start_date = f"{year}-01-01"

        if month == 12:
            end_date = f"{year}-12-31"
        else:
            first_day_next_month = date(year, month + 1, 1)
            last_day_of_month = first_day_next_month - timedelta(days=1)
            end_date = last_day_of_month.strftime('%Y-%m-%d')

        print(f"    计算 {stat_date}（{start_date} 至 {end_date}）")

        city_data = fetcher.sql_client.query_all_city_data(start_date, end_date)
        province_groups, warnings = fetcher._group_by_province_enhanced(city_data)

        statistics = []
        for province, cities in province_groups.items():
            from app.fetchers.city_statistics.province_statistics_fetcher import calculate_province_statistics
            stat = calculate_province_statistics(cities)
            if stat:
                stat['province_name'] = province
                statistics.append(stat)

        from app.fetchers.city_statistics.province_statistics_fetcher import calculate_province_rankings, validate_province_statistics
        statistics = calculate_province_rankings(statistics)
        statistics, validation_warnings = validate_province_statistics(city_data, statistics, stat_date)

        fetcher.sql_client.insert_province_statistics(statistics, 'ytd_to_month', stat_date)

    print(f"  完成：已计算 {end_month} 个ytd_to_month记录")


async def calculate_current_month(year: int, month: int):
    """计算当月累计统计（month_current）"""
    fetcher = ProvinceStatisticsFetcher()

    year_month = f"{year}-{month:02d}"
    start_date = f"{year_month}-01"

    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    calc_date = last_day

    print(f"\n  计算当月累计：{year_month}（截至 {calc_date}）")
    await fetcher._calculate_and_store_current_month(calc_date)


async def convert_to_monthly(year: int, month: int):
    """将当月累计转换为完整月统计（month_complete）"""
    fetcher = ProvinceStatisticsFetcher()

    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)

    print(f"  转换为完整月统计：{year}-{month:02d}")
    await fetcher._convert_current_to_monthly(next_month)


async def calculate_year_to_date(year: int, month: int, day: int):
    """计算年初至今累计统计（year_to_date）"""
    fetcher = ProvinceStatisticsFetcher()
    calc_date = date(year, month, day)

    print(f"\n  计算年初至今累计：截至 {calc_date}")
    await fetcher._calculate_and_store_annual_ytd(calc_date)


def verify_results(end_month: int):
    """验证新标准计算结果"""
    print("\n" + "="*80)
    print("验证新标准计算结果")
    print("="*80)

    sql_client = ProvinceSQLServerClient()
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        print(f"\n省级统计汇总（2026年1-{end_month}月）：")
        print("-" * 80)

        check_sql = """
        SELECT stat_type, COUNT(*) as total_records,
               COUNT(DISTINCT stat_date) as date_count,
               AVG(city_count) as avg_cities,
               MIN(city_count) as min_cities,
               MAX(city_count) as max_cities
        FROM province_statistics_new_standard
        WHERE stat_date LIKE '2026%'
        GROUP BY stat_type
        ORDER BY stat_type
        """
        cursor.execute(check_sql)

        rows = cursor.fetchall()
        if not rows:
            print("  未找到2026年数据")
            return

        for row in rows:
            print(f"  {row.stat_type:20} | {row.total_records:4} 条记录 | "
                  f"{row.date_count:3} 个日期 | 平均{row.avg_cities:.1f}城市 "
                  f"(范围:{row.min_cities:.0f}-{row.max_cities:.0f})")

        print(f"\n各月份数据详情（2026年1-{end_month}月）：")
        print("-" * 80)

        cursor.execute("""
            SELECT stat_date, stat_type, COUNT(*) as count,
                   AVG(city_count) as avg_cities
            FROM province_statistics_new_standard
            WHERE stat_date LIKE '2026%'
            GROUP BY stat_date, stat_type
            ORDER BY stat_date, stat_type
        """)

        rows = cursor.fetchall()
        for row in rows:
            print(f"  {row.stat_date:12} | {row.stat_type:20} | {row.count:3} 省份 | "
                  f"平均{row.avg_cities:.1f}城市")

        # 显示最近一个月的城市数量
        latest_month = f"2026-{end_month:02d}"
        print(f"\n各省份城市数量（{latest_month} month_complete）：")
        print("-" * 80)

        cursor.execute(f"""
            SELECT province_name, city_count, city_names
            FROM province_statistics_new_standard
            WHERE stat_date = '{latest_month}' AND stat_type = 'month_complete'
            ORDER BY city_count DESC, province_name
        """)

        rows = cursor.fetchall()
        for row in rows:
            print(f"  {row.province_name:10} | {row.city_count:3} 个城市")

        print("\n重要提示：")
        print("  - 云南省数据只包含8个地级市（昆明、曲靖、玉溪等）")
        print("  - 8个自治州数据未包含（已临时关闭第4类查询）")

    finally:
        cursor.close()
        conn.close()


def verify_old_standard_results(end_month: int):
    """验证旧标准计算结果"""
    print("\n" + "="*80)
    print("验证旧标准计算结果")
    print("="*80)

    sql_client = ProvinceOldStandardSQLServerClient()
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        print(f"\n旧标准省级统计汇总（2026年1-{end_month}月）：")
        print("-" * 80)

        check_sql = """
        SELECT stat_type, COUNT(*) as total_records,
               COUNT(DISTINCT stat_date) as date_count,
               AVG(city_count) as avg_cities,
               MIN(city_count) as min_cities,
               MAX(city_count) as max_cities
        FROM province_statistics_old_standard
        WHERE stat_date LIKE '2026%'
        GROUP BY stat_type
        ORDER BY stat_type
        """
        cursor.execute(check_sql)

        rows = cursor.fetchall()
        if not rows:
            print("  未找到2026年旧标准数据")
            return

        for row in rows:
            print(f"  {row.stat_type:20} | {row.total_records:4} 条记录 | "
                  f"{row.date_count:3} 个日期 | 平均{row.avg_cities:.1f}城市 "
                  f"(范围:{row.min_cities:.0f}-{row.max_cities:.0f})")

        # 显示达标率字段
        print(f"\n达标率字段示例（2026-{end_month:02d} month_complete）：")
        print("-" * 80)

        cursor.execute(f"""
            SELECT TOP 5
                province_name,
                pm2_5_concentration,
                exceed_days,
                valid_days,
                compliance_rate,
                exceed_rate
            FROM province_statistics_old_standard
            WHERE stat_date = '2026-{end_month:02d}' AND stat_type = 'monthly'
            ORDER BY compliance_rate DESC
        """)

        rows = cursor.fetchall()
        for row in rows:
            print(f"  {row.province_name:10} | PM2.5: {row.pm2_5_concentration:6.1f} μg/m³ | "
                  f"超标: {row.exceed_days:3}天 / 有效: {row.valid_days:3}天 | "
                  f"达标率: {row.compliance_rate:5.1f}%")

    finally:
        cursor.close()
        conn.close()


async def main():
    """主函数"""
    # 获取要计算的月份（默认当前月份）
    today = datetime.now()
    default_month = today.month if today.year == 2026 else 4
    end_month = int(sys.argv[1]) if len(sys.argv) > 1 else default_month
    end_month = max(1, min(12, end_month))

    print("="*80)
    print("重新计算2026年省级统计数据（完整版）")
    print("="*80)
    print(f"\n计算范围：2026年1月至{end_month}月")
    print("数据类型：ytd_to_month, month_current, month_complete, year_to_date")
    print("\n重要说明：")
    print("  - 只使用主查询（第2、3、4类查询已临时关闭）")
    print("  - 云南省只包含8个地级市，不包含8个自治州")
    print("  - 修约规则：日修约→统计修约，新标准保留1位，旧标准取整")

    try:
        # ========== 新标准计算 ==========
        print("\n" + "="*80)
        print("【新标准计算】")
        print("="*80)

        clear_2026_province_statistics()

        print("\n步骤2：计算ytd_to_month（年初到各月累计）")
        await calculate_ytd_to_month(2026, end_month)

        print("\n步骤3：计算month_current和month_complete")
        for month in range(1, end_month + 1):
            print(f"\n--- 处理 2026-{month:02d} ---")
            await calculate_current_month(2026, month)
            await convert_to_monthly(2026, month)

        print("\n步骤4：计算year_to_date（年初至今累计）")
        if end_month == 12:
            last_day = date(2026, 12, 31)
        else:
            last_day = date(2026, end_month + 1, 1) - timedelta(days=1)

        await calculate_year_to_date(2026, last_day.month, last_day.day)

        # ========== 旧标准计算 ==========
        print("\n" + "="*80)
        print("【旧标准计算】")
        print("="*80)

        old_fetcher = ProvinceStatisticsOldStandardFetcher()

        print("\n步骤5：计算旧标准省级统计数据...")
        await old_fetcher.fetch_and_store()

        # ========== 验证结果 ==========
        print("\n" + "="*80)
        print("【验证结果】")
        print("="*80)

        verify_results(end_month)
        verify_old_standard_results(end_month)

        print("\n" + "="*80)
        print("重新计算完成！")
        print("="*80)
        print(f"\n已重新计算2026年1-{end_month}月的省级统计数据")
        print("  - 新标准：province_statistics_new_standard")
        print("  - 旧标准：province_statistics_old_standard")
        print("  - 达标率字段：exceed_days, valid_days, compliance_rate, exceed_rate")

    except Exception as e:
        print(f"\n执行失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
