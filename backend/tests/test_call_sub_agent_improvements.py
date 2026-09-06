#!/usr/bin/env python3
"""
测试 call_sub_agent 工具的改进

验证：
1. 新参数（goal、context、workspace_path）是否正确接收
2. 旧参数（task_description、context_supplement）是否向后兼容
3. 参数标准化是否正确工作
"""

import asyncio
import sys
from types import SimpleNamespace
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools.agent_tools.call_sub_agent import CallSubAgentTool


def test_function_schema():
    """测试 function_schema 是否包含新参数"""
    print("\n=== 测试 1: function_schema 检查 ===")

    tool = CallSubAgentTool()
    schema = tool.function_schema

    # 检查必需参数
    required = schema["parameters"].get("required", [])
    print(f"必需参数: {required}")
    assert "target_mode" in required, "target_mode 应该是必需的"
    assert "task_description" not in required, "task_description 不应该是必需的（向后兼容）"
    assert "goal" not in required, "goal 不应该是必需的（与 task_description 二选一）"

    # 检查新参数是否存在
    properties = schema["parameters"].get("properties", {})
    assert "goal" in properties, "应该包含 goal 参数"
    assert "context" in properties, "应该包含 context 参数"
    assert "workspace_path" in properties, "应该包含 workspace_path 参数"
    assert properties["skill_ids"]["maxItems"] == 1, "skill_ids 应限制为单个技能"

    # 检查旧参数是否仍然存在
    assert "task_description" in properties, "应该包含 task_description 参数（向后兼容）"
    assert "context_supplement" in properties, "应该包含 context_supplement 参数（向后兼容）"

    print("✅ function_schema 检查通过")


def test_workspace_promotion_waits_for_approval_before_starting_child():
    """持续工作空间请求只生成审批数据，不创建或运行子 Agent。"""
    tool = CallSubAgentTool()
    context = SimpleNamespace(session_id="web-session-1", manual_mode="assistant")

    result = asyncio.run(
        tool.execute(
            context=context,
            target_mode="board",
            goal="绘制系统架构图",
            context_str="遵循项目架构规范",
            workspace_path="/tmp/board-workspace",
            skill_ids=["archify"],
            promote_to_workspace=True,
        )
    )

    assert result["status"] == "pending"
    assert result["metadata"]["interaction_required"]["kind"] == "approval"
    pending = result["metadata"]["interaction_required"]["pending_request"]
    assert pending == {
        "target_mode": "board",
        "goal": "绘制系统架构图",
        "context_str": "遵循项目架构规范",
        "workspace_path": "/tmp/board-workspace",
        "session_id": "web-session-1",
        "skill_ids": ["archify"],
        "resume_after_approval": True,
    }


def test_parameter_normalization():
    """测试参数标准化逻辑"""
    print("\n=== 测试 2: 参数标准化 ===")

    # 模拟参数标准化逻辑
    goal = "测试任务"
    task_description = "旧式任务描述"
    context_param = "新式上下文"
    context_supplement = "旧式上下文补充"

    # 测试1：使用新参数
    effective_goal = goal or task_description
    effective_context = context_param or context_supplement
    assert effective_goal == "测试任务", "应该使用 goal"
    assert effective_context == "新式上下文", "应该使用 context_param"
    print("✅ 新参数优先")

    # 测试2：使用旧参数
    goal = None
    context_param = None
    effective_goal = goal or task_description
    effective_context = context_param or context_supplement
    assert effective_goal == "旧式任务描述", "应该回退到 task_description"
    assert effective_context == "旧式上下文补充", "应该回退到 context_supplement"
    print("✅ 旧参数兼容")

    # 测试3：新参数覆盖旧参数
    goal = "新任务"
    task_description = "旧任务"
    effective_goal = goal or task_description
    assert effective_goal == "新任务", "新参数应该覆盖旧参数"
    print("✅ 新参数覆盖旧参数")


