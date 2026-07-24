from app.agent.resources.normalizer import normalize_tool_resources


def _document():
    return {
        "kind": "file",
        "logical_key": "report:current",
        "role": "report",
        "label": "report",
        "locator": {"path": "/tmp/report.html"},
        "presentation_type": "document",
        "presentation": {"format": "html", "preview": {"type": "html", "url": "/preview"}},
    }


def test_explicit_resources_are_normalized():
    resources, rejected = normalize_tool_resources(result={"resources": [_document()]})
    assert rejected == []
    assert len(resources) == 1
    assert resources[0].resource_key() == "report:current"


def test_legacy_fields_are_not_inferred():
    resources, rejected = normalize_tool_resources(result={"file_path": "/tmp/old.html", "data_id": "old"})
    assert resources == []
    assert rejected == []


def test_invalid_explicit_resource_is_rejected():
    resources, rejected = normalize_tool_resources(result={"resources": [{"kind": "file"}]})
    assert resources == []
    assert rejected and rejected[0]["field"] == "resources[0]"
