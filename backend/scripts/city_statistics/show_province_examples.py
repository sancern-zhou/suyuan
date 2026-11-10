"""
省级统计数据查询示例

展示一些常用的查询示例
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient


def show_examples():
    """展示查询示例"""
    client = ProvinceSQLServerClient()

    if not client.test_connection():
        print("数据库连接失败")
        return

    import pyodbc
    conn = pyodbc.connect(client.connection_string, timeout=30)
    cursor = conn.cursor()

    print("="*100)
    print("省级空气质量统计数据查询示例")
    print("="*100)

    # 示例1：查询最新月份的省级排名（前10名）
    print("\n【示例1】2026年3月省级空气质量排名（前10名）")
    print("-"*100)

    sql = """
    SELECT TOP 10
        province_name AS 省份,
        pm2_5_concentration AS PM2_5,
        comprehensive_index AS 综合指数,
        comprehensive_index_rank AS 排名,
        city_count AS 城市数,
        sample_coverage AS 覆盖率
    FROM province_statistics
    WHERE stat_type = 'monthly' AND stat_date = '2026-03-01'
    ORDER BY comprehensive_index_rank
    """

    cursor.execute(sql)
    print(f"{'排名':<6}{'省份':<8}{'PM2.5(μg/m³)':<15}{'综合指数':<12}{'城市数':<8}{'覆盖率'}")
    print("-"*100)
    for row in cursor.fetchall():
        print(f"{row.排名:<6}{row.省份:<8}{row.PM2_5:<15}{row.综合指数:<12}{row.城市数:<8}{row.覆盖率}%")

    # 示例2：查询河北省的详细信息
    print("\n\n【示例2】河北省2026年3月详细信息")
    print("-"*100)

    sql = """
    SELECT
        province_name AS 省份,
        so2_concentration AS SO2,
        no2_concentration AS NO2,
        pm10_concentration AS PM10,
        pm2_5_concentration AS PM2_5,
        co_concentration AS CO,
        o3_8h_concentration AS O3_8h,
        comprehensive_index AS 综合指数,
        comprehensive_index_rank AS 排名,
        city_count AS 城市数,
        city_names AS 城市列表
    FROM province_statistics
    WHERE stat_type = 'monthly' AND stat_date = '2026-03-01' AND province_name = '河北'
    """

    cursor.execute(sql)
    row = cursor.fetchone()

    if row:
        print(f"省份: {row.省份}")
        print(f"排名: {row.排名}")
        print(f"城市数: {row.城市数}")
        print(f"\n污染物浓度:")
        print(f"  SO₂:  {row.SO2} μg/m³")
        print(f"  NO₂:  {row.NO2} μg/m³")
        print(f"  PM10: {row.PM10} μg/m³")
        print(f"  PM2.5: {row.PM2_5} μg/m³")
        print(f"  CO:   {row.CO} mg/m³")
        print(f"  O₃_8h: {row.O3_8h} μg/m³")
        print(f"\n综合指数: {row.综合指数}")
        print(f"\n城市列表: {row.城市列表}")

    # 示例3：查询广东省近3个月的趋势
    print("\n\n【示例3】广东省近3个月空气质量趋势")
    print("-"*100)

    sql = """
    SELECT
        stat_date AS 月份,
        pm2_5_concentration AS PM2_5,
        comprehensive_index AS 综合指数,
        comprehensive_index_rank AS 排名
    FROM province_statistics
    WHERE stat_type = 'monthly' AND province_name = '广东'
      AND stat_date >= '2026-01-01'
    ORDER BY stat_date
    """

    cursor.execute(sql)
    print(f"{'月份':<15}{'PM2.5(μg/m³)':<15}{'综合指数':<12}{'排名'}")
    print("-"*100)
    for row in cursor.fetchall():
        month_str = str(row.月份)[:7] if hasattr(row.月份, '__str__') else row.月份
        print(f"{month_str:<15}{row.PM2_5:<15}{row.综合指数:<12}{row.排名}")

    # 示例4：对比各省市的PM2.5浓度
    print("\n\n【示例4】各省PM2.5浓度对比（2026年3月）")
    print("-"*100)

    sql = """
    SELECT
        CASE
            WHEN comprehensive_index_rank <= 10 THEN '前10名'
            WHEN comprehensive_index_rank <= 20 THEN '中游'
            ELSE '后10名'
        END AS 分组,
        AVG(pm2_5_concentration) AS 平均PM2_5
    FROM province_statistics
    WHERE stat_type = 'monthly' AND stat_date = '2026-03-01'
    GROUP BY CASE
        WHEN comprehensive_index_rank <= 10 THEN '前10名'
        WHEN comprehensive_index_rank <= 20 THEN '中游'
        ELSE '后10名'
    END
    ORDER BY
        CASE
            WHEN 分组 = '前10名' THEN 1
            WHEN 分组 = '中游' THEN 2
            ELSE 3
        END
    """

    cursor.execute(sql)
    print(f"{'分组':<15}{'平均PM2.5浓度(μg/m³)'}")
    print("-"*100)
    for row in cursor.fetchall():
        print(f"{row.分组:<15}{row.平均PM2_5}")

    cursor.close()
    conn.close()

    print("\n" + "="*100)
    print("查询示例展示完成！")
    print("="*100)


if __name__ == "__main__":
    show_examples()
