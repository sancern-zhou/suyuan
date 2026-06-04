from app.api.session_routes import _extract_visualizations_from_messages


def test_extract_visualizations_from_nested_tool_results():
    messages = [
        {
            "type": "tool_result",
            "data": {
                "result": {
                    "visuals": [{"id": "top", "type": "chart"}],
                    "tool_results": [
                        {"result": {"visuals": [{"id": "nested", "type": "image"}]}},
                    ],
                },
                "results": [
                    {"data": {"visuals": [{"id": "multi", "type": "table"}]}},
                ],
            },
        },
    ]

    visuals = _extract_visualizations_from_messages(messages)

    assert [visual["id"] for visual in visuals] == ["top", "nested", "multi"]
