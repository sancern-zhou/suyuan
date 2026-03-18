"""
检查air_quality_hourly表中济宁相关的数据
"""
import asyncio
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.db.database import async_session
from sqlalchemy import text


async def check_jining():
    """检查济宁相关数据"""
    async with async_session() as session:
        # 查看所有站点ID
        sites_query = text("""
            SELECT DISTINCT site_id, COUNT(*) as cnt
            FROM air_quality_hourly
            GROUP BY site_id
            ORDER BY cnt DESC
            LIMIT 30;
        """)
        sites_result = await session.execute(sites_query)
        sites = sites_result.all()

        print(f"站点列表 (共{len(sites)}个):")
        for site, cnt in sites:
            if '济宁' in site or 'jining' in site.lower():
                print(f"  * {site}: {cnt} 条记录")
            else:
                print(f"    {site}: {cnt} 条记录")

        # 查看最新数据时间
        time_query = text("""
            SELECT MAX(forecast_time) as latest, MIN(forecast_time) as earliest
            FROM air_quality_hourly
        """)
        time_result = await session.execute(time_query)
        time_range = time_result.fetchone()

        print(f"\n数据时间范围:")
        print(f"  最早: {time_range[1]}")
        print(f"  最新: {time_range[0]}")

        # 查看包含济宁的站点数据
        jining_query = text("""
            SELECT * FROM air_quality_hourly
            WHERE site_id LIKE '%济宁%'
            ORDER BY forecast_time DESC
            LIMIT 5;
        """)
        jining_result = await session.execute(jining_query)
        jining_data = jining_result.all()

        print(f"\n济宁站点最新5条数据:")
        for row in jining_data:
            d = dict(row._asdict())
            print(f"  站点: {d['site_id']}")
            print(f"  时间: {d['forecast_time']}")
            print(f"  AQI: {d['aqi']}, PM2.5: {d['pm25']}")
            print()


if __name__ == "__main__":
    asyncio.run(check_jining())
