"""
Unit Tests for HYSPLIT CONTROL File Generator

测试CONTROL文件生成器的功能
"""

import unittest
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import os

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.utils.hysplit_control_generator import HYSPLITControlGenerator


class TestHYSPLITControlGenerator(unittest.TestCase):
    """HYSPLIT CONTROL文件生成器测试"""

    def setUp(self):
        """初始化测试"""
        self.generator = HYSPLITControlGenerator()
        self.test_start_time = datetime(2024, 10, 1, 12, 0, 0)

    def test_generate_backward_control(self):
        """测试生成后向轨迹CONTROL文件"""
        control = self.generator.generate_backward_control(
            lat=23.13,
            lon=113.26,
            height=100.0,
            start_time=self.test_start_time,
            hours=72,
            meteo_dir="data/meteo/gdas1/",
            meteo_files=["gdas1.oct24.w1"]
        )

        print("\n" + "=" * 60)
        print("TEST 1: Backward Trajectory CONTROL File")
        print("=" * 60)
        print(control)
        print("=" * 60)

        # 验证基本内容
        self.assertIn("24 10  1 12", control)  # 起始时间
        self.assertIn("1", control)  # 起始位置数量
        self.assertIn("23.1300 113.2600 100.0", control)  # 起始位置
        self.assertIn("-72", control)  # 后向72小时
        self.assertIn("gdas1.oct24.w1", control)  # 气象文件
        self.assertIn("tdump", control)  # 输出文件名

    def test_generate_forward_control(self):
        """测试生成正向轨迹CONTROL文件"""
        control = self.generator.generate_forward_control(
            lat=23.13,
            lon=113.26,
            height=100.0,
            start_time=self.test_start_time,
            hours=72,
            meteo_dir="data/meteo/gdas1/",
            meteo_files=["gdas1.oct24.w1", "gdas1.oct24.w2"]
        )

        print("\n" + "=" * 60)
        print("TEST 2: Forward Trajectory CONTROL File")
        print("=" * 60)
        print(control)
        print("=" * 60)

        # 验证基本内容
        self.assertIn("24 10  1 12", control)  # 起始时间
        self.assertIn("72", control)  # 正向72小时（不是-72）
        self.assertIn("2", control)  # 2个气象文件
        self.assertIn("gdas1.oct24.w1", control)
        self.assertIn("gdas1.oct24.w2", control)

    def test_write_control_file(self):
        """测试写入CONTROL文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            control = self.generator.generate_backward_control(
                lat=23.13,
                lon=113.26,
                height=100.0,
                start_time=self.test_start_time,
                hours=72,
                meteo_dir="data/meteo/gdas1/",
                meteo_files=["gdas1.oct24.w1"]
            )

            output_path = Path(tmpdir) / "CONTROL"
            self.generator.write_control_file(control, str(output_path))

            # 验证文件存在
            self.assertTrue(output_path.exists())

            # 验证文件内容
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertEqual(content, control)

            print("\n" + "=" * 60)
            print("TEST 3: Write CONTROL File")
            print("=" * 60)
            print(f"File written to: {output_path}")
            print(f"File size: {len(content)} bytes")
            print("=" * 60)

    def test_generate_setup_cfg(self):
        """测试生成SETUP.CFG文件"""
        setup = self.generator.generate_setup_cfg()

        print("\n" + "=" * 60)
        print("TEST 4: SETUP.CFG File")
        print("=" * 60)
        print(setup)
        print("=" * 60)

        # 验证基本内容
        self.assertIn("&SETUP", setup)
        self.assertIn("tratio = 0.75", setup)
        self.assertIn("mgmin = 10", setup)
        self.assertIn("/", setup)

    def test_multiple_meteo_files(self):
        """测试多个气象文件"""
        meteo_files = [
            "gdas1.oct24.w1",
            "gdas1.oct24.w2",
            "gdas1.oct24.w3"
        ]

        control = self.generator.generate_backward_control(
            lat=23.13,
            lon=113.26,
            height=100.0,
            start_time=self.test_start_time,
            hours=168,  # 7天
            meteo_dir="data/meteo/gdas1/",
            meteo_files=meteo_files
        )

        print("\n" + "=" * 60)
        print("TEST 5: Multiple Meteo Files (7-day trajectory)")
        print("=" * 60)
        print(control)
        print("=" * 60)

        # 验证气象文件数量
        self.assertIn("3", control)  # 3个文件
        for filename in meteo_files:
            self.assertIn(filename, control)

    def test_different_locations(self):
        """测试不同位置"""
        locations = [
            {"name": "Guangzhou", "lat": 23.13, "lon": 113.26},
            {"name": "Beijing", "lat": 39.90, "lon": 116.41},
            {"name": "Shanghai", "lat": 31.23, "lon": 121.47}
        ]

        print("\n" + "=" * 60)
        print("TEST 6: Different Locations")
        print("=" * 60)

        for loc in locations:
            control = self.generator.generate_backward_control(
                lat=loc["lat"],
                lon=loc["lon"],
                height=100.0,
                start_time=self.test_start_time,
                hours=72,
                meteo_dir="data/meteo/gdas1/",
                meteo_files=["gdas1.oct24.w1"]
            )

            print(f"\nLocation: {loc['name']}")
            print(f"Coordinates: {loc['lat']:.4f}, {loc['lon']:.4f}")

            # 验证坐标在CONTROL文件中
            coord_str = f"{loc['lat']:.4f} {loc['lon']:.4f}"
            self.assertIn(coord_str, control)

        print("=" * 60)

    def test_different_heights(self):
        """测试不同高度"""
        heights = [100, 500, 1000, 1500]

        print("\n" + "=" * 60)
        print("TEST 7: Different Heights")
        print("=" * 60)

        for height in heights:
            control = self.generator.generate_backward_control(
                lat=23.13,
                lon=113.26,
                height=float(height),
                start_time=self.test_start_time,
                hours=72,
                meteo_dir="data/meteo/gdas1/",
                meteo_files=["gdas1.oct24.w1"]
            )

            print(f"\nHeight: {height}m")

            # 验证高度在CONTROL文件中
            height_str = f"{float(height):.1f}"
            self.assertIn(height_str, control)

        print("=" * 60)


def run_all_tests():
    """运行所有测试"""
    print("=" * 80)
    print("HYSPLIT CONTROL GENERATOR UNIT TESTS")
    print("=" * 80)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestHYSPLITControlGenerator)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests: {result.testsRun}")
    print(f"Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failed: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun) * 100:.1f}%")
    print("=" * 80)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
