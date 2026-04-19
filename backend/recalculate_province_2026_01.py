"""
重新计算2026年1月份省级统计数据

修复内容：
1. 使用全省所有城市（而不是仅168城市）
2. 验证计算结果准确性

作者：Claude Code
版本：2.0.0
日期：2026-04-17
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceStatisticsFetcher
import structlog

logger = structlog.get_logger()


async def recalculate_january_2026():
    """重新计算2026年1月份的省级统计数据"""

    print("="*100)
    print("重新计算2026年1月份省级统计数据")
    print("="*100)

    # 创建抓取器实例
    fetcher = ProvinceStatisticsFetcher()

    # 模拟2026年2月1日（将1月current_month转换为monthly）
    today = datetime(2026, 2, 1).date()

    print(f"\n模拟日期：{today.isoformat()}")
    print(f"目标：重新计算2026年1月份的省级统计\n")

    try:
        # 步骤1：将2026年1月的current_month转换为monthly
        print("步骤1：将2026年1月的current_month转换为monthly")
        print("-"*100)
        await fetcher._convert_current_to_monthly(today)
        print("✓ 转换完成\n")

        # 步骤2：重新计算2026年1月的current_month数据（覆盖现有数据）
        print("步骤2：重新计算2026年1月的current_month数据")
        print("-"*100)
        await fetcher._calculate_and_store_current_month(today)
        print("✓ current_month计算完成\n")

        # 步骤3：重新计算2026年度累计数据（截至1月31日）
        print("步骤3：重新计算2026年度累计数据（截至1月31日）")
        print("-"*100)
        await fetcher._calculate_and_store_annual_ytd(today)
        print("✓ annual_ytd计算完成\n")

        print("="*100)
        print("重新计算完成！")
        print("="*100)

        # 验证结果
        await verify_results()

    except Exception as e:
        print(f"\n✗ 计算失败：{e}")
        import traceback
        traceback.print_exc()
        raise


async def verify_results():
    """验证计算结果"""

    print("\n" + "="*100)
    print("验证计算结果")
    print("="*100)

    import pyodbc

    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=180.184.30.94,1433;"
        "DATABASE=XcAiDb;"
        "UID=sa;"
        "PWD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR;"
        "TrustServerCertificate=yes"
    )

    try:
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        # 查询2026年1月的省级统计结果
        sql = """
        SELECT
            stat_type,
            province_name,
            pm2_5_concentration,
            city_count,
            data_days,
            sample_coverage
        FROM province_statistics_new_standard
        WHERE stat_date = '2026-01-01'
        ORDER BY stat_type, pm2_5_concentration DESC
        """

        cursor.execute(sql)
        rows = cursor.fetchall()

        # 按统计类型分组
        monthly_data = []
        current_month_data = []
        annual_ytd_data = []

        for row in rows:
            if row.stat_type == 'monthly':
                monthly_data.append(row)
            elif row.stat_type == 'current_month':
                current_month_data.append(row)
            elif row.stat_type == 'annual_ytd':
                annual_ytd_data.append(row)

        # 显示monthly数据
        print("\n1. 月度统计（monthly）- 2026年1月完整月")
        print("-"*100)
        if monthly_data:
            print(f"{'省份':10s} {'PM2.5均值':>12s} {'城市数':>8s} {'数据天数':>10s} {'样本覆盖率':>12s}")
            print("-"*100)
            for row in monthly_data[:10]:  # 显示前10个
                print(f"{row.province_name:10s} {row.pm2_5_concentration:12.2f} {row.city_count:8d} {row.data_days:10d} {row.sample_coverage:12.1f}%")
            if len(monthly_data) > 10:
                print(f"... 还有 {len(monthly_data)-10} 个省份")
            print(f"总计：{len(monthly_data)} 个省份")
        else:
            print("无数据")

        # 显示current_month数据
        print("\n2. 当月累计（current_month）- 2026年1月1日至1月31日")
        print("-"*100)
        if current_month_data:
            print(f"{'省份':10s} {'PM2.5均值':>12s} {'城市数':>8s} {'数据天数':>10s} {'样本覆盖率':>12s}")
            print("-"*100)
            for row in current_month_data[:10]:  # 显示前10个
                print(f"{row.province_name:10s} {row.pm2_5_concentration:12.2f} {row.city_count:8d} {row.data_days:10d} {row.sample_coverage:12.1f}%")
            if len(current_month_data) > 10:
                print(f"... 还有 {len(current_month_data)-10} 个省份")
            print(f"总计：{len(current_month_data)} 个省份")
        else:
            print("无数据")

        # 显示annual_ytd数据
        print("\n3. 年度累计（annual_ytd）- 2026年1月1日至1月31日")
        print("-"*100)
        if annual_ytd_data:
            print(f"{'省份':10s} {'PM2.5均值':>12s} {'城市数':>8s} {'数据天数':>10s} {'样本覆盖率':>12s}")
            print("-"*100)
            for row in annual_ytd_data[:10]:  # 显示前10个
                print(f"{row.province_name:10s} {row.pm2_5_concentration:12.2f} {row.city_count:8d} {row.data_days:10d} {row.sample_coverage:12.1f}%")
            if len(annual_ytd_data) > 10:
                print(f"... 还有 {len(annual_ytd_data)-10} 个省份")
            print(f"总计：{len(annual_ytd_data)} 个省份")
        else:
            print("无数据")

        # 详细检查广东和新疆
        print("\n" + "="*100)
        print("重点省份验证（广东、新疆）")
        print("="*100)

        for province in ['广东', '新疆']:
            sql_detail = """
            SELECT
                stat_type,
                pm2_5_concentration,
                city_count,
                data_days,
                city_names
            FROM province_statistics_new_standard
            WHERE province_name = ?
              AND stat_date = '2026-01-01'
            """

            cursor.execute(sql_detail, [province])
            rows_detail = cursor.fetchall()

            print(f"\n{province}省：")
            for row in rows_detail:
                print(f"  {row.stat_type}:")
                print(f"    PM2.5均值: {row.pm2_5_concentration} μg/m³")
                print(f"    城市数量: {row.city_count}")
                print(f"    数据天数: {row.data_days}")
                print(f"    城市列表: {row.city_names}")

                # 验证数据天数
                if row.stat_type == 'monthly':
                    expected_days = row.city_count * 31  # 1月有31天
                    if row.data_days == expected_days:
                        print(f"    ✓ 数据天数正确：{row.city_count}个城市 × 31天 = {expected_days}")
                    else:
                        print(f"    ✗ 数据天数异常：预期{expected_days}，实际{row.data_days}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"\n✗ 验证失败：{e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    print("\n开始重新计算...")
    asyncio.run(recalculate_january_2026())
    print("\n完成！")


if __name__ == "__main__":
    main()
