from app.agent.session.workspace_routing import (
    bind_workspace_request_to_source_query,
    build_workspace_approval_request,
    build_workspace_promotion,
    is_workspace_switch_only_request,
    is_workspace_promotion,
)


def test_workspace_promotion_has_stable_session_contract():
    promotion = build_workspace_promotion(
        target_mode="board",
        session_id="assistant__to__board__20260905",
        artifact_id="board-1",
    )

    assert promotion == {
        "promoted": True,
        "target_mode": "board",
        "workspace_type": "board",
        "session_id": "assistant__to__board__20260905",
        "artifact_id": "board-1",
        "reason": "artifact_editing",
        "sticky": True,
    }
    assert is_workspace_promotion(promotion)


def test_workspace_promotion_rejects_non_persistent_or_incomplete_metadata():
    assert not is_workspace_promotion({"promoted": True, "target_mode": "query"})
    assert not is_workspace_promotion({"promoted": True, "target_mode": "board", "session_id": ""})


def test_workspace_approval_resumes_the_original_user_task():
    promotion = build_workspace_promotion(target_mode="ppt", session_id="web-session")
    pending = build_workspace_approval_request(
        promotion=promotion,
        goal="切换到PPT模式并等待用户后续操作",
    )

    bound = bind_workspace_request_to_source_query(
        pending,
        "把上传的季度总结制作成一份 PPT",
    )

    assert bound["goal"] == "把上传的季度总结制作成一份 PPT"
    assert bound["resume_after_approval"] is True


def test_workspace_switch_only_request_does_not_start_an_acknowledgement_run():
    assert is_workspace_switch_only_request("切换到 PPT 模式", "ppt")
    assert is_workspace_switch_only_request("进入画板工作空间", "board")
    assert not is_workspace_switch_only_request("切换到PPT模式并制作季度总结", "ppt")

    pending = {
        "target_mode": "ppt",
        "goal": "切换到 PPT 模式",
        "session_id": "web-session",
    }
    bound = bind_workspace_request_to_source_query(pending, "切换到 PPT 模式")
    assert bound["resume_after_approval"] is False
