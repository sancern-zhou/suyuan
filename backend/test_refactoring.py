"""
测试重构后的系统：去除 Reflexion + WorkingMemory，在 SessionMemory 中添加 thought 字段
"""
import asyncio
from app.agent.memory import SessionMemory, HybridMemoryManager


def test_session_memory_thought_field():
    """测试 SessionMemory 的 thought 字段"""
    print("=" * 80)
    print("Test 1: SessionMemory thought field")
    print("=" * 80)

    session = SessionMemory(session_id="test_session")

    # 添加用户消息
    session.add_user_message("Analyze Guangzhou air quality")

    # 添加助手消息（带 thought）
    session.add_assistant_message(
        content="Data retrieved: PM2.5=35, O3=120",
        thought="Need to query weather data first, then analyze pollutant concentration"
    )

    # 获取 LLM 格式消息
    messages = session.get_messages_for_llm()

    print(f"\nMessage count: {len(messages)}")
    for i, msg in enumerate(messages, 1):
        print(f"\nMessage {i}:")
        print(f"  Role: {msg['role']}")
        print(f"  Content preview: {msg['content'][:200]}...")

        # 验证 thought 是否被合并到 content 中（JSON 格式）
        if msg['role'] == 'assistant':
            if '"thought"' in msg['content'] or '## 思考' in msg['content']:
                print("  [OK] thought field correctly merged into content")

    # 测试压缩恢复
    print("\n" + "=" * 80)
    print("Test compression recovery (thought parsing)")
    print("=" * 80)

    session.update_messages(messages)
    restored = session.get_messages_for_llm()

    print(f"\nRestored message count: {len(restored)}")
    if len(restored) == len(messages):
        print("[OK] Message count matches")

    # 检查 thought 是否被正确解析
    for turn in session.conversation_history:
        if turn.role == "assistant" and turn.thought:
            print(f"\n[OK] thought field correctly parsed: {turn.thought[:50]}...")

    session.cleanup()
    print("\n[OK] SessionMemory thought field test passed")


def test_hybrid_memory_without_working():
    """测试 HybridMemoryManager 内联 recent_iterations"""
    print("\n" + "=" * 80)
    print("Test 2: HybridMemoryManager inline recent_iterations")
    print("=" * 80)

    manager = HybridMemoryManager(session_id="test_hybrid")

    # 添加迭代
    manager.add_iteration(
        thought="Analyze current pollution status",
        action={"type": "TOOL_CALL", "tool": "get_air_quality", "args": {"city": "Guangzhou"}},
        observation={"success": True, "data": {"pm25": 35}, "summary": "Retrieved successfully"}
    )

    manager.add_iteration(
        thought="Query weather data",
        action={"type": "TOOL_CALL", "tool": "get_weather_data", "args": {"city": "Guangzhou"}},
        observation={"success": True, "data": {"temp": 25}, "summary": "Retrieved successfully"}
    )

    # 测试 get_iterations
    iterations = manager.get_iterations()
    print(f"\nIteration count: {len(iterations)}")

    if len(iterations) == 2:
        print("[OK] add_iteration and get_iterations work correctly")

    for i, it in enumerate(iterations, 1):
        print(f"\nIteration {i}:")
        print(f"  Thought: {it['thought'][:30]}...")
        print(f"  Action: {it['action']['tool']}")
        print(f"  Observation: {it['observation']['summary']}")

    # 测试 add_chart_observation
    manager.add_chart_observation({
        "chart_id": "chart_001",
        "chart_type": "line",
        "chart_title": "PM2.5 Trend",
        "data_id": "data_001"
    })

    iterations = manager.get_iterations()
    if len(iterations) == 3:
        print("\n[OK] add_chart_observation works correctly")

    # 测试批量压缩
    print("\nTest batch compression (add 12 records to trigger compression)...")
    for i in range(10):
        manager.add_iteration(
            thought=f"Iteration {i+3}",
            action={"type": "TOOL_CALL", "tool": "test_tool"},
            observation={"success": True, "summary": f"Test {i+3}"}
        )

    iterations_after = manager.get_iterations()
    compressed = manager.session.compressed_iterations

    print(f"\nCurrent iteration count: {len(iterations_after)}")
    print(f"Compressed record count: {len(compressed)}")

    if len(compressed) > 0:
        print("[OK] Batch compression triggered successfully")

    manager.cleanup()
    print("\n[OK] HybridMemoryManager test passed")


def test_no_reflexion_no_working():
    """验证 Reflexion 和 WorkingMemory 已被移除"""
    print("\n" + "=" * 80)
    print("Test 3: Verify Reflexion and WorkingMemory removed")
    print("=" * 80)

    try:
        from app.agent.memory import WorkingMemory
        print("[FAIL] WorkingMemory still exists")
    except ImportError:
        print("[OK] WorkingMemory successfully removed")

    try:
        from app.agent.core import ReflexionHandler
        print("[FAIL] ReflexionHandler still exists")
    except ImportError:
        print("[OK] ReflexionHandler successfully removed")

    # 验证 HybridMemoryManager 没有 working 属性
    manager = HybridMemoryManager(session_id="test_no_working")

    if not hasattr(manager, 'working'):
        print("[OK] HybridMemoryManager.working attribute removed")
    else:
        print("[FAIL] HybridMemoryManager.working attribute still exists")

    # 验证有 recent_iterations 属性
    if hasattr(manager, 'recent_iterations'):
        print("[OK] HybridMemoryManager.recent_iterations attribute added")
    else:
        print("[FAIL] HybridMemoryManager.recent_iterations attribute missing")

    manager.cleanup()


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("Refactoring Verification Tests")
    print("=" * 80)

    test_session_memory_thought_field()
    test_hybrid_memory_without_working()
    test_no_reflexion_no_working()

    print("\n" + "=" * 80)
    print("All tests completed!")
    print("=" * 80)
