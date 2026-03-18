"""
测试广东省 Suncere API 返回的数据结构

测试两个接口：
1. DATCityDay - 日报数据接口
2. GetReportForRangeListFilterAsync - 统计报表接口
"""

import asyncio
import json
from datetime import datetime
from app.services.gd_suncere_api_client import get_gd_suncere_api_client


async def test_day_data_api():
    """测试日报数据接口"""
    print("\n" + "="*80)
    print("测试 1: 日报数据接口 (DATCityDay)")
    print("="*80)

    try:
        api_client = get_gd_suncere_api_client()

        # 查询参数
        city_codes = ["440100"]  # 广州
        start_date = "2026-03-01"
        end_date = "2026-03-07"

        print(f"查询参数:")
        print(f"  - 城市: 广州 ({city_codes})")
        print(f"  - 日期范围: {start_date} 至 {end_date}")

        response = api_client.query_city_day_data(
            city_codes=city_codes,
            start_date=start_date,
            end_date=end_date
        )

        print(f"\n响应状态: {'成功' if response.get('success') else '失败'}")

        if response.get("success"):
            result = response.get("result", [])
            print(f"返回记录数: {len(result)}")

            if result:
                first_record = result[0]
                print(f"\n第一条记录的所有字段 ({len(first_record)} 个):")
                for i, (key, value) in enumerate(first_record.items(), 1):
                    value_preview = str(value)[:100] if value is not None else "None"
                    print(f"  {i:2d}. {key:30s} = {value_preview}")

                # 检查城市相关字段
                print(f"\n城市相关字段检查:")
                city_related_fields = ['city', 'city_name', 'cityName', 'CityName', 'cityCode', 'CityCode', '城市', '城市名称']
                for field in city_related_fields:
                    if field in first_record:
                        print(f"  ✓ {field} = {first_record[field]}")
                    else:
                        print(f"  ✗ {field} (不存在)")

                # 保存完整响应
                output_file = "tests/day_data_response.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(response, f, ensure_ascii=False, indent=2)
                print(f"\n完整响应已保存到: {output_file}")
        else:
            print(f"错误信息: {response.get('msg', 'Unknown error')}")

    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()


async def test_report_data_api():
    """测试统计报表接口"""
    print("\n" + "="*80)
    print("测试 2: 统计报表接口 (GetReportForRangeListFilterAsync)")
    print("="*80)

    try:
        api_client = get_gd_suncere_api_client()

        # 查询参数
        city_codes = ["440100"]  # 广州
        start_time = "2026-03-01 00:00:00"
        end_time = "2026-03-07 23:59:59"

        print(f"查询参数:")
        print(f"  - 城市: 广州 ({city_codes})")
        print(f"  - 时间范围: {start_time} 至 {end_time}")

        # 计算数据源类型
        from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool
        data_source = QueryGDSuncereDataTool.calculate_data_source(end_time)
        print(f"  - 数据源类型: {data_source} ({'原始实况' if data_source == 0 else '审核实况'})")

        endpoint = "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeListFilterAsync"
        payload = {
            "AreaType": 2,  # 城市级别
            "TimeType": 8,  # 任意时间
            "TimePoint": [start_time, end_time],
            "StationCode": city_codes,
            "DataSource": data_source
        }

        token = api_client.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "SysCode": "SunAirProvince",
            "syscode": "SunAirProvince",
            "Content-Type": "application/json"
        }

        url = f"{api_client.BASE_URL}{endpoint}"
        print(f"\n请求端点: {endpoint}")
        print(f"完整URL: {url}")

        import requests
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        print(f"\nHTTP状态码: {response.status_code}")

        if response.status_code == 200:
            response_data = response.json()
            print(f"响应成功: {response_data.get('success')}")

            if response_data.get("success"):
                result = response_data.get("result")

                # 处理不同的响应格式
                if isinstance(result, list):
                    records = result
                    print(f"返回格式: 列表，记录数 = {len(records)}")
                elif isinstance(result, dict):
                    records = result.get("items", [])
                    print(f"返回格式: 字典，items 记录数 = {len(records)}")
                    print(f"字典键: {list(result.keys())}")
                else:
                    records = []
                    print(f"返回格式: 未知类型 {type(result)}")

                if records:
                    first_record = records[0]
                    print(f"\n第一条记录的所有字段 ({len(first_record)} 个):")
                    for i, (key, value) in enumerate(first_record.items(), 1):
                        value_preview = str(value)[:100] if value is not None else "None"
                        print(f"  {i:2d}. {key:30s} = {value_preview}")

                    # 检查城市相关字段
                    print(f"\n城市相关字段检查:")
                    city_related_fields = ['city', 'city_name', 'cityName', 'CityName', 'cityCode', 'CityCode', '城市', '城市名称']
                    for field in city_related_fields:
                        if field in first_record:
                            print(f"  ✓ {field} = {first_record[field]}")
                        else:
                            print(f"  ✗ {field} (不存在)")

                    # 保存完整响应
                    output_file = "tests/report_data_response.json"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(response_data, f, ensure_ascii=False, indent=2)
                    print(f"\n完整响应已保存到: {output_file}")
                else:
                    print("没有返回记录")
            else:
                print(f"API 错误: {response_data.get('msg', 'Unknown error')}")
        else:
            print(f"HTTP 错误: {response.text[:500]}")

    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """运行所有测试"""
    print("\n" + "="*80)
    print("广东省 Suncere API 数据结构测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    await test_day_data_api()
    await test_report_data_api()

    print("\n" + "="*80)
    print("测试完成")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
