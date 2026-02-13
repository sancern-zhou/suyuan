"""
测试颗粒物离子组分API
"""
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.utils.particulate_api_client import get_particulate_api_client
import json

def test_ionic_api():
    client = get_particulate_api_client()

    # 测试多个时间段
    test_cases = [
        # 2024年数据（可能存在）
        {
            "name": "2024年1月",
            "station": "新兴",
            "code": "1042b",
            "start": "2024-01-01 00:00:00",
            "end": "2024-01-31 23:59:59",
            "time_type": 1
        },
        # 2024年4月（之前的日志尝试的时间）
        {
            "name": "2024年4月",
            "station": "新兴",
            "code": "1042b",
            "start": "2024-04-01 00:00:00",
            "end": "2024-04-30 23:59:59",
            "time_type": 1
        },
        # 单日测试
        {
            "name": "2024年4月9日单日",
            "station": "新兴",
            "code": "1042b",
            "start": "2024-04-09 00:00:00",
            "end": "2024-04-09 23:59:59",
            "time_type": 1
        }
    ]

    for test in test_cases:
        print(f"\n{'='*60}")
        print(f"测试: {test['name']}")
        print(f"时间: {test['start']} ~ {test['end']}")
        print(f"{'='*60}")

        result = client.get_ionic_analysis(
            station=test['station'],
            code=test['code'],
            start_time=test['start'],
            end_time=test['end'],
            time_type=test['time_type'],
            data_type=0
        )

        print(f"\nAPI调用状态: {result.get('success')}")

        if not result.get('success'):
            print(f"错误: {result.get('error')}")
            continue

        api_response = result.get('api_response', {})
        result_data = api_response.get('result', {})
        records = result_data.get('resultOne', [])

        print(f"记录数: {len(records)}")

        if records:
            print(f"\n✅ 找到数据！")
            print(f"首条记录:")
            first = records[0]
            print(f"  时间: {first.get('TimePoint')}")
            print(f"  站点: {first.get('StationName')}")
            print(f"  编码: {first.get('Code')}")

            # 显示离子数据
            ions = ['SO₄²⁻', 'NO₃⁻', 'NH₄⁺', 'Cl⁻', 'Na⁺', 'K⁺', 'Mg²⁺', 'Ca²⁺']
            print(f"\n  离子浓度:")
            for ion in ions:
                val = first.get(ion, '—')
                if val not in ['—', '', None]:
                    print(f"    {ion}: {val}")
        else:
            print(f"\n❌ 无数据")
            print(f"返回字段: {list(result_data.keys())}")

            # 显示API知道要查什么
            if 'queryNames' in result_data:
                print(f"\nAPI查询的离子: {result_data['queryNames'][:5]}...")
            if 'inputCodes' in result_data:
                print(f"因子编码: {result_data['inputCodes'][:5]}...")

if __name__ == '__main__':
    test_ionic_api()
