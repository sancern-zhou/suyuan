from app.tools.utility.parse_pdf_tool import ParsePDFTool


def test_table_dimensions_are_derived_when_extractor_omits_counts():
    table = {
        "page": 2,
        "data": [["name", "value"], ["noise", "54.2"], ["wind", "1.8"]],
    }

    assert ParsePDFTool._table_dimensions(table) == (3, 2)


def test_text_and_table_markdown_accept_tables_without_rows_or_cols():
    tool = ParsePDFTool()
    table = {"page": 1, "data": [["a", "b"], ["c", "d"]]}

    text_markdown = "\n".join(
        tool._build_text_markdown(
            {"table_count": 1, "tables": [table], "content": "source"}
        )
    )
    table_markdown = "\n".join(
        tool._build_tables_markdown({"table_count": 1, "tables": [table]})
    )

    assert "**行数**: 2" in text_markdown
    assert "**列数**: 2" in text_markdown
    assert "**行数**: 2" in table_markdown
    assert "**列数**: 2" in table_markdown