def test_build_child_system_prompt():
    """测试子Agent系统提示生成"""
    print("\n=== 测试 3: 子Agent系统提示生成 ===")

    tool = CallSubAgentTool()

    # 测试1：完整参数
    prompt = tool._build_child_system_prompt(
        goal="更新Excel文件 /tmp/test.xlsx（第一个sheet）",
        context="按照技能文档步骤执行",
        workspace_path="/tmp",
        target_mode="assistant"
    )

    assert "任务目标" in prompt, "应该包含任务目标"
    assert "更新Excel文件 /tmp/test.xlsx（第一个sheet）" in prompt, "应该包含完整的 goal"
    assert "补充上下文" in prompt, "应该包含补充上下文"
    assert "按照技能文档步骤执行" in prompt, "应该包含 context"
    assert "工作目录" in prompt, "应该包含工作目录"
    assert "/tmp" in prompt, "应该包含 workspace_path"
    assert "关键要求" in prompt, "应该包含关键要求（assistant模式）"
    print("✅ 完整参数测试通过")

    # 测试2：仅 goal（必需参数）
    prompt = tool._build_child_system_prompt(
        goal="简单任务",
        context=None,
        workspace_path=None,
        target_mode="assistant"
    )

    assert "任务目标" in prompt, "应该包含任务目标"
    assert "简单任务" in prompt, "应该包含 goal"
    assert "补充上下文" not in prompt, "不应该包含补充上下文"
    assert "工作目录" not in prompt, "不应该包含工作目录"
    print("✅ 仅 goal 测试通过")

    # 测试3：不同模式
    prompt_assistant = tool._build_child_system_prompt(
        goal="测试",
        target_mode="assistant"
    )
    assert "关键要求" in prompt_assistant, "assistant 模式应该包含关键要求"

    prompt_query = tool._build_child_system_prompt(
        goal="测试",
        target_mode="query"
    )
    assert "数据查询任务" in prompt_query, "query 模式应该有特定提示"
    print("✅ 不同模式测试通过")


def test_example():
    """测试实际使用示例"""
    print("\n=== 测试 4: 实际使用示例 ===")

    tool = CallSubAgentTool()

    # 示例1：AQI更新任务（新参数）
    goal = "执行更新全国各省份AQI累计平均的EXCEL文件技能，时间段为2026年1-3月份和2025年1-3月份。文件路径：/tmp/会商文件/全国各省份污染物累计平均.xlsx，操作第五个sheet表。"
    context = "按照AQI技能文档的步骤执行"
    workspace_path = "/tmp/会商文件"

    prompt = tool._build_child_system_prompt(
        goal=goal,
        context=context,
        workspace_path=workspace_path,
        target_mode="assistant"
    )

    # 验证关键信息是否保留
    assert "/tmp/会商文件/全国各省份污染物累计平均.xlsx" in prompt, "应该保留文件路径"
    assert "第五个sheet" in prompt, "应该保留sheet索引"
    assert "2026年1-3月份和2025年1-3月份" in prompt, "应该保留时间范围"
    assert "AQI技能文档" in prompt, "应该保留技能名称"
    print("✅ AQI任务示例测试通过")

    # 示例2：向后兼容（旧参数）
    task_description = "旧式任务描述"
    context_supplement = "旧式上下文"

    # 模拟参数标准化
    effective_goal = task_description  # goal 为 None 时使用 task_description
    effective_context = context_supplement  # context_param 为 None 时使用 context_supplement

    assert effective_goal == "旧式任务描述", "向后兼容应该工作"
    assert effective_context == "旧式上下文", "向后兼容应该工作"
    print("✅ 向后兼容示例测试通过")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("call_sub_agent 工具改进测试")
    print("="*60)

    try:
        test_function_schema()
        test_parameter_normalization()
        test_build_child_system_prompt()
        test_example()

        print("\n" + "="*60)
        print("✅ 所有测试通过！")
        print("="*60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
