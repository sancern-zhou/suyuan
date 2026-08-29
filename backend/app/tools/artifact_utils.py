"""Helpers for tool-returned deliverable artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.tools.resource_declarations import (
    derivative_file,
    directory_artifact,
    primary_file,
    single_file_product,
)


def preview_output_path(*descriptors: Any) -> Path | None:
    """Resolve a renderer output descriptor to an existing local file."""
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            continue
        for key in ("pdf_path", "html_path", "markdown_path", "svg_path", "file_path", "local_path"):
            value = descriptor.get(key)
            if not isinstance(value, str) or not value:
                continue
            candidate = Path(value).expanduser().resolve()
            if candidate.is_file():
                return candidate
    return None


def attach_report_package_resources(
    result_data: Dict[str, Any],
    qmd_path: str | Path,
    *,
    report_id: str,
    html_path: str | Path | None = None,
    docx_path: str | Path | None = None,
    pdf_path: str | Path | None = None,
    share_html_path: str | Path | None = None,
    generator: str = "report_package",
) -> Dict[str, Any]:
    """Attach one canonical ReportPackage snapshot rooted at report.qmd."""
    source = Path(qmd_path).expanduser().resolve()
    if source.suffix.lower() != ".qmd":
        raise ValueError("report package primary must be a QMD file")

    group_key = f"report:{report_id}"
    primary = primary_file(
        source,
        group_key=group_key,
        tool_name=generator,
        role="report",
        renderer="markdown",
        capabilities=("preview", "download", "render"),
        label=report_id,
        metadata={"artifact_kind": "report", "report_id": report_id},
    )
    primary["resource_key"] = "qmd"
    resources = [primary]

    preview = Path(html_path).expanduser().resolve() if html_path else None
    if preview is not None and preview.is_file():
        html_preview = directory_artifact(
            preview.parent,
            entrypoint=preview.name,
            group_key=group_key,
            tool_name=generator,
            role="report",
            renderer="html",
            capabilities=("preview",),
            label=preview.name,
        )
        html_preview.update(
            resource_key="html",
            parent_key="qmd",
            relation="preview",
        )
        resources.append(html_preview)

    if docx_path is None:
        candidate = source.with_name("report.docx")
        if candidate.is_file():
            docx_path = candidate
    if pdf_path is None:
        candidate = source.with_name("report.pdf")
        if candidate.is_file():
            pdf_path = candidate

    rendition_specs = (
        ("docx", docx_path, "file"),
        ("pdf", pdf_path, "pdf"),
        ("share_html", share_html_path, "html"),
    )
    for resource_key, raw_path, renderer in rendition_specs:
        if not raw_path:
            continue
        rendition_path = Path(raw_path).expanduser().resolve()
        if not rendition_path.is_file():
            continue
        rendition = derivative_file(
            rendition_path,
            group_key=group_key,
            parent_key="qmd",
            tool_name=generator,
            relation="rendition",
            role="report",
            renderer=renderer,
            capabilities=("download",),
            label=rendition_path.name,
        )
        rendition["resource_key"] = resource_key
        resources.append(rendition)

    result_data["resources"] = resources
    return result_data


def attach_document_resources(
    result_data: Dict[str, Any],
    file_path: str | Path,
    *,
    kind: str = "office",
    format: Optional[str] = None,
    title: Optional[str] = None,
    preview_path: str | Path | None = None,
    generator: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach a primary file and optional preview directly as resources."""
    logical_key = str(
        metadata.get("report_id") if isinstance(metadata, dict) and metadata.get("report_id")
        else metadata.get("artifact_id") if isinstance(metadata, dict) and metadata.get("artifact_id")
        else title or Path(file_path).stem
    )
    path = Path(file_path).expanduser().resolve()
    fmt = (format or path.suffix.lstrip(".") or "document").lower()
    if kind == "report":
        if fmt != "qmd":
            raise ValueError("report resources must keep report.qmd as the primary")
        resolved_preview = None
        if preview_path:
            candidate = Path(preview_path).expanduser().resolve()
            if candidate.is_file():
                resolved_preview = candidate
        if resolved_preview is None:
            rendered_html = path.with_name("report.html")
            if rendered_html.is_file():
                resolved_preview = rendered_html
        return attach_report_package_resources(
            result_data,
            path,
            report_id=logical_key,
            html_path=resolved_preview,
            generator=generator or "document",
        )

    if kind == "html_artifact":
        group_key = f"html-artifact:{logical_key}"
    elif (format or path.suffix.lstrip(".")).lower() == "pptx":
        group_key = f"presentation:{logical_key}"
    else:
        group_key = f"office:{logical_key}"
    renderer_by_format = {
        "pdf": "pdf",
        "html": "html",
        "qmd": "markdown",
        "md": "markdown",
        "xlsx": "spreadsheet",
        "xls": "spreadsheet",
        "pptx": "presentation",
        "ppt": "presentation",
        "png": "image",
        "jpg": "image",
        "jpeg": "image",
        "svg": "image",
    }
    role = "output"
    capabilities = (
        ("preview", "download", "edit")
        if fmt in {"docx", "xlsx", "pptx"}
        else ("preview", "download")
    )
    primary = primary_file(
        path,
        group_key=group_key,
        tool_name=generator or "document",
        role=role,
        renderer=renderer_by_format.get(fmt, "file"),
        capabilities=capabilities,
        label=title or path.name,
        metadata={"artifact_kind": kind},
    )
    primary["resource_key"] = "source:html" if kind == "html_artifact" and fmt == "html" else fmt
    resources = [primary]

    resolved_preview = None
    if preview_path:
        candidate = Path(preview_path).expanduser().resolve()
        if candidate.is_file() and candidate != path:
            resolved_preview = candidate
    if kind == "html_artifact" and fmt == "html":
        resolved_preview = path
    if resolved_preview is not None:
        preview_fmt = resolved_preview.suffix.lower().lstrip(".") or "file"
        if kind == "html_artifact" and preview_fmt == "html":
            derivative = directory_artifact(
                resolved_preview.parent,
                entrypoint=resolved_preview.name,
                group_key=group_key,
                tool_name=generator or "document",
                role=role,
                renderer="html",
                capabilities=("preview",),
                label=resolved_preview.name,
            )
            derivative.update(
                resource_key="preview:html",
                parent_key=primary["resource_key"],
                relation="preview",
            )
        else:
            derivative = derivative_file(
                resolved_preview,
                group_key=group_key,
                parent_key=primary["resource_key"],
                tool_name=generator or "document",
                relation="preview",
                role=role,
                renderer=renderer_by_format.get(preview_fmt, "file"),
            )
        if not (kind == "html_artifact" and preview_fmt == "html"):
            derivative["resource_key"] = preview_fmt
        resources.append(derivative)
    result_data["resources"] = resources
    return result_data


