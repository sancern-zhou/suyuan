"""
NOAA HYSPLIT tdump文件分析 - 对比成功和失败任务的原始数据
"""
import asyncio
import sys
import os
import httpx
from datetime import datetime, timedelta

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


async def fetch_tdump_file(job_id: str):
    """获取tdump文件原始内容"""
    url = f"https://www.ready.noaa.gov/hypubout/tdump.{job_id}.txt"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            else:
                return None
        except Exception as e:
            print(f"  [错误] {str(e)}")
            return None


async def analyze_tdump_structure(content: str, job_id: str):
    """分析tdump文件结构"""
    print(f"\n{'='*80}")
    print(f"Job {job_id} - tdump文件结构分析")
    print(f"{'='*80}")

    if not content:
        print("  [无法获取内容]")
        return

    lines = content.split('\n')

    print(f"\n[基本信息]")
    print(f"  总行数: {len(lines)}")
    print(f"  文件大小: {len(content)} bytes")

    # 分析头部
    print(f"\n[头部信息 (前10行)]")
    for i, line in enumerate(lines[:10]):
        if line.strip():
            print(f"  {i+1}: {repr(line)}")

    # 分析数据行
    data_lines = [l for l in lines if l.strip() and not l.strip().startswith('0000')]
    print(f"\n[数据行统计]")
    print(f"  数据行数: {len(data_lines)}")

    # 分析每一行的格式
    if data_lines:
        print(f"\n[数据行格式样本 (前3行)]")
        for i, line in enumerate(data_lines[:3]):
            parts = line.split()
            print(f"  行{i+1}: {len(parts)}个字段")
            print(f"    原始: {line[:100]}...")
            if len(parts) >= 10:
                print(f"    字段: {parts[:10]}")

    # 统计小时数
    hour_counts = {}
    for line in data_lines:
        parts = line.split()
        if len(parts) >= 3:
            hour_num = parts[2]
            hour_counts[hour_num] = hour_counts.get(hour_num, 0) + 1

    print(f"\n[小时统计]")
    print(f"  不同小时数: {len(hour_counts)}")
    if hour_counts:
        hours = sorted(hour_counts.keys())
        print(f"  小时范围: {hours[0]} - {hours[-1]}")


async def compare_jobs():
    """对比成功和失败的任务"""
    print("="*80)
    print("NOAA HYSPLIT tdump文件对比分析")
    print("="*80)

    # 成功的任务 (24小时, gfs0p25)
    success_job = "126486"

    # 失败的任务 (72小时, gfs0p25) - 模型完成但0端点
    failed_job = "126391"

    print(f"\n对比任务:")
    print(f"  成功任务: {success_job} (24小时, gfs0p25)")
    print(f"  失败任务: {failed_job} (72小时, gfs0p25)")

    # 获取两个任务的tdump内容
    success_content = await fetch_tdump_file(success_job)
    failed_content = await fetch_tdump_file(failed_job)

    # 分析结构
    await analyze_tdump_structure(success_content, success_job)
    await analyze_tdump_structure(failed_content, failed_job)

    # 对比分析
    if success_content and failed_content:
        print(f"\n{'='*80}")
        print("对比结论")
        print(f"{'='*80}")

        success_lines = len([l for l in success_content.split('\n') if l.strip()])
        failed_lines = len([l for l in failed_content.split('\n') if l.strip()])

        print(f"\n  成功任务行数: {success_lines}")
        print(f"  失败任务行数: {failed_lines}")
        print(f"  比例: {failed_lines/success_lines:.2f}x")

        # 检查失败任务是否有数据
        if failed_lines > 20:
            print(f"\n  [发现] 失败任务tdump文件存在且有数据 ({failed_lines}行)")
            print(f"  [推断] 问题可能在于:")
            print(f"    1. tdump文件格式与解析器预期不符")
            print(f"    2. 72小时轨迹的数据格式不同于24小时")
            print(f"    3. 解析器的正则表达式或字段位置需要调整")
        else:
            print(f"\n  [发现] 失败任务tdump文件为空或很小")
            print(f"  [推断] NOAA服务器确实没有生成轨迹数据")


async def test_endpoint_parsing():
    """测试端点解析逻辑"""
    print(f"\n{'='*80}")
    print("测试端点解析逻辑")
    print(f"{'='*80}")

    job_id = "126391"
    content = await fetch_tdump_file(job_id)

    if not content:
        print("  无法获取tdump文件")
        return

    print(f"\n使用现有解析器测试:")

    # 模拟解析器的正则表达式
    import re

    # NOAA HYSPLIT使用的正则模式 (从noaa_hysplit_api.py复制)
    pattern = re.compile(r'^\s*(\d+)\s+([\d\-]+)\s+(\d+)\s+'  # year, month, day, hour
                         r'(\d+)\s+(\d+)\s+([\d\-\.]+)\s+'  # lat, lon, height
                         r'([\d\-\.]+)\s+([\d\-\.]+)\s+([\d\-\.]+)\s+'  # pressure, temperature
                         r'([\d\-\.]+)\s+([\d\-\.]+)\s+([\d\-\.]+)\s+'  # more fields
                         r'([\d\-\.]+)\s+([\d\-\.]+)\s+([\d\-\.]+)\s+'
                         r'([\d\-\.]+)\s+([\d\-\.]+)\s+([\d\-\.]+)')

    lines = content.split('\n')
    matches = []

    for line in lines:
        match = pattern.match(line)
        if match:
            matches.append(match)

    print(f"  总行数: {len(lines)}")
    print(f"  匹配数: {len(matches)}")

    if len(lines) > 0 and len(matches) == 0:
        print(f"\n  [问题] 所有行都无法匹配正则表达式")
        print(f"\n  前5行原始内容:")
        for i, line in enumerate(lines[:5]):
            if line.strip():
                print(f"    {i+1}: {repr(line)}")


async def main():
    """主测试函数"""
    await compare_jobs()
    await test_endpoint_parsing()

    print(f"\n{'='*80}")
    print("测试完成")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
