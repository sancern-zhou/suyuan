from app.agent.context.context_builder import SimplifiedContextBuilder


def test_social_mode_injects_agent_control_with_assistant_style_wording():
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)
    builder.current_mode = "social"

    system_prompt = builder._build_system_prompt()

    assert "<agent_control>" in system_prompt
    assert "我先整理眼前的对话、工具结果和刚刚完成的动作" in system_prompt
    assert "需要补信息时，再安静地调用合适的工具" in system_prompt
    assert "不要重复调用已成功且结果仍有效的工具" not in system_prompt


def test_non_social_mode_keeps_agent_control():
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)
    builder.current_mode = "expert"

    system_prompt = builder._build_system_prompt()

    assert "<agent_control>" in system_prompt
    assert "我先整理眼前的对话、工具结果和刚刚完成的动作" in system_prompt
    assert "同一份仍然有效的结果已经拿到后，就继续使用它" in system_prompt
