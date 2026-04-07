"""
对比工具和脚本的首要污染物统计差异
"""
import sys
sys.path.insert(0, '/home/xckj/suyuan/backend')

from app.services.gd_suncere_api_client import get_gd_suncere_api_client
import math
import csv

# 新标准（HJ 633-2024）断点
BREAKPOINTS_NEW = {
    'PM2_5': [(0, 35, 0, 50), (35, 75, 50, 100), (75, 115, 100, 150), (115, 150, 150, 200),
              (150, 250, 200, 300), (250, 350, 300, 400), (350, 500, 400, 500)],
    'PM10': [(0, 50, 0, 50), (50, 150, 50, 100), (150, 250, 100, 150), (250, 350, 150, 200),
             (350, 420, 200, 300), (420, 500, 300, 400), (500, 600, 400, 500)],
    'O3_8h': [(0, 100, 0, 50), (100, 160, 50, 100), (160, 215, 100, 150), (215, 265, 150, 200),
              (265, 800, 200, 300)],
    'NO2': [(0, 40, 0, 50), (40, 80, 50, 100), (80, 180, 100, 150), (180, 280, 150, 200),
            (280, 565, 200, 300), (565, 750, 300, 400), (750, 940, 400, 500)],
    'SO2': [(0, 50, 0, 50), (50, 150, 50, 100), (150, 475, 100, 150), (475, 800, 150, 200),
            (800, 1600, 200, 300), (1600, 2100, 300, 400), (2100, 2620, 400, 500)],
    'CO': [(0, 2, 0, 50), (2, 4, 50, 100), (4, 14, 100, 150), (14, 24, 150, 200),
           (24, 36, 200, 300), (36, 48, 300, 400), (48, 60, 400, 500)]
}

def calculate_iaqi_new(concentration, pollutant):
    if concentration <= 0:
        return 0
    breakpoints = BREAKPOINTS_NEW.get(pollutant, [])
    for bp_low, bp_high, iqi_low, iqi_high in breakpoints:
        if bp_low < concentration <= bp_high:
            ratio = (concentration - bp_low) / (bp_high - bp_low)
            iaqi = iqi_low + (iqi_high - iqi_low) * ratio
            return iaqi
    return 0

def safe_float(value, default=0.0):
    if value is None or value == '' or value == '-':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

# 读取扣沙数据
sand_data = {}
with open('/home/xckj/suyuan/backend/app/tools/query/query_new_standard_report/扣沙数据.csv', 'r', encoding='gbk') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row.get('name') == '韶关':
            timepoint = row.get('timepoint', '')
            date_parts = timepoint.split('/')
            if len(date_parts) >= 3:
                date_key = f"{date_parts[0]}-{date_parts[1].zfill(2)}-{date_parts[2].split()[0].zfill(2)}"
                sand_data[date_key] = {
                    'primary': row.get('primarypollutant', ''),
                    'aqi': row.get('aqi', ''),
                }

# 获取API数据
api_client = get_gd_suncere_api_client()
result = api_client.query_city_day_data(
    city_codes=['440200'],
    start_date='2025-03-01',
    end_date='2025-04-30',
    data_type=1
)

if isinstance(result, dict) and 'result' in result:
    data = result['result']
else:
    data = result if isinstance(result, list) else []

print("="*80)
print("分析韶关首要污染物统计差异")
print("="*80)
print()

# 统计首要污染物
primary_pollutant_days = {'PM2_5': 0, 'PM10': 0, 'SO2': 0, 'NO2': 0, 'CO': 0, 'O3_8h': 0}
all_days_detail = []

