"""
将2026年1月的current_month数据转换为monthly

作者：Claude Code
版本：1.0.0
日期：2026-04-17
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceStatisticsFetcher


async def convert_january_to_monthly():
    """将2026年1月的current_month数据转换为monthly"""

    print("="*100)
    print("将2026年1月的current_month数据转换为monthly")
    print("="*100)

    # 创建抓取器实例
    fetcher = ProvinceStatisticsFetcher()

    # 模拟2026年2月1日（将1月current_month转换为monthly）
    today = datetime(2026, 2, 1).date()

    print(f"\n模拟日期：{today.isoformat()}")
    print(f"目标：将2026年1月的current_month转换为monthly\n")

    try:
        # 执行转换
        await fetcher._convert_current_to_monthly(today)

        print("\n" + "="*100)
        print("转换完成！")
        print("="*100)

        # 验证结果
        await verify_conversion()

    except Exception as e:
        print(f"\n✗ 转换失败：{e}")
        import traceback
        traceback.print_exc()
        raise


async def verify_conversion():
    """验证转换结果"""

    print("\n" + "="*100)
    print("验证转换结果")
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

    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    # 查询广东省的数据
    sql = """
    SELECT
        stat_type,
        pm2_5_concentration,
        city_count,
        data_days
    FROM province_statistics_new_standard
    WHERE stat_date = '2026-01-01'
      AND province_name LIKE N'%广东%'
    ORDER BY stat_type
    """

    cursor.execute(sql)
    rows = cursor.fetchall()

    print("\n广东省 2026年1月数据（转换后）：")
    for row in rows:
        print(f"  {row.stat_type}: PM2.5={row.pm2_5_concentration} μg/m³, 城市={row.city_count}, 天数={row.data_days}")

    # 验证monthly数据是否已更新
    monthly_data = [row for row in rows if row.stat_type == 'monthly']

    if monthly_data:
        row = monthly_data[0]
        if row.city_count == 21:
            print("\n✓ monthly数据已更新：21个城市")
        else:
            print(f"\n✗ monthly数据未更新：仍为{row.city_count}个城市（应为21个）")
    else:
        print("\n✗ 未找到monthly数据")

    cursor.close()
    conn.close()


def main():
    """主函数"""
    print("\n开始转换...")
    asyncio.run(convert_january_to_monthly())
    print("\n完成！")


if __name__ == "__main__":
    main()
