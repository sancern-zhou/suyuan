from app.api.session_routes import (
    _extract_office_documents_from_messages,
    _extract_visualizations_from_messages,
)
from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.observation_processor import ObservationProcessor
import pytest


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


def test_extract_office_documents_preserves_report_html_preview_with_markdown_preview():
    messages = [
        {
            "type": "tool_result",
            "timestamp": "2026-06-04T11:00:00",
            "data": {
                "result": {
                    "summary": "报告包已创建",
                    "metadata": {"generator": "create_report_package"},
                    "data": {
                        "file_path": "/tmp/reports/ops_audit/report.qmd",
                        "file_type": "report",
                        "markdown_preview": {"content": "# qmd", "file_type": "report"},
                        "html_preview": {
                            "html_id": "ops_audit",
                            "html_url": "/api/reports/ops_audit/html",
                            "file_type": "report",
                        },
                    },
                },
            },
        },
    ]

    documents = _extract_office_documents_from_messages(messages)

    assert len(documents) == 1
    assert documents[0]["markdown_preview"]["content"] == "# qmd"
    assert documents[0]["html_preview"]["html_url"] == "/api/reports/ops_audit/html"
    assert documents[0]["file_type"] == "report"


def test_extract_office_documents_accepts_svg_preview_for_diagram_files():
    messages = [
        {
            "type": "tool_result",
            "timestamp": "2026-06-12T02:00:00",
            "data": {
                "result": {
                    "summary": "自由画布图表已生成",
                    "metadata": {"generator": "create_diagram_artifact"},
                    "data": {
                        "file_path": "/tmp/html_artifacts/diagram/assets/diagram.drawio",
                        "file_type": "drawio",
                        "svg_preview": {
                            "svg_path": "/tmp/html_artifacts/diagram/assets/diagram.drawio.svg",
                            "svg_url": "/api/html-artifacts/diagram/assets/diagram.drawio.svg",
                            "file_type": "drawio_svg",
                            "format": "drawio_svg",
                        },
                        "related_files": [
                            {
                                "path": "/tmp/html_artifacts/diagram/assets/diagram.drawio",
                                "url": "/api/html-artifacts/diagram/assets/diagram.drawio",
                                "format": "drawio",
                            }
                        ],
                    },
                },
            },
        },
    ]

    documents = _extract_office_documents_from_messages(messages)

    assert len(documents) == 1
    assert documents[0]["file_type"] == "drawio"
    assert documents[0]["svg_preview"]["svg_url"] == "/api/html-artifacts/diagram/assets/diagram.drawio.svg"
    assert documents[0]["related_files"][0]["format"] == "drawio"


@pytest.mark.asyncio
async def test_document_events_preserve_markdown_and_html_preview_for_same_report():
    processor = ObservationProcessor(finalizer=None, event_bus=RuntimeEventBus())
    observation = {
        "success": True,
        "summary": "报告包已创建",
        "metadata": {"generator": "create_report_package"},
        "data": {
            "file_path": "/tmp/reports/ops_audit/report.qmd",
            "file_type": "report",
            "markdown_preview": {"content": "# qmd", "file_type": "report"},
            "html_preview": {
                "html_id": "ops_audit",
                "html_url": "/api/reports/ops_audit/html",
                "file_type": "report",
            },
        },
    }

    events = [event async for event in processor._document_events(observation)]

    assert len(events) == 1
    assert events[0]["data"]["markdown_preview"]["content"] == "# qmd"
    assert events[0]["data"]["html_preview"]["html_url"] == "/api/reports/ops_audit/html"
    assert events[0]["data"]["file_type"] == "report"


@pytest.mark.asyncio
async def test_document_events_emit_svg_preview_for_diagram_files():
    processor = ObservationProcessor(finalizer=None, event_bus=RuntimeEventBus())
    observation = {
        "success": True,
        "summary": "自由画布图表已生成",
        "metadata": {"generator": "create_diagram_artifact"},
        "data": {
            "file_path": "/tmp/html_artifacts/diagram/assets/diagram.drawio",
            "file_type": "drawio",
            "svg_preview": {
                "svg_path": "/tmp/html_artifacts/diagram/assets/diagram.drawio.svg",
                "svg_url": "/api/html-artifacts/diagram/assets/diagram.drawio.svg",
                "file_type": "drawio_svg",
                "format": "drawio_svg",
            },
            "related_files": [
                {
                    "path": "/tmp/html_artifacts/diagram/assets/diagram.drawio",
                    "url": "/api/html-artifacts/diagram/assets/diagram.drawio",
                    "format": "drawio",
                }
            ],
        },
    }

    events = [event async for event in processor._document_events(observation)]

    assert len(events) == 1
    assert events[0]["type"] == "office_document"
    assert events[0]["data"]["file_type"] == "drawio"
    assert events[0]["data"]["svg_preview"]["svg_url"] == "/api/html-artifacts/diagram/assets/diagram.drawio.svg"
    assert events[0]["data"]["related_files"][0]["format"] == "drawio"
