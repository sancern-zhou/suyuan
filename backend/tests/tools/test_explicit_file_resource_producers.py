from app.agent.resources.contracts import ResourceDeclaration
from app.tools.resource_declarations import (
    data_resource,
    directory_artifact,
    file_product,
    single_file_product,
    preview_file,
    primary_file,
    file_products,
)


def test_file_product_declares_one_group_with_bound_preview(tmp_path):
    document = tmp_path / "report.docx"
    preview = tmp_path / "report.pdf"
    document.write_bytes(b"docx")
    preview.write_bytes(b"pdf")

    members = file_product(
        primary_path=document,
        group_key="report:air",
        tool_name="write_file",
        previews=[preview_file(preview, renderer="pdf")],
    )

    assert [member["relation"] for member in members] == ["primary", "preview"]
    assert members[1]["parent_key"] == members[0]["resource_key"]
    assert all(member["group_key"] == "report:air" for member in members)
    assert all("format" in member and "media_type" in member for member in members)
    assert [ResourceDeclaration.model_validate(member) for member in members]


def test_primary_file_has_complete_contract_without_path_metadata(tmp_path):
    output = tmp_path / "result.csv"
    output.write_text("value\n1\n")

    member = primary_file(
        output,
        group_key="python:result",
        tool_name="execute_python",
    )

    assert member["resource_key"] == "primary:csv"
    assert member["format"] == "csv"
    assert member["media_type"] == "text/csv"
    assert member["capabilities"] == ["download"]
    assert member["metadata"] == {"size": output.stat().st_size}
    assert str(output) not in str(member["metadata"])


def test_directory_artifact_has_trusted_entrypoint_only(tmp_path):
    artifact = tmp_path / "site"
    artifact.mkdir()
    (artifact / "index.html").write_text("<h1>report</h1>")

    member = directory_artifact(
        artifact,
        entrypoint="index.html",
        group_key="html:report",
        tool_name="browser",
    )

    assert member["kind"] == "artifact"
    assert member["renderer"] == "html"
    assert member["metadata"] == {"entrypoint": "index.html"}
    assert ResourceDeclaration.model_validate(member)


def test_primary_keys_are_deterministic_for_same_format(tmp_path):
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    first.write_bytes(b"a")
    second.write_bytes(b"b")

    assert primary_file(
        first, group_key="report:a", tool_name="tool"
    )["resource_key"] == primary_file(
        second, group_key="report:b", tool_name="tool"
    )["resource_key"]


def test_existing_generic_producer_seams_emit_only_valid_grouped_members(tmp_path):
    first = tmp_path / "one.txt"
    second = tmp_path / "two.json"
    first.write_text("one")
    second.write_text("{}")

    members = [
        single_file_product(first, tool_name="write_file"),
        *file_products([first, second], tool_name="bash"),
        data_resource("analysis:v1:abc", tool_name="execute_python"),
    ]

    declarations = [ResourceDeclaration.model_validate(member) for member in members]
    assert all(declaration.relation.value == "primary" for declaration in declarations)
    assert all(declaration.group_key for declaration in declarations)
    assert all(declaration.format and declaration.media_type for declaration in declarations)


def test_single_file_product_infers_preview_contract_for_supported_documents(tmp_path):
    html = tmp_path / "report.html"
    html.write_text("<h1>report</h1>", encoding="utf-8")
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    binary = tmp_path / "archive.bin"
    binary.write_bytes(b"data")

    html_resource = single_file_product(html, tool_name="write_file")
    pdf_resource = single_file_product(pdf, tool_name="browser")
    binary_resource = single_file_product(binary, tool_name="bash")

    assert (html_resource["renderer"], html_resource["capabilities"]) == (
        "html",
        ["preview", "download"],
    )
    assert (pdf_resource["renderer"], pdf_resource["capabilities"]) == (
        "pdf",
        ["preview", "download"],
    )
    assert (binary_resource["renderer"], binary_resource["capabilities"]) == (
        "file",
        ["download"],
    )
