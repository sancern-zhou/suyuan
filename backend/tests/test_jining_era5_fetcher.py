"""
测试济宁市 ERA5 Fetcher

手动运行测试脚本，验证济宁市站点级 ERA5 数据抓取功能
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fetchers.weather.jining_era5_fetcher import JiningERA5Fetcher
import structlog

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


async def test_jining_era5_fetcher():
    """测试济宁市 ERA5 Fetcher"""

    print("=" * 60)
    print("济宁市 ERA5 Fetcher 测试")
    print("=" * 60)

    # 创建 Fetcher 实例
    fetcher = JiningERA5Fetcher()

    # 显示站点信息
    print("\n1. 济宁市监测站点:")
    print("-" * 60)
    for station_id, info in fetcher.stations.items():
        print(f"  {station_id}: {info['name']}")
        print(f"      坐标: ({info['lat']}, {info['lon']})")

    # 显示市中心点
    print("\n2. 济宁市中心点:")
    print("-" * 60)
    print(f"  {fetcher.city_center['name']}")
    print(f"      坐标: ({fetcher.city_center['lat']}, {fetcher.city_center['lon']})")

    # 生成站点数据点
    print("\n3. 生成站点数据点:")
    print("-" * 60)
    station_points = await fetcher._get_station_points()
    print(f"  站点数量: {len(station_points)}")
    for point in station_points:
        print(f"  - {point['station_id']}: {point['name']}")
        print(f"      原始坐标: ({point['original_lat']}, {point['original_lon']})")
        print(f"      网格坐标: ({point['lat']}, {point['lon']})")

    # 生成市中心数据点
    print("\n4. 生成市中心数据点:")
    print("-" * 60)
    city_center_point = await fetcher._get_city_center_point()
    print(f"  名称: {city_center_point['name']}")
    print(f"  原始坐标: ({city_center_point['original_lat']}, {city_center_point['original_lon']})")
    print(f"  网格坐标: ({city_center_point['lat']}, {city_center_point['lon']})")

    # 测试单个站点数据抓取（使用今天的数据）
    print("\n5. 测试单个站点数据抓取:")
    print("-" * 60)

    test_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"  测试日期: {test_date}")
    print(f"  测试站点: 11149A (火炬城)")

    result = await fetcher.fetch_station_data("11149A", test_date)
    print(f"\n  结果:")
    for key, value in result.items():
        print(f"    {key}: {value}")

    # 测试批量数据抓取（站点 + 市中心）
    print("\n6. 测试批量数据抓取（站点 + 市中心）:")
    print("-" * 60)

    print(f"  测试日期: {test_date}")
    print(f"  抓取数据点：6个站点 + 1个市中心 = 7个点")

    result = await fetcher.fetch_and_store_for_date(test_date)
    print(f"\n  结果:")
    for key, value in result.items():
        print(f"    {key}: {value}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


async def test_grid_alignment():
    """测试网格对齐功能"""
    from app.fetchers.weather.jining_era5_fetcher import JiningERA5Fetcher

    print("\n网格对齐测试:")
    print("-" * 60)

    fetcher = JiningERA5Fetcher()
    grid_spacing = 0.25

    for station_id, info in fetcher.stations.items():
        original_lat = info['lat']
        original_lon = info['lon']

        # 对齐到网格
        grid_lat = round(original_lat / grid_spacing) * grid_spacing
        grid_lon = round(original_lon / grid_spacing) * grid_spacing

        print(f"  {station_id} - {info['name']}")
        print(f"    原始坐标: ({original_lat}, {original_lon})")
        print(f"    网格坐标: ({grid_lat}, {grid_lon})")
        print(f"    偏移: ({abs(grid_lat - original_lat):.4f}, {abs(grid_lon - original_lon):.4f}) 度")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_jining_era5_fetcher())

    # 运行网格对齐测试
    asyncio.run(test_grid_alignment())
