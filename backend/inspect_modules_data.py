"""检查 modules_data 的实际 JSON 结构"""
import asyncio
import aioodbc
import json
from config.settings import settings

async def inspect_modules_data():
    conn = await aioodbc.connect(dsn=settings.sqlserver_connection_string)
    cursor = await conn.cursor()

    # 获取最新一条记录的 modules_data
    await cursor.execute('''
        SELECT TOP 1
            session_id,
            query_text,
            modules_data
        FROM analysis_history
        ORDER BY created_at DESC
    ''')

    row = await cursor.fetchone()

    if row:
        session_id = row[0]
        query_text = row[1]
        modules_data_json = row[2]

        print(f'\n=== 最新历史记录 ===')
        print(f'Session ID: {session_id}')
        print(f'Query: {query_text}')
        print(f'\n=== modules_data 原始 JSON (前 500 字符) ===')
        print(modules_data_json[:500] if modules_data_json else 'NULL')

        if modules_data_json:
            try:
                # 解析 JSON
                data = json.loads(modules_data_json)

                print(f'\n=== modules_data 结构分析 ===')
                print(f'顶层键: {list(data.keys())}')

                # 检查 weather_analysis 字段
                if 'weather_analysis' in data:
                    weather = data['weather_analysis']
                    print(f'\n=== weather_analysis 类型 ===')
                    print(f'Type: {type(weather).__name__}')

                    if isinstance(weather, dict):
                        print(f'Keys: {list(weather.keys())}')
                        print(f'\n=== weather_analysis.content 类型 ===')
                        content = weather.get('content')
                        print(f'Type: {type(content).__name__}')
                        print(f'Content preview: {str(content)[:200]}...')

                        if 'visuals' in weather:
                            visuals = weather['visuals']
                            print(f'\n=== visuals ===')
                            print(f'Type: {type(visuals).__name__}')
                            print(f'Count: {len(visuals) if isinstance(visuals, list) else "N/A"}')
                            if isinstance(visuals, list) and len(visuals) > 0:
                                print(f'First visual keys: {list(visuals[0].keys())}')

            except json.JSONDecodeError as e:
                print(f'\n❌ JSON 解析失败: {e}')
    else:
        print('未找到历史记录')

    await cursor.close()
    await conn.close()

if __name__ == "__main__":
    asyncio.run(inspect_modules_data())
