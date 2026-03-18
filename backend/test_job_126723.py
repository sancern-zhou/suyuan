"""
测试Job 126723 (快速溯源72小时)
"""
import asyncio
import httpx
import sys

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def test_job_126723():
    """测试Job 126723"""
    job_id = "126723"
    url = f"https://www.ready.noaa.gov/hypubout/tdump.{job_id}.txt"

    print(f"{'='*80}")
    print(f"Job {job_id} - 快速溯源 (72小时, gfs0p25)")
    print(f"{'='*80}\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, follow_redirects=True)

        print(f"[HTTP响应]")
        print(f"  Status: {resp.status_code}")
        print(f"  Content-Length: {resp.headers.get('content-length', 'unknown')}")
        print(f"  Text Length: {len(resp.text)}")

        if len(resp.text) == 0:
            print(f"\n[错误] 文件为空！")
            return

        lines = resp.text.split("\n")
        print(f"  总行数: {len(lines)}")

        # 查找数据行
        data_lines = []
        for i, line in enumerate(lines):
            parts = line.split()
            if len(parts) >= 12:
                try:
                    traj_id = int(parts[0])
                    lat = float(parts[9])
                    data_lines.append((i+1, line, parts))
                except (ValueError, IndexError):
                    pass

        print(f"\n[数据行分析]")
        print(f"  有效数据行: {len(data_lines)}")

        if len(data_lines) == 0:
            print(f"\n  [问题] 没有找到符合条件的数据行！")
            print(f"\n  前50行内容:")
            for i, line in enumerate(lines[:50]):
                print(f"    {i+1:3d}: {line[:100]}")
        else:
            print(f"\n  前5个数据点:")
            for line_num, line, parts in data_lines[:5]:
                print(f"    行{line_num}: {line}")

            # 模拟解析器逻辑
            print(f"\n[模拟解析器]")
            endpoints = []
            for line in resp.text.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("<"):
                    continue

                parts = line.split()
                if len(parts) >= 12:
                    try:
                        year = int(parts[2])
                        if year < 100:
                            year += 2000

                        endpoint = {
                            "trajectory_id": int(parts[0]),
                            "lat": float(parts[9]),
                            "lon": float(parts[10]),
                            "height": float(parts[11]),
                        }
                        endpoints.append(endpoint)
                    except (ValueError, IndexError):
                        continue

            print(f"  解析结果: {len(endpoints)} 个端点")

            if len(endpoints) == 0 and len(data_lines) > 0:
                print(f"\n  [异常!] 找到{len(data_lines)}行数据，但解析器返回0个端点！")
                print(f"  这说明解析逻辑有问题...")

async def main():
    await test_job_126723()

if __name__ == "__main__":
    asyncio.run(main())