for record in data:
    timestamp = record.get('timePoint', '')
    date_only = timestamp[:10] if len(timestamp) >= 10 else timestamp

    # 检查是否扣沙日
    is_sand_day = date_only in sand_data

    if is_sand_day:
        # 扣沙日：使用扣沙表的首要污染物
        primary_from_sand = sand_data[date_only]['primary']

        if primary_from_sand and primary_from_sand not in ('—', '', None):
            import re
            sand_pollutants = re.split(r'[，,]', primary_from_sand)
            primary_pollutants_this_day = [p.strip() for p in sand_pollutants if p.strip()]

            for p in primary_pollutants_this_day:
                dict_key = p
                if p == 'PM2.5':
                    dict_key = 'PM2_5'
                elif p.upper() == 'O3_8H':
                    dict_key = 'O3_8h'

                if dict_key in primary_pollutant_days:
                    primary_pollutant_days[dict_key] += 1

        all_days_detail.append({
            'date': date_only,
            'type': '扣沙日',
            'primary': primary_from_sand if primary_from_sand else '无',
            'aqi': sand_data[date_only]['aqi']
        })
    else:
        # 非扣沙日：计算IAQI
        pm25 = safe_float(record.get('pM2_5', 0) or 0)
        pm10 = safe_float(record.get('pM10', 0) or 0)
        o3_8h = safe_float(record.get('o3_8H', 0) or 0)
        no2 = safe_float(record.get('nO2', 0) or 0)
        so2 = safe_float(record.get('sO2', 0) or 0)
        co = safe_float(record.get('co', 0) or 0)

        pm25_iaqi = 0 if is_sand_day else math.ceil(calculate_iaqi_new(pm25, 'PM2_5'))
        pm10_iaqi = 0 if is_sand_day else math.ceil(calculate_iaqi_new(pm10, 'PM10'))
        o3_8h_iaqi = math.ceil(calculate_iaqi_new(o3_8h, 'O3_8h'))
        no2_iaqi = math.ceil(calculate_iaqi_new(no2, 'NO2'))
        so2_iaqi = math.ceil(calculate_iaqi_new(so2, 'SO2'))
        co_iaqi = math.ceil(calculate_iaqi_new(co, 'CO'))

        aqi = max(pm25_iaqi, pm10_iaqi, o3_8h_iaqi, no2_iaqi, so2_iaqi, co_iaqi)

        # 找出首要污染物
        primaries_this_day = []
        if aqi > 50:
            for pollutant, iaqi in [('PM2_5', pm25_iaqi), ('PM10', pm10_iaqi), ('O3_8h', o3_8h_iaqi),
                                    ('NO2', no2_iaqi), ('SO2', so2_iaqi), ('CO', co_iaqi)]:
                if iaqi == aqi:
                    primary_pollutant_days[pollutant] += 1
                    primaries_this_day.append(pollutant)

        all_days_detail.append({
            'date': date_only,
            'type': '非扣沙日',
            'primary': ','.join(primaries_this_day) if primaries_this_day else '无',
            'aqi': aqi,
            'pm25_iaqi': pm25_iaqi,
            'pm10_iaqi': pm10_iaqi,
            'o3_8h_iaqi': o3_8h_iaqi
        })

print("首要污染物统计汇总:")
for pollutant, count in primary_pollutant_days.items():
    if count > 0:
        print(f"  {pollutant}: {count}天")

print(f"\n总计: {sum(primary_pollutant_days.values())}天")
print()

# 查找2025-04-11的详细情况
print("2025-04-11的详细情况:")
for day in all_days_detail:
    if day['date'] == '2025-04-11':
        print(f"  日期: {day['date']}")
        print(f"  类型: {day['type']}")
        print(f"  首要污染物: {day['primary']}")
        print(f"  AQI: {day['aqi']}")
        if 'pm25_iaqi' in day:
            print(f"  PM2.5_IAQI: {day['pm25_iaqi']}")
            print(f"  PM10_IAQI: {day['pm10_iaqi']}")
            print(f"  O3_8h_IAQI: {day['o3_8h_iaqi']}")

print("\n所有PM2.5作为首要污染物的日期:")
for day in all_days_detail:
    if 'PM2_5' in day['primary'] or 'PM2.5' in day['primary']:
        print(f"  {day['date']}: {day['primary']}, AQI={day['aqi']}")

print("\n所有PM10作为首要污染物的日期:")
for day in all_days_detail:
    if 'PM10' in day['primary']:
        print(f"  {day['date']}: {day['primary']}, AQI={day['aqi']}")
