"""
模拟完整启动流程，验证 refresh_tools 机制
"""
import asyncio
import sys
sys.path.insert(0, r"D:\溯源\backend")


async def simulate_startup():
    print("=" * 80)
    print("Simulating backend startup process")
    print("=" * 80)

    # Step 1: 检查 global_tool_registry
    print("\n[Step 1] Checking global_tool_registry...")
    from app.tools import global_tool_registry
    global_tools = global_tool_registry.list_tools()
    print(f"  Total tools in global_tool_registry: {len(global_tools)}")
    print(f"  Has 'unpack_office': {'unpack_office' in global_tools}")

    # Step 2: 初始化 LLM 工具（模拟 startup_event）
    print("\n[Step 2] Initializing LLM tools (initialize_llm_tools)...")
    from app.services.lifecycle_manager import initialize_llm_tools
    try:
        initialize_llm_tools()
        print("  [OK] LLM tools initialized")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # Step 3: 创建 Agent 实例（模拟 app.routers.agent 模块加载）
    print("\n[Step 3] Creating Agent instance (simulating module load)...")
    from app.agent import create_react_agent
    agent = create_react_agent(with_test_tools=False)
    tools_before_refresh = agent.get_available_tools()
    print(f"  Total tools in agent (before refresh): {len(tools_before_refresh)}")
    print(f"  Has 'unpack_office': {'unpack_office' in tools_before_refresh}")

    # Step 4: 刷新 Agent 工具（模拟 main.py:startup_event 中的逻辑）
    print("\n[Step 4] Refreshing agent tools...")
    try:
        agent.refresh_tools()
        print("  [OK] Agent tools refreshed")
    except Exception as e:
        print(f"  [ERROR] Refresh failed: {e}")
        import traceback
        traceback.print_exc()

    tools_after_refresh = agent.get_available_tools()
    print(f"  Total tools in agent (after refresh): {len(tools_after_refresh)}")
    print(f"  Has 'unpack_office': {'unpack_office' in tools_after_refresh}")

    # Step 5: 对比差异
    print("\n[Step 5] Comparing tool lists...")
    if len(tools_after_refresh) > len(tools_before_refresh):
        added_tools = set(tools_after_refresh) - set(tools_before_refresh)
        print(f"  [+] Added tools ({len(added_tools)}): {sorted(added_tools)}")
    elif len(tools_after_refresh) < len(tools_before_refresh):
        removed_tools = set(tools_before_refresh) - set(tools_after_refresh)
        print(f"  [-] Removed tools ({len(removed_tools)}): {sorted(removed_tools)}")
    else:
        print(f"  [=] No change in tool count")

    # Step 6: 验证结果
    print("\n[Step 6] Final verification...")
    if 'unpack_office' in tools_after_refresh:
        print("  [SUCCESS] unpack_office is available in agent!")
    else:
        print("  [FAILURE] unpack_office is STILL missing!")

        # 额外诊断
        print("\n[Diagnosis] Checking what's different...")
        missing_tools = set(global_tools) - set(tools_after_refresh)
        print(f"  Tools in global but not in agent ({len(missing_tools)}):")
        for tool in sorted(missing_tools)[:10]:  # 只显示前 10 个
            print(f"    - {tool}")

    print("\n" + "=" * 80)
    print("Simulation completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(simulate_startup())
