"""
Unit Tests for HYSPLIT Output Parser

测试HYSPLIT输出解析器功能
"""

import unittest
from datetime import datetime
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.utils.hysplit_output_parser import HYSPLITOutputParser


# 模拟的tdump文件内容（后向轨迹，72小时）
MOCK_TDUMP_BACKWARD = """     1 BACKWARD OMEGA
    24 10  1 12     1
    24 10  1 12  0   23.1300  113.2600   100.0
    24 10  1 12  0   23.1300  113.2600   100.0
    24 10  1 11  1   23.1450  113.2300   105.5
    24 10  1 10  2   23.1600  113.2000   110.2
    24 10  1  9  3   23.1750  113.1700   115.0
    24 10  1  8  4   23.1900  113.1400   120.3
    24 10  1  7  5   23.2050  113.1100   125.8
    24 10  1  6  6   23.2200  113.0800   131.5
    24 10  1  5  7   23.2350  113.0500   137.4
    24 10  1  4  8   23.2500  113.0200   143.5
    24 10  1  3  9   23.2650  112.9900   149.8
    24 10  1  2 10   23.2800  112.9600   156.3
    24 10  1  1 11   23.2950  112.9300   163.0
    24 10  1  0 12   23.3100  112.9000   169.9
    24  9 30 23 13   23.3250  112.8700   177.0
    24  9 30 22 14   23.3400  112.8400   184.3
    24  9 30 21 15   23.3550  112.8100   191.8
    24  9 30 20 16   23.3700  112.7800   199.5
    24  9 30 19 17   23.3850  112.7500   207.4
    24  9 30 18 18   23.4000  112.7200   215.5
    24  9 30 17 19   23.4150  112.6900   223.8
    24  9 30 16 20   23.4300  112.6600   232.3
    24  9 30 15 21   23.4450  112.6300   241.0
    24  9 30 14 22   23.4600  112.6000   249.9
    24  9 30 13 23   23.4750  112.5700   259.0
    24  9 30 12 24   23.4900  112.5400   268.3
"""

# 模拟的正向轨迹tdump
MOCK_TDUMP_FORWARD = """     1 FORWARD OMEGA
    24 10  1 12     1
    24 10  1 12  0   23.1300  113.2600   100.0
    24 10  1 12  0   23.1300  113.2600   100.0
    24 10  1 13  1   23.1150  113.2900   95.5
    24 10  1 14  2   23.1000  113.3200   91.0
    24 10  1 15  3   23.0850  113.3500   86.5
    24 10  1 16  4   23.0700  113.3800   82.0
    24 10  1 17  5   23.0550  113.4100   77.5
"""


