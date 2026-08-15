from app.social.agent_bridge import _heartbeat_should_notify


def test_heartbeat_ok_response_is_not_notified():
    assert _heartbeat_should_notify("HEARTBEAT_OK", use_social_context=True) is False


def test_structured_silent_response_is_not_notified():
    summary = '{"heartbeat_silent": true, "reason": "告警文件不存在"}'

    assert _heartbeat_should_notify(summary, use_social_context=True) is False


def test_regular_heartbeat_summary_is_notified_in_social_context():
    assert _heartbeat_should_notify("发现运城市臭氧告警，已生成溯源报告。", use_social_context=True) is True
