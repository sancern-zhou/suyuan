"""
快速检查省级统计数据
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient
import pyodbc

client = ProvinceSQLServerClient()
conn = pyodbc.connect(client.connection_string, timeout=30)
cursor = conn.cursor()

print('='*100)
print('省级统计数据快速检查')
print('='*100)

# 1. 查看所有不同的日期
sql = 'SELECT DISTINCT stat_date FROM province_statistics ORDER BY stat_date'
cursor.execute(sql)
dates = [str(row.stat_date)[:10] for row in cursor.fetchall()]
print(f'\n【统计日期】共{len(dates)}个月')
print(f'最早: {dates[0]}')
print(f'最晚: {dates[-1]}')

# 2. 查看所有省份
sql = 'SELECT DISTINCT province_name FROM province_statistics ORDER BY province_name'
cursor.execute(sql)
provinces = [row.province_name for row in cursor.fetchall()]
print(f'\n【省份数量】{len(provinces)}个')

# 3. 查看2026年3月的前10名
print(f'\n【2026年3月排名前10】')
sql = '''
SELECT TOP 10 province_name, pm2_5_concentration, comprehensive_index, comprehensive_index_rank, city_count
FROM province_statistics
WHERE stat_date = '2026-03-01' AND stat_type = 'monthly'
ORDER BY comprehensive_index_rank
'''
cursor.execute(sql)
for row in cursor.fetchall():
    print(f"{row.comprehensive_index_rank:2d}. {row.province_name:<6} PM2.5={row.pm2_5_concentration:>6} μg/m³  综合指数={row.comprehensive_index}  城市={row.city_count}个")

# 4. 查看河北省数据
print(f'\n【河北省最近数据】')
sql = '''
SELECT TOP 6 stat_date, pm2_5_concentration, comprehensive_index, comprehensive_index_rank
FROM province_statistics
WHERE province_name = '河北' AND stat_type = 'monthly'
ORDER BY stat_date DESC
'''
cursor.execute(sql)
for row in cursor.fetchall():
    print(f"{str(row.stat_date)[:7]}: PM2.5={row.pm2_5_concentration:>6} μg/m³  综合指数={row.comprehensive_index}  排名={row.comprehensive_index_rank}")

# 5. 查看2026年3月河北省的city_names
print(f'\n【河北省2026年3月的城市列表】')
sql = '''
SELECT city_names, city_count
FROM province_statistics
WHERE stat_date = '2026-03-01' AND province_name = '河北'
'''
cursor.execute(sql)
row = cursor.fetchone()
if row:
    print(f"城市数量: {row.city_count}")
    print(f"城市列表: {row.city_names}")

print('\n' + '='*100)
cursor.close()
conn.close()