def attach_mutated_document_resources(
    result_data: Dict[str, Any],
    file_path: str | Path,
    *,
    generator: str,
) -> list[dict[str, Any]]:
    """Build the canonical resource group after a file mutation.

    Preview refresh and durable publication are one lifecycle. Managed reports
    and HTML artifacts must never fall back to a download-only generic file.
    """
    path = Path(file_path).expanduser().resolve()
    report_refresh = result_data.get("report_preview_refresh") or {}
    if report_refresh.get("success"):
        attach_report_package_resources(
            result_data,
            path,
            report_id=str(result_data["report_id"]),
            html_path=report_refresh.get("html_path"),
            generator=generator,
        )
        return result_data["resources"]

    html_refresh = result_data.get("html_artifact_preview_refresh") or {}
    if html_refresh.get("success"):
        artifact_id = str(result_data.get("artifact_id") or html_refresh.get("artifact_id") or path.parent.name)
        attach_document_resources(
            result_data,
            path,
            kind="html_artifact",
            format="html",
            title=artifact_id,
            generator=generator,
            metadata={"artifact_id": artifact_id},
        )
        return result_data["resources"]

    resources = [single_file_product(path, tool_name=generator)]
    result_data["resources"] = resources
    return resources


def build_artifact_resume_context(
    result_data: Dict[str, Any],
    file_path: str | Path,
    *,
    extra_resume: Optional[Dict[str, Any]] = None,
    tool_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Return top-level Agent resume fields for an explicit artifact result."""
    path = Path(file_path)
    resume = {
        "artifact_path": str(path),
        "artifact_format": path.suffix.lstrip(".") or None,
        "tool_hint": tool_hint or "Artifact preview and download resources are published automatically.",
    }
    if extra_resume:
        resume.update({key: value for key, value in extra_resume.items() if value is not None})
    return {
        "resources": result_data.get("resources", []),
        "llm_resume": resume,
    }
