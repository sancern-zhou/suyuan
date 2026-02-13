"""
检查数据库中实际的空气质量表名
"""
import asyncio
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.db.database import async_session
from sqlalchemy import text


async def check_table_names():
    """检查所有空气质量相关的表"""
    async with async_session() as session:
        # 查询所有表名
        query = text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename LIKE '%air_quality%'
            OR tablename LIKE '%city%'
            OR tablename LIKE '%aqi%'
            ORDER BY tablename;
        """)
        result = await session.execute(query)
        tables = [row[0] for row in result.all()]

        print("空气质量相关的表:")
        for table in tables:
            print(f"  - {table}")

        # 检查每个表的记录数
        for table in tables:
            count_query = text(f"SELECT COUNT(*) FROM {table}")
            count_result = await session.execute(count_query)
            count = count_result.scalar()
            print(f"\n{table}: {count} 条记录")

            # 如果是 AirQuality_Beijing，显示几条示例数据
            if 'Beijing' in table or 'beijing' in table:
                sample_query = text(f"SELECT * FROM {table} LIMIT 3")
                sample_result = await session.execute(sample_query)
                samples = sample_result.all()
                print(f"  示例数据:")
                for sample in samples:
                    print(f"    {dict(sample._asdict())}")


async def main():
    await check_table_names()


if __name__ == "__main__":
    asyncio.run(main())
