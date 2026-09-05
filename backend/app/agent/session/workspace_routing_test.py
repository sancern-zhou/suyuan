from app.agent.session.workspace_routing import (
    build_workspace_promotion,
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
