from app.db.session_repository import SessionRepository


class _LightRow:
    id = 42
    role = "assistant"
    timestamp = None
    sequence_number = 7
    msg_metadata = None

    def __init__(
        self,
        *,
        msg_type,
        display_content,
        content_preview,
        human_feedback=None,
        ownership=None,
    ):
        self.msg_type = msg_type
        self.display_content = display_content
        self.content_preview = content_preview
        self.human_feedback = human_feedback
        for key, value in (ownership or {}).items():
            setattr(self, f"ownership_{key}", value)


def test_lightweight_final_message_uses_complete_content():
    complete = "备件保障：保证有足够的备件及备用仪器。" + "根据实际需要进行增加。" * 300
    truncated_json_preview = '"' + complete[:330] + "\\"
    row = _LightRow(
        msg_type="final",
        display_content=complete,
        content_preview=truncated_json_preview,
    )

    message = SessionRepository()._message_row_to_light_dict(row)

    assert len(complete) > 2000
    assert message["content"] == complete
    assert "content_preview" not in message


def test_lightweight_process_message_keeps_bounded_preview():
    row = _LightRow(
        msg_type="tool_result",
        display_content=None,
        content_preview="工具结果预览",
    )

    message = SessionRepository()._message_row_to_light_dict(row)

    assert message["content"] == "工具结果预览"
    assert message["content_preview"] == "工具结果预览"


def test_lightweight_tool_result_preserves_human_feedback_contract():
    feedback = {
        "feedback_id": "ops-audit:abc",
        "required": True,
        "report_input_path": "/data/report_input.json",
        "items": [{"item_id": "issue-1", "kind": "issue", "title": "待确认问题"}],
    }
    row = _LightRow(
        msg_type="tool_result",
        display_content=None,
        content_preview="确定性规则已执行",
        human_feedback=feedback,
    )

    message = SessionRepository()._message_row_to_light_dict(row)

    assert message["data"]["result"]["data"]["human_feedback"] == feedback


def test_lightweight_tool_result_parses_json_string_feedback():
    row = _LightRow(
        msg_type="tool_result",
        display_content=None,
        content_preview="工具结果预览",
        human_feedback='{"feedback_id": "ops-audit:abc", "required": true, "items": []}',
    )

    message = SessionRepository()._message_row_to_light_dict(row)

    assert message["data"]["result"]["data"]["human_feedback"]["feedback_id"] == "ops-audit:abc"


def test_lightweight_final_message_restores_delivery_ownership():
    # JSON 文本与驱动已解码两种形态都要能回填（replyOutcomes 所有权扫描依赖）。
    row = _LightRow(
        msg_type="final",
        display_content="报告生成完毕",
        content_preview="报告生成完毕",
        ownership={
            "run_id": "fac994d8631c4103a43c7ea3cba4b648",
            "resource_ids": '["04a3fc268ec8a048fa4659bdc0efb340"]',
            "resource_group_ids": ["7c0a810a5ffa84c55a9c8ab16a5648be"],
            "resource_run_ids": None,
        },
    )

    message = SessionRepository()._message_row_to_light_dict(row)

    assert message["data"]["run_id"] == "fac994d8631c4103a43c7ea3cba4b648"
    assert message["data"]["resource_ids"] == ["04a3fc268ec8a048fa4659bdc0efb340"]
    assert message["data"]["resource_group_ids"] == ["7c0a810a5ffa84c55a9c8ab16a5648be"]
    assert "resource_run_ids" not in message["data"]


def test_lightweight_final_message_without_ownership_keeps_light_data():
    row = _LightRow(
        msg_type="final",
        display_content="纯文本回复",
        content_preview="纯文本回复",
    )

    message = SessionRepository()._message_row_to_light_dict(row)

    assert "data" not in message
