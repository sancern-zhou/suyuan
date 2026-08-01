from app.agent.resources.normalizer import normalize_tool_resources


def _document():
    return {
        "kind": "file",
        "group_key": "report:current",
        "resource_key": "html",
        "relation": "primary",
        "role": "report",
        "label": "report",
        "locator": {"path": "/tmp/report.html"},
        "format": "html",
        "media_type": "text/html",
        "renderer": "html",
        "capabilities": ["preview", "download"],
    }


def test_explicit_resources_are_normalized():
    resources, rejected = normalize_tool_resources(result={"resources": [_document()]})
    assert rejected == []
    assert len(resources) == 1
    assert resources[0].catalog_key() == ("report", "report:current", "html")


def test_legacy_fields_are_not_inferred():
    resources, rejected = normalize_tool_resources(result={"file_path": "/tmp/old.html", "data_id": "old"})
    assert resources == []
    assert rejected == []


def test_invalid_explicit_resource_is_rejected():
    resources, rejected = normalize_tool_resources(result={"resources": [{"kind": "file"}]})
    assert resources == []
    assert rejected and rejected[0]["field"] == "resources[0]"
