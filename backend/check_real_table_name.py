"""
检查实际的空气质量历史表名称
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
            AND (tablename LIKE '%air_quality%'
                 OR tablename LIKE '%aqi%'
                 OR tablename LIKE '%city%')
            ORDER BY tablename;
        """)
        result = await session.execute(query)
        tables = [row[0] for row in result.all()]

        print("空气质量相关的表:")
        for table in tables:
            print(f"  - {table}")

        # 检查每个表的记录数
        for table in tables:
            try:
                count_query = text(f"SELECT COUNT(*) FROM {table}")
                count_result = await session.execute(count_query)
                count = count_result.scalar()
                print(f"  {table}: {count} 条记录")
            except Exception as e:
                print(f"  {table}: 查询失败 - {e}")


if __name__ == "__main__":
    asyncio.run(check_table_names())
