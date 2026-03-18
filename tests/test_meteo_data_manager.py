"""
Unit Tests for Meteorological Data Manager

测试气象数据管理器功能
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.external_apis.meteo_data_manager import MeteoDataManager


class TestMeteoDataManager:
    """气象数据管理器测试"""

    @pytest.fixture
    def temp_cache_dir(self):
        """创建临时缓存目录"""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def manager(self, temp_cache_dir):
        """创建MeteoDataManager实例"""
        return MeteoDataManager(
            cache_dir=temp_cache_dir,
            max_cache_days=30,
            ftp_timeout=30
        )

    def test_manager_initialization(self, manager, temp_cache_dir):
        """测试管理器初始化"""
        print("\n" + "=" * 60)
        print("TEST 1: Manager Initialization")
        print("=" * 60)

        assert manager is not None
        assert manager.cache_dir.exists()
        assert str(manager.cache_dir) == temp_cache_dir
        assert manager.max_cache_days == 30
        assert manager.ftp_timeout == 30

        print(f"[OK] Cache directory: {manager.cache_dir}")
        print(f"[OK] Max cache days: {manager.max_cache_days}")
        print("=" * 60)

    def test_filename_generation(self, manager):
        """测试GDAS文件名生成"""
        print("\n" + "=" * 60)
        print("TEST 2: GDAS Filename Generation")
        print("=" * 60)

        test_cases = [
            (datetime(2025, 11, 1, 12, 0), "gdas1.nov25.w1"),   # 11月1日 -> w1
            (datetime(2025, 11, 7, 12, 0), "gdas1.nov25.w1"),   # 11月7日 -> w1
            (datetime(2025, 11, 8, 12, 0), "gdas1.nov25.w2"),   # 11月8日 -> w2
            (datetime(2025, 11, 15, 12, 0), "gdas1.nov25.w3"),  # 11月15日 -> w3
            (datetime(2025, 11, 22, 12, 0), "gdas1.nov25.w4"),  # 11月22日 -> w4
            (datetime(2025, 11, 29, 12, 0), "gdas1.nov25.w5"),  # 11月29日 -> w5
            (datetime(2025, 10, 1, 12, 0), "gdas1.oct25.w1"),   # 10月
            (datetime(2024, 12, 15, 12, 0), "gdas1.dec24.w3"),  # 2024年
        ]

        for dt, expected_filename in test_cases:
            filename = manager._get_filename_for_date(dt)
            assert filename == expected_filename
            print(f"[OK] {dt.strftime('%Y-%m-%d')} -> {filename}")

        print("=" * 60)

    def test_week_of_month_calculation(self, manager):
        """测试月内周数计算"""
        print("\n" + "=" * 60)
        print("TEST 3: Week of Month Calculation")
        print("=" * 60)

        test_cases = [
            (datetime(2025, 11, 1), 1),
            (datetime(2025, 11, 7), 1),
            (datetime(2025, 11, 8), 2),
            (datetime(2025, 11, 14), 2),
            (datetime(2025, 11, 15), 3),
            (datetime(2025, 11, 21), 3),
            (datetime(2025, 11, 22), 4),
            (datetime(2025, 11, 28), 4),
            (datetime(2025, 11, 29), 5),
            (datetime(2025, 11, 30), 5),
        ]

        for dt, expected_week in test_cases:
            week = manager._get_week_of_month(dt)
            assert week == expected_week
            print(f"[OK] Day {dt.day:2d} -> Week {week}")

        print("=" * 60)

    def test_required_files_for_timerange(self, manager):
        """测试时间范围所需文件计算"""
        print("\n" + "=" * 60)
        print("TEST 4: Required Files for Time Range")
        print("=" * 60)

        # 测试1: 同一周内
        start = datetime(2025, 11, 1, 12, 0)
        end = datetime(2025, 11, 3, 12, 0)
        files = manager.get_required_files_for_timerange(start, end)

        print(f"\nTest 4.1: Same week")
        print(f"Start: {start}")
        print(f"End: {end}")
        print(f"Required files: {files}")

        assert len(files) == 1
        assert files[0] == "gdas1.nov25.w1"

        # 测试2: 跨周
        start = datetime(2025, 11, 5, 12, 0)
        end = datetime(2025, 11, 10, 12, 0)
        files = manager.get_required_files_for_timerange(start, end)

        print(f"\nTest 4.2: Across weeks")
        print(f"Start: {start}")
        print(f"End: {end}")
        print(f"Required files: {files}")

        assert len(files) == 2
        assert "gdas1.nov25.w1" in files
        assert "gdas1.nov25.w2" in files

        # 测试3: 跨月
        start = datetime(2025, 10, 28, 12, 0)
        end = datetime(2025, 11, 3, 12, 0)
        files = manager.get_required_files_for_timerange(start, end)

        print(f"\nTest 4.3: Across months")
        print(f"Start: {start}")
        print(f"End: {end}")
        print(f"Required files: {files}")

        assert len(files) >= 2
        assert any("oct25" in f for f in files)
        assert any("nov25" in f for f in files)

        print("=" * 60)

    def test_local_availability_check(self, manager, temp_cache_dir):
        """测试本地文件可用性检查"""
        print("\n" + "=" * 60)
        print("TEST 5: Local Availability Check")
        print("=" * 60)

        # 创建一些模拟文件
        test_files = [
            "gdas1.nov25.w1",
            "gdas1.nov25.w2",
        ]

        # 创建第一个文件
        file1 = Path(temp_cache_dir) / test_files[0]
        file1.write_bytes(b"mock data")

        # 检查可用性
        availability = manager.check_local_availability(test_files)

        print(f"\nAvailability check results:")
        for filename, available in availability.items():
            status = "[AVAILABLE]" if available else "[MISSING]"
            print(f"  {status} {filename}")

        assert availability[test_files[0]] is True
        assert availability[test_files[1]] is False

        print("=" * 60)

    def test_cache_stats(self, manager, temp_cache_dir):
        """测试缓存统计"""
        print("\n" + "=" * 60)
        print("TEST 6: Cache Statistics")
        print("=" * 60)

        # 创建一些模拟文件
        for i in range(3):
            filename = f"gdas1.nov25.w{i+1}"
            file_path = Path(temp_cache_dir) / filename
            file_path.write_bytes(b"mock data" * 1000)  # ~9KB each

        stats = manager.get_cache_stats()

        print(f"\nCache statistics:")
        print(f"  Total files: {stats['total_files']}")
        print(f"  Total size: {stats['total_size_mb']} MB")
        print(f"  Cache directory: {stats['cache_dir']}")

        assert stats["total_files"] == 3
        assert stats["total_size"] > 0

        print("=" * 60)

    def test_clean_old_cache(self, manager, temp_cache_dir):
        """测试清理过期缓存"""
        print("\n" + "=" * 60)
        print("TEST 7: Clean Old Cache")
        print("=" * 60)

        # 创建一些模拟文件
        import time
        old_file = Path(temp_cache_dir) / "gdas1.oct25.w1"
        new_file = Path(temp_cache_dir) / "gdas1.nov25.w1"

        old_file.write_bytes(b"old data")
        new_file.write_bytes(b"new data")

        # 修改旧文件的修改时间（40天前）
        old_time = time.time() - (40 * 24 * 3600)
        import os
        os.utime(old_file, (old_time, old_time))

        # 清理30天以上的文件
        result = manager.clean_old_cache(max_age_days=30)

        print(f"\nCleanup results:")
        print(f"  Files deleted: {result['files_deleted']}")
        print(f"  Files kept: {result['files_kept']}")
        print(f"  Space freed: {result['space_freed']} bytes")

        assert result["files_deleted"] == 1
        assert result["files_kept"] == 1
        assert not old_file.exists()
        assert new_file.exists()

        print("=" * 60)

    @pytest.mark.skip(reason="Requires network connection to NOAA FTP")
    def test_download_file_from_ftp(self, manager):
        """测试从FTP下载文件（需要网络连接）"""
        print("\n" + "=" * 60)
        print("TEST 8: Download File from FTP (SKIPPED - requires network)")
        print("=" * 60)

        # 尝试下载当前月的第一周数据
        now = datetime.utcnow()
        filename = manager._get_filename_for_date(now)

        print(f"Attempting to download: {filename}")

        result = manager.download_file(filename)

        if result["success"]:
            print(f"[OK] Download successful")
            print(f"  File: {result['filename']}")
            print(f"  Size: {result['file_size']} bytes")
            print(f"  Time: {result.get('download_time', 'N/A')} seconds")
        else:
            print(f"[FAIL] Download failed: {result.get('error')}")

        print("=" * 60)


def run_all_tests():
    """运行所有测试"""
    print("=" * 80)
    print("METEOROLOGICAL DATA MANAGER UNIT TESTS")
    print("=" * 80)
    print("\nNOTE: FTP download tests are skipped by default.")
    print("Real downloads require network connection to NOAA FTP server.")
    print("=" * 80)

    # 运行pytest
    exit_code = pytest.main([
        __file__,
        "-v",
        "-s",  # 显示print输出
        "--tb=short"
    ])

    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    if exit_code == 0:
        print("[OK] All tests passed")
        print("\nNext steps:")
        print("1. Test FTP download manually (remove @pytest.mark.skip)")
        print("2. Integrate with HYSPLITRealWrapper")
        print("3. Run end-to-end trajectory calculation")
    else:
        print("[FAIL] Some tests failed")
        print("\nPlease check the error messages above")

    print("=" * 80)

    return exit_code


if __name__ == "__main__":
    exit(run_all_tests())
