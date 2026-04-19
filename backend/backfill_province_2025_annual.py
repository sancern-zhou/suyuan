"""
补充2025年省级统计数据（annual_ytd）

功能：为2025年补充年度累计统计（annual_ytd）
作者：Claude Code
日期：2026-04-17
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.fetchers.city_statistics.province_statistics_fetcher import (
    ProvinceStatisticsFetcher,
    ProvinceSQLServerClient
)
import structlog

logger = structlog.get_logger()


def backfill_2025_annual_ytd():
    """补充2025年的annual_ytd数据"""

    print("=" * 60)
    print("开始补充2025年省级统计数据（annual_ytd）")
    print("=" * 60)
    print()

    fetcher = ProvinceStatisticsFetcher()
    sql_client = ProvinceSQLServerClient()

    # 2025年全年数据
    year = 2025
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    print(f"查询时间范围：{start_date} 至 {end_date}")
    print()

    try:
        # 步骤1：查询2025年全年的数据
        print("步骤1：查询2025年全年数据...")
        city_data = sql_client.query_all_city_data(start_date, end_date)
        total_cities = len(city_data)
        total_records = sum(len(records) for records in city_data.values())

        print(f"  - 城市（地级市）数量：{total_cities}")
        print(f"  - 总记录数：{total_records}")
        print()

        # 步骤2：按省份分组
        print("步骤2：按省份分组...")
        province_groups, grouping_warnings = fetcher._group_by_province_enhanced(city_data)

        print(f"  - 省份数量：{len(province_groups)}")
        print(f"  - 分组警告：{len(grouping_warnings)}")
        if grouping_warnings:
            for warning in grouping_warnings[:5]:
                print(f"    警告：{warning}")
        print()

        # 步骤3：计算统计指标
        print("步骤3：计算省级统计指标...")
        from app.fetchers.city_statistics.province_statistics_fetcher import (
            calculate_province_statistics,
            calculate_province_rankings
        )

        statistics = []
        for province, cities in province_groups.items():
            stat = calculate_province_statistics(cities)

            if stat:
                stat['province_name'] = province
                statistics.append(stat)

        print(f"  - 成功计算的省份数量：{len(statistics)}")
        print()

        # 步骤4：计算排名
        print("步骤4：计算省份排名...")
        statistics = calculate_province_rankings(statistics)
        print(f"  - 排名计算完成")
        print()

        # 步骤5：数据验证
        print("步骤5：数据验证...")
        from app.fetchers.city_statistics.province_statistics_fetcher import (
            validate_province_statistics
        )

        stat_date = str(year)  # 格式：2025（年，表示年初至今）
        statistics, validation_warnings = validate_province_statistics(
            city_data, statistics, stat_date
        )

        print(f"  - 验证警告数量：{len(validation_warnings)}")
        if validation_warnings:
            print("  - 前5个警告：")
            for warning in validation_warnings[:5]:
                print(f"    {warning}")
        print()

        # 步骤6：存储数据库
        print("步骤6：存储到数据库...")
        sql_client.insert_province_statistics(statistics, 'annual_ytd', stat_date)
        print(f"  - 已插入{len(statistics)}条记录")
        print()

        # 步骤7：验证结果
        print("步骤7：验证插入结果...")
        import pyodbc
        conn = pyodbc.connect(sql_client.connection_string, timeout=30)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) as count
            FROM province_statistics_new_standard
            WHERE stat_type = 'annual_ytd' AND stat_date = ?
        """, [stat_date])

        count = cursor.fetchone().count
        print(f"  - 数据库中2025年annual_ytd记录数：{count}条")

        # 显示部分数据示例
        cursor.execute("""
            SELECT TOP 5 province_name, comprehensive_index, comprehensive_index_rank,
                   pm2_5_concentration, city_count
            FROM province_statistics_new_standard
            WHERE stat_type = 'annual_ytd' AND stat_date = ?
            ORDER BY comprehensive_index
        """, [stat_date])

        print()
        print("  - 综合指数排名前5的省份：")
        for i, row in enumerate(cursor, 1):
            print(f"    {i}. {row.province_name}: "
                  f"综合指数={row.comprehensive_index:.3f}, "
                  f"PM2.5={row.pm2_5_concentration:.1f}, "
                  f"城市数={row.city_count}")

        cursor.close()
        conn.close()

        print()
        print("=" * 60)
        print("2025年省级统计数据（annual_ytd）补充完成！")
        print("=" * 60)
        return True

    except Exception as e:
        logger.error(
            "backfill_2025_annual_ytd_failed",
            error=str(e),
            exc_info=True
        )
        print(f"\n错误：{str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = backfill_2025_annual_ytd()
    sys.exit(0 if success else 1)
