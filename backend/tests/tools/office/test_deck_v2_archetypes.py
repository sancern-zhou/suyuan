from app.tools.office.deck.archetypes import render_slide_to_create_pptx
from app.tools.office.deck.models import DeckSlideSpec, DeckSpec
from app.tools.office.deck.normalizer import normalize_deck_for_create_pptx


def test_render_cover_to_title_slide():
    slide = DeckSlideSpec(
        id="s01",
        archetype="cover",
        title="濮阳市智慧环保建设项目二期实施方案",
        subtitle="智慧感知、平台协同与闭环治理能力建设",
    )

    rendered = render_slide_to_create_pptx(slide)

    assert rendered["type"] == "title"
    assert rendered["title"] == slide.title
    assert rendered["subtitle"] == slide.subtitle


def test_render_three_column_points_to_summary_items():
    slide = DeckSlideSpec.model_validate(
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
        }
    )

    rendered = render_slide_to_create_pptx(slide)

    assert rendered["type"] == "summary"
    assert rendered["title"] == slide.title
    assert rendered["items"][0]["title"] == "感知补强"


def test_render_evidence_table_to_table_slide():
    slide = DeckSlideSpec.model_validate(
        {
            "id": "s03",
            "archetype": "evidence_table",
            "title": "建设内容清单",
            "table": [["类别", "内容"], ["感知", "站点与视频接入"]],
        }
    )

    rendered = render_slide_to_create_pptx(slide)

    assert rendered["type"] == "table"
    assert rendered["table"][0] == ["类别", "内容"]


def test_render_chart_story_prefers_native_chart():
    slide = DeckSlideSpec.model_validate(
        {
            "id": "s04",
            "archetype": "chart_story",
            "title": "能力建设进度逐季提升",
            "message": "平台能力在二三季度集中上线。",
            "chart": {
                "type": "line",
                "data": {
                    "labels": ["Q1", "Q2", "Q3"],
                    "datasets": [{"name": "上线模块", "values": [2, 6, 10]}],
                },
            },
        }
    )

    rendered = render_slide_to_create_pptx(slide)

    assert rendered["type"] == "data_story"
    assert rendered["chart"]["type"] == "line"
    assert rendered["message"] == slide.message


def test_normalize_deck_v2_adds_design_brief_and_rendered_slides():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v2",
            "deck_type": "implementation_proposal",
            "title": "濮阳市智慧环保建设项目二期实施方案",
            "audience": "government_decision_makers",
            "tone": "formal",
            "slides": [
                {
                    "id": "s01",
                    "archetype": "cover",
                    "title": "濮阳市智慧环保建设项目二期实施方案",
                    "subtitle": "智慧感知、平台协同与闭环治理能力建设",
                }
            ],
        }
    )

    result = normalize_deck_for_create_pptx(deck)

    assert result["title"] == deck.title
    assert result["design_brief"]["audience"] == "government_decision_makers"
    assert result["design_brief"]["style"] == "Proposal Deck V2"
    assert result["slides"][0]["type"] == "title"
