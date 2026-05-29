import pytest
from pydantic import ValidationError

from app.tools.office.deck.deck_tool import CreatePptxFromDeckTool
from app.tools.office.deck.models import DeckSpec
from app.tools.office.deck.normalizer import normalize_deck_for_create_pptx
from app.tools.office.deck.visual_rules import validate_visual_rules


def test_deck_spec_accepts_business_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "广东省空气质量分析汇报",
            "audience": "management",
            "tone": "analytical",
            "slides": [
                {
                    "id": "s01",
                    "type": "metric_dashboard",
                    "title": "全省核心指标概览",
                    "metrics": [
                        {"label": "PM2.5均值", "value": 38, "unit": "ug/m3", "tone": "warning"}
                    ],
                }
            ],
        }
    )

    assert deck.version == "suyuan.deck.v1"
    assert deck.slides[0].type == "metric_dashboard"


def test_deck_spec_requires_slide_id_and_type():
    try:
        DeckSpec.model_validate(
            {
                "version": "suyuan.deck.v1",
                "title": "缺少类型",
                "slides": [{"title": "问题页"}],
            }
        )
    except ValidationError as exc:
        assert "id" in str(exc)
        assert "type" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")


def test_visual_rules_reject_text_only_business_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "纯文字风险",
            "slides": [
                {
                    "id": "s02",
                    "type": "map_insight",
                    "title": "珠三角污染分析",
                    "insights": ["污染累积明显", "扩散条件较差"],
                }
            ],
        }
    )

    issues = validate_visual_rules(deck)

    assert issues
    assert issues[0]["type"] == "missing_visual_evidence"
    assert issues[0]["slide_id"] == "s02"


def test_visual_rules_allow_section_without_visual():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "章节页",
            "slides": [{"id": "s01", "type": "section", "title": "一、总体情况"}],
        }
    )

    assert validate_visual_rules(deck) == []


def test_normalize_metric_dashboard_to_metrics_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "指标页",
            "slides": [
                {
                    "id": "s01",
                    "type": "metric_dashboard",
                    "title": "核心指标",
                    "metrics": [{"label": "AQI", "value": 85}],
                }
            ],
        }
    )

    result = normalize_deck_for_create_pptx(deck)

    assert result["title"] == "指标页"
    assert result["slides"][0]["type"] == "metrics"
    assert result["slides"][0]["metrics"][0]["label"] == "AQI"


def test_normalize_map_insight_to_image_text_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "地图页",
            "slides": [
                {
                    "id": "s02",
                    "type": "map_insight",
                    "title": "污染空间分布",
                    "visual": {"kind": "map", "asset": "assets/maps/pm25.png"},
                    "insights": ["北部污染较高", "沿海扩散较好"],
                }
            ],
        }
    )

    result = normalize_deck_for_create_pptx(deck)

    slide = result["slides"][0]
    assert slide["type"] == "image_text"
    assert slide["image"]["path"] == "assets/maps/pm25.png"
    assert slide["bullets"] == ["北部污染较高", "沿海扩散较好"]


@pytest.mark.asyncio
async def test_create_pptx_from_deck_rejects_missing_visual():
    tool = CreatePptxFromDeckTool()

    result = await tool.execute(
        deck={
            "version": "suyuan.deck.v1",
            "title": "非法纯文字",
            "slides": [
                {
                    "id": "s01",
                    "type": "map_insight",
                    "title": "空间分布",
                    "insights": ["只有文字"],
                }
            ],
        }
    )

    assert result["success"] is False
    assert "missing_visual_evidence" in result["summary"]
