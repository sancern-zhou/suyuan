"""
检查city_aqi_publish_history表的实际结构
"""
import asyncio
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.db.database import async_session
from sqlalchemy import text


async def check_table_structure():
    """检查表结构"""
    async with async_session() as session:
        # 查询表结构
        query = text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'city_aqi_publish_history'
            ORDER BY ordinal_position;
        """)
        result = await session.execute(query)
        columns = result.all()

        print("city_aqi_publish_history 表结构:")
        print("-" * 50)
        for col in columns:
            print(f"  {col[0]:<25} {col[1]:<20} {col[2]}")

        # 查询示例数据
        sample_query = text("""
            SELECT * FROM city_aqi_publish_history
            LIMIT 3;
        """)
        sample_result = await session.execute(sample_query)
        samples = sample_result.all()

        print("\n示例数据:")
        print("-" * 50)
        for sample in samples:
            print(f"  {dict(sample._asdict())}")


if __name__ == "__main__":
    asyncio.run(check_table_structure())
