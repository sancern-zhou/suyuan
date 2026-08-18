from app.boards.design import (
    build_board_structural_digest,
    normalize_board_design_spec,
    normalize_board_theme_tokens,
)

SAMPLE_XML = """<mxfile><diagram><mxGraphModel><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="lane" value="处置域" vertex="1" parent="1" style="swimlane;container=1">
  <mxGeometry x="20" y="20" width="420" height="260" as="geometry"/>
</mxCell>
<mxCell id="start" value="接收告警" vertex="1" parent="lane" style="rounded=1">
  <mxGeometry x="20" y="60" width="120" height="60" as="geometry"/>
</mxCell>
<mxCell id="decision" value="需要升级？" vertex="1" parent="lane" style="rhombus">
  <mxGeometry x="180" y="60" width="100" height="80" as="geometry"/>
</mxCell>
<mxCell id="finish" value="通知负责人" vertex="1" parent="lane" style="rounded=1">
  <mxGeometry x="320" y="60" width="80" height="60" as="geometry"/>
</mxCell>
<mxCell id="edge_start_decision" value="检查" edge="1" parent="lane" source="start" target="decision">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
<mxCell id="edge_decision_finish" value="是" edge="1" parent="lane" source="decision" target="finish">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
</root></mxGraphModel></diagram></mxfile>"""


def test_structural_digest_extracts_graph_and_selected_neighborhood():
    digest = build_board_structural_digest(
        SAMPLE_XML,
        selected_cells=[{"id": "decision", "value": "需要升级？"}],
    )

    assert digest["status"] == "ok"
    assert digest["metrics"]["node_count"] == 4
    assert digest["metrics"]["edge_count"] == 2
    assert digest["metrics"]["container_count"] == 1
    assert digest["type_candidates"][0] == "flowchart"
    assert digest["selected_subgraph"]["node_ids"] == ["decision", "finish", "start"]
    assert digest["selected_subgraph"]["edge_ids"] == [
        "edge_start_decision",
        "edge_decision_finish",
    ]
    decision = next(node for node in digest["nodes"] if node["id"] == "decision")
    assert decision["parent"] == "lane"
    assert decision["depth"] == 1
    assert decision["shape"] == "decision"


def test_design_spec_normalizes_invalid_values_and_infers_type():
    digest = build_board_structural_digest(SAMPLE_XML)

    spec = normalize_board_design_spec(
        {
            "audience": "unknown",
            "detail_level": "huge",
            "canvas_preset": "poster",
            "focus_cell_ids": [
                "decision",
                "finish",
                "extra",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
            ],
        },
        structural_digest=digest,
    )

    assert spec["diagram_type"] == "flowchart"
    assert spec["audience"] == "mixed"
    assert spec["detail_level"] == "balanced"
    assert spec["canvas_preset"] == "auto"
    assert len(spec["focus_cell_ids"]) == 8


def test_theme_tokens_accept_only_complete_hex_colors():
    tokens = normalize_board_theme_tokens(
        {
            "accent": "#123abc",
            "surface": "red",
            "unknown": "#000000",
        }
    )

    assert tokens["accent"] == "#123ABC"
    assert tokens["surface"] == "#FFFFFF"
    assert "unknown" not in tokens
