"""
深入分析NOAA HYSPLIT tdump文件完整结构
"""
import asyncio
import sys
import os
import httpx

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


async def analyze_full_tdump(job_id: str):
    """完整分析tdump文件"""
    url = f"https://www.ready.noaa.gov/hypubout/tdump.{job_id}.txt"

    print(f"{'='*80}")
    print(f"Job {job_id} - 完整tdump文件分析")
    print(f"{'='*80}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code != 200:
            print(f"无法获取文件: {resp.status_code}")
            return

        content = resp.text
        lines = content.split('\n')

        print(f"\n[文件统计]")
        print(f"  总行数: {len(lines)}")
        print(f"  文件大小: {len(content)} bytes")

        print(f"\n[完整内容 - 前50行]")
        for i, line in enumerate(lines[:50]):
            print(f"  {i+1:3d}: {repr(line)}")

        print(f"\n[完整内容 - 后50行]")
        for i, line in enumerate(lines[-50:]):
            print(f"  {len(lines)-50+i+1:3d}: {repr(line)}")

        # 查找包含数字坐标的行
        print(f"\n[查找轨迹数据行]")
        trajectory_lines = []
        for i, line in enumerate(lines):
            # 查找包含经纬度数字格式的行 (如 35.4154 -116.5875)
            if any(char.isdigit() for char in line) and '.' in line:
                parts = line.split()
                # 检查是否是数字行
                numeric_count = sum(1 for p in parts if p.replace('.', '').replace('-', '').isdigit())
                if numeric_count >= 5:
                    trajectory_lines.append((i+1, line))

        print(f"  找到可能的轨迹数据行: {len(trajectory_lines)}")
        if trajectory_lines:
            print(f"\n  前10个轨迹数据行:")
            for line_num, line in trajectory_lines[:10]:
                print(f"    {line_num:3d}: {line[:100]}")

        # 分析文件结构特征
        print(f"\n[文件结构特征]")
        gfsq_count = sum(1 for line in lines if 'GFSQ' in line or 'GDAS' in line)
        print(f"  气象源记录行 (GFSQ/GDAS): {gfsq_count}")

        # 查找包含完整时间戳的行
        print(f"\n[查找时间戳行]")
        timestamp_lines = []
        for i, line in enumerate(lines):
            # 查找类似 2026 01 25 00 格式的行
            parts = line.split()
            if len(parts) >= 4:
                # 检查前4个是否都是数字
                if all(p.isdigit() or p.replace('-', '').isdigit() for p in parts[:4]):
                    timestamp_lines.append((i+1, line))

        print(f"  找到可能的时间戳行: {len(timestamp_lines)}")
        if timestamp_lines:
            print(f"\n  前10个时间戳行:")
            for line_num, line in timestamp_lines[:10]:
                print(f"    {line_num:3d}: {line[:100]}")


async def compare_success_failure():
    """对比成功和失败任务的完整结构"""
    jobs = {
        "成功(24h)": "126486",
        "失败(72h)": "126391"
    }

    for name, job_id in jobs.items():
        await analyze_full_tdump(job_id)
        print("\n")


async def main():
    await compare_success_failure()


if __name__ == "__main__":
    asyncio.run(main())
