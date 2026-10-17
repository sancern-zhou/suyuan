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


def test_agent_control_guides_concurrent_tool_calls():
    """独立调用同轮并发的通用引导注入所有模式(2026-10-16)。

    引导位于 _build_agent_control_prompt(平台层, 所有模式共享);
    jiangsu_query 等项目模式需完整部署环境才能注册, 这里用内置模式验证。
    """
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)

    for mode in ("social", "expert"):
        builder.current_mode = mode
        system_prompt = builder._build_system_prompt()
        assert "必须在同一轮一次性并行发起" in system_prompt, mode
        assert "只有下一步确实依赖上一步结果" in system_prompt, mode
        assert "同一维度的查询不要跨轮重复" in system_prompt, mode
