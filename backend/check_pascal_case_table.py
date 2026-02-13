"""
检查是否存在PascalCase表名
"""
import asyncio
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.db.database import async_session
from sqlalchemy import text


async def check_exact_table():
    """精确检查表名"""
    async with async_session() as session:
        # 检查 CityAQIPublishHistory (PascalCase)
        try:
            query = text("""
                SELECT COUNT(*) FROM "CityAQIPublishHistory"
            """)
            result = await session.execute(query)
            count = result.scalar()
            print(f"CityAQIPublishHistory (PascalCase): {count} 条记录")

            # 查看表结构
            schema_query = text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'CityAQIPublishHistory'
                ORDER BY ordinal_position;
            """)
            schema_result = await session.execute(schema_query)
            columns = schema_result.all()

            print("\n表结构:")
            for col in columns:
                print(f"  {col[0]}: {col[1]}")

        except Exception as e:
            print(f"CityAQIPublishHistory 不存在或查询失败: {e}")

        # 检查 city_aqi_publish_history (snake_case)
        try:
            query = text("""
                SELECT COUNT(*) FROM city_aqi_publish_history
            """)
            result = await session.execute(query)
            count = result.scalar()
            print(f"\ncity_aqi_publish_history (snake_case): {count} 条记录")
        except Exception as e:
            print(f"city_aqi_publish_history 不存在或查询失败: {e}")


if __name__ == "__main__":
    asyncio.run(check_exact_table())
