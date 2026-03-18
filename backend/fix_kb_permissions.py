"""
将知识库类型从PRIVATE改为PUBLIC
"""
import asyncio
import sys
sys.path.insert(0, '.')

from sqlalchemy import update, text
from app.db.database import async_session

async def fix_kb_type():
    async with async_session() as db:
        # 将owner为anonymous的PRIVATE知识库改为PUBLIC
        result = await db.execute(
            text('''
                UPDATE knowledge_bases
                SET kb_type = 'PUBLIC'
                WHERE owner_id = 'anonymous'
                AND kb_type = 'PRIVATE'
            ''')
        )
        await db.commit()

        print(f'Updated {result.rowcount} knowledge bases from PRIVATE to PUBLIC')

        # 验证
        result = await db.execute(
            text('''
                SELECT id, name, kb_type, owner_id
                FROM knowledge_bases
                ORDER BY created_at DESC
            ''')
        )

        print('\\n=== Updated Knowledge Bases ===')
        for row in result.fetchall():
            print(f'{row[1][:30]} | {row[2]} | Owner: {row[3]}')

asyncio.run(fix_kb_type())
