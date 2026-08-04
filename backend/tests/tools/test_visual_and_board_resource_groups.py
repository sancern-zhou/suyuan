import json

import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.tools.resource_declarations import (
    board_product,
    generated_file_products,
    resources_for_visuals,
)
from app.tools.visualization.create_report_chart.tool import CreateReportChartTool


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


def test_generated_office_file_and_pdf_preview_are_one_resource_group(tmp_path):
    document = tmp_path / "report.docx"
    preview = tmp_path / "report.pdf"
    document.write_bytes(b"docx")
    preview.write_bytes(b"pdf")

    resources = validate(
        generated_file_products(
            [document],
            tool_name="execute_python",
            preview_paths={str(document): str(preview)},
        )
    )

    assert len(resources) == 2
    primary, child = resources
    assert primary.resource_key == "primary:docx"
    assert primary.renderer.value == "file"
    assert set(item.value for item in primary.capabilities) == {"download"}
    assert child.parent_key == primary.resource_key
    assert child.relation.value == "preview"
    assert child.renderer.value == "pdf"
    assert {resource.group_key for resource in resources} == {primary.group_key}


def test_generated_image_is_previewable_resource(tmp_path):
    image = tmp_path / "analysis.png"
    image.write_bytes(b"png")

    [resource] = validate(
        generated_file_products([image], tool_name="execute_python")
    )

    assert resource.renderer.value == "image"
    assert set(item.value for item in resource.capabilities) == {"preview", "download"}


@pytest.mark.asyncio
async def test_create_report_chart_publishes_visual_and_image_resources(tmp_path, monkeypatch):
    image = tmp_path / "generated-chart.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        "app.tools.resource_declarations.get_data_registry", lambda: tmp_path
    )
    monkeypatch.setattr(
        "app.tools.visualization.create_report_chart.renderer.render_report_chart",
        lambda **_kwargs: {
            "visuals": [{
                "id": "generated-chart",
                "type": "bar",
                "title": "Generated chart",
                "local_path": str(image),
            }],
            "summary": "generated",
        },
    )

    result = await CreateReportChartTool().execute(
        chart_type="bar",
        title="Generated chart",
        data={"labels": ["A"], "values": [1]},
    )
    resources = validate(result["resources"])

    assert "image_url" not in result["visuals"][0]
    assert "url" not in result["visuals"][0]
    assert [resource.resource_key for resource in resources] == [
        "chart-spec", "chart-image"
    ]
    assert resources[0].kind.value == "visual"
    assert resources[1].renderer.value == "image"


def test_create_report_chart_loads_structured_object_from_file_payload():
    expected = {"labels": ["A", "B"], "values": [1, 2]}

    class Context:
        def get_data_payload(self, file_path):
            assert file_path == "/session/data/chart-input.json"
            return expected

    actual = CreateReportChartTool()._resolve_chart_data(
        data=None,
        file_path="/session/data/chart-input.json",
        context=Context(),
    )

    assert actual == expected
