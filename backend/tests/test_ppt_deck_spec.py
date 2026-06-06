import pytest
from pydantic import ValidationError

from app.tools.office.deck.models import DeckSpec, SlideArchetype
from app.tools.office.deck.validators import validate_deck_design


def test_deck_v2_accepts_archetype_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v2",
            "deck_type": "implementation_proposal",
            "title": "濮阳市智慧环保建设项目二期实施方案",
            "audience": "government_decision_makers",
            "tone": "formal, evidence-led, implementation-focused",
            "slides": [
                {
                    "id": "s01",
                    "archetype": "cover",
                    "title": "濮阳市智慧环保建设项目二期实施方案",
                    "subtitle": "智慧感知、平台协同与闭环治理能力建设",
                },
                {
                    "id": "s02",
                    "archetype": "executive_summary",
                    "title": "二期建设聚焦从看得见到管得住",
                    "message": "围绕感知补强、平台升级、业务闭环和运营考核形成综合治理能力。",
                    "content": {
                        "items": [
                            {"title": "感知补强", "body": "完善空气、水、源、视频等多源监测能力"},
                            {"title": "平台升级", "body": "建设统一数据底座、预警研判和调度指挥能力"},
                            {"title": "闭环治理", "body": "形成发现、研判、派单、处置、复核全过程闭环"},
                        ]
                    },
                },
            ],
        }
    )

    assert deck.version == "suyuan.deck.v2"
    assert deck.deck_type == "implementation_proposal"
    assert deck.slides[1].archetype == "executive_summary"
    assert deck.slides[1].content.items[0].title == "感知补强"


def test_deck_v2_rejects_v1_version():
    with pytest.raises(ValidationError) as exc:
        DeckSpec.model_validate(
            {
                "version": "suyuan.deck.v1",
                "title": "旧版",
                "slides": [{"id": "s01", "type": "cover", "title": "旧版封面"}],
            }
        )

    assert "suyuan.deck.v2" in str(exc.value)


def test_deck_v2_rejects_low_level_type_field():
    with pytest.raises(ValidationError) as exc:
        DeckSpec.model_validate(
            {
                "version": "suyuan.deck.v2",
                "deck_type": "implementation_proposal",
                "title": "错误输入",
                "slides": [{"id": "s01", "type": "title", "title": "低层类型"}],
            }
        )

    message = str(exc.value)
    assert "archetype" in message


def test_slide_archetype_list_contains_core_proposal_types():
    assert "implementation_plan" in SlideArchetype.__args__
    assert "architecture_overview" in SlideArchetype.__args__
    assert "closing_actions" in SlideArchetype.__args__


def test_design_validator_rejects_text_only_content_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v2",
            "deck_type": "implementation_proposal",
            "title": "纯文字风险",
            "slides": [
                {
                    "id": "s02",
                    "archetype": "key_message",
                    "title": "平台能力建设",
                    "message": "只写一句话没有视觉证据。",
                }
            ],
        }
    )

    issues = validate_deck_design(deck)

    assert issues[0]["type"] == "content_slide_without_visual_evidence"
    assert issues[0]["slide_id"] == "s02"
    assert "suggested_archetypes" in issues[0]


def test_design_validator_allows_section_without_visual():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v2",
            "deck_type": "implementation_proposal",
            "title": "章节页",
            "slides": [{"id": "s01", "archetype": "section_divider", "title": "一、建设背景"}],
        }
    )

    assert validate_deck_design(deck) == []


def test_design_validator_rejects_long_title():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v2",
            "deck_type": "implementation_proposal",
            "title": "标题过长",
            "slides": [
                {
                    "id": "s01",
                    "archetype": "cover",
                    "title": "这是一个明显超过二十四个中文字符并且不适合作为PPT页面标题的长标题",
                }
            ],
        }
    )

    issues = validate_deck_design(deck)

    assert issues[0]["type"] == "slide_title_too_long"
