#!/usr/bin/env python3
"""
GDAS数据自动下载脚本

使用说明：
  python scripts/download_gdas_data.py --help
  python scripts/download_gdas_data.py --test        # 下载测试数据（2个文件）
  python scripts/download_gdas_data.py --all         # 下载所有可用数据
  python scripts/download_gdas_data.py --weeks 4     # 下载4周数据
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加backend路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.external_apis.meteo_data_manager import MeteoDataManager


def main():
    parser = argparse.ArgumentParser(description="GDAS气象数据下载工具")
    parser.add_argument(
        "--test",
        action="store_true",
        help="下载测试数据（过去2周的GDAS文件）"
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=2,
        help="下载过去N周的数据（默认：2周）"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="下载所有可用数据（谨慎使用，会占用大量磁盘空间）"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载，即使文件已存在"
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default="data/hysplit/meteo",
        help="缓存目录路径"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式：显示将下载的文件，但不实际下载"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("GDAS气象数据下载工具")
    print("=" * 80)
    print(f"缓存目录：{args.cache_dir}")
    print(f"FTP服务器：{MeteoDataManager.FTP_HOST}")
    print(f"FTP目录：{MeteoDataManager.FTP_DIR}")
    print("=" * 80)

    # 创建管理器
    manager = MeteoDataManager(
        cache_dir=args.cache_dir,
        max_cache_days=365,  # 下载的数据保存1年
        ftp_timeout=60
    )

    # 确定时间范围
    now = datetime.utcnow()
    if args.test:
        # 测试：下载过去2周的数据
        end_time = now
        start_time = now - timedelta(weeks=2)
        print(f"\n[模式] 测试模式")
        print(f"时间范围：{start_time.strftime('%Y-%m-%d')} 至 {end_time.strftime('%Y-%m-%d')}")

    elif args.all:
        # 全部：下载过去3个月的数据（估算）
        end_time = now
        start_time = now - timedelta(days=90)
        print(f"\n[模式] 完整模式")
        print(f"时间范围：{start_time.strftime('%Y-%m-%d')} 至 {end_time.strftime('%Y-%m-%d')}")
        print(f"⚠️  这将下载大量数据（约1GB），请确保磁盘空间充足")

    else:
        # 指定周数
        end_time = now
        start_time = now - timedelta(weeks=args.weeks)
        print(f"\n[模式] 自定义模式")
        print(f"时间范围：{start_time.strftime('%Y-%m-%d')} 至 {end_time.strftime('%Y-%m-%d')}")
        print(f"周数：{args.weeks}周")

    # 计算需要的文件
    required_files = manager.get_required_files_for_timerange(start_time, end_time)

    print(f"\n计算结果：")
    print(f"  需要文件数：{len(required_files)}")
    print(f"  文件列表：")
    for f in required_files:
        print(f"    - {f}")

    # 检查本地可用性
    availability = manager.check_local_availability(required_files)
    missing_files = [f for f, avail in availability.items() if not avail]
    existing_files = [f for f, avail in availability.items() if avail]

    print(f"\n本地检查：")
    print(f"  已存在：{len(existing_files)}个文件")
    print(f"  需要下载：{len(missing_files)}个文件")

    if existing_files:
        print(f"\n  已存在文件：")
        for f in existing_files:
            file_path = Path(args.cache_dir) / f
            size = file_path.stat().st_size if file_path.exists() else 0
            print(f"    ✅ {f} ({size/1024/1024:.1f} MB)")

    if missing_files:
        print(f"\n  需下载文件：")
        for f in missing_files:
            print(f"    ⏳ {f}")

    # 估算下载大小
    estimated_size_mb = len(missing_files) * 12  # 每个文件约12MB
    print(f"\n估算信息：")
    print(f"  预计下载大小：{estimated_size_mb} MB")
    print(f"  预计下载时间：{estimated_size_mb / 100:.1f} 分钟（假设100KB/s）")

    # 确认下载
    if not missing_files:
        print(f"\n✅ 所有需要的文件都已存在，无需下载！")
        return 0

    if args.dry_run:
        print(f"\n[预览模式] 未实际下载文件")
        return 0

    print(f"\n" + "=" * 80)
    response = input("是否开始下载？(y/N): ").strip().lower()
    if response != 'y':
        print("下载已取消")
        return 0

    # 开始下载
    print(f"\n开始下载...")
    print("=" * 80)

    success_count = 0
    fail_count = 0

    for filename in missing_files:
        print(f"\n下载中：{filename}")
        print("-" * 40)

        result = manager.download_file(
            filename=filename,
            force_redownload=args.force
        )

        if result["success"]:
            if result.get("downloaded"):
                print(f"  ✅ 下载成功")
                print(f"     文件大小：{result['file_size']/1024/1024:.1f} MB")
                print(f"     下载时间：{result['download_time']:.1f} 秒")
                success_count += 1
            else:
                print(f"  ℹ️  文件已存在（跳过）")
                success_count += 1
        else:
            print(f"  ❌ 下载失败")
            print(f"     错误：{result['error']}")
            fail_count += 1

    # 下载完成统计
    print(f"\n" + "=" * 80)
    print("下载完成统计")
    print("=" * 80)
    print(f"  成功：{success_count}个文件")
    print(f"  失败：{fail_count}个文件")
    print(f"  总计：{success_count + fail_count}个文件")

    if fail_count > 0:
        print(f"\n⚠️  部分文件下载失败，请检查网络连接或稍后重试")
        return 1
    else:
        print(f"\n✅ 所有文件下载成功！")
        print(f"\n下一步：")
        print(f"  1. 运行验证脚本：python scripts/verify_gdas_data.py")
        print(f"  2. 运行HYSPLIT测试：python scripts/test_hysplit_with_real_data.py")

        return 0


if __name__ == "__main__":
    exit(main())
