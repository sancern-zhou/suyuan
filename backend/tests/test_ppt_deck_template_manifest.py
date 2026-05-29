from app.tools.office.deck.deck_tool import build_semantic_values_from_deck
from app.tools.office.deck.models import DeckSpec
from app.tools.office.deck.template_manifest import TemplateManifest


def test_template_manifest_maps_semantic_slots_to_physical_slots():
    manifest = TemplateManifest.model_validate(
        {
            "template": "gov_air_quality_monthly",
            "slots": {
                "cover.title": "s001_slot001",
                "map_insight.main_map": "s004_slot002",
                "map_insight.key_findings": "s004_slot005",
            },
        }
    )

    replacements = manifest.to_physical_replacements(
        {
            "cover.title": "广东省3月空气质量分析汇报",
            "map_insight.main_map": "assets/maps/pm25.png",
        }
    )

    assert replacements == {
        "s001_slot001": "广东省3月空气质量分析汇报",
        "s004_slot002": "assets/maps/pm25.png",
    }


def test_template_manifest_reports_unknown_semantic_slots():
    manifest = TemplateManifest.model_validate(
        {"template": "demo", "slots": {"cover.title": "s001_slot001"}}
    )

    unknown = manifest.unknown_semantic_slots({"cover.title": "标题", "missing.slot": "内容"})

    assert unknown == ["missing.slot"]


def test_build_semantic_values_from_deck():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "模板填充",
            "slides": [
                {"id": "cover", "type": "cover", "title": "标题", "subtitle": "副标题"},
                {
                    "id": "map",
                    "type": "map_insight",
                    "title": "地图页",
                    "visual": {"kind": "map", "asset": "assets/maps/pm25.png"},
                    "insights": ["发现一", "发现二"],
                },
            ],
        }
    )

    values = build_semantic_values_from_deck(deck)

    assert values["cover.title"] == "标题"
    assert values["cover.subtitle"] == "副标题"
    assert values["map_insight.title"] == "地图页"
    assert values["map_insight.main_map"] == "assets/maps/pm25.png"
    assert values["map_insight.key_findings"] == "发现一\n发现二"
