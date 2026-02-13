"""
完整模拟_get_endpoints流程
"""
import asyncio
import httpx
import sys

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def parse_endpoints(text: str):
    """解析HYSPLIT端点数据（从noaa_hysplit_api.py复制）"""
    endpoints = []

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<"):
            continue

        parts = line.split()
        if len(parts) >= 12:
            try:
                year = int(parts[2])
                if year < 100:
                    year += 2000

                endpoints.append({
                    "trajectory_id": int(parts[0]),
                    "year": year,
                    "month": int(parts[3]),
                    "day": int(parts[4]),
                    "hour": int(parts[5]),
                    "age_hours": float(parts[8]),
                    "lat": float(parts[9]),
                    "lon": float(parts[10]),
                    "height": float(parts[11]),
                    "pressure": float(parts[12]) if len(parts) > 12 else None,
                    "timestamp": f"{year}-{int(parts[3]):02d}-{int(parts[4]):02d}T{int(parts[5]):02d}:00:00Z"
                })
            except (ValueError, IndexError) as e:
                print(f"  [解析失败] {e}: {line[:50]}")
                continue

    return endpoints


async def simulate_get_endpoints(job_id: str):
    """模拟_get_endpoints流程"""
    urls = [
        f"https://www.ready.noaa.gov/hypubout/tdump.{job_id}.txt",
        f"https://www.ready.noaa.gov/hypub-bin/trajendpts.pl?jobidno={job_id}",
    ]

    print(f"\n{'='*80}")
    print(f"Job {job_id} - 模拟_get_endpoints流程")
    print(f"{'='*80}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, url in enumerate(urls):
            print(f"\n[尝试 {i+1}] {url}")

            resp = await client.get(url, follow_redirects=True)

            print(f"  Status: {resp.status_code}")
            print(f"  Text Length: {len(resp.text)}")
            print(f"  > 100: {len(resp.text) > 100}")

            # 条件1: status == 200
            if resp.status_code != 200:
                print(f"  [跳过] status != 200")
                continue

            # 条件2: len > 100
            if len(resp.text) <= 100:
                print(f"  [跳过] text too short")
                continue

            # 解析端点
            endpoints = parse_endpoints(resp.text)
            print(f"  解析结果: {len(endpoints)} 个端点")

            # 条件3: endpoints不为空
            if endpoints:
                print(f"  [成功] 返回 {len(endpoints)} 个端点")
                return endpoints
            else:
                print(f"  [失败] 解析返回0个端点")

        print(f"\n[结论] 所有URL都失败，返回空列表")
        return []


async def main():
    print("="*80)
    print("模拟_get_endpoints流程 - 找出为什么返回0个端点")
    print("="*80)

    # 测试失败的任务
    result = await simulate_get_endpoints("126723")

    print(f"\n{'='*80}")
    print(f"最终结果: {len(result)} 个端点")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
