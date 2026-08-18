from app.boards.quality import evaluate_drawio_quality


def _board_xml(nodes: list[str], edges: list[str] | None = None) -> str:
    return (
        "<mxfile><diagram><mxGraphModel><root>"
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        + "".join(nodes)
        + "".join(edges or [])
        + "</root></mxGraphModel></diagram></mxfile>"
    )


def _node(cell_id: str, x: int, *, style: str = "rounded=1", parent: str = "1") -> str:
    return (
        f'<mxCell id="{cell_id}" value="节点{cell_id}" vertex="1" parent="{parent}" style="{style}">'
        f'<mxGeometry x="{x}" y="20" width="120" height="60" as="geometry"/>'
        "</mxCell>"
    )


def test_quality_report_applies_design_budget_and_theme_focus_rules():
    nodes = [
        _node(
            f"n{index}",
            index * 140,
            style="rounded=1;fillColor=#EAF2FF;strokeColor=#1677FF" if index < 3 else "rounded=1",
        )
        for index in range(13)
    ]
    report = evaluate_drawio_quality(
        _board_xml(nodes),
        design_spec={"diagram_type": "architecture", "detail_level": "balanced"},
    )
    codes = {warning["code"] for warning in report["warnings"]}

    assert report["status"] == "warning"
    assert "complexity_budget_exceeded" in codes
    assert "large_diagram_needs_zones" in codes
    assert "too_many_focal_nodes" in codes
    assert report["metrics"]["accent_node_count"] == 3
    assert report["metrics"]["complexity_budget"] == {"nodes": 12, "edges": 16}
    assert report["design_spec"]["diagram_type"] == "architecture"
    assert report["structural_digest"]["metrics"]["node_count"] == 13


def test_quality_report_flags_unlabeled_decision_branch_and_container_overflow():
    nodes = [
        (
            '<mxCell id="lane" value="责任域" vertex="1" parent="1" style="swimlane;container=1">'
            '<mxGeometry x="20" y="20" width="300" height="180" as="geometry"/></mxCell>'
        ),
        _node("decision", 260, style="rhombus", parent="lane"),
        _node("result", 20, parent="lane"),
    ]
    edges = [
        (
            '<mxCell id="edge" edge="1" parent="lane" source="decision" target="result">'
            '<mxGeometry relative="1" as="geometry"/></mxCell>'
        )
    ]
    report = evaluate_drawio_quality(_board_xml(nodes, edges))
    codes = {warning["code"] for warning in report["warnings"]}

    assert "decision_branch_unlabeled" in codes
    assert "container_child_overflow" in codes
    assert report["metrics"]["decision_branch_unlabeled_count"] == 1
    assert report["metrics"]["container_overflow_count"] == 1
