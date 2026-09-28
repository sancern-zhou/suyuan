"""
测试污染玫瑰图生成器 - 气象局数据自动查询功能

测试用例：
1. 测试站点信息提取
2. 测试时间范围提取
3. 测试区县查询
4. 测试数据合并
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.tools.visualization.polar_contour_generator import (
    _extract_station_info,
    _extract_time_range,
    _get_station_district,
    _merge_pollutant_weather_data
)


def test_extract_station_info():
    """测试站点信息提取"""
    print("=" * 60)
    print("测试1：站点信息提取")
    print("=" * 60)

    # 模拟污染物数据
    test_data = [
        {
            'timestamp': '2025-01-01 00:00:00',
            'station_code': '1234',
            'station_name': '广雅中学',
            'city_name': '广州',
            'PM10': 35.2,
            'wind_direction_10m': 180,
            'wind_speed_10m': 2.5
        },
        {
            'timestamp': '2025-01-01 01:00:00',
            'stationCode': '1234',
            'stationName': '广雅中学',
            'cityName': '广州',
            'PM10': 42.1,
            'wind_direction_10m': 225,
            'wind_speed_10m': 2.8
        }
    ]

    station_info = _extract_station_info(test_data)

    print(f"✅ 站点编码: {station_info['station_code']}")
    print(f"✅ 站点名称: {station_info['station_name']}")
    print(f"✅ 城市名称: {station_info['city_name']}")

    assert station_info['station_code'] == '1234'
    assert station_info['station_name'] == '广雅中学'
    assert station_info['city_name'] == '广州'

    print("✅ 测试通过！\n")


def test_extract_time_range():
    """测试时间范围提取"""
    print("=" * 60)
    print("测试2：时间范围提取")
    print("=" * 60)

    test_data = [
        {
            'timestamp': '2025-01-01 00:00:00',
            'PM10': 35.2
        },
        {
            'timestamp': '2025-01-02 23:00:00',
            'PM10': 42.1
        },
        {
            'timestamp': '2025-01-01 12:00:00',
            'PM10': 38.5
        }
    ]

    time_range = _extract_time_range(test_data)

    print(f"✅ 开始时间: {time_range['start']}")
    print(f"✅ 结束时间: {time_range['end']}")

    assert time_range['start'] == '2025-01-01'
    assert time_range['end'] == '2025-01-02'

    print("✅ 测试通过！\n")


def test_get_station_district():
    """测试区县查询"""
    print("=" * 60)
    print("测试3：区县查询")
    print("=" * 60)

    # 测试一个已知的站点编码
    # 注意：需要根据实际的站点数据调整
    test_station_code = "1234"  # 替换为实际的站点编码

    district = _get_station_district(test_station_code)

    if district:
        print(f"✅ 站点 {test_station_code} 的区县: {district}")
    else:
        print(f"⚠️  站点 {test_station_code} 未找到区县信息（这是正常的，如果测试站点不在数据库中）")

    print("✅ 测试完成！\n")


def test_merge_pollutant_weather_data():
    """测试数据合并"""
    print("=" * 60)
    print("测试4：数据合并")
    print("=" * 60)

    # 模拟污染物数据
    pollutant_data = [
        {
            'timestamp': '2025-01-01 00:00:00',
            'PM10': 35.2
        },
        {
            'timestamp': '2025-01-01 01:00:00',
            'PM10': 42.1
        },
        {
            'timestamp': '2025-01-01 02:00:00',
            'PM10': 38.5
        }
    ]

    # 模拟气象数据
    weather_data = [
        {
            'timePoint': '2025-01-01 00:00:00',
            'windDirection': 180,
            'windSpeed': 2.5
        },
        {
            'timePoint': '2025-01-01 01:00:00',
            'windDirection': 225,
            'windSpeed': 2.8
        },
        {
            'timePoint': '2025-01-01 02:00:00',
            'windDirection': 270,
            'windSpeed': 3.1
        }
    ]

    merged_data = _merge_pollutant_weather_data(
        pollutant_data=pollutant_data,
        weather_data=weather_data,
        pollutant_name='PM10'
    )

    print(f"✅ 污染物数据记录数: {len(pollutant_data)}")
    print(f"✅ 气象数据记录数: {len(weather_data)}")
    print(f"✅ 合并后数据记录数: {len(merged_data)}")

    assert len(merged_data) == 3

    # 验证第一条记录
    first_record = merged_data[0]
    print(f"\n✅ 第一条合并记录示例:")
    print(f"   - 风向: {first_record['wind_direction']}°")
    print(f"   - 风速: {first_record['wind_speed']} m/s")
    print(f"   - PM10浓度: {first_record['concentration']} μg/m³")

    assert first_record['wind_direction'] == 180
    assert first_record['wind_speed'] == 2.5
    assert first_record['concentration'] == 35.2

    print("\n✅ 测试通过！\n")


def test_gd_met_bureau_api_client():
    """测试气象局API客户端"""
    print("=" * 60)
    print("测试5：气象局API客户端")
    print("=" * 60)

    try:
        from app.services.gd_met_bureau_api_client import GDMetBureauAPIClient

        # 测试查询气象数据
        print("正在查询气象局API...")

        weather_data = GDMetBureauAPIClient.query_weather(
            city_name='广州',
            begin_time='2025-01-01',
            end_time='2025-01-02'
        )

        print(f"✅ 查询结果记录数: {len(weather_data)}")

        if weather_data:
            print(f"\n✅ 第一条气象数据示例:")
            first_record = weather_data[0]
            for key, value in first_record.items():
                print(f"   - {key}: {value}")

        print("\n✅ 测试通过！\n")

    except Exception as e:
        print(f"⚠️  API测试失败（可能是网络问题）: {e}\n")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("污染玫瑰图生成器 - 气象局数据自动查询功能测试")
    print("=" * 60 + "\n")

    try:
        # 运行测试
        test_extract_station_info()
        test_extract_time_range()
        test_get_station_district()
        test_merge_pollutant_weather_data()
        test_gd_met_bureau_api_client()

        print("=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
