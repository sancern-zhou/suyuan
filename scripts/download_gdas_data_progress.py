#!/usr/bin/env python3
"""
GDAS数据下载工具 - 增强版（带进度条和下载速率显示）

功能：
- 实时显示下载速率 (KB/s, MB/s)
- 进度条显示下载进度
- 下载百分比
- 剩余时间估算
- 支持中断和恢复
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
import ftplib
import time
import os

# 添加backend路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.external_apis.meteo_data_manager import MeteoDataManager

# 下载进度类
class DownloadProgress:
    def __init__(self, filename, total_size):
        self.filename = filename
        self.total_size = total_size
        self.downloaded = 0
        self.start_time = time.time()
        self.last_time = self.start_time
        self.last_downloaded = 0

    def update(self, chunk_size):
        self.downloaded += chunk_size
        now = time.time()

        # 计算速度（每秒）
        time_delta = now - self.last_time
        if time_delta >= 0.5:  # 每0.5秒更新一次显示
            speed = (self.downloaded - self.last_downloaded) / time_delta
            self.last_time = now
            self.last_downloaded = self.downloaded
            return speed
        return None

    def get_progress(self):
        if self.total_size > 0:
            percent = (self.downloaded / self.total_size) * 100
        else:
            percent = 0

        elapsed = time.time() - self.start_time
        if self.downloaded > 0 and elapsed > 0:
            avg_speed = self.downloaded / elapsed
            remaining = self.total_size - self.downloaded
            eta = remaining / avg_speed if avg_speed > 0 else 0
        else:
            avg_speed = 0
            eta = 0

        return {
            'percent': percent,
            'downloaded_mb': self.downloaded / 1024 / 1024,
            'total_mb': self.total_size / 1024 / 1024,
            'speed_kbps': avg_speed / 1024,
            'speed_mbps': avg_speed / 1024 / 1024,
            'eta_seconds': eta,
            'eta_formatted': self.format_time(eta)
        }

    def format_time(self, seconds):
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds/60)}m {int(seconds%60)}s"
        else:
            return f"{int(seconds/3600)}h {int((seconds%3600)/60)}m"

def download_file_with_progress(ftp, filename, local_path, progress_callback=None):
    """
    下载文件并报告进度

    Args:
        ftp: FTP连接
        filename: 远程文件名
        local_path: 本地保存路径
        progress_callback: 进度回调函数

    Returns:
        dict: 下载结果
    """
    try:
        # 获取文件大小
        ftp.sendcmd(f'TYPE I')
        file_size = ftp.size(filename)

        print(f"\n正在下载: {filename}")
        print(f"文件大小: {file_size / 1024 / 1024:.1f} MB")
        print("-" * 80)

        # 初始化进度跟踪
        progress = DownloadProgress(filename, file_size)

        # 下载文件
        with open(local_path, 'wb') as f:
            def write_chunk(data):
                f.write(data)
                if progress_callback:
                    progress_callback(len(data))

            # 设置进度回调
            def progress_hook(block):
                speed = progress.update(len(block))
                prog = progress.get_progress()

                # 显示进度条
                bar_length = 40
                filled_length = int(bar_length * prog['percent'] / 100)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)

                # 显示信息
                sys.stdout.write(f'\r{bar}')
                sys.stdout.write(f' {prog["percent"]:6.1f}%')
                sys.stdout.write(f' | {prog["downloaded_mb"]:6.1f}MB / {prog["total_mb"]:6.1f}MB')
                sys.stdout.write(f' | {prog["speed_mbps"]:6.2f} MB/s')
                sys.stdout.write(f' | ETA: {prog["eta_formatted"]:>8}')
                sys.stdout.flush()

            ftp.retrbinary(f'RETR {filename}', progress_hook)

        print("\n" + "-" * 80)

        # 验证下载
        actual_size = os.path.getsize(local_path)
        if actual_size == file_size:
            return {
                "success": True,
                "filename": filename,
                "file_size": file_size,
                "download_time": time.time() - progress.start_time
            }
        else:
            return {
                "success": False,
                "filename": filename,
                "error": f"文件大小不匹配: {actual_size} != {file_size}"
            }

    except Exception as e:
        return {
            "success": False,
            "filename": filename,
            "error": str(e)
        }

def main():
    parser = argparse.ArgumentParser(description="GDAS气象数据下载工具 - 增强版")
    parser.add_argument("--test", action="store_true", help="下载测试数据（过去2周）")
    parser.add_argument("--weeks", type=int, default=2, help="下载过去N周的数据")
    parser.add_argument("--all", action="store_true", help="下载所有可用数据")
    parser.add_argument("--force", action="store_true", help="强制重新下载")
    parser.add_argument("--cache-dir", type=str, default="data/hysplit/meteo", help="缓存目录路径")
    parser.add_argument("--dry-run", action="store_true", help="预览模式")
    parser.add_argument("--show-stats", action="store_true", help="显示详细统计")

    args = parser.parse_args()

    print("=" * 100)
    print("GDAS气象数据下载工具 - 增强版")
    print("=" * 100)
    print(f"缓存目录: {args.cache_dir}")
    print(f"FTP服务器: {MeteoDataManager.FTP_HOST}")
    print(f"FTP目录: {MeteoDataManager.FTP_DIR}")
    print("=" * 100)

    # 创建管理器
    manager = MeteoDataManager(
        cache_dir=args.cache_dir,
        max_cache_days=365,
        ftp_timeout=60
    )

    # 确定时间范围
    now = datetime.utcnow()
    if args.test:
        end_time = now
        start_time = now - timedelta(weeks=2)
        print(f"\n[模式] 测试模式")
        print(f"时间范围: {start_time.strftime('%Y-%m-%d')} 至 {end_time.strftime('%Y-%m-%d')}")
    elif args.all:
        end_time = now
        start_time = now - timedelta(days=90)
        print(f"\n[模式] 完整模式")
        print(f"时间范围: {start_time.strftime('%Y-%m-%d')} 至 {end_time.strftime('%Y-%m-%d')}")
    else:
        end_time = now
        start_time = now - timedelta(weeks=args.weeks)
        print(f"\n[模式] 自定义模式")
        print(f"时间范围: {start_time.strftime('%Y-%m-%d')} 至 {end_time.strftime('%Y-%m-%d')}")
        print(f"周数: {args.weeks}周")

    # 计算需要的文件
    required_files = manager.get_required_files_for_timerange(start_time, end_time)
    availability = manager.check_local_availability(required_files)
    missing_files = [f for f in required_files if not availability[f] or args.force]

    print(f"\n文件统计:")
    print(f"  总计: {len(required_files)} 个文件")
    print(f"  已存在: {len(required_files) - len(missing_files)} 个文件")
    print(f"  需下载: {len(missing_files)} 个文件")

    if missing_files:
        print(f"\n需要下载的文件:")
        for f in missing_files:
            print(f"  - {f}")

    if not missing_files:
        print(f"\n✅ 所有需要的文件都已存在，无需下载！")
        return 0

    if args.dry_run:
        print(f"\n[预览模式] 未实际下载文件")
        return 0

    # 确认下载
    print(f"\n" + "=" * 100)
    response = "y"  # 自动确认
    if response != 'y':
        print("下载已取消")
        return 0

    # 连接FTP并下载
    print(f"\n连接到FTP服务器...")
    try:
        ftp = ftplib.FTP(timeout=60)
        ftp.connect(MeteoDataManager.FTP_HOST, 21)
        ftp.login()
        ftp.cwd(MeteoDataManager.FTP_DIR)
        print(f"✅ 已连接到FTP服务器")
    except Exception as e:
        print(f"❌ FTP连接失败: {e}")
        return 1

    # 下载文件
    success_count = 0
    fail_count = 0
    total_downloaded = 0
    total_size = 0
    start_time = time.time()

    print(f"\n开始下载 {len(missing_files)} 个文件...")
    print("=" * 100)

    for i, filename in enumerate(missing_files, 1):
        local_path = Path(args.cache_dir) / filename
        print(f"\n[{i}/{len(missing_files)}] 准备下载: {filename}")

        # 下载文件
        result = download_file_with_progress(
            ftp, filename, local_path
        )

        if result["success"]:
            success_count += 1
            total_downloaded += result["file_size"]
            total_size += result["file_size"]
            print(f"✅ 下载成功")
            print(f"   文件大小: {result['file_size']/1024/1024:.1f} MB")
            print(f"   下载时间: {result['download_time']:.2f} 秒")
        else:
            fail_count += 1
            total_size += 0
            print(f"❌ 下载失败")
            print(f"   错误: {result['error']}")

    # 关闭FTP连接
    ftp.quit()

    # 下载完成统计
    end_time = time.time()
    total_time = end_time - start_time

    print(f"\n" + "=" * 100)
    print("下载完成统计")
    print("=" * 100)
    print(f"  总文件数: {len(missing_files)}")
    print(f"  成功下载: {success_count}")
    print(f"  下载失败: {fail_count}")
    print(f"  下载大小: {total_downloaded/1024/1024:.1f} MB")
    print(f"  总耗时: {total_time:.2f} 秒")
    if total_time > 0:
        print(f"  平均速度: {total_downloaded/1024/1024/total_time:.2f} MB/s")
    print(f"=" * 100)

    if fail_count > 0:
        print(f"\n⚠️  部分文件下载失败")
        print(f"请检查网络连接或稍后重试")
        return 1
    else:
        print(f"\n🎉 所有文件下载成功！")
        print(f"\n下一步:")
        print(f"  1. 运行验证脚本: python scripts/verify_gdas_data.py")
        print(f"  2. 运行HYSPLIT测试: python scripts/test_hysplit_with_real_data.py")
        return 0

if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print(f"\n\n⚠️  下载被用户中断")
        print(f"您可以稍后使用 --force 参数继续下载未完成的文件")
        exit(1)
