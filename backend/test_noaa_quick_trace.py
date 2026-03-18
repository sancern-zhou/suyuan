"""
模拟快速溯源的NOAA轨迹分析测试
精确复制快速溯源的参数和条件
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))

from app.external_apis.noaa_hysplit_api import NOAAHysplitAPI


async def test_quick_trace_scenario():
    """精确模拟快速溯源场景"""
    print("=" * 80)
    print("模拟快速溯源场景 - 北京时间2026-02-03 14:00")
    print("=" * 80)

    # 快速溯源的精确参数
    lat = 35.4154  # 济宁市
    lon = 116.5875

    # 告警时间：北京时间2026-02-03 14:00
    # 转换为UTC：2026-02-03 06:00
    alert_time_beijing = "2026-02-03 14:00:00"
    alert_time_utc = datetime(2026, 2, 3, 6, 0, 0, tzinfo=timezone.utc)

    # 快速溯源使用的是调整后的时间（往前推1天）
    adjusted_time = alert_time_utc - timedelta(hours=24)  # 2026-02-02 06:00 UTC

    heights = [100, 500, 1000]
    hours = 72
    direction = "Backward"
    meteo_source = "gfs0p25"  # 快速溯源使用的气象源

    print(f"\n【告警信息】")
    print(f"  告警时间(北京): {alert_time_beijing}")
    print(f"  告警时间(UTC): {alert_time_utc.isoformat()}")
    print(f"  调整后时间(UTC): {adjusted_time.isoformat()}")
    print(f"  当前时间(UTC): {datetime.utcnow().isoformat()}")

    print(f"\n【NOAA轨迹参数】")
    print(f"  位置: ({lat}, {lon})")
    print(f"  开始时间: {adjusted_time.isoformat()}")
    print(f"  高度层: {heights}")
    print(f"  时长: {hours}小时")
    print(f"  方向: {direction}")
    print(f"  气象源: {meteo_source}")

    print(f"\n【时间分析】")
    time_diff = datetime.now(timezone.utc) - adjusted_time
    print(f"  距离现在: {time_diff.total_seconds()/3600:.1f} 小时前")

    # 判断GFS数据是否可用
    # GFS 0.25°数据通常只有最近8天
    gfs_available_days = 8
    days_old = time_diff.total_seconds() / 86400
    print(f"  GFS可用天数: {gfs_available_days}天")
    print(f"  请求时间距今: {days_old:.1f}天")
    if days_old > gfs_available_days:
        print(f"  ⚠️  超出GFS数据范围！")
    else:
        print(f"  ✅ 在GFS数据范围内")

    print("\n" + "-" * 80)
    print("开始NOAA轨迹分析...")
    print("-" * 80)

    api = NOAAHysplitAPI()

    try:
        result = await api.run_trajectory(
            lat=lat,
            lon=lon,
            start_time=adjusted_time,
            heights=heights,
            hours=hours,
            direction=direction,
            meteo_source=meteo_source
        )

        print(f"\n【结果】")
        print(f"  Success: {result.get('success')}")
        print(f"  Job ID: {result.get('job_id')}")
        print(f"  Model Complete: {result.get('model_complete')}")
        print(f"  Endpoints Count: {len(result.get('endpoints_data', []))}")
        print(f"  Local Plot: {result.get('local_plot')}")
        print(f"  Plot Success: {result.get('plot_success')}")

        if result.get('error'):
            print(f"  Error: {result.get('error')}")

        # 显示端点样本
        endpoints = result.get('endpoints_data', [])
        if endpoints:
            print(f"\n【前3个端点样本】")
            for i, ep in enumerate(endpoints[:3]):
                print(f"  {i+1}. {ep['timestamp']}: ({ep['lat']:.4f}, {ep['lon']:.4f}) @ {ep['height']:.0f}m")

    except Exception as e:
        print(f"\n[异常]")
        print(f"  错误类型: {type(e).__name__}")
        print(f"  错误信息: {str(e)}")

    print("\n" + "=" * 80)


async def test_alternative_meteo_sources():
    """测试不同气象源"""
    print("\n" + "=" * 80)
    print("测试不同气象源")
    print("=" * 80)

    api = NOAAHysplitAPI()

    lat = 35.4154
    lon = 116.5875

    # 使用3天前的时间（确保数据可用）
    start_time = datetime.utcnow() - timedelta(days=3)

    heights = [500]  # 简化：只测试一个高度
    hours = 24  # 简化：缩短时长
    direction = "Backward"

    meteo_sources = [
        ("gdas1", "GDAS 1° (历史数据，推荐)"),
        ("reanalysis", "Reanalysis数据"),
    ]

    for source, description in meteo_sources:
        print(f"\n{'-' * 40}")
        print(f"测试气象源: {source}")
        print(f"说明: {description}")
        print(f"开始时间: {start_time.isoformat()}")

        try:
            result = await api.run_trajectory(
                lat=lat,
                lon=lon,
                start_time=start_time,
                heights=heights,
                hours=hours,
                direction=direction,
                meteo_source=source
            )

            print(f"  ✅ Success: {result.get('success')}")
            print(f"  Job ID: {result.get('job_id')}")
            print(f"  Endpoints: {len(result.get('endpoints_data', []))}")

            if result.get('error'):
                print(f"  ❌ Error: {result.get('error')}")

        except Exception as e:
            print(f"  ❌ 异常: {str(e)}")

    print("\n" + "=" * 80)


async def test_recent_time_with_gfs():
    """测试最近时间使用GFS"""
    print("\n" + "=" * 80)
    print("测试最近时间使用GFS 0p25")
    print("=" * 80)

    api = NOAAHysplitAPI()

    lat = 35.4154
    lon = 116.5875

    # 使用1天前的时间（GFS应该可用）
    start_time = datetime.utcnow() - timedelta(days=1)

    heights = [500]
    hours = 24
    direction = "Backward"
    meteo_source = "gfs0p25"

    print(f"\n参数:")
    print(f"  开始时间: {start_time.isoformat()}")
    print(f"  距今: 1天")
    print(f"  气象源: {meteo_source}")

    print(f"\n开始测试...")

    try:
        result = await api.run_trajectory(
            lat=lat,
            lon=lon,
            start_time=start_time,
            heights=heights,
            hours=hours,
            direction=direction,
            meteo_source=meteo_source
        )

        print(f"\n【结果】")
        print(f"  Success: {result.get('success')}")
        print(f"  Job ID: {result.get('job_id')}")
        print(f"  Endpoints: {len(result.get('endpoints_data', []))}")
        print(f"  Local Plot: {result.get('local_plot')}")

        if not result.get('success'):
            print(f"  ❌ Error: {result.get('error')}")

    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")

    print("\n" + "=" * 80)


async def main():
    """主测试函数"""
    await test_quick_trace_scenario()
    await test_alternative_meteo_sources()
    await test_recent_time_with_gfs()


if __name__ == "__main__":
    asyncio.run(main())
