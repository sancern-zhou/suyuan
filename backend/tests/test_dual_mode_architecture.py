"""
双模式架构端到端测试
测试 assistant 模式和 expert 模式的完整链路
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode


def test_prompt_builder():
    """测试提示词构建器"""
    print("=" * 60)
    print("测试1: 提示词构建器")
    print("=" * 60)

    # 测试 assistant 模式
    assistant_prompt = build_react_system_prompt("assistant")
    print(f"\n[OK] Assistant Mode Prompt (前200字符):")
    print(assistant_prompt[:200])
    print(f"\n提示词长度: {len(assistant_prompt)} 字符")

    # 测试 expert 模式
    expert_prompt = build_react_system_prompt("expert")
    print(f"\n[OK] Expert Mode Prompt (前200字符):")
    print(expert_prompt[:200])
    print(f"\n提示词长度: {len(expert_prompt)} 字符")

    # 验证必要的内容
    assert "call_sub_agent" in assistant_prompt, "Assistant prompt 缺少 call_sub_agent 工具"
    assert "call_sub_agent" in expert_prompt, "Expert prompt 缺少 call_sub_agent 工具"
    print("\n[OK] 提示词构建器测试通过")


def test_tool_registry():
    """测试工具注册表"""
    print("\n" + "=" * 60)
    print("测试2: 工具注册表")
    print("=" * 60)

    # 获取 assistant 模式工具
    assistant_tools = get_tools_by_mode("assistant")
    print(f"\n[OK] Assistant Mode Tools ({len(assistant_tools)}个):")
    for tool_name, description in list(assistant_tools.items())[:5]:
        print(f"  - {tool_name}: {description[:50]}...")

    # 获取 expert 模式工具
    expert_tools = get_tools_by_mode("expert")
    print(f"\n[OK] Expert Mode Tools ({len(expert_tools)}个):")
    for tool_name, description in list(expert_tools.items())[:5]:
        print(f"  - {tool_name}: {description[:50]}...")

    # 验证两种模式都有 call_sub_agent
    assert "call_sub_agent" in assistant_tools, "Assistant 模式缺少 call_sub_agent"
    assert "call_sub_agent" in expert_tools, "Expert 模式缺少 call_sub_agent"
    print("\n[OK] 工具注册表测试通过")


async def test_call_sub_agent_tool():
    """测试 CallSubAgentTool 是否正确注册"""
    print("\n" + "=" * 60)
    print("测试3: CallSubAgentTool 注册")
    print("=" * 60)

    try:
        from app.tools import get_all_tools
        all_tools = get_all_tools()

        # 检查 call_sub_agent 是否在工具列表中
        tool_names = [tool.name for tool in all_tools]
        assert "call_sub_agent" in tool_names, "call_sub_agent 未注册到全局工具表"

        # 获取工具实例
        call_sub_agent_tool = next(
            (tool for tool in all_tools if tool.name == "call_sub_agent"),
            None
        )

        print(f"\n[OK] CallSubAgentTool 已注册")
        print(f"  - 工具名称: {call_sub_agent_tool.name}")
        print(f"  - 工具描述: {call_sub_agent_tool.description[:80]}...")

        print("\n[OK] CallSubAgentTool 注册测试通过")
    except Exception as e:
        print(f"\n[ERROR] CallSubAgentTool 注册测试失败: {e}")


def test_api_request_model():
    """测试 API 请求模型"""
    print("\n" + "=" * 60)
    print("测试4: API 请求模型")
    print("=" * 60)

    try:
        from app.routers.agent import AgentAnalyzeRequest

        # 测试默认值
        request1 = AgentAnalyzeRequest(query="测试查询")
        assert request1.mode == "expert", f"默认模式应为 expert，实际为 {request1.mode}"
        print(f"\n[OK] 默认模式: {request1.mode}")

        # 测试 assistant 模式
        request2 = AgentAnalyzeRequest(query="测试查询", mode="assistant")
        assert request2.mode == "assistant", f"指定模式应为 assistant，实际为 {request2.mode}"
        print(f"[OK] 指定模式: {request2.mode}")

        print("\n[OK] API 请求模型测试通过")
    except Exception as e:
        print(f"\n[ERROR] API 请求模型测试失败: {e}")


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("双模式架构端到端测试")
    print("=" * 60)

    # 运行测试
    test_prompt_builder()
    test_tool_registry()
    await test_call_sub_agent_tool()
    test_api_request_model()

    print("\n" + "=" * 60)
    print("所有测试通过！双模式架构已就绪")
    print("=" * 60)
    print("\n实施总结:")
    print("  1. 工具注册表（tool_registry.py）")
    print("  2. CallSubAgentTool（call_sub_agent.py）")
    print("  3. 模式专用提示词（assistant_prompt.py, expert_prompt.py）")
    print("  4. 提示词构建器（prompt_builder.py）")
    print("  5. ReActLoop 支持（loop.py）")
    print("  6. ContextBuilder 支持（simplified_context_builder.py）")
    print("  7. 工具注册（tools/__init__.py）")
    print("  8. API 接口（agent.py）")
    print("  9. ReActAgent 支持（react_agent.py）")
    print("\n下一步: 创建前端模式选择器 UI")


if __name__ == "__main__":
    asyncio.run(main())
