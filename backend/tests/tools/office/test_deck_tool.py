from __future__ import annotations

import pytest

from app.tools.office.deck.deck_tool import CreatePptxFromDeckTool


@pytest.mark.asyncio
async def test_create_pptx_from_deck_missing_deck_returns_clear_error():
    result = await CreatePptxFromDeckTool().execute(deck=None)

    assert result["success"] is False
    assert result["data"]["error"] == "deck 参数缺失"


@pytest.mark.asyncio
async def test_create_pptx_from_deck_rejects_v1_contract():
    result = await CreatePptxFromDeckTool().execute(
        deck={
            "version": "suyuan.deck.v1",
            "title": "旧版",
            "slides": [{"id": "s01", "type": "cover", "title": "旧版封面"}],
        }
    )

    assert result["success"] is False
    assert result["data"]["error"] == "deck_schema_invalid"
    assert "suyuan.deck.v2" in result["summary"]


@pytest.mark.asyncio
async def test_create_pptx_from_deck_rejects_text_only_content_slide():
    result = await CreatePptxFromDeckTool().execute(
        deck={
            "version": "suyuan.deck.v2",
            "deck_type": "implementation_proposal",
            "title": "非法纯文字",
            "slides": [
                {
                    "id": "s01",
                    "archetype": "key_message",
                    "title": "平台能力建设",
                    "message": "只有文字",
                }
            ],
        }
    )

    assert result["success"] is False
    assert result["data"]["error"] == "deck_design_invalid"
    assert result["data"]["issues"][0]["type"] == "content_slide_without_visual_evidence"


@pytest.mark.asyncio
async def test_create_pptx_from_deck_delegates_normalized_slides(monkeypatch):
    captured = {}

    async def fake_execute(self, **kwargs):
        captured.update(kwargs)
        return {"success": True, "data": {"file_path": "/tmp/demo.pptx"}, "summary": "ok"}

    monkeypatch.setattr("app.tools.office.create_pptx_tool.CreatePptxTool.execute", fake_execute)

    result = await CreatePptxFromDeckTool().execute(
        deck={
            "version": "suyuan.deck.v2",
            "deck_type": "implementation_proposal",
            "title": "濮阳市智慧环保建设项目二期实施方案",
            "slides": [
                {
                    "id": "s01",
                    "archetype": "cover",
                    "title": "濮阳市智慧环保建设项目二期实施方案",
                    "subtitle": "智慧感知、平台协同与闭环治理能力建设",
                },
                {
                    "id": "s02",
                    "archetype": "three_column_points",
                    "title": "二期建设聚焦三类能力",
                    "content": {
                        "items": [
                            {"title": "感知补强", "body": "完善多源监测能力"},
                            {"title": "平台升级", "body": "统一数据底座与研判能力"},
                            {"title": "闭环治理", "body": "处置、复核、考核闭环"},
                        ]
                    },
                },
            ],
        },
        output_file="/tmp/demo.pptx",
        quality="standard",
        run_validation=True,
    )

    assert result["success"] is True
    assert captured["title"] == "濮阳市智慧环保建设项目二期实施方案"
    assert captured["slides"][0]["type"] == "title"
    assert captured["slides"][1]["type"] == "summary"
    assert captured["output_file"] == "/tmp/demo.pptx"
    assert captured["quality"] == "standard"
    assert captured["run_validation"] is True
