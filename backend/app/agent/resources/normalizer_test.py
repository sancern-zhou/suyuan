import pytest

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


@pytest.mark.parametrize(
    ("format_name", "preview", "expected_type"),
    [
        ("docx", {"pdf_id": "word-1", "pdf_url": "/api/office/pdf/word-1"}, "pdf"),
        ("pptx", {"pdf_url": "/api/file/deck.pdf", "pages": [{"slide": 1}]}, "pdf"),
        ("pptx", {"pages": [{"slide": 1, "png_path": "/tmp/slide-1.png"}]}, "presentation"),
        ("xlsx", {"file_type": "xlsx", "editable": True}, "spreadsheet"),
        ("qmd", {"html_id": "report-1", "html_url": "/api/reports/report-1"}, "html"),
        ("md", {"content": "# Report"}, "markdown"),
        ("png", {"html_url": "/api/file/image.png"}, "image"),
        ("drawio", {}, "none"),
    ],
)
def test_document_resources_receive_a_canonical_preview_type(format_name, preview, expected_type):
    document = _document()
    document["presentation"] = {"format": format_name, "preview": preview}

    resources, rejected = normalize_tool_resources(result={"resources": [document]})

    assert rejected == []
    assert resources[0].presentation.preview_type.value == expected_type
    assert resources[0].presentation.model_dump(mode="json")["preview_type"] == expected_type


def test_document_resource_honors_an_explicit_preview_type():
    document = _document()
    document["presentation"] = {
        "format": "custom",
        "preview_type": "html",
        "preview": {"html_url": "/api/custom/preview"},
    }

    resources, rejected = normalize_tool_resources(result={"resources": [document]})

    assert rejected == []
    assert resources[0].presentation.preview_type.value == "html"


def test_drawio_resource_never_enters_the_document_preview_contract():
    document = _document()
    document["presentation"] = {
        "format": "drawio",
        "preview_type": "html",
        "preview": {"html_url": "/api/file/board.html"},
    }

    resources, rejected = normalize_tool_resources(result={"resources": [document]})

    assert rejected == []
    assert resources[0].presentation.preview_type.value == "none"
