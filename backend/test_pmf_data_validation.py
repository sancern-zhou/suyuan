"""
PMF数据验证
确认东莞站点的水溶性离子和碳组分数据是否满足PMF要求
"""

import sys
import os

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.particulate_api_client import get_particulate_api_client


def validate_pmf_data():
    """验证PMF数据"""
    print("=" * 80)
    print("PMF数据验证（东莞 1037b）")
    print("=" * 80)

    client = get_particulate_api_client()

    # 测试1: 水溶性离子
    print("\n【测试1】水溶性离子数据")
    print("-" * 80)

    response_ions = client.get_ionic_analysis(
        station="东莞",
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59",
        time_type="Hour"
    )

    ions_data = None
    if response_ions.get("success"):
        api_response = response_ions.get("api_response")
        ions_data = api_response.get("data", {}).get("result", {}).get("resultOne", [])
        print(f"✓ 成功获取 {len(ions_data)} 条水溶性离子记录")

        # 检查PMF核心组分
        first = ions_data[0]
        pmf_ions = {"SO4²⁻": "SO4", "NO₃⁻": "NO3", "NH₄⁺": "NH4"}

        print(f"\n核心组分检查:")
        for field, comp in pmf_ions.items():
            if field in first:
                value = first.get(field)
                is_valid = value not in ["—", "", None]
                if is_valid:
                    # 统计所有记录中的有效数据
                    valid_count = sum(1 for r in ions_data if r.get(field) not in ["—", "", None])
                    completeness = valid_count / len(ions_data) * 100
                    print(f"  ✓ {field} ({comp}): {valid_count}/{len(ions_data)} 条有效 ({completeness:.1f}%)")
                else:
                    print(f"  ✗ {field} ({comp}): 无数据")

    else:
        print(f"✗ 获取失败: {response_ions.get('error')}")

    # 测试2: 碳组分
    print("\n【测试2】碳组分数据 (OC, EC)")
    print("-" * 80)

    response_carbon = client.get_carbon_components(
        station="东莞",
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59"
    )

    carbon_data = None
    if response_carbon.get("success"):
        api_response = response_carbon.get("api_response")
        carbon_data = api_response.get("data", {}).get("result", {}).get("resultData", [])
        print(f"✓ 成功获取 {len(carbon_data)} 条碳组分记录")

        if carbon_data:
            first = carbon_data[0]
            print(f"\n核心组分检查:")
            for field in ["OC（TOT）", "EC（TOT）"]:
                if field in first:
                    value = first.get(field)
                    is_valid = value not in ["—", "", None]
                    if is_valid:
                        valid_count = sum(1 for r in carbon_data if r.get(field) not in ["—", "", None])
                        completeness = valid_count / len(carbon_data) * 100
                        comp_name = "OC" if "OC" in field else "EC"
                        print(f"  ✓ {field} ({comp_name}): {valid_count}/{len(carbon_data)} 条有效 ({completeness:.1f}%)")
                    else:
                        print(f"  ✗ {field}: 无数据")

    else:
        print(f"✗ 获取失败: {response_carbon.get('error')}")

    # PMF要求评估
    print("\n" + "=" * 80)
    print("PMF数据评估")
    print("=" * 80)

    ions_pass = ions_data is not None and len(ions_data) >= 20
    carbon_pass = carbon_data is not None and len(carbon_data) >= 20

    print(f"\n水溶性离子:")
    print(f"  样本数: {len(ions_data) if ions_data else 0} {'✓' if ions_pass else '✗'} (要求 >= 20)")
    if ions_data and ions_data[0]:
        has_3_components = 0
        for field in ["SO4²⁻", "NO₃⁻", "NH₄⁺"]:
            if field in ions_data[0] and ions_data[0].get(field) not in ["—", "", None]:
                has_3_components += 1
        print(f"  核心组分: {has_3_components} 个 {'✓' if has_3_components >= 3 else '✗'} (要求 >= 3)")

    print(f"\n碳组分:")
    print(f"  样本数: {len(carbon_data) if carbon_data else 0} {'✓' if carbon_pass else '✗'} (要求 >= 20)")
    if carbon_data and carbon_data[0]:
        has_oc_ec = 0
        for field in ["OC（TOT）", "EC（TOT）"]:
            if field in carbon_data[0] and carbon_data[0].get(field) not in ["—", "", None]:
                has_oc_ec += 1
        print(f"  核心组分: {has_oc_ec} 个 {'✓' if has_oc_ec >= 2 else '✗'} (要求 >= 2)")

    print("\n" + "=" * 80)
    print("最终结论")
    print("=" * 80)

    if ions_pass and carbon_pass:
        print("✓ 数据满足PMF源解析要求！")
        print("  - 水溶性离子和碳组分都有足够的样本数")
        print("  - 可以进行PMF源解析分析")
        return True
    elif ions_pass:
        print("△ 部分满足PMF要求")
        print("  - 水溶性离子数据充足")
        print("  - 碳组分数据不足")
        print("  - 建议使用水溶性离子数据进行PMF分析")
        return False
    else:
        print("✗ 数据不满足PMF要求")
        print("  - 样本数不足")
        print("  - 需要更多数据或更换站点/日期")
        return False


if __name__ == "__main__":
    success = validate_pmf_data()
    sys.exit(0 if success else 1)
