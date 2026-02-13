"""
立即测试Job 126863
"""
import asyncio
import httpx
import sys

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def parse_endpoints(text: str):
    endpoints = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<"):
            continue
        parts = line.split()
        if len(parts) >= 12:
            try:
                endpoints.append({
                    "lat": float(parts[9]),
                    "lon": float(parts[10]),
                })
            except (ValueError, IndexError):
                continue
    return endpoints


async def test_job_126863():
    job_id = "126863"
    url = f"https://www.ready.noaa.gov/hypubout/tdump.{job_id}.txt"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, follow_redirects=True)

        print(f"Job {job_id}")
        print(f"  Status: {resp.status_code}")
        print(f"  Length: {len(resp.text)}")

        endpoints = parse_endpoints(resp.text)
        print(f"  Endpoints: {len(endpoints)}")


asyncio.run(test_job_126863())
