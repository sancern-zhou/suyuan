"""
测试 get_particulate_components 工具（参考项目模式）
"""

import sys
import os

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_component_executor_integration():
    """测试ComponentExecutor中get_particulate_components的加载"""
    print("=" * 80)
    print("get_particulate_components 工具集成测试")
    print("=" * 80)

    from app.agent.experts.component_executor import ComponentExecutor

    executor = ComponentExecutor()
    tools = executor._load_tools()

    print(f"\n已加载工具数量: {len(tools)}")

    # 检查 get_particulate_components
    print("\n【get_particulate_components 工具验证】")
    if "get_particulate_components" in tools:
        print("✓ get_particulate_components 已成功加载")
        tool = tools["get_particulate_components"]
        print(f"  Schema名称: {tool.function_schema['name']}")
        print(f"  描述: {tool.function_schema['description'][:100]}...")
        print(f"  必需参数: {tool.function_schema['parameters']['required']}")
        print(f"  可选参数: {list(tool.function_schema['parameters']['properties'].keys() - set(tool.function_schema['parameters']['required']))}")

        # 检查类属性
        if hasattr(tool, 'DETECTION_ITEM_CODES'):
            print(f"\n  DetectionitemCodes 清单:")
            print(f"  {tool.DETECTION_ITEM_CODES}")
            print(f"\n  组分名称映射:")
            for code, name in tool.COMPONENT_NAMES.items():
                print(f"    {code} -> {name}")
    else:
        print("✗ get_particulate_components 未加载")

    # 检查其他颗粒物工具
    print("\n【其他颗粒物工具统计】")
    particulate_tools = [t for t in tools.keys() if "pm25" in t.lower() or "particulate" in t.lower()]
    for tool in sorted(particulate_tools):
        print(f"  - {tool}")

    return tools


def test_tool_schema():
    """测试工具Schema是否符合参考项目规范"""
    print("\n" + "=" * 80)
    print("工具Schema规范验证")
    print("=" * 80)

    from app.tools.query.get_particulate_components.tool import GetParticulateComponentsTool

    tool = GetParticulateComponentsTool()

    print("\n【参数验证】")
    schema = tool.function_schema

    # 验证必需参数
    required = schema['parameters']['required']
    expected_required = ["station", "code", "start_time", "end_time"]
    if set(required) == set(expected_required):
        print(f"✓ 必需参数正确: {required}")
    else:
        print(f"✗ 必需参数不匹配")
        print(f"  期望: {expected_required}")
        print(f"  实际: {required}")

    # 验证 data_type 参数
    data_type_param = schema['parameters']['properties']['data_type']
    if set(data_type_param['enum']) == {0, 1, 4, 5, 7, 15}:
        print(f"✓ data_type 枚举值正确: {data_type_param['enum']}")
    else:
        print(f"✗ data_type 枚举值不匹配: {data_type_param['enum']}")

    # 验证 time_granularity 参数
    time_gran_param = schema['parameters']['properties']['time_granularity']
    if set(time_gran_param['enum']) == {1, 2, 3, 5}:
        print(f"✓ time_granularity 枚举值正确: {time_gran_param['enum']}")
    else:
        print(f"✗ time_granularity 枚举值不匹配: {time_gran_param['enum']}")

    print("\n【DetectionitemCodes 验证】")
    expected_codes = [
        "a36001", "a36002", "a36003", "a36004", "a36006",
        "a36005", "a36007", "a36008", "a340101", "a340091"
    ]
    if tool.DETECTION_ITEM_CODES == expected_codes:
        print(f"✓ DetectionitemCodes 清单正确（10个组分）")
    else:
        print(f"✗ DetectionitemCodes 清单不匹配")
        print(f"  期望: {expected_codes}")
        print(f"  实际: {tool.DETECTION_ITEM_CODES}")

    print("\n【组分名称映射验证】")
    expected_mapping = {
        "a36001": "Cl⁻",
        "a36002": "NO₃⁻",
        "a36003": "SO₄²⁻",
        "a36004": "Na⁺",
        "a36006": "K⁺",
        "a36005": "NH₄⁺",
        "a36007": "Mg²⁺",
        "a36008": "Ca²⁺",
        "a340101": "OC",
        "a340091": "EC"
    }
    if tool.COMPONENT_NAMES == expected_mapping:
        print(f"✓ 组分名称映射正确（10个映射）")
    else:
        print(f"✗ 组分名称映射不匹配")
        print(f"  期望数量: {len(expected_mapping)}")
        print(f"  实际数量: {len(tool.COMPONENT_NAMES)}")


if __name__ == "__main__":
    print("get_particulate_components 工具测试")
    print("=" * 80)

    # 测试1: 工具加载
    tools = test_component_executor_integration()

    # 测试2: Schema验证
    test_tool_schema()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
