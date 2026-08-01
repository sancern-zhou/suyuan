from dataclasses import dataclass
from collections.abc import Callable

from app.agent.resources.normalizer import normalize_tool_resources
from app.tools.resource_declarations import (
    board_product,
    chart_resource,
    directory_artifact,
    file_product,
    preview_file,
    single_file_product,
)


@dataclass(frozen=True)
class Producer:
    name: str
    category: str
    fixture_result: Callable[[], dict]


def test_every_output_producer_category_declares_valid_resources(tmp_path):
    files = {}
    for suffix in ("txt", "md", "pdf", "docx", "xlsx", "pptx", "png", "drawio", "json", "nc"):
        target = tmp_path / f"output.{suffix}"
        target.write_bytes(b"fixture")
        files[suffix] = target
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "index.html").write_text("<h1>fixture</h1>", encoding="utf-8")

    def one(name, suffix):
        return lambda: {"resources": [single_file_product(files[suffix], tool_name=name)]}

    producers = [
        Producer("bash", "generic-command", one("bash", "txt")),
        Producer("write_file", "generic-file", one("write_file", "md")),
        Producer("office_docx", "office", lambda: {"resources": file_product(
            primary_path=files["docx"], group_key="office:docx", tool_name="office_docx",
            previews=[preview_file(files["pdf"], renderer="pdf")], role="report")}),
        Producer("spreadsheet", "office", one("spreadsheet", "xlsx")),
        Producer("presentation", "office", one("presentation", "pptx")),
        Producer("report_package", "report", one("report_package", "pdf")),
        Producer("html_artifact", "html-artifact", lambda: {"resources": [directory_artifact(
            artifact, entrypoint="index.html", group_key="html:fixture", tool_name="html_artifact")]}),
        Producer("chart", "chart", lambda: {"resources": [chart_resource(
            "chart-1", path=files["json"], group_key="chart:fixture", tool_name="chart")]}),
        Producer("map", "map", lambda: {"resources": [chart_resource(
            "map-1", path=files["json"], group_key="map:fixture", tool_name="map")]}),
        Producer("board", "board", lambda: {"resources": board_product(
            xml_path=files["drawio"], artifact_id="board-1", tool_name="board",
            screenshot_path=files["png"])}),
        Producer("browser_download", "browser", one("browser_download", "pdf")),
        Producer("browser_screenshot", "browser", one("browser_screenshot", "png")),
        Producer("gfs_download", "gfs", one("gfs_download", "nc")),
        Producer("gfs_processor", "gfs", one("gfs_processor", "json")),
        Producer("analysis_export", "analysis", one("analysis_export", "json")),
    ]

    expected_categories = {
        "generic-command", "generic-file", "office", "report", "html-artifact",
        "chart", "map", "board", "browser", "gfs", "analysis",
    }
    assert {producer.category for producer in producers} == expected_categories
    for producer in producers:
        declarations, rejected = normalize_tool_resources(result=producer.fixture_result())
        assert not rejected, producer.name
        assert declarations, f"{producer.name} produced output without resources"
