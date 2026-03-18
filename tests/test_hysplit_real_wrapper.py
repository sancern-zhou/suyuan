"""
Unit Tests for HYSPLIT Real Wrapper

测试HYSPLIT真实模型封装器完整集成
"""

import pytest
import asyncio
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.external_apis.hysplit_real_wrapper import HYSPLITRealWrapper


class TestHYSPLITRealWrapper:
    """HYSPLIT真实模型封装器测试"""

    @pytest.fixture
    def wrapper(self):
        """创建HYSPLITRealWrapper实例"""
        return HYSPLITRealWrapper(
            hysplit_exec_path="data/hysplit/exec/hyts_std.exe",
            working_dir="data/hysplit/working",
            timeout=30  # 缩短超时时间用于测试
        )

    @pytest.fixture
    def mock_meteo_files(self):
        """创建模拟气象数据文件"""
        # 创建临时目录
        tmpdir = tempfile.mkdtemp()
        meteo_dir = Path(tmpdir) / "meteo"
        meteo_dir.mkdir()

        # 创建空的ARL格式文件（仅用于路径测试）
        meteo_file = meteo_dir / "gdas1.nov25.w1"
        meteo_file.write_bytes(b"")

        yield [str(meteo_file)]

        # 清理
        shutil.rmtree(tmpdir)

    def test_wrapper_initialization(self, wrapper):
        """测试封装器初始化"""
        print("\n" + "=" * 60)
        print("TEST 1: Wrapper Initialization")
        print("=" * 60)

        assert wrapper is not None
        assert wrapper.hysplit_exec_path.exists()
        assert wrapper.working_dir.exists()
        assert wrapper.control_generator is not None
        assert wrapper.output_parser is not None
        assert wrapper.timeout == 30

        print(f"[OK] HYSPLIT exec path: {wrapper.hysplit_exec_path}")
        print(f"[OK] Working directory: {wrapper.working_dir}")
        print(f"[OK] Timeout: {wrapper.timeout}s")
        print("=" * 60)

    @pytest.mark.asyncio
    async def test_backward_trajectory_no_meteo(self, wrapper, mock_meteo_files):
        """测试后向轨迹（缺少气象数据场景）"""
        print("\n" + "=" * 60)
        print("TEST 2: Backward Trajectory (No Meteo Data)")
        print("=" * 60)

        result = await wrapper.run_backward_trajectory(
            lat=23.13,
            lon=113.26,
            height=100,
            start_time=datetime(2025, 11, 19, 12, 0),
            hours=24,
            meteo_data_paths=mock_meteo_files
        )

        print(f"Success: {result['success']}")
        print(f"Error: {result.get('error', 'N/A')}")
        print(f"Trajectory points: {len(result['trajectory'])}")
        print(f"Metadata: {result['metadata']}")

        # 预期失败（因为气象文件是空的）
        assert result["success"] is False
        assert "error" in result
        assert result["trajectory"] == []
        assert "metadata" in result

        print("\n[OK] Expected failure: Empty meteorological data file")
        print("=" * 60)

    @pytest.mark.asyncio
    async def test_forward_trajectory_no_meteo(self, wrapper, mock_meteo_files):
        """测试正向轨迹（缺少气象数据场景）"""
        print("\n" + "=" * 60)
        print("TEST 3: Forward Trajectory (No Meteo Data)")
        print("=" * 60)

        result = await wrapper.run_forward_trajectory(
            lat=23.13,
            lon=113.26,
            height=100,
            start_time=datetime(2025, 11, 19, 12, 0),
            hours=24,
            meteo_data_paths=mock_meteo_files
        )

        print(f"Success: {result['success']}")
        print(f"Error: {result.get('error', 'N/A')}")

        # 预期失败（因为气象文件是空的）
        assert result["success"] is False
        assert "error" in result

        print("\n[OK] Expected failure: Empty meteorological data file")
        print("=" * 60)

    @pytest.mark.asyncio
    async def test_missing_meteo_files(self, wrapper):
        """测试气象文件缺失场景"""
        print("\n" + "=" * 60)
        print("TEST 4: Missing Meteorological Files")
        print("=" * 60)

        result = await wrapper.run_backward_trajectory(
            lat=23.13,
            lon=113.26,
            height=100,
            start_time=datetime(2025, 11, 19, 12, 0),
            hours=24,
            meteo_data_paths=["/nonexistent/path/gdas1.nov25.w1"]
        )

        print(f"Success: {result['success']}")
        print(f"Error: {result.get('error', 'N/A')}")

        # 预期失败
        assert result["success"] is False
        assert "error" in result

        print("\n[OK] Expected failure: Meteorological files not found")
        print("=" * 60)

    @pytest.mark.asyncio
    async def test_invalid_parameters(self, wrapper, mock_meteo_files):
        """测试无效参数"""
        print("\n" + "=" * 60)
        print("TEST 5: Invalid Parameters")
        print("=" * 60)

        # 测试无效经纬度
        result = await wrapper.run_backward_trajectory(
            lat=999.0,  # 无效纬度
            lon=113.26,
            height=100,
            start_time=datetime(2025, 11, 19, 12, 0),
            hours=24,
            meteo_data_paths=mock_meteo_files
        )

        print(f"Success: {result['success']}")
        print(f"Error: {result.get('error', 'N/A')}")

        # HYSPLIT可能会执行失败或返回空结果
        assert "trajectory" in result
        assert "metadata" in result

        print("\n[OK] Invalid parameters handled")
        print("=" * 60)

    def test_control_generation_integration(self, wrapper):
        """测试CONTROL文件生成集成"""
        print("\n" + "=" * 60)
        print("TEST 6: CONTROL File Generation Integration")
        print("=" * 60)

        # 使用内部方法测试CONTROL生成
        control_content = wrapper._generate_control(
            lat=23.13,
            lon=113.26,
            height=100.0,
            start_time=datetime(2025, 11, 19, 12, 0),
            hours=24,
            direction="backward",
            meteo_dir="./meteo/",
            meteo_files=["gdas1.nov25.w1"]
        )

        print("CONTROL content generated:")
        print("-" * 40)
        print(control_content[:300])  # 打印前300字符
        print("-" * 40)

        assert "25 11 19 12" in control_content  # 起始时间
        assert "23.1300" in control_content  # 纬度
        assert "113.2600" in control_content  # 经度
        assert "100.0" in control_content  # 高度
        assert "-24" in control_content  # 后向24小时

        print("\n[OK] CONTROL file content validated")
        print("=" * 60)

    def test_meteo_files_preparation(self, wrapper, mock_meteo_files):
        """测试气象文件准备"""
        print("\n" + "=" * 60)
        print("TEST 7: Meteorological Files Preparation")
        print("=" * 60)

        meteo_info = wrapper._prepare_meteo_files(
            mock_meteo_files,
            Path(wrapper.working_dir)
        )

        print(f"Meteo directory: {meteo_info['meteo_dir']}")
        print(f"Meteo filenames: {meteo_info['meteo_filenames']}")

        assert "meteo_dir" in meteo_info
        assert "meteo_filenames" in meteo_info
        assert len(meteo_info["meteo_filenames"]) > 0
        assert meteo_info["meteo_dir"].endswith("/")

        print("\n[OK] Meteorological files prepared successfully")
        print("=" * 60)


def run_all_tests():
    """运行所有测试"""
    print("=" * 80)
    print("HYSPLIT REAL WRAPPER INTEGRATION TESTS")
    print("=" * 80)
    print("\nNOTE: These tests verify integration logic.")
    print("Real trajectory calculations require GDAS meteorological data.")
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
        print("[OK] All integration tests passed")
        print("\nNext steps:")
        print("1. Download GDAS meteorological data (Phase 3.1-4)")
        print("2. Run end-to-end test with real meteo data")
        print("3. Integrate with TrajectoryCalculatorService")
    else:
        print("[FAIL] Some tests failed")
        print("\nPlease check the error messages above")

    print("=" * 80)

    return exit_code


if __name__ == "__main__":
    exit(run_all_tests())
