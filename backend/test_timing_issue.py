"""
测试timing问题：模型完成后立即获取tdump可能失败
"""
import asyncio
import httpx
import sys

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def parse_endpoints(text: str):
    """解析端点"""
    endpoints = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<"):
            continue
        parts = line.split()
        if len(parts) >= 12:
            try:
                endpoints.append({
                    "trajectory_id": int(parts[0]),
                    "lat": float(parts[9]),
                    "lon": float(parts[10]),
                    "height": float(parts[11]),
                })
            except (ValueError, IndexError):
                continue
    return endpoints


async def test_job_timing(job_id: str, expected_endpoints: int):
    """测试job的端点获取时机"""
    result_url = f"https://www.ready.noaa.gov/hypub-bin/trajresults.pl?jobidno={job_id}"
    tdump_url = f"https://www.ready.noaa.gov/hypubout/tdump.{job_id}.txt"

    print(f"\n{'='*80}")
    print(f"Job {job_id} - 期望端点数: {expected_endpoints}")
    print(f"{'='*80}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 检查完成状态
        resp = await client.get(result_url)
        complete = "Complete Hysplit" in resp.text or "Percent complete: 100" in resp.text
        print(f"\n[完成状态]")
        print(f"  页面显示完成: {complete}")

        # 获取tdump
        resp = await client.get(tdump_url)
        print(f"\n[tdump文件]")
        print(f"  Status: {resp.status_code}")
        print(f"  Length: {len(resp.text)}")

        # 解析端点
        endpoints = parse_endpoints(resp.text)
        print(f"\n[解析结果]")
        print(f"  端点数: {len(endpoints)}")
        print(f"  期望: {expected_endpoints}")
        print(f"  匹配: {len(endpoints) == expected_endpoints}")

        # 如果失败，等待后重试
        if len(endpoints) != expected_endpoints:
            print(f"\n[重试] 等待5秒后重新获取...")
            await asyncio.sleep(5)

            resp = await client.get(tdump_url)
            endpoints = parse_endpoints(resp.text)
            print(f"  重试后端点数: {len(endpoints)}")
            print(f"  匹配: {len(endpoints) == expected_endpoints}")


async def main():
    print("="*80)
    print("测试timing问题 - 检查模型完成后tdump是否立即可用")
    print("="*80)

    # 72小时任务，期望 73*3 = 219 个端点（包括起始点）
    await test_job_timing("126723", 219)

    # 24小时任务，期望 25*1 = 25 个端点（包括起始点）
    await test_job_timing("126757", 25)


if __name__ == "__main__":
    asyncio.run(main())
