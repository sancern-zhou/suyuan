#!/bin/bash
# 更新2025年所有统计数据

cd /home/xckj/suyuan/backend

echo "=========================================="
echo "开始更新2025年统计数据"
echo "=========================================="

# 清除2025年数据
echo ""
echo "[1/2] 清除2025年旧数据..."
python -c "
import sys
import pyodbc
sys.path.insert(0, '.')
from app.fetchers.city_statistics.city_statistics_fetcher import SQLServerClient

sql_client = SQLServerClient()
conn = pyodbc.connect(sql_client.connection_string, timeout=30)
cursor = conn.cursor()

# 清除城市统计2025年数据
cursor.execute(\"DELETE FROM city_168_statistics_new_standard WHERE stat_date LIKE '2025%'\")
city_deleted = cursor.rowcount
print(f'  ✓ 城市统计已删除: {city_deleted} 条')

# 清除省级统计2025年数据
cursor.execute(\"DELETE FROM province_statistics_new_standard WHERE stat_date LIKE '2025%'\")
province_deleted = cursor.rowcount
print(f'  ✓ 省级统计已删除: {province_deleted} 条')

conn.commit()
cursor.close()
conn.close()
"

# 重新计算2025年数据
echo ""
echo "[2/2] 重新计算2025年数据..."
python -c "
import asyncio
import sys
from datetime import date
sys.path.insert(0, '.')
from manual_update_2026_statistics import update_specific_months

async def update_2025():
    # 模拟用户输入
    import io
    sys.stdin = io.StringIO('2025\\ny\\n')
    await update_specific_months()

asyncio.run(update_2025())
"

echo ""
echo "=========================================="
echo "2025年数据更新完成！"
echo "=========================================="
