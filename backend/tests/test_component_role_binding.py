"""
测试组分专家工具 role 参数绑定修复

验证修复：ToolNode 创建时应该正确传递 role 参数
以确保参数绑定器能够按 role 过滤工具结果。

问题背景：
- ToolCallPlan 中定义了 role（如 "water-soluble", "carbon", "crustal", "trace"）
- 但 ToolNode 创建时丢失了 role
- 导致参数绑定器无法匹配 get_pm25_ionic[role=water-soluble].data_id

修复方案：
- 在 _build_graph_from_plan() 的所有分支都传递 plan.role
"""

import pytest
from app.agent.core.tool_dependency_graph import ToolDependencyGraph, ToolNode
from app.agent.core.expert_plan_generator import ToolCallPlan


def test_tool_call_plan_has_role():
    """验证 ToolCallPlan 可以正确设置 role"""
    plan = ToolCallPlan(
        tool="get_pm25_ionic",
        purpose="获取PM2.5水溶性离子数据",
        role="water-soluble"
    )

    assert plan.role == "water-soluble", "ToolCallPlan 应该保留 role 字段"


def test_tool_node_creation_with_role():
    """验证 ToolNode 创建时正确传递 role"""
    node = ToolNode(
        tool_name="get_pm25_ionic",
        index=0,
        expert_type="component",
        role="water-soluble"
    )

    assert node.role == "water-soluble", "ToolNode 应该保留 role 字段"


def test_tool_node_creation_without_role():
    """验证 ToolNode 创建时 role 可以为 None"""
    node = ToolNode(
        tool_name="get_weather_data",
        index=0,
        expert_type="weather"
        # 没有传递 role
    )

    assert node.role is None, "ToolNode.role 应该默认为 None"


def test_tool_dependency_graph_preserves_role():
    """验证 ToolDependencyGraph 构建时保留 role"""
    # 创建带有 role 的工具计划
    tool_plan = [
        ToolCallPlan(
            tool="get_pm25_ionic",
            purpose="获取PM2.5水溶性离子数据",
            role="water-soluble"
        ),
        ToolCallPlan(
            tool="get_pm25_carbon",
            purpose="获取PM2.5碳组分数据",
            role="carbon"
        ),
        ToolCallPlan(
            tool="get_pm25_crustal",
            purpose="获取PM2.5地壳元素数据",
            role="crustal"
        ),
    ]

    # 构建依赖图（不使用 tool_graph_config）
    graph = ToolDependencyGraph(expert_type="component")
    graph.build_from_tool_plan(tool_plan, context={})

    # 验证所有节点都保留了 role
    nodes = list(graph.nodes.values())
    assert len(nodes) == 3, f"应该有3个节点，实际有 {len(nodes)} 个"

    role_map = {node.tool_name: node.role for node in nodes}

    assert role_map.get("get_pm25_ionic") == "water-soluble", \
        f"get_pm25_ionic 的 role 应该是 water-soluble，实际是 {role_map.get('get_pm25_ionic')}"

    assert role_map.get("get_pm25_carbon") == "carbon", \
        f"get_pm25_carbon 的 role 应该是 carbon，实际是 {role_map.get('get_pm25_carbon')}"

    assert role_map.get("get_pm25_crustal") == "crustal", \
        f"get_pm25_crustal 的 role 应该是 crustal，实际是 {role_map.get('get_pm25_crustal')}"


def test_tool_dependency_graph_with_same_tool_different_roles():
    """验证同一工具使用不同 role 时的处理"""
    tool_plan = [
        ToolCallPlan(
            tool="get_pm25_crustal",
            purpose="获取PM2.5地壳元素数据",
            role="crustal"
        ),
        ToolCallPlan(
            tool="get_pm25_crustal",
            purpose="获取PM2.5微量元素数据",
            role="trace"
        ),
    ]

    graph = ToolDependencyGraph(expert_type="component")
    graph.build_from_tool_plan(tool_plan, context={})

    # 验证两个节点都有正确的 role
    nodes = list(graph.nodes.values())
    assert len(nodes) == 2

    # 通过索引区分两个节点
    crustal_node = next((n for n in nodes if n.role == "crustal"), None)
    trace_node = next((n for n in nodes if n.role == "trace"), None)

    assert crustal_node is not None, "应该找到 role=crustal 的节点"
    assert trace_node is not None, "应该找到 role=trace 的节点"

    assert crustal_node.index == 0, "crustal 节点应该在索引 0"
    assert trace_node.index == 1, "trace 节点应该在索引 1"


if __name__ == "__main__":
    print("测试组分专家 role 参数绑定修复...")

    # 快速验证
    from app.agent.core.expert_plan_generator import ToolCallPlan

    # 测试1: ToolCallPlan 保留 role
    plan = ToolCallPlan(
        tool="get_pm25_ionic",
        purpose="获取PM2.5水溶性离子数据",
        role="water-soluble"
    )
    print(f"✓ ToolCallPlan.role: {plan.role}")

    # 测试2: ToolNode 保留 role
    from app.agent.core.tool_dependency_graph import ToolNode
    node = ToolNode(
        tool_name="get_pm25_ionic",
        index=0,
        expert_type="component",
        role="water-soluble"
    )
    print(f"✓ ToolNode.role: {node.role}")

    # 测试3: ToolDependencyGraph 保留 role
    tool_plan = [
        ToolCallPlan(tool="get_pm25_ionic", role="water-soluble", purpose="test"),
        ToolCallPlan(tool="get_pm25_carbon", role="carbon", purpose="test"),
    ]

    graph = ToolDependencyGraph(expert_type="component")
    graph.build_from_tool_plan(tool_plan, context={})

    roles = {n.tool_name: n.role for n in graph.nodes.values()}
    print(f"✓ ToolDependencyGraph roles: {roles}")

    assert roles["get_pm25_ionic"] == "water-soluble"
    assert roles["get_pm25_carbon"] == "carbon"

    print("\n所有测试通过！")
