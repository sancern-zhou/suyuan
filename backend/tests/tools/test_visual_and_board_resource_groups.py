import json

from app.agent.resources.contracts import ResourceDeclaration
from app.tools.resource_declarations import board_product, resources_for_visuals


def validate(resources):
    return [ResourceDeclaration.model_validate(resource) for resource in resources]


def test_chart_spec_and_image_are_one_resource_group(tmp_path, monkeypatch):
    image = tmp_path / "chart.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        "app.tools.resource_declarations.get_data_registry", lambda: tmp_path
    )
    resources = validate(
        resources_for_visuals(
            [
                {
                    "id": "chart-1",
                    "type": "bar",
                    "title": "Air quality",
                    "local_path": str(image),
                    "payload": {"series": [1, 2], "image_url": "/api/image/chart-1"},
                }
            ],
            tool_name="create_report_chart",
        )
    )
    by_key = {resource.resource_key: resource for resource in resources}

    chart = by_key["chart-spec"]
    rendition = by_key["chart-image"]
    assert chart.kind.value == "visual"
    assert chart.renderer.value == "chart"
    assert chart.media_type == "application/json"
    assert rendition.relation.value == "rendition"
    assert rendition.parent_key == "chart-spec"
    spec = json.loads((tmp_path / "charts" / "chart-1.json").read_text())
    assert "image_url" not in str(spec)
    assert str(tmp_path) not in str(spec)


def test_board_xml_and_screenshot_are_bound(tmp_path):
    xml = tmp_path / "board.drawio"
    screenshot = tmp_path / "board.png"
    xml.write_text("<mxfile/>")
    screenshot.write_bytes(b"png")
    resources = validate(
        board_product(
            xml_path=xml,
            artifact_id="board-1",
            screenshot_path=screenshot,
            tool_name="create_drawio_board",
        )
    )
    by_key = {resource.resource_key: resource for resource in resources}

    board = by_key["board-xml"]
    preview = by_key["board-preview"]
    assert board.renderer.value == "board"
    assert board.media_type == "application/xml"
    assert preview.parent_key == board.resource_key
    assert preview.relation.value == "preview"
    assert {resource.group_key for resource in resources} == {"board:board-1"}
