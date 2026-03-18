"""
检查air_quality_hourly表的结构和数据
"""
import asyncio
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.db.database import async_session
from sqlalchemy import text


async def check_air_quality_hourly():
    """检查air_quality_hourly表"""
    async with async_session() as session:
        # 查看表结构
        schema_query = text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'air_quality_hourly'
            ORDER BY ordinal_position;
        """)
        schema_result = await session.execute(schema_query)
        columns = schema_result.all()

        print("air_quality_hourly 表结构:")
        for col in columns:
            print(f"  {col[0]}: {col[1]}")

        # 查看所有城市
        cities_query = text("""
            SELECT DISTINCT station_name, COUNT(*) as cnt
            FROM air_quality_hourly
            GROUP BY station_name
            ORDER BY cnt DESC
            LIMIT 20;
        """)
        cities_result = await session.execute(cities_query)
        cities = cities_result.all()

        print(f"\n城市列表 (共{len(cities)}个):")
        for city, cnt in cities:
            print(f"  {city}: {cnt} 条记录")

        # 查看最新数据
        latest_query = text("""
            SELECT * FROM air_quality_hourly
            ORDER BY time_point DESC
            LIMIT 3;
        """)
        latest_result = await session.execute(latest_query)
        latest = latest_result.all()

        print(f"\n最新3条数据:")
        for row in latest:
            print(f"  {dict(row._asdict())}")


if __name__ == "__main__":
    asyncio.run(check_air_quality_hourly())
