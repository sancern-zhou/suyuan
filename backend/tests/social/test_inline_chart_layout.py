from app.social.inline_charts import attach_reply_resources, reply_chart_ids


IMAGE_ID = "0123456789abcdef0123456789abcdef"
SPEC_ID = "fedcba9876543210fedcba9876543210"


def marker(resource_id):
    return f"[[chart:{resource_id}]]"


def test_static_image_and_interactive_spec_match_their_own_ids():
    image = {"file_id": "image", "resource_id": IMAGE_ID, "group_id": "chart", "mime_type": "image/png"}
    spec = {
        "file_id": "spec", "resource_id": SPEC_ID, "group_id": "chart",
        "resource_key": "chart-spec", "interactive": True,
    }
    for resources in ([spec, image], [image, spec]):
        history = [
            {"type": "final", "content": marker(IMAGE_ID)},
            {"role": "assistant", "content": marker(SPEC_ID)},
            {"type": "final", "content": "下一轮"},
        ]
        attach_reply_resources(history, resources)
        assert [message["attachments"] for message in history] == [[image], [spec], []]


def test_only_assistant_chart_ids_outside_code_are_looked_up():
    image = {"file_id": IMAGE_ID, "mime_type": "image/png"}
    history = [
        {"type": "user", "content": marker(SPEC_ID)},
        {"type": "final", "content": f"`{marker(SPEC_ID)}` {marker(IMAGE_ID)} [[chart:chart_0]]"},
    ]
    assert reply_chart_ids(history) == {IMAGE_ID}
    attach_reply_resources(history, [image])
    assert "attachments" not in history[0]
    assert history[1]["attachments"] == []


def test_duplicate_references_preserve_unrelated_file_ids_and_do_not_revive_old_group():
    image = {"file_id": "image", "resource_id": IMAGE_ID, "group_id": "chart", "mime_type": "image/png"}
    unrelated = {"file_id": "existing-file", "url": "/api/upload/existing-file"}
    history = [{"type": "final", "content": f"{marker(IMAGE_ID)} {marker(IMAGE_ID)}", "attachments": [unrelated, image]}]
    same_group = {"file_id": "spec", "resource_id": SPEC_ID, "group_id": "chart", "resource_key": "chart-spec"}
    attach_reply_resources(history, [same_group], chart_descriptors=[image])
    assert history[0]["attachments"] == [unrelated, image]


def test_run_resources_go_to_their_own_reply_not_the_latest():
    history = [
        {"type": "user"}, {"type": "tool_result", "role": "assistant", "data": {"run_id": "run1"}},
        {"type": "final", "content": "第一轮"}, {"type": "user"},
        {"type": "final", "data": {"run_id": "run2"}, "content": "第二轮"},
    ]
    resources = [{"file_id": "f1", "run_id": "run1"}, {"file_id": "f2", "run_id": "run2"}, {"file_id": "unknown"}]
    attach_reply_resources(history, resources)
    assert "attachments" not in history[1]
    assert history[2]["attachments"] == [resources[0]]
    assert history[4]["attachments"] == [resources[1]]


def test_new_group_versions_replace_old_attachment_urls():
    history = [{"type": "final", "attachments": [{"file_id": "old", "group_id": "report"}]}]
    current = {"file_id": "new", "group_id": "report", "run_id": "resource-edit"}
    attach_reply_resources(history, [current])
    assert history[0]["attachments"] == [current]
