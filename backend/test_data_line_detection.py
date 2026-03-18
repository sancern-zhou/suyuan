"""
检测tdump文件中真正的数据行
"""
import asyncio
import httpx
import re

async def find_real_data_lines(job_id: str):
    """查找真正的数据行"""
    url = f"https://www.ready.noaa.gov/hypubout/tdump.{job_id}.txt"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, follow_redirects=True)
        text = resp.text

        lines = text.split("\n")

        print(f"\n{'='*80}")
        print(f"Job {job_id} - 查找真正的数据行")
        print(f"{'='*80}")

        # 查找模式
        print(f"\n[查找包含12个以上字段的行]")
        data_lines = []
        for i, line in enumerate(lines):
            parts = line.split()
            if len(parts) >= 12:
                # 验证是否是数字行
                try:
                    # 尝试解析关键字段
                    traj_id = int(parts[0])
                    year = int(parts[2])
                    lat = float(parts[9])
                    lon = float(parts[10])
                    height = float(parts[11])

                    data_lines.append((i+1, line, parts))
                    if len(data_lines) <= 5:
                        print(f"  行{i+1}: {len(parts)}个字段")
                        print(f"    {line[:100]}")
                        print(f"    traj_id={traj_id}, year={year}, lat={lat}, lon={lon}, height={height}")
                except (ValueError, IndexError):
                    pass

        print(f"\n  共找到 {len(data_lines)} 行有效数据")

        # 分析文件结构
        print(f"\n[文件结构分析]")
        for i, line in enumerate(lines[:30]):
            parts = line.split()
            print(f"  {i+1:3d}: [{len(parts):2d}字段] {line[:80]}")


async def main():
    print("="*80)
    print("分析tdump文件结构，定位真正的数据行")
    print("="*80)

    await find_real_data_lines("126486")  # 成功
    await find_real_data_lines("126391")  # 失败


if __name__ == "__main__":
    asyncio.run(main())