class TestHYSPLITOutputParser(unittest.TestCase):
    """HYSPLIT输出解析器测试"""

    def setUp(self):
        """初始化测试"""
        self.parser = HYSPLITOutputParser()

    def test_parse_backward_tdump(self):
        """测试解析后向轨迹tdump文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(MOCK_TDUMP_BACKWARD)
            tdump_path = f.name

        try:
            result = self.parser.parse_tdump(tdump_path)

            print("\n" + "=" * 60)
            print("TEST 1: Parse Backward Trajectory tdump")
            print("=" * 60)
            print(f"Success: {result['success']}")
            print(f"Points count: {len(result['trajectory'])}")
            print(f"Start time: {result['metadata']['start_time']}")
            print(f"Start position: {result['metadata']['start_lat']}, {result['metadata']['start_lon']}")
            print(f"Start height: {result['metadata']['start_height']}m")

            # 打印前5个点
            print("\nFirst 5 points:")
            for i, point in enumerate(result['trajectory'][:5]):
                print(f"  Point {i}: age={point['age_hours']}h, "
                      f"lat={point['lat']}, lon={point['lon']}, "
                      f"height={point['height']}m")

            print("=" * 60)

            # 验证
            self.assertTrue(result['success'])
            self.assertGreater(len(result['trajectory']), 0)
            self.assertEqual(result['metadata']['start_time'], "2024-10-01T12:00:00Z")
            self.assertEqual(result['metadata']['start_lat'], 23.13)
            self.assertEqual(result['metadata']['start_lon'], 113.26)
            self.assertEqual(result['metadata']['start_height'], 100.0)

            # 验证第一个点
            first_point = result['trajectory'][0]
            self.assertEqual(first_point['age_hours'], 0)
            self.assertEqual(first_point['lat'], 23.13)
            self.assertEqual(first_point['lon'], 113.26)
            self.assertEqual(first_point['height'], 100.0)

        finally:
            Path(tdump_path).unlink()

    def test_parse_forward_tdump(self):
        """测试解析正向轨迹tdump文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(MOCK_TDUMP_FORWARD)
            tdump_path = f.name

        try:
            result = self.parser.parse_tdump(tdump_path)

            print("\n" + "=" * 60)
            print("TEST 2: Parse Forward Trajectory tdump")
            print("=" * 60)
            print(f"Success: {result['success']}")
            print(f"Points count: {len(result['trajectory'])}")

            # 打印所有点
            print("\nAll points:")
            for i, point in enumerate(result['trajectory']):
                print(f"  Point {i}: age={point['age_hours']}h, "
                      f"lat={point['lat']}, lon={point['lon']}, "
                      f"height={point['height']}m")

            print("=" * 60)

            # 验证
            self.assertTrue(result['success'])
            self.assertEqual(len(result['trajectory']), 6)  # 6个点

            # 验证最后一个点
            last_point = result['trajectory'][-1]
            self.assertEqual(last_point['age_hours'], 5)

        finally:
            Path(tdump_path).unlink()

    def test_convert_to_udf_v2(self):
        """测试转换为UDF v2.0格式"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(MOCK_TDUMP_BACKWARD)
            tdump_path = f.name

        try:
            parse_result = self.parser.parse_tdump(tdump_path)
            udf_result = self.parser.convert_to_udf_v2(
                parse_result,
                direction="backward"
            )

            print("\n" + "=" * 60)
            print("TEST 3: Convert to UDF v2.0 Format")
            print("=" * 60)
            print(f"Status: {udf_result['status']}")
            print(f"Success: {udf_result['success']}")
            print(f"Schema version: {udf_result['metadata']['schema_version']}")
            print(f"Generator: {udf_result['metadata']['generator']}")
            print(f"Scenario: {udf_result['metadata']['scenario']}")
            print(f"Record count: {udf_result['metadata']['record_count']}")
            print(f"Algorithm: {udf_result['metadata']['algorithm']}")
            print(f"Data source: {udf_result['metadata']['data_source']}")
            print("=" * 60)

            # 验证UDF v2.0格式
            self.assertEqual(udf_result['status'], 'success')
            self.assertTrue(udf_result['success'])
            self.assertEqual(udf_result['metadata']['schema_version'], 'v2.0')
            self.assertEqual(udf_result['metadata']['generator'], 'hysplit_real_v5')
            self.assertEqual(udf_result['metadata']['scenario'], 'backward_trajectory_hysplit')
            self.assertGreater(udf_result['metadata']['record_count'], 0)

        finally:
            Path(tdump_path).unlink()

    def test_pressure_temperature_estimation(self):
        """测试气压和温度估算"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(MOCK_TDUMP_BACKWARD)
            tdump_path = f.name

        try:
            result = self.parser.parse_tdump(tdump_path)

            print("\n" + "=" * 60)
            print("TEST 4: Pressure and Temperature Estimation")
            print("=" * 60)

            # 打印前5个点的气象参数
            for i, point in enumerate(result['trajectory'][:5]):
                print(f"Point {i}: height={point['height']}m, "
                      f"pressure={point['pressure']}hPa, "
                      f"temperature={point['temperature']}°C")

            print("=" * 60)

            # 验证气压和温度存在且合理
            for point in result['trajectory']:
                self.assertIn('pressure', point)
                self.assertIn('temperature', point)
                self.assertGreater(point['pressure'], 0)
                self.assertLess(point['temperature'], 50)  # 合理范围

        finally:
            Path(tdump_path).unlink()

    def test_file_not_found(self):
        """测试文件不存在的情况"""
        result = self.parser.parse_tdump("nonexistent_file.txt")

        print("\n" + "=" * 60)
        print("TEST 5: File Not Found")
        print("=" * 60)
        print(f"Success: {result['success']}")
        print(f"Error: {result.get('error')}")
        print("=" * 60)

        self.assertFalse(result['success'])
        self.assertIn('error', result)

    def test_empty_file(self):
        """测试空文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("")  # 空文件
            tdump_path = f.name

        try:
            result = self.parser.parse_tdump(tdump_path)

            print("\n" + "=" * 60)
            print("TEST 6: Empty File")
            print("=" * 60)
            print(f"Success: {result['success']}")
            print(f"Error: {result.get('error')}")
            print("=" * 60)

            self.assertFalse(result['success'])

        finally:
            Path(tdump_path).unlink()


def run_all_tests():
    """运行所有测试"""
    print("=" * 80)
    print("HYSPLIT OUTPUT PARSER UNIT TESTS")
    print("=" * 80)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestHYSPLITOutputParser)
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
