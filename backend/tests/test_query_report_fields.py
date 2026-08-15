"""
测试 query_gd_suncere_report 工具的 API 返回字段
"""
import asyncio
from datetime import datetime
from app.tools.query.query_gd_suncere.tool import execute_query_gd_suncere_report


async def test_query_report_fields():
    """测试 query_gd_suncere_report 返回的字段"""
    print("\n" + "="*80)
    print("测试 query_gd_suncere_report 工具")
    print("="*80)

    try:
        # 查询参数
        cities = ["广州"]
        start_time = "2026-03-01 00:00:00"
        end_time = "2026-03-07 23:59:59"
        time_type = 8  # 任意时间
        area_type = 2  # 城市级别

        print(f"\n查询参数:")
        print(f"  - 城市: {cities}")
        print(f"  - 时间范围: {start_time} 至 {end_time}")
        print(f"  - 报表类型: {time_type} (任意时间)")
        print(f"  - 区域类型: {area_type} (城市级别)")

        # 调用工具
        result = execute_query_gd_suncere_report(
            cities=cities,
            start_time=start_time,
            end_time=end_time,
            time_type=time_type,
            area_type=area_type
        )

        print(f"\n响应状态: {result.get('status')}")
        print(f"成功: {result.get('success')}")

        if result.get("success") and result.get("data"):
            data = result.get("data")
            print(f"\n返回记录数: {len(data)}")

            if data:
                first_record = data[0]
                print(f"\n第一条记录的所有字段 ({len(first_record)} 个):")
                print("="*80)

                # 按类别分组显示字段
                basic_fields = []
                concentration_fields = []
                index_fields = []
                level_fields = []
                max_fields = []
                other_fields = []

                for key, value in first_record.items():
                    value_preview = str(value)[:50] if value is not None else "None"
                    field_line = f"  {key:30s} = {value_preview}"

                    if key in ["cityCode", "cityName", "districtCode", "districtName", "stationCode", "stationName", "timePoint"]:
                        basic_fields.append(field_line)
                    elif "o3" in key.lower() or "so2" in key.lower() or "no2" in key.lower() or "pm" in key.lower() or "co" in key.lower():
                        if "Max" in key or "max" in key:
                            max_fields.append(field_line)
                        elif "Index" in key or "index" in key:
                            index_fields.append(field_line)
                        else:
                            concentration_fields.append(field_line)
                    elif "Level" in key or "level" in key or "Rate" in key or "rate" in key:
                        level_fields.append(field_line)
                    else:
                        other_fields.append(field_line)

                print("\n【基本信息】")
                for line in basic_fields:
                    print(line)

                print("\n【浓度字段】")
                for line in concentration_fields:
                    print(line)

                print("\n【指数字段】")
                for line in index_fields:
                    print(line)

                print("\n【等级/比率字段】")
                for line in level_fields:
                    print(line)

                print("\n【最大值字段】")
                for line in max_fields:
                    print(line)

                print("\n【其他字段】")
                for line in other_fields:
                    print(line)

                # 检查是否有百分位数字段
                print("\n" + "="*80)
                print("【百分位数字段检查】")
                print("="*80)

                percentile_keywords = ["P95", "p95", "P90", "p90", "percentile", "Percentile"]
                found_percentile = False

                for key in first_record.keys():
                    for keyword in percentile_keywords:
                        if keyword in key:
                            print(f"  ✓ 发现百分位数字段: {key} = {first_record[key]}")
                            found_percentile = True
                            break

                if not found_percentile:
                    print("  ✗ 未发现百分位数字段 (P95, P90 等)")
                    print("  说明: API 可能只在内部使用百分位数计算综合指数，但不返回百分位数值本身")

        else:
            print(f"\n错误信息: {result.get('error', 'Unknown error')}")
            if result.get("summary"):
                print(f"摘要: {result.get('summary')}")

    except Exception as e:
        print(f"\n异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_query_report_fields())
