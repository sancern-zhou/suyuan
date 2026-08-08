from app.agent.context.context_builder import SimplifiedContextBuilder


def test_interruption_flag_does_not_inject_user_visible_prompt():
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)

    user_conversation = builder._build_user_conversation(
        query="先看下技能",
        iteration=1,
        latest_observation="",
        conversation_history=[{"role": "user", "content": "抓取广东省监测中心近半年的招标信息"}],
        is_interruption=True,
    )

    assert "用户已中断对话并重新输入" not in user_conversation
    assert "之前中断了对话" not in user_conversation
    assert "先看下技能" in user_conversation
