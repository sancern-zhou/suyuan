import pytest
from pydantic import ValidationError

from app.agent.resources.contracts import ResourceDeclaration


def test_document_resource_requires_logical_key():
    with pytest.raises(ValueError, match="logical_key"):
        ResourceDeclaration.model_validate({
            "kind": "file",
            "role": "report",
            "label": "report",
            "locator": {"path": "/tmp/report.html"},
            "presentation_type": "document",
            "presentation": {"format": "html", "preview": {"type": "html", "url": "/p"}},
        })


def test_resource_key_is_stable_and_file_can_have_document_presentation():
    resource = ResourceDeclaration.model_validate({
        "kind": "file", "logical_key": "upload:file-1", "role": "attachment",
        "label": "report.docx", "locator": {"path": "/tmp/report.docx"},
        "presentation_type": "document",
        "presentation": {"format": "pdf", "preview": {"type": "pdf", "url": "/p"}},
    })
    assert resource.resource_key() == "upload:file-1"


def test_legacy_top_level_fields_are_not_accepted():
    with pytest.raises(ValidationError):
        ResourceDeclaration.model_validate({"file_path": "/tmp/old.docx"})
