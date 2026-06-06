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
