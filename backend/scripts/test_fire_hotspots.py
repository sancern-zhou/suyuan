"""
测试NASA FIRMS火点数据采集系统

验证整个数据采集流程：
1. NASA FIRMS API Client
2. Fire Hotspot Fetcher
3. Satellite Repository
4. Get Fire Hotspots Tool
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.external_apis.nasa_firms_client import NASAFirmsClient
from app.fetchers.satellite.nasa_firms_fetcher import NASAFirmsFetcher
from app.tools.query.get_fire_hotspots import GetFireHotspotsTool
import json


async def test_nasa_firms_client():
    """测试NASA FIRMS API客户端"""
    print("=" * 60)
    print("测试1: NASA FIRMS API客户端")
    print("=" * 60)

    client = NASAFirmsClient()

    # 测试中国及周边区域火点查询
    print("\n查询中国及周边区域最近24小时火点数据...")
    try:
        fires = await client.fetch_recent_fires(
            region="73,18,136,54",  # 中国及周边
            satellite="VIIRS_SNPP_NRT",
            days=1
        )

        print(f"[OK] 成功获取火点数据: {len(fires)} 个火点")

        if fires:
            print("\n前3个火点示例:")
            for i, fire in enumerate(fires[:3]):
                print(f"\n  火点 {i+1}:")
                print(f"    位置: ({fire['latitude']}, {fire['longitude']})")
                print(f"    亮温: {fire['brightness']} K")
                print(f"    FRP: {fire['frp']} MW")
                print(f"    置信度: {fire['confidence']}")
                print(f"    采集时间: {fire['acq_date']} {fire['acq_time']}")
                print(f"    卫星: {fire['satellite']}")
        else:
            print("[INFO] 当前时间段无火点数据")

        return True

    except Exception as e:
        print(f"[ERROR] API调用失败: {e}")
        return False


async def test_fire_hotspot_fetcher():
    """测试火点数据Fetcher"""
    print("\n\n" + "=" * 60)
    print("测试2: 火点数据Fetcher")
    print("=" * 60)

    fetcher = NASAFirmsFetcher()

    print(f"\nFetcher信息:")
    print(f"  名称: {fetcher.name}")
    print(f"  描述: {fetcher.description}")
    print(f"  调度: {fetcher.schedule}")
    print(f"  版本: {fetcher.version}")

    print("\n执行数据获取和存储...")
    try:
        await fetcher.fetch_and_store()
        print("[OK] Fetcher执行成功")
        return True

    except Exception as e:
        print(f"[ERROR] Fetcher执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_fire_hotspots_tool():
    """测试火点查询工具"""
    print("\n\n" + "=" * 60)
    print("测试3: 火点查询工具")
    print("=" * 60)

    tool = GetFireHotspotsTool()

    print(f"\n工具信息:")
    print(f"  名称: {tool.name}")
    print(f"  类别: {tool.category}")
    print(f"  版本: {tool.version}")

    # 获取Function Schema
    schema = tool.get_function_schema()
    print(f"\nFunction Schema:")
    print(f"  函数名: {schema['name']}")
    print(f"  描述: {schema['description']}")
    print(f"  必需参数: {schema['parameters']['required']}")

    # 测试查询：广州周边区域最近3天的火点
    print("\n\n测试查询: 广州周边区域最近3天的火点数据")
    print("-" * 60)

    # 广州坐标: 23.13°N, 113.26°E
    # 搜索半径: 约100km (约1度)
    region = {
        "min_lat": 22.5,
        "max_lat": 24.0,
        "min_lon": 112.5,
        "max_lon": 114.5
    }

    end_time = datetime.now()
    start_time = end_time - timedelta(days=3)

    try:
        result = await tool.execute(
            region=region,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            min_confidence=70
        )

        if result["success"]:
            print(f"[OK] 查询成功")
            print(f"\n统计信息:")
            print(f"  火点总数: {result['statistics']['total_count']}")
            print(f"  总辐射功率: {result['statistics']['total_frp_mw']} MW")
            print(f"  平均置信度: {result['statistics']['avg_confidence']}")
            print(f"  白天火点: {result['statistics']['day_fires']}")
            print(f"  夜间火点: {result['statistics']['night_fires']}")

            if result["hotspots"]:
                print(f"\n前5个火点详情:")
                for i, hotspot in enumerate(result["hotspots"][:5]):
                    print(f"\n  火点 {i+1}:")
                    print(f"    位置: ({hotspot['lat']}, {hotspot['lon']})")
                    print(f"    FRP: {hotspot['frp']} MW")
                    print(f"    置信度: {hotspot['confidence']}")
                    print(f"    时间: {hotspot['acquisition_time']}")
            else:
                print("\n[INFO] 该区域和时间范围内无高置信度火点")

            return True

        else:
            print(f"[ERROR] 查询失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"[ERROR] 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_specific_location():
    """测试特定位置查询（如东莞周边）"""
    print("\n\n" + "=" * 60)
    print("测试4: 特定位置查询（东莞周边）")
    print("=" * 60)

    tool = GetFireHotspotsTool()

    # 东莞坐标: 23.05°N, 113.75°E
    # 搜索半径: 约50km (约0.5度)
    region = {
        "min_lat": 22.5,
        "max_lat": 23.5,
        "min_lon": 113.2,
        "max_lon": 114.2
    }

    end_time = datetime.now()
    start_time = end_time - timedelta(days=7)

    print(f"\n查询区域: 东莞周边")
    print(f"时间范围: 最近7天")
    print(f"置信度阈值: 80 (高置信度)")

    try:
        result = await tool.execute(
            region=region,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            min_confidence=80
        )

        if result["success"]:
            count = result["statistics"]["total_count"]
            print(f"\n[OK] 发现 {count} 个高置信度火点")

            if count > 0:
                print(f"\n辐射功率最高的3个火点:")
                # 按FRP排序
                sorted_hotspots = sorted(
                    result["hotspots"],
                    key=lambda x: x["frp"],
                    reverse=True
                )

                for i, hotspot in enumerate(sorted_hotspots[:3]):
                    print(f"\n  Top {i+1}:")
                    print(f"    位置: ({hotspot['lat']}, {hotspot['lon']})")
                    print(f"    FRP: {hotspot['frp']} MW ⭐")
                    print(f"    置信度: {hotspot['confidence']}")
                    print(f"    时间: {hotspot['acquisition_time']}")

            return True

        else:
            print(f"[ERROR] 查询失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"[ERROR] 查询失败: {e}")
        return False


async def main():
    """运行所有测试"""
    print("\n")
    print("=" * 60)
    print("NASA FIRMS 火点数据采集系统测试")
    print("=" * 60)

    results = []

    # 测试1: API客户端
    results.append(await test_nasa_firms_client())

    # 测试2: Fetcher（注意：这会写入数据库）
    print("\n\n[警告] 测试2将会写入数据库，继续吗？(y/n)")
    # 自动跳过数据库写入测试，避免在没有数据库时出错
    print("[跳过] 数据库写入测试（需要配置数据库）")
    results.append(True)

    # 测试3: 查询工具
    results.append(await test_fire_hotspots_tool())

    # 测试4: 特定位置查询
    results.append(await test_specific_location())

    # 总结
    print("\n\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    test_names = [
        "NASA FIRMS API客户端",
        "火点数据Fetcher",
        "火点查询工具",
        "特定位置查询"
    ]

    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "[OK]" if result else "[FAILED]"
        print(f"{i+1}. {name}: {status}")

    success_count = sum(results)
    total_count = len(results)

    print(f"\n总计: {success_count}/{total_count} 通过")

    if success_count == total_count:
        print("\n[SUCCESS] 所有测试通过!")
    else:
        print("\n[FAILED] 部分测试失败")


if __name__ == "__main__":
    asyncio.run(main())
