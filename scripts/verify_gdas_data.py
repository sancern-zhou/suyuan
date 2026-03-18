#!/usr/bin/env python3
"""
GDAS数据验证脚本

验证下载的GDAS数据文件完整性和可用性
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.external_apis.meteo_data_manager import MeteoDataManager


def main():
    print("=" * 80)
    print("GDAS数据验证工具")
    print("=" * 80)

    # 检查缓存目录
    cache_dir = Path("data/hysplit/meteo")
    if not cache_dir.exists():
        print(f"❌ 缓存目录不存在：{cache_dir}")
        print(f"   请先运行：python scripts/download_gdas_data.py --test")
        return 1

    print(f"✅ 缓存目录存在：{cache_dir}")

    # 创建管理器
    manager = MeteoDataManager(cache_dir=str(cache_dir))

    # 获取所有GDAS文件
    gdas_files = list(cache_dir.glob("gdas1.*"))
    if not gdas_files:
        print(f"❌ 缓存目录中没有找到GDAS文件")
        print(f"   请先运行：python scripts/download_gdas_data.py --test")
        return 1

    print(f"✅ 找到 {len(gdas_files)} 个GDAS文件")

    # 统计信息
    total_size = 0
    file_list = []

    for file_path in gdas_files:
        if file_path.is_file():
            stat = file_path.stat()
            size_mb = stat.st_size / 1024 / 1024
            total_size += stat.st_size

            # 解析文件名
            filename = file_path.name
            try:
                # 解析文件名格式：gdas1.MONYY.wN
                parts = filename.split('.')
                if len(parts) >= 4:
                    month_abbr = parts[1][:3]
                    year = int("20" + parts[1][3:])
                    week = int(parts[3])
                    file_list.append({
                        'filename': filename,
                        'size_mb': size_mb,
                        'month': month_abbr,
                        'year': year,
                        'week': week
                    })
            except Exception as e:
                file_list.append({
                    'filename': filename,
                    'size_mb': size_mb,
                    'error': str(e)
                })

    # 显示文件列表
    print(f"\n文件列表：")
    print("-" * 80)
    print(f"{'文件名':<25} {'大小(MB)':<12} {'年月':<10} {'周':<5}")
    print("-" * 80)

    for file_info in sorted(file_list, key=lambda x: (x.get('year', 0), x.get('month', ''), x.get('week', 0))):
        if 'error' in file_info:
            print(f"{file_info['filename']:<25} {file_info['size_mb']:>10.1f}     [文件名格式错误]")
        else:
            print(f"{file_info['filename']:<25} {file_info['size_mb']:>10.1f}     {file_info['year']}-{file_info['month']} w{file_info['week']:<3}")

    print("-" * 80)
    print(f"{'总计':<25} {total_size/1024/1024:>10.1f}     {len(gdas_files)} 个文件")

    # 检查时间范围覆盖
    print(f"\n" + "=" * 80)
    print("时间范围分析")
    print("=" * 80)

    # 确定数据覆盖的时间范围
    time_ranges = []
    for file_info in file_list:
        if 'error' not in file_info:
            # 估算文件覆盖的日期范围
            # 假设每周文件覆盖7天
            year = file_info['year']
            week = file_info['week']

            # 计算该周的开始日期（简化计算）
            # 1月1日是周1，每7天一周
            days_from_start = (week - 1) * 7
            from datetime import date
            first_day = date(year, 1, 1)
            start_date = first_day + timedelta(days=days_from_start)
            end_date = start_date + timedelta(days=6)

            time_ranges.append({
                'file': file_info['filename'],
                'start': start_date,
                'end': end_date
            })

    if time_ranges:
        time_ranges.sort(key=lambda x: x['start'])

        print(f"数据覆盖时间范围：")
        print(f"  最早：{time_ranges[0]['start']}")
        print(f"  最晚：{time_ranges[-1]['end']}")

        # 计算覆盖天数
        total_days = 0
        for tr in time_ranges:
            total_days += 7

        print(f"  总天数：{total_days} 天")

    # 测试文件可用性
    print(f"\n" + "=" * 80)
    print("文件可用性测试")
    print("=" * 80)

    # 测试文件名生成和匹配
    now = datetime.utcnow()
    test_dates = [
        now - timedelta(days=1),
        now - timedelta(days=7),
        now - timedelta(days=14),
        now - timedelta(days=30),
    ]

    print(f"测试文件名生成和匹配：")
    for test_date in test_dates:
        expected_filename = manager._get_filename_for_date(test_date)
        file_path = cache_dir / expected_filename

        exists = file_path.exists()
        status = "✅" if exists else "❌"
        print(f"  {status} {test_date.strftime('%Y-%m-%d')} → {expected_filename}")

    # 获取当前时间范围需要的文件
    print(f"\n当前时间范围分析（过去30天）：")
    end_time = now
    start_time = now - timedelta(days=30)

    required_files = manager.get_required_files_for_timerange(start_time, end_time)
    availability = manager.check_local_availability(required_files)

    print(f"  需要文件：{len(required_files)} 个")
    print(f"  可用文件：{sum(availability.values())} 个")

    missing = [f for f, avail in availability.items() if not avail]
    if missing:
        print(f"\n  ❌ 缺失文件：")
        for f in missing:
            print(f"     - {f}")
        print(f"\n建议：运行下载脚本补充缺失文件")
        print(f"     python scripts/download_gdas_data.py --weeks 4")
    else:
        print(f"\n  ✅ 所有需要的文件都已下载")

    # 缓存统计
    print(f"\n" + "=" * 80)
    print("缓存统计信息")
    print("=" * 80)

    stats = manager.get_cache_stats()
    print(f"  总文件数：{stats['total_files']}")
    print(f"  总大小：{stats.get('total_size_mb', 0)} MB")
    print(f"  缓存目录：{stats['cache_dir']}")

    if stats['oldest_file_date']:
        print(f"  最旧文件：{stats['oldest_file_date']}")
    if stats['newest_file_date']:
        print(f"  最新文件：{stats['newest_file_date']}")

    # 建议
    print(f"\n" + "=" * 80)
    print("建议和下一步")
    print("=" * 80)

    if len(missing) > 0:
        print(f"⚠️  检测到缺失文件，建议下载：")
        print(f"   python scripts/download_gdas_data.py --weeks 4")
    else:
        print(f"✅ GDAS数据验证完成！")
        print(f"\n下一步：")
        print(f"  1. 测试HYSPLIT集成")
        print(f"     python scripts/test_hysplit_with_real_data.py")
        print(f"  2. 集成到轨迹计算服务")
        print(f"     更新 TrajectoryCalculatorService")

    print(f"\n  3. 查看数据使用说明")
    print(f"     cat GDAS_DATA_DOWNLOAD_GUIDE.md")

    return 0


if __name__ == "__main__":
    exit(main())
