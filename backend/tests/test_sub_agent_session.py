"""
测试子Agent Session连续对话功能
"""

import asyncio
import pytest
from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
from app.agent.session.session_manager import get_session_manager
from app.agent.context.execution_context import ExecutionContext
from app.agent.memory.hybrid_manager import HybridMemoryManager


@pytest.mark.asyncio
async def test_session_generation():
    """测试session_id生成"""
    tool = CallSubAgentTool()

    # 测试session_id生成格式
    session_id = tool._generate_session_id("social", "expert")
    print(f"✓ 生成的session_id: {session_id}")

    # 验证格式
    assert session_id.startswith("social__to__expert__"), "session_id格式错误"
    parts = session_id.split("__")
    assert len(parts) == 4, "session_id应该有4部分"
    assert parts[0] == "social", "父模式应该是social"
    assert parts[2] == "expert", "子模式应该是expert"

    print("✓ session_id生成格式验证通过")


@pytest.mark.asyncio
async def test_session_model_fields():
    """测试Session模型的新字段"""
    from app.agent.session.models import Session

    # 创建子Agent session
    session = Session(
        session_id="social__to__expert__20250409_143052",
        query="测试查询",
        parent_mode="social",
        child_mode="expert",
        is_sub_agent_session=True
    )

    print(f"✓ Session创建成功")
    print(f"  - session_id: {session.session_id}")
    print(f"  - parent_mode: {session.parent_mode}")
    print(f"  - child_mode: {session.child_mode}")
    print(f"  - is_sub_agent_session: {session.is_sub_agent_session}")

    assert session.parent_mode == "social"
    assert session.child_mode == "expert"
    assert session.is_sub_agent_session == True

    print("✓ Session模型字段验证通过")


@pytest.mark.asyncio
async def test_session_save_and_load():
    """测试session保存和加载"""
    session_manager = get_session_manager()

    # 创建并保存session
    from app.agent.session.models import Session

    session = Session(
        session_id="social__to__expert__20250409_test",
        query="测试查询",
        parent_mode="social",
        child_mode="expert",
        is_sub_agent_session=True
    )

    # 添加对话历史
    session.conversation_history = [
        {"role": "user", "content": "第一次查询", "timestamp": "2025-04-09T14:30:00"},
        {"role": "assistant", "content": "第一次回答", "timestamp": "2025-04-09T14:30:10"}
    ]

    # 保存
    success = session_manager.save_session(session)
    assert success, "session保存失败"
    print("✓ session保存成功")

    # 加载
    loaded = session_manager.get_session("social__to__expert__20250409_test")
    assert loaded is not None, "session加载失败"
    assert loaded.session_id == "social__to__expert__20250409_test"
    assert len(loaded.conversation_history) == 2
    print("✓ session加载成功")
    print(f"  - 对话历史条数: {len(loaded.conversation_history)}")

    # 清理测试session
    session_manager.delete_session("social__to__expert__20250409_test")
    print("✓ 测试session已清理")


@pytest.mark.asyncio
async def test_session_manager_lists_sub_sessions():
    """测试SessionManager列出子Agent session"""
    session_manager = get_session_manager()

    # 创建测试session
    from app.agent.session.models import Session

    test_session = Session(
        session_id="social__to__query__20250409_test_list",
        query="测试列表",
        parent_mode="social",
        child_mode="query",
        is_sub_agent_session=True
    )

    session_manager.save_session(test_session)

    # 列出所有session
    all_sessions = session_manager.list_sessions()

    # 查找我们的测试session
    found = False
    for s in all_sessions:
        if s.session_id == "social__to__query__20250409_test_list":
            found = True
            print(f"✓ 找到测试session: {s.session_id}")
            break

    assert found, "未能在列表中找到测试session"

    # 清理
    session_manager.delete_session("social__to__query__20250409_test_list")
    print("✓ 测试session已清理")


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("测试子Agent Session连续对话功能")
    print("=" * 60)

    await test_session_generation()
    print()

    await test_session_model_fields()
    print()

    await test_session_save_and_load()
    print()

    await test_session_manager_lists_sub_sessions()
    print()

    print("=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
