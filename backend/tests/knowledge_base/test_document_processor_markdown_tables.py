from types import SimpleNamespace

from app.knowledge_base.document_processor import DocumentProcessor


def test_process_elements_preserves_unstructured_tables_as_markdown():
    processor = DocumentProcessor()

    Table = type("Table", (), {"__str__": lambda self: self._text})
    table = Table()
    table._text = "污染物 1小时平均 24小时平均 年平均 SO2 350 150 60 NO2 200 80 40"
    table.metadata = SimpleNamespace(
        text_as_html=(
            "<table>"
            "<tr><td>污染物</td><td>1小时平均</td><td>24小时平均</td><td>年平均</td></tr>"
            "<tr><td>SO2</td><td>350</td><td>150</td><td>60</td></tr>"
            "<tr><td>NO2</td><td>200</td><td>80</td><td>40</td></tr>"
            "</table>"
        )
    )

    content = processor._process_elements(["前言", table, "后记"])

    assert "前言" in content
    assert "后记" in content
    assert "[表格]" in content
    assert "| 污染物 | 1小时平均 | 24小时平均 | 年平均 |" in content
    assert "| SO2 | 350 | 150 | 60 |" in content
    assert "| NO2 | 200 | 80 | 40 |" in content
