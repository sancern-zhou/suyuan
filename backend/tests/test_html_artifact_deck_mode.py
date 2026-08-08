from __future__ import annotations

import pytest

from app.services.html_artifact_service import HtmlArtifactService
from app.tools.html_artifact import tool as html_tool_module
from app.tools.html_artifact.tool import CreateHtmlArtifactTool


def test_fixed_prompts_do_not_embed_html_artifact_deck_usage() -> None:
    from app.agent.prompts import assistant_prompt, report_prompt

    assistant_text = assistant_prompt.build_assistant_prompt([])
    report_text = report_prompt.build_report_prompt([])

    assert 'presentation_kind="deck"' not in assistant_text
    assert 'layout_system="guizang"' not in assistant_text
    assert 'presentation_kind="deck"' not in report_text
    assert 'layout_system="guizang"' not in report_text


def test_create_html_artifact_schema_exposes_guizang_deck_mode() -> None:
    schema = CreateHtmlArtifactTool().get_function_schema()
    properties = schema["parameters"]["properties"]

    assert properties["display_mode"]["enum"] == ["presentation", "dashboard", "story", "single_page", "custom"]
    assert properties["presentation_kind"]["enum"] == ["deck", "page", "cover"]
    assert properties["layout_system"]["enum"] == ["guizang", "custom"]
    assert properties["presentation_style"]["enum"] == ["magazine", "swiss"]
    assert "guizang" in properties["layout_system"]["description"]
    assert "read_file" in schema["description"]
    assert "template_magazine=" in properties["layout_system"]["description"]
    assert "调用本工具前先读取" in properties["html_content"]["description"]
    assert "不要凭空编写新的 deck 框架" in properties["html_content"]["description"]


@pytest.mark.asyncio
async def test_create_html_artifact_records_guizang_deck_metadata(tmp_path, monkeypatch) -> None:
    service = HtmlArtifactService(root=tmp_path)
    monkeypatch.setattr(html_tool_module, "html_artifact_service", service)

    result = await CreateHtmlArtifactTool().execute(
        artifact_id="visual_deck",
        html_content="<!doctype html><html><head><title>Deck</title></head><body></body></html>",
        title="视觉优先演示",
        display_mode="presentation",
        presentation_kind="deck",
        layout_system="guizang",
        presentation_style="swiss",
        validation="swiss",
    )

    assert result["success"] is True
    meta = service.read_meta("visual_deck")
    assert meta["display_mode"] == "presentation"
    assert meta["presentation_kind"] == "deck"
    assert meta["layout_system"] == "guizang"
    assert meta["presentation_style"] == "swiss"
    assert meta["deck_asset_paths"]["template_swiss"].endswith("template-swiss.html")
    assert meta["deck_asset_paths"]["validate_swiss"].endswith("validate-swiss-deck.mjs")
    assert [item["resource_key"] for item in result["resources"]] == [
        "source:html",
        "preview:html",
    ]
    assert result["llm_resume"] == {
        "artifact_path": result["data"]["file_path"],
        "artifact_format": "html",
        "tool_hint": "Artifact preview and download resources are published automatically.",
        "artifact_id": "visual_deck",
    }
