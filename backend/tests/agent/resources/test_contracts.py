import pytest
from pydantic import ValidationError

from app.agent.resources.contracts import ResourceDeclaration, ResourceRelation


def test_grouped_preview_declaration_is_explicit():
    primary = ResourceDeclaration.model_validate({
        "kind": "file",
        "group_key": "report:air-quality",
        "resource_key": "docx",
        "relation": "primary",
        "role": "report",
        "label": "空气质量报告.docx",
        "locator": {"path": "/tmp/report.docx"},
        "format": "docx",
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "renderer": "file",
        "capabilities": ["download", "edit", "preview"],
    })
    preview = ResourceDeclaration.model_validate({
        "kind": "file",
        "group_key": "report:air-quality",
        "resource_key": "html-preview",
        "parent_key": "docx",
        "relation": "preview",
        "role": "report",
        "label": "HTML预览",
        "locator": {"path": "/tmp/report.html"},
        "format": "html",
        "media_type": "text/html",
        "renderer": "html",
        "capabilities": ["preview"],
    })

    assert primary.relation is ResourceRelation.PRIMARY
    assert primary.catalog_key() == ("report", "report:air-quality", "docx")
    assert preview.parent_key == primary.resource_key


def test_derivative_requires_parent_key():
    with pytest.raises(ValueError, match="parent_key"):
        ResourceDeclaration.model_validate({
            "kind": "file",
            "group_key": "report:x",
            "resource_key": "pdf",
            "relation": "preview",
            "role": "report",
            "label": "PDF",
            "locator": {"path": "/tmp/x.pdf"},
            "format": "pdf",
            "media_type": "application/pdf",
            "renderer": "pdf",
        })


def test_primary_rejects_parent_key():
    with pytest.raises(ValueError, match="primary resource cannot have parent_key"):
        ResourceDeclaration.model_validate({
            "kind": "file",
            "group_key": "report:x",
            "resource_key": "docx",
            "parent_key": "other",
            "relation": "primary",
            "role": "report",
            "label": "DOCX",
            "locator": {"path": "/tmp/x.docx"},
            "format": "docx",
            "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "renderer": "file",
        })


def test_metadata_size_limit_remains_enforced():
    with pytest.raises(ValueError, match="metadata exceeds"):
        ResourceDeclaration.model_validate({
            "kind": "file",
            "group_key": "file:x",
            "resource_key": "primary:txt",
            "relation": "primary",
            "role": "output",
            "label": "x.txt",
            "locator": {"path": "/tmp/x.txt"},
            "format": "txt",
            "media_type": "text/plain",
            "renderer": "file",
            "metadata": {"value": "x" * 9000},
        })


def test_docx_renderer_declarations_are_accepted():
    # cf05c53a 五处声明（generated_file_products、report_package renditions、
    # validate_office、QMD 渲染挂载、attach_document_resources）统一 renderer='docx'，
    # 枚举漏登记会把整条 durable 发布链炸成 resource_declaration_invalid。
    primary = ResourceDeclaration.model_validate({
        "kind": "file",
        "group_key": "report:jsops-risk-report",
        "resource_key": "docx",
        "relation": "primary",
        "role": "report",
        "label": "report.docx",
        "locator": {"path": "/tmp/report.docx"},
        "format": "docx",
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "renderer": "docx",
        "capabilities": ["preview", "download", "edit"],
    })
    rendition = ResourceDeclaration.model_validate({
        "kind": "file",
        "group_key": "report:jsops-risk-report",
        "resource_key": "docx",
        "parent_key": "qmd",
        "relation": "rendition",
        "role": "report",
        "label": "report.docx",
        "locator": {"path": "/tmp/report.docx"},
        "format": "docx",
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "renderer": "docx",
        "capabilities": ["download"],
    })

    assert primary.renderer.value == "docx"
    assert rendition.renderer.value == "docx"


def test_legacy_presentation_contract_is_rejected():
    with pytest.raises(ValidationError):
        ResourceDeclaration.model_validate({
            "kind": "file",
            "logical_key": "report:old",
            "role": "report",
            "label": "old.html",
            "locator": {"path": "/tmp/old.html"},
            "presentation_type": "document",
            "presentation": {"format": "html", "preview": {"url": "/old"}},
        })
