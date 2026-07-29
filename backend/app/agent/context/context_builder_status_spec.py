from app.agent.context.context_builder import SimplifiedContextBuilder


def test_user_conversation_does_not_inject_empty_current_status_heading():
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)

    user_conversation = builder._build_user_conversation(
        query="继续当前任务",
        iteration=1,
        latest_observation="",
        conversation_history=[{"role": "user", "content": "历史消息"}],
    )

    assert "## 当前状态" not in user_conversation
    assert "## 当前进行的任务\n继续当前任务" in user_conversation
