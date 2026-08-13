"""
简化版测试运行器 - 不依赖pytest

直接运行三个脚本并验证输出
"""

import sys
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fetchers.consultation.monthly_district_pollutant_ranking import generate_district_ranking
from app.fetchers.consultation.monthly_station_high_values import generate_station_high_values
from app.fetchers.consultation.monthly_pollution_events_components import generate_pollution_events_components


def test_district_ranking():
    """测试区县排名脚本"""
    print("\n===== 测试区县排名脚本 =====")

    result_file = generate_district_ranking(2026, 5)

    # 验证文件存在
    assert result_file is not None, "区县排名文件生成失败"
    assert result_file.exists(), f"区县排名文件不存在：{result_file}"

    # 读取并验证数据
    with open(result_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        records = list(reader)

    # 验证记录数（广东区县应>=100）
    assert len(records) >= 100, f"区县数量不足：{len(records)}，预期>=100"

    # 验证字段
    fieldnames = reader.fieldnames
    required_fields = ["district", "city", "pm25", "pm25_yoy", "pm10", "pm10_yoy",
                      "no2", "no2_yoy", "o3", "o3_yoy", "aqi", "aqi_yoy",
                      "co", "co_yoy", "so2", "so2_yoy"]
    for field in required_fields:
        assert field in fieldnames, f"缺少字段：{field}"

    # 验证第一条记录
    first = records[0]
    assert first.get('district'), "第一条记录：区县名称为空"
    assert first.get('city'), "第一条记录：城市名称为空"

    # 验证非空率（核心污染物数据应至少80%非空）
    # 注意：AQI可能不适用于月度数据，所以只检查常规污染物
    pollutants = ['pm25', 'pm10', 'no2', 'o3', 'co', 'so2']
    for pollutant in pollutants:
        non_null_count = sum(1 for r in records if r.get(pollutant))
        non_null_rate = non_null_count / len(records)
        assert non_null_rate >= 0.8, f"{pollutant} 非空率不足：{non_null_rate:.1%}，预期>=80%"

    print(f"✓ 区县排名测试通过：{len(records)} 条记录")
    print(f"  核心污染物（PM2.5/PM10/NO2/O3/CO/SO2）非空率均>=80%")
    return result_file


def test_station_high_values():
    """测试高值站点脚本"""
    print("\n===== 测试高值站点脚本 =====")

    result_file = generate_station_high_values(2026, 5)

    # 验证文件存在
    assert result_file is not None, "高值站点文件生成失败"
    assert result_file.exists(), f"高值站点文件不存在：{result_file}"

    # 读取并验证数据
    with open(result_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        records = list(reader)

    # 验证记录数（至少要有一些高值站点）
    assert len(records) >= 1, f"高值站点数量不足：{len(records)}"

    # 验证字段
    fieldnames = reader.fieldnames
    required_fields = ["station", "city", "high_value_reason", "pm25", "pm25_yoy",
                      "pm10", "pm10_yoy", "no2", "no2_yoy", "o3", "o3_yoy",
                      "aqi", "aqi_yoy", "co", "co_yoy", "so2", "so2_yoy"]
    for field in required_fields:
        assert field in fieldnames, f"缺少字段：{field}"

    # 验证第一条记录
    first = records[0]
    assert first.get('station'), "第一条记录：站点名称为空"
    assert first.get('high_value_reason'), "第一条记录：高值原因为空"
    reason = first['high_value_reason']
    assert "_浓度" in reason or "_同比" in reason, f"高值原因格式错误：{reason}"

    # 验证非空率（核心污染物数据应至少80%非空）
    # 注意：AQI在站点数据中可能不全，所以只检查常规污染物
    pollutants = ['pm25', 'pm10', 'no2', 'o3', 'co', 'so2']
    for pollutant in pollutants:
        non_null_count = sum(1 for r in records if r.get(pollutant))
        non_null_rate = non_null_count / len(records)
        assert non_null_rate >= 0.8, f"{pollutant} 非空率不足：{non_null_rate:.1%}，预期>=80%"

    print(f"✓ 高值站点测试通过：{len(records)} 条记录")
    print(f"  核心污染物（PM2.5/PM10/NO2/O3/CO/SO2）非空率均>=80%")
    return result_file


def test_pollution_events():
    """测试污染过程脚本"""
    print("\n===== 测试污染过程脚本 =====")

    result_file = generate_pollution_events_components(2026, 5)

    # 如果没有污染过程，返回None是正常的
    if result_file is None:
        print("✓ 污染过程测试通过：无污染事件（正常）")
        return None

    # 如果有污染过程，验证文件
    assert result_file.exists(), f"污染过程文件不存在：{result_file}"

    # 读取并验证数据
    with open(result_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        records = list(reader)

    # 验证字段
    fieldnames = reader.fieldnames
    required_fields = ["city", "station", "date", "aqi", "primary_pollutant"]
    for field in required_fields:
        assert field in fieldnames, f"缺少字段：{field}"

    # 验证所有记录的AQI>100
    for record in records:
        try:
            aqi = float(record.get('aqi', 0))
            assert aqi > 100, f"污染过程AQI应>100：{aqi}"
        except (ValueError, TypeError) as e:
            raise AssertionError(f"AQI不是有效数字：{record.get('aqi')}")

    print(f"✓ 污染过程测试通过：{len(records)} 条记录")
    return result_file


def test_integration():
    """集成测试：验证所有文件在同一目录"""
    print("\n===== 集成测试 =====")

    district_file = test_district_ranking()
    station_file = test_station_high_values()
    pollution_file = test_pollution_events()

    # 验证文件在同一目录
    if pollution_file:
        assert district_file.parent == station_file.parent == pollution_file.parent, "文件输出目录不一致"
        print(f"\n✓ 所有文件在同一目录：{district_file.parent}")
    else:
        assert district_file.parent == station_file.parent, "文件输出目录不一致"
        print(f"\n✓ 所有文件在同一目录：{district_file.parent}")

    print("\n===== 全部测试通过 =====")
    print(f"1. 区县排名：{district_file}")
    print(f"2. 高值站点：{station_file}")
    if pollution_file:
        print(f"3. 污染过程：{pollution_file}")
    else:
        print(f"3. 污染过程：无（无污染事件）")


if __name__ == "__main__":
    try:
        test_integration()
        print("\n✓✓✓ 所有测试通过 ✓✓✓")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗✗✗ 测试失败 ✗✗✗")
        print(f"错误：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗✗✗ 测试异常 ✗✗✗")
        print(f"异常：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
