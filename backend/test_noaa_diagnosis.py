"""
NOAA HYSPLIT API 诊断脚本
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))

from app.external_apis.noaa_hysplit_api import NOAAHysplitAPI


async def test_noaa_api():
    """测试NOAA API"""
    print("=" * 80)
    print("NOAA HYSPLIT API 诊断测试")
    print("=" * 80)

    api = NOAAHysplitAPI()

    # 测试参数（使用日志中的参数）
    lat = 35.4154
    lon = 116.5875
    start_time = datetime.utcnow() - timedelta(days=1)
    heights = [100, 500, 1000]
    hours = 72
    direction = "Backward"
    meteo_source = "gfs0p25"

    print(f"\n测试参数:")
    print(f"  位置: ({lat}, {lon})")
    print(f"  开始时间: {start_time}")
    print(f"  高度: {heights}")
    print(f"  时长: {hours}小时")
    print(f"  方向: {direction}")
    print(f"  气象源: {meteo_source}")

    print("\n" + "-" * 80)
    print("开始测试...")
    print("-" * 80)

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

        print(f"\n[结果]")
        print(f"  Success: {result.get('success')}")
        print(f"  Job ID: {result.get('job_id')}")

        endpoints_data = result.get('endpoints_data', [])
        if endpoints_data:
            print(f"  端点数: {len(endpoints_data)}")
            print(f"\n前3个端点:")
            for i, ep in enumerate(endpoints_data[:3]):
                print(f"    {i+1}. 时间={ep['timestamp']}, 位置=({ep['lat']}, {ep['lon']}), 高度={ep['height']}m")
        else:
            print(f"  端点数: 0")
            print(f"  Error: {result.get('error')}")

        image_base64 = result.get('trajectory_image_base64')
        if image_base64:
            print(f"  图像: 已生成 ({len(image_base64)} bytes)")
        else:
            print(f"  图像: 未生成")

        # 额外信息
        print(f"  Model Complete: {result.get('model_complete')}")
        print(f"  Local Plot: {result.get('local_plot')}")
        print(f"  Plot Success: {result.get('plot_success')}")

    except Exception as e:
        print(f"\n[异常]")
        print(f"  错误类型: {type(e).__name__}")
        print(f"  错误信息: {str(e)}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


async def test_result_urls():
    """测试结果文件URL访问"""
    print("\n" + "=" * 80)
    print("测试结果文件URL访问")
    print("=" * 80)

    import httpx

    # 使用日志中的job_id
    job_id = "125733"

    urls = [
        f"https://www.ready.noaa.gov/hypubout/tdump.{job_id}.txt",
        f"https://www.ready.noaa.gov/hypub-bin/trajendpts.pl?jobidno={job_id}",
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in urls:
            print(f"\n测试URL: {url}")
            try:
                resp = await client.get(url, follow_redirects=False)
                print(f"  状态码: {resp.status_code}")
                print(f"  Content-Length: {resp.headers.get('content-length', 'unknown')}")
                print(f"  Location: {resp.headers.get('location', 'none')}")
                print(f"  响应长度: {len(resp.text)}")

                if resp.status_code == 302:
                    print(f"  [重定向] 被重定向到 notfound.php")

                if len(resp.text) > 0:
                    print(f"  响应预览: {resp.text[:200]}")

            except Exception as e:
                print(f"  [错误] {str(e)}")

    print("\n" + "=" * 80)


async def test_alternative_time():
    """测试更早的时间（结果文件可能已过期）"""
    print("\n" + "=" * 80)
    print("测试更早的时间（避免文件过期）")
    print("=" * 80)

    api = NOAAHysplitAPI()

    # 使用3天前的时间（避免文件过期）
    lat = 35.4154
    lon = 116.5875
    start_time = datetime.utcnow() - timedelta(days=3)
    heights = [500]  # 只测试一个高度
    hours = 24  # 缩短时长
    direction = "Backward"
    meteo_source = "reanalysis"  # 使用reanalysis数据源

    print(f"\n测试参数:")
    print(f"  开始时间: {start_time} (3天前)")
    print(f"  高度: {heights}")
    print(f"  时长: {hours}小时")
    print(f"  气象源: {meteo_source}")

    print("\n开始测试...")

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

        print(f"\n[结果]")
        print(f"  Success: {result.get('success')}")
        print(f"  Job ID: {result.get('job_id')}")
        print(f"  端点数: {len(result.get('endpoints', []))}")
        print(f"  Error: {result.get('error')}")

    except Exception as e:
        print(f"\n[异常] {str(e)}")

    print("\n" + "=" * 80)


async def main():
    """主测试函数"""
    await test_noaa_api()
    await test_result_urls()
    await test_alternative_time()


if __name__ == "__main__":
    asyncio.run(main())
