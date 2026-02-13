"""
测试专家执行器地理上下文注入功能
"""

import sys
import os

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_geo_context_extraction():
    """测试地理上下文提取"""
    print("=" * 80)
    print("地理上下文提取测试")
    print("=" * 80)

    from app.agent.experts.component_executor import ComponentExecutor

    executor = ComponentExecutor()

    # 测试不同类型的查询
    test_queries = [
        "分析东莞的PM2.5组分",
        "广州从化天湖站的水溶性离子数据",
        "深圳和佛山的大气污染对比",
        "查询新兴站2024年12月的颗粒物数据"
    ]

    for query in test_queries:
        print(f"\n【查询】: {query}")
        geo_context = executor._build_geo_context(query)

        if geo_context:
            print("✓ 提取到地理上下文:")
            print("-" * 60)
            # 只显示前500字符，避免输出过长
            preview = geo_context[:500] + "..." if len(geo_context) > 500 else geo_context
            print(preview)
            print("-" * 60)
        else:
            print("✗ 未提取到地理上下文")


def test_station_mapping():
    """测试城市→站点映射"""
    print("\n" + "=" * 80)
    print("城市→站点映射测试")
    print("=" * 80)

    from app.agent.experts.component_executor import ComponentExecutor

    executor = ComponentExecutor()

    # 测试城市映射
    test_cities = [
        ["广州"],
        ["东莞"],
        ["深圳"],
        ["佛山"]
    ]

    for cities in test_cities:
        print(f"\n【城市】: {cities[0]}")
        mappings = executor._get_city_station_mappings(cities)

        if mappings:
            print("✓ 找到站点映射:")
            print(mappings)
        else:
            print("✗ 未找到站点映射")


def test_full_integration():
    """测试完整的地理上下文注入到提示词"""
    print("\n" + "=" * 80)
    print("完整集成测试（地理上下文注入到提示词）")
    print("=" * 80)

    from app.agent.experts.component_executor import ComponentExecutor

    executor = ComponentExecutor()

    test_task_description = "分析东莞2024年12月24日的PM2.5化学组分特征，包括水溶性离子、碳组分和地壳元素"

    print(f"\n【任务描述】: {test_task_description}")

    # 提取地理上下文
    geo_context = executor._build_geo_context(test_task_description)

    if geo_context:
        print("\n✓ 地理上下文提取成功:")
        print("=" * 60)
        print(geo_context)
        print("=" * 60)
        print("\n✓ 此地理上下文将被注入到专家执行器的提示词中")
        print("✓ LLM在生成工具参数时可以看到可用的站点信息")
    else:
        print("\n✗ 未提取到地理上下文")


if __name__ == "__main__":
    print("专家执行器地理上下文注入功能测试")
    print("=" * 80)

    # 测试1: 地理上下文提取
    test_geo_context_extraction()

    # 测试2: 城市→站点映射
    test_station_mapping()

    # 测试3: 完整集成测试
    test_full_integration()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
