"""
测试tdump文件长度检查
"""
import asyncio
import httpx

async def check_tdump_length(job_id: str):
    """检查tdump文件长度"""
    urls = [
        f"https://www.ready.noaa.gov/hypubout/tdump.{job_id}.txt",
        f"https://www.ready.noaa.gov/hypub-bin/trajendpts.pl?jobidno={job_id}",
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in urls:
            print(f"\n{'='*60}")
            print(f"URL: {url}")
            print(f"{'='*60}")

            try:
                resp = await client.get(url, follow_redirects=True)
                print(f"  Status: {resp.status_code}")
                print(f"  Content-Length: {resp.headers.get('content-length', 'unknown')}")
                print(f"  Text Length: {len(resp.text)}")
                print(f"  > 100 check: {len(resp.text) > 100}")

                if len(resp.text) > 0:
                    print(f"\n  前200字符预览:")
                    print(f"    {resp.text[:200]}")

                    # 测试解析
                    lines = resp.text.strip().split("\n")
                    print(f"\n  总行数: {len(lines)}")
                    data_lines = [l for l in lines if l.strip() and not l.startswith('#') and not l.startswith('<')]
                    print(f"  数据行数: {len(data_lines)}")

                    # 测试解析
                    parts = data_lines[0].split() if data_lines else []
                    print(f"  第一行字段数: {len(parts)}")

            except Exception as e:
                print(f"  [错误] {str(e)}")


async def main():
    print("="*60)
    print("检查tdump文件长度和内容")
    print("="*60)

    # 成功任务
    await check_tdump_length("126486")

    # 失败任务
    await check_tdump_length("126391")


if __name__ == "__main__":
    asyncio.run(main())
