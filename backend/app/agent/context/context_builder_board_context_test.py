from app.agent.context.context_builder import SimplifiedContextBuilder


def test_board_user_conversation_includes_selected_cells_summary():
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)
    builder.current_mode = "board"
    builder.board_context = {
        "selected_cells": [
            {
                "id": "container-1",
                "value": "业务容器",
                "vertex": True,
                "geometry": {"x": 10, "y": 20, "width": 120, "height": 80},
            }
        ]
    }

    user_conversation = builder._build_user_conversation(
        query="我选中一个容器",
        iteration=1,
        latest_observation="",
        conversation_history=[{"role": "user", "content": "历史消息"}],
    )

    assert "## 当前画板选中状态" in user_conversation
    assert "当前已选中 1 个元素" in user_conversation
    assert "container-1" in user_conversation
    assert "业务容器" in user_conversation
    assert "geometry=(x=10, y=20, w=120, h=80)" in user_conversation
