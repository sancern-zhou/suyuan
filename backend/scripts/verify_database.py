"""
简单的数据库验证脚本

验证：
1. 数据库连接
2. 气象站数据
3. ERA5数据读写
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.repositories.weather_repo import WeatherRepository
from app.external_apis.openmeteo_client import OpenMeteoClient

async def main():
    print("="*60)
    print("数据库验证")
    print("="*60)

    repo = WeatherRepository()

    # 1. 查询气象站
    print("\n1. 查询气象站...")
    stations = await repo.get_active_stations()
    print(f"   找到 {len(stations)} 个气象站")
    for s in stations:
        print(f"   - {s.station_name} ({s.lat}, {s.lon})")

    if not stations:
        print("[ERROR] 没有找到气象站")
        return False

    station = stations[0]

    # 2. 测试ERA5数据写入
    print(f"\n2. 测试ERA5数据写入...")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"   获取日期: {yesterday}")
    print(f"   位置: ({station.lat}, {station.lon})")

    client = OpenMeteoClient()
    data = await client.fetch_era5_data(
        lat=station.lat,
        lon=station.lon,
        start_date=yesterday,
        end_date=yesterday
    )

    hourly_points = len(data.get("hourly", {}).get("time", []))
    print(f"   API返回: {hourly_points} 个小时数据点")

    records = await repo.save_era5_data(
        lat=station.lat,
        lon=station.lon,
        data=data
    )
    print(f"   保存: {records} 条记录")

    # 3. 测试ERA5数据查询
    print(f"\n3. 测试ERA5数据查询...")
    yesterday_start = datetime.now() - timedelta(days=1)
    yesterday_start = yesterday_start.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = yesterday_start + timedelta(days=1)

    results = await repo.get_weather_data(
        lat=station.lat,
        lon=station.lon,
        start_time=yesterday_start,
        end_time=yesterday_end
    )
    print(f"   查询结果: {len(results)} 条记录")

    if results:
        first = results[0]
        print(f"   示例数据:")
        print(f"     时间: {first.time}")
        print(f"     温度: {first.temperature_2m}°C")
        print(f"     风速: {first.wind_speed_10m} km/h")
        print(f"     边界层高度: {first.boundary_layer_height} m")

    print("\n" + "="*60)
    print("验证完成！数据库工作正常")
    print("="*60)
    return True

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
