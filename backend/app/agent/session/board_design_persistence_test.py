from app.agent.session.conversation_persistence import ConversationPersistenceService


def test_normalize_drawio_board_persists_lightweight_design_contract():
    normalized = ConversationPersistenceService.normalize_drawio_board(
        {
            "board_id": "board-1",
            "current_version_id": "version-2",
            "revision": 2,
            "title": "系统架构图",
            "current_xml": "<mxfile>large</mxfile>",
            "design_spec": {
                "diagram_type": "architecture",
                "audience": "mixed",
                "detail_level": "balanced",
            },
            "theme_tokens": {"accent": "#1677FF"},
            "structural_digest": {"nodes": ["must-not-persist"]},
        }
    )

    assert normalized == {
        "artifact_kind": "drawio_board",
        "board_id": "board-1",
        "active_board_id": "board-1",
        "title": "系统架构图",
        "current_version_id": "version-2",
        "revision": 2,
        "selected_cells": [],
        "updated_at": None,
        "design_spec": {
            "diagram_type": "architecture",
            "audience": "mixed",
            "detail_level": "balanced",
        },
        "theme_tokens": {"accent": "#1677FF"},
    }
