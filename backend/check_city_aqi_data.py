"""
检查city_aqi_publish_history表的数据情况
"""
import asyncio
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.db.database import async_session
from sqlalchemy import text


async def check_data():
    """检查数据"""
    async with async_session() as session:
        # 检查总记录数
        count_query = text("SELECT COUNT(*) FROM city_aqi_publish_history")
        count_result = await session.execute(count_query)
        total_count = count_result.scalar()
        print(f"city_aqi_publish_history 总记录数: {total_count}")

        if total_count > 0:
            # 检查所有城市
            cities_query = text("""
                SELECT area, COUNT(*) as cnt
                FROM city_aqi_publish_history
                GROUP BY area
                ORDER BY cnt DESC
            """)
            cities_result = await session.execute(cities_query)
            cities = cities_result.all()

            print(f"\n所有城市 (共{len(cities)}个):")
            for city, cnt in cities:
                print(f"  {city}: {cnt} 条记录")

            # 检查最新数据时间
            latest_query = text("""
                SELECT MAX(time_point) as latest_time, MIN(time_point) as earliest_time
                FROM city_aqi_publish_history
            """)
            latest_result = await session.execute(latest_query)
            latest = latest_result.fetchone()

            print(f"\n数据时间范围:")
            print(f"  最早: {latest[1]}")
            print(f"  最新: {latest[0]}")

            # 检查最新几条数据
            sample_query = text("""
                SELECT time_point, area, aqi, pm2_5, pm10, o3, no2, so2, co
                FROM city_aqi_publish_history
                ORDER BY time_point DESC
                LIMIT 10
            """)
            sample_result = await session.execute(sample_query)
            samples = sample_result.all()

            print(f"\n最新10条数据:")
            for s in samples:
                print(f"  {s[0]} - {s[1]} - AQI:{s[2]} PM2.5:{s[3]}")
        else:
            print("\n表为空，没有数据。")


if __name__ == "__main__":
    asyncio.run(check_data())
