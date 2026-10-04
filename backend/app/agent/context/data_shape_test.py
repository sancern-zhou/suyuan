"""data_shape：外置数据形状元数据的构造、渲染与资源图注入。"""

from datetime import datetime

import pytest

from app.agent.context.data_shape import (
    build_data_shape,
    dataframe_column_types,
    infer_column_types,
    render_shape_line,
    shape_from_records,
    shape_summary_suffix,
)


def test_infer_column_types_from_sample_values():
    records = [
        {"StationName": "许昌", "Aqi": 72, "IsApp": True, "Note": None},
        {"StationName": "郑州", "Aqi": 63.5, "IsApp": False, "Note": "x"},
    ]
    types = infer_column_types(records)
    assert types == {"StationName": "str", "Aqi": "int", "IsApp": "bool", "Note": "str"}


def test_build_data_shape_and_render_line():
    shape = build_data_shape({"TimePoint": "datetime", "StationName": "varchar", "Aqi": "float"}, 864, "db")
    assert shape["source"] == "db"
    assert shape["row_count"] == 864
    line = render_shape_line(shape)
    assert line.endswith("| 864行")
    assert "TimePoint:datetime" in line
    assert "StationName:varchar" in line


def test_render_shape_line_truncates_long_column_lists():
    shape = build_data_shape({f"col_{i}": "str" for i in range(20)}, 5, "inferred")
    line = render_shape_line(shape)
    assert "…共 20 列" in line
    assert "col_19" not in line


def test_shape_summary_suffix_empty_without_shape():
    assert shape_summary_suffix(None) == ""
    assert shape_summary_suffix({"columns": []}) == ""


def test_shape_from_records_marks_inferred_source():
    shape = shape_from_records([{"a": 1}], 1)
    assert shape["source"] == "inferred"


def test_dataframe_column_types_mark_datetime_as_readback_string():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({
        "TimePoint": ["2026-10-03 08:00:00"],
        "Aqi": [72],
    })
    frame["TimePoint"] = pd.to_datetime(frame["TimePoint"])
    types = dataframe_column_types(frame)
    assert types["TimePoint"] == "datetime-str"
    assert types["Aqi"] == "int"


def test_resource_map_appends_data_shape_for_data_resources():
    from app.agent.resources.resource_map import project_agent_resource_map
    from app.agent.resources.resource_service import StoredResource

    def make_resource(resource_id: str, metadata: dict) -> StoredResource:
        return StoredResource(
            resource_id=resource_id,
            session_id="s1",
            group_id="g1",
            parent_resource_id=None,
            resource_key="primary:data",
            relation="primary",
            kind="data",
            role="output",
            label=resource_id,
            locator={"path": "/tmp/x.json"},
            format="json",
            media_type="application/json",
            renderer="file",
            capabilities=["preview"],
            metadata=metadata,
            tool_name="execute_crawler_sql_query",
            run_id="r1",
            turn_sequence=1,
            version=1,
            status="active",
            created_at=datetime(2026, 10, 4),
            updated_at=datetime(2026, 10, 4),
        )

    shaped = make_resource("res-shape", {"data_shape": build_data_shape({"StationName": "varchar", "Aqi": "float"}, 864, "db")})
    plain = make_resource("res-plain", {})
    rendered = project_agent_resource_map([shaped, plain])
    assert "StationName:varchar" in rendered
    assert "864行" in rendered
    assert rendered.count("data_shape:") == 1
