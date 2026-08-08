"""
月度数据补充脚本的pytest测试

测试三个独立脚本：
1. 区县污染物排名：monthly_district_pollutant_ranking.py
2. 高值站点数据：monthly_station_high_values.py
3. 污染过程与组分：monthly_pollution_events_components.py

测试断言：
- 输出文件存在
- 行数达到预期
- 关键字段非空
- 同比字段存在
- 无污染过程时不生成分组分文件
"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fetchers.consultation.monthly_district_pollutant_ranking import generate_district_pollutant_ranking
from app.fetchers.consultation.monthly_station_high_values import generate_station_high_values
from app.fetchers.consultation.monthly_pollution_events_components import (
    MonthlyPollutionEventsComponents,
    generate_pollution_events_components,
)


class TestMonthlyDistrictRanking:
    """测试区县污染物排名脚本"""

    def test_district_ranking_file_exists(self):
        """测试区县排名文件是否存在"""
        result = generate_district_pollutant_ranking(2026, 5)
        assert result is not None, "区县排名文件生成失败"
        assert result.exists(), f"区县排名文件不存在：{result}"

    def test_district_ranking_min_records(self):
        """测试区县排名记录数量（广东区县数应>100）"""
        result = generate_district_pollutant_ranking(2026, 5)
        if result:
            import csv
            with open(result, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                records = list(reader)
                # 广东区县数量应该超过100
                assert len(records) >= 100, f"区县数量不足：{len(records)}，预期>=100"

    def test_district_ranking_required_fields(self):
        """测试区县排名必需字段"""
        result = generate_district_pollutant_ranking(2026, 5)
        if result:
            import csv
            with open(result, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i == 0:  # 只检查第一条记录
                        assert row.get('district'), "缺少district字段"
                        assert row.get('city'), "缺少city字段"

                        # 检查至少有一个污染物有数据
                        has_pollutant = any(row.get(p) for p in ['pm25', 'pm10', 'no2', 'o3', 'co', 'so2'])
                        assert has_pollutant, "所有污染物字段都为空"
                        break

    def test_district_ranking_yoy_fields(self):
        """测试区县排名同比字段存在"""
        result = generate_district_pollutant_ranking(2026, 5)
        if result:
            import csv
            with open(result, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                # 检查是否有同比字段
                yoy_fields = [f for f in fieldnames if f.endswith('_yoy')]
                assert len(yoy_fields) >= 7, f"同比字段不足：{yoy_fields}"

    def test_district_ranking_outputs_city_name_and_code(self):
        """区县数据应同时输出中文城市名和城市编码"""
        from app.fetchers.consultation.monthly_district_pollutant_ranking import (
            MonthlyDistrictPollutantRanking,
        )
        generator = MonthlyDistrictPollutantRanking(2026, 5)
        assert generator.output_dir == Path("/tmp/A会商文件/2026年05月")
        current = {
            "天河区": {"city": "440100", "pm25": 20.0},
        }
        last_year = {
            "天河区": {"city": "440100", "pm25": 25.0},
        }

        rows = generator._merge_with_yoy(current, last_year)

        assert rows[0]["city"] == "广州"
        assert rows[0]["city_code"] == "440100"


class TestMonthlyStationHighValues:
    """测试高值站点脚本"""

    def test_station_high_values_file_exists(self):
        """测试高值站点文件是否存在"""
        result = generate_station_high_values(2026, 5)
        assert result is not None, "高值站点文件生成失败"
        assert result.exists(), f"高值站点文件不存在：{result}"

    def test_station_high_values_min_records(self):
        """测试高值站点记录数量（至少应该有几个高值站点）"""
        result = generate_station_high_values(2026, 5)
        if result:
            import csv
            with open(result, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                records = list(reader)
                # 高值站点数量应该超过0
                assert len(records) >= 1, f"高值站点数量不足：{len(records)}"

    def test_station_high_values_required_fields(self):
        """测试高值站点必需字段"""
        result = generate_station_high_values(2026, 5)
        if result:
            import csv
            with open(result, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i == 0:  # 只检查第一条记录
                        assert row.get('station'), "缺少station字段"
                        assert row.get('high_value_reason'), "缺少high_value_reason字段"

                        # 检查至少有一个污染物有数据
                        has_pollutant = any(row.get(p) for p in ['pm25', 'pm10', 'no2', 'o3', 'co', 'so2'])
                        assert has_pollutant, "所有污染物字段都为空"
                        break

    def test_station_high_values_yoy_fields(self):
        """测试高值站点同比字段存在"""
        result = generate_station_high_values(2026, 5)
        if result:
            import csv
            with open(result, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                # 检查是否有同比字段
                yoy_fields = [f for f in fieldnames if f.endswith('_yoy')]
                assert len(yoy_fields) >= 7, f"同比字段不足：{yoy_fields}"

    def test_station_high_values_outputs_city_name_and_code(self):
        """站点数据应把行政区划码映射为中文城市名，并保留城市编码"""
        from app.fetchers.consultation.monthly_station_high_values import (
            MonthlyStationHighValues,
        )
        generator = MonthlyStationHighValues(2026, 5)
        assert generator.output_dir == Path("/tmp/A会商文件/2026年05月")
        current = {
            "郁南城西": {"city": "445300", "pm25": 20.0},
        }
        last_year = {
            "郁南城西": {"city": "445300", "pm25": 10.0},
        }

        rows = generator._merge_station_with_yoy(current, last_year)

        assert rows[0]["city"] == "云浮"
        assert rows[0]["city_code"] == "445300"


class TestMonthlyPollutionEvents:
    """测试污染过程脚本"""

    def test_pollution_events_defaults_to_consultation_file_dir(self):
        """污染过程数据默认输出到A会商文件月度目录"""
        generator = MonthlyPollutionEventsComponents(2026, 5)

        assert generator.output_dir == Path("/tmp/A会商文件/2026年05月")

    def test_pollution_events_no_data_is_ok(self):
        """测试无污染过程时返回None（正常情况）"""
        result = generate_pollution_events_components(2026, 5)
        # 如果5月没有污染过程，返回None是正常的
        if result is None:
            assert True, "无污染过程是正常情况"
        else:
            # 如果有污染过程，验证文件存在
            assert result.exists(), f"污染过程文件不存在：{result}"

    def test_pollution_events_no_event_writes_explicit_outputs(self, tmp_path, monkeypatch):
        """无污染过程时也应显式输出空事件文件和组分清单"""
        generator = MonthlyPollutionEventsComponents(2026, 5)
        generator.output_dir = tmp_path

        monkeypatch.setattr(
            generator,
            "fetch_city_day_data",
            lambda: [
                {
                    "cityName": "广州",
                    "stationName": "广州",
                    "timePoint": "2026-05-10",
                    "AQI": 80,
                    "primaryPollutant": "O3",
                }
            ],
        )

        result = generator.generate()

        pollution_file = tmp_path / "pollution_events_202605.csv"
        manifest = tmp_path / "component_data_manifest_202605.json"
        assert result == pollution_file
        assert pollution_file.exists()
        assert manifest.exists()

        import csv
        import json
        with open(pollution_file, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        with open(manifest, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        assert rows == []
        assert manifest_data["status"] == "no_pollution_events"
        assert manifest_data["event_count"] == 0

    def test_pollution_events_required_fields(self):
        """测试污染过程必需字段"""
        result = generate_pollution_events_components(2026, 5)
        if result is None:
            # 无污染过程时跳过测试
            return

        import csv
        with open(result, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames

            # 检查必需字段
            required_fields = ["city", "station", "date", "aqi", "primary_pollutant"]
            for field in required_fields:
                assert field in fieldnames, f"缺少字段：{field}"

            # 验证所有污染记录的AQI>100
            for row in reader:
                try:
                    aqi = float(row.get('aqi', 0))
                    assert aqi > 100, f"污染过程AQI应>100：{aqi}"
                except (ValueError, TypeError):
                    pytest.fail(f"AQI不是有效数字：{row.get('aqi')}")

    def test_pollution_events_generate_component_manifest(self, tmp_path, monkeypatch):
        """有污染过程时应生成小时数据、组分数据和清单"""
        generator = MonthlyPollutionEventsComponents(2026, 5)
        generator.output_dir = tmp_path

        monkeypatch.setattr(
            generator,
            "fetch_city_day_data",
            lambda: [
                {
                    "cityName": "广州",
                    "stationName": "广雅中学",
                    "timePoint": "2026-05-10",
                    "AQI": 128,
                    "primaryPollutant": "O3",
                }
            ],
        )
        monkeypatch.setattr(
            generator,
            "fetch_hourly_pollutants",
            lambda event: [{"timestamp": "2026-05-10 00:00:00", "station": "广雅中学", "O3": 190}],
        )
        monkeypatch.setattr(
            generator,
            "fetch_component_dataset",
            lambda event, component_type: [
                {"timestamp": "2026-05-10 00:00:00", "station": "广雅中学", component_type: 1.2}
            ],
        )

        result = generator.generate()

        assert result is not None
        assert result.exists()
        manifest = tmp_path / "component_data_manifest_202605.json"
        assert manifest.exists()
        generated_names = {path.name for path in tmp_path.iterdir()}
        assert "pollution_events_202605.csv" in generated_names
        assert any(name.startswith("hourly_pollution_") for name in generated_names)
        assert any(name.startswith("vocs_components_") for name in generated_names)
        assert any(name.startswith("pm25_ionic_components_") for name in generated_names)


# 集成测试：一起生成并验证
class TestMonthlyDataIntegration:
    """集成测试：生成所有数据并验证"""

    def test_generate_all_monthly_data(self):
        """测试生成所有月度数据"""
        print("\n===== 集成测试：生成所有月度数据 =====")

        # 1. 生成区县排名
        print("1. 生成区县排名...")
        district_file = generate_district_pollutant_ranking(2026, 5)
        assert district_file is not None, "区县排名生成失败"

        # 2. 生成高值站点
        print("2. 生成高值站点...")
        station_file = generate_station_high_values(2026, 5)
        assert station_file is not None, "高值站点生成失败"

        # 3. 生成污染过程（可能返回None）
        print("3. 生成污染过程...")
        pollution_file = generate_pollution_events_components(2026, 5)

        # 4. 验证文件在同一目录
        print("4. 验证文件位置...")
        if pollution_file:
            assert district_file.parent == station_file.parent == pollution_file.parent, "文件输出目录不一致"
            print(f"\n✓ 集成测试通过")
            print(f"  区县排名：{district_file}")
            print(f"  高值站点：{station_file}")
            print(f"  污染过程：{pollution_file}")
        else:
            assert district_file.parent == station_file.parent, "文件输出目录不一致"
            print(f"\n✓ 集成测试通过")
            print(f"  区县排名：{district_file}")
            print(f"  高值站点：{station_file}")
            print(f"  污染过程：无（无污染事件）")


if __name__ == "__main__":
    # 可以直接运行：python test_monthly_data_scripts.py
    pytest.main([__file__, "-v", "-s"])
