from app.agent.prompts.social_prompt import build_social_prompt


def test_social_prompt_does_not_embed_full_heartbeat_context_snapshot():
    prompt = build_social_prompt(
        available_tools=["schedule_task"],
        heartbeat_file_path="/tmp/HEARTBEAT.md",
        heartbeat_context="- name: 旧任务\n  schedule: \"0 9 * * *\"\n  enabled: true",
    )

    assert "HEARTBEAT.md：`/tmp/HEARTBEAT.md`" not in prompt
    assert "当前 HEARTBEAT.md 内容快照" not in prompt
    assert "旧任务" not in prompt
    assert "schedule_task" not in prompt
    assert "定时任务" not in prompt
