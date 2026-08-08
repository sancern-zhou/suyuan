import asyncio
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from app.services import pdf_converter as pdf_converter_module
from app.services.pdf_converter import PDFConverter


def test_convert_to_pdf_normalizes_docx_table_spacing_without_changing_source(monkeypatch, tmp_path: Path):
    source = tmp_path / "uploaded.docx"
    source_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:tbl><w:tr><w:tc><w:p><w:pPr><w:pStyle w:val="Compact"/><w:spacing w:line="400" w:lineRule="exact"/></w:pPr><w:r><w:t>单元格</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
  </w:body>
</w:document>
"""
    with ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", source_xml)

    converter = PDFConverter()
    converter.output_dir = tmp_path / "pdfs"
    converter.output_dir.mkdir()
    seen_input_paths = []

    def fake_run_soffice(args):
        input_path = Path(args[-1])
        seen_input_paths.append(input_path)
        assert input_path != source

        with ZipFile(input_path) as archive:
            converted_xml = archive.read("word/document.xml").decode("utf-8")
        assert 'w:pStyle w:val="Compact"' not in converted_xml
        assert 'w:lineRule="exact"' not in converted_xml
        assert "单元格" in converted_xml

        (converter.output_dir / "uploaded.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(pdf_converter_module, "run_soffice", fake_run_soffice)

    result = asyncio.run(converter.convert_to_pdf(str(source)))

    assert result["pdf_path"].endswith(".pdf")
    assert Path(result["pdf_path"]).exists()
    assert seen_input_paths and not seen_input_paths[0].exists()

    with ZipFile(source) as archive:
        original_xml = archive.read("word/document.xml").decode("utf-8")
    assert 'w:pStyle w:val="Compact"' in original_xml
    assert 'w:lineRule="exact"' in original_xml


def test_pdf_source_normalizes_image_paragraph_exact_line_spacing(tmp_path: Path):
    source = tmp_path / "uploaded-with-image.docx"
    source_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr>
        <w:spacing w:line="440" w:lineRule="exact" w:before="0" w:after="0"/>
        <w:ind w:firstLine="480"/>
      </w:pPr>
      <w:r><w:drawing/></w:r>
    </w:p>
  </w:body>
</w:document>
"""
    with ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", source_xml)

    converter = PDFConverter()

    with converter._office_pdf_source(source) as preview_source:
        assert preview_source != source
        with ZipFile(preview_source) as archive:
            preview_xml = archive.read("word/document.xml").decode("utf-8")

    assert 'w:lineRule="exact"' not in preview_xml
    assert "<w:drawing" in preview_xml
    assert 'w:firstLine="480"' in preview_xml
    assert not preview_source.exists()

    with ZipFile(source) as archive:
        original_xml = archive.read("word/document.xml").decode("utf-8")
    assert 'w:lineRule="exact"' in original_xml
