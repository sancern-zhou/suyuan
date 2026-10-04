"""采集库表契约：渲染进工具描述、1054 自愈附真实字段。"""

import json

import pytest

from app.agent.context.data_shape import build_data_shape
from app.tools.query.execute_crawler_sql_query import table_contracts
from app.tools.query.execute_crawler_sql_query.table_contracts import table_column_types
from app.tools.query.execute_crawler_sql_query.table_contracts import (
    load_table_contracts,
    render_table_contracts,
    reset_cache,
)
from app.tools.query.execute_crawler_sql_query.tool import ExecuteCrawlerSQLQueryTool


@pytest.fixture(autouse=True)
def _reset_contract_cache():
    reset_cache()
    yield
    reset_cache()


def _write_contracts(tmp_path, content: str):
    path = tmp_path / table_contracts.CONTRACT_FILENAME
    path.write_text(content, encoding="utf-8")
    return path


CONTRACT_YAML = """
tables:
  StationDay:
    time_columns: ["Date"]
    dimension_columns: ["PositionName", "CityCode", "UniqueCode", "StationCode", "Area"]
    value_columns: ["Id", "Type", "Level", "Aqi", "SO2", "PM2_5", "O3_8h"]
    mark_columns: ["SO2Mark", "PM2_5Mark", "O3_8hMark"]
    caliber_columns: ["DataTableType", "DataSourceType", "DataTypePlan"]
  CityDay:
    time_columns: ["Date"]
    dimension_columns: ["Area", "CityCode"]
    value_columns: ["Id", "AQI", "PM2_5", "O3_8h"]
    mark_columns: ["CO_Mark", "O3_8h_Mark"]
    caliber_columns: ["DataTableType", "DataSourceType", "DataTypePlan"]
"""


def _use_tmp_contracts(tmp_path, monkeypatch):
    path = _write_contracts(tmp_path, CONTRACT_YAML)
    monkeypatch.setattr(
        table_contracts, "_candidate_paths", lambda: [path]
    )
    return path


def test_load_contracts_from_candidate_path(tmp_path, monkeypatch):
    _use_tmp_contracts(tmp_path, monkeypatch)
    contracts = load_table_contracts()
    assert contracts and set(contracts["tables"]) == {"StationDay", "CityDay"}


def test_render_contracts_includes_columns_and_mark_note(tmp_path, monkeypatch):
    _use_tmp_contracts(tmp_path, monkeypatch)
    rendered = render_table_contracts()
    assert "表字段契约" in rendered
    assert "**StationDay**" in rendered
    assert "PositionName" in rendered  # 真实维度列（不是 StationName）
    assert "SO2Mark" in rendered
    assert "CO_Mark" in rendered
    assert "大小写" in rendered


def test_render_contracts_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        table_contracts,
        "_candidate_paths",
        lambda: [tmp_path / "absent.yaml"],
    )
    assert render_table_contracts() == ""


def test_tool_description_embeds_contracts(tmp_path, monkeypatch):
    _use_tmp_contracts(tmp_path, monkeypatch)
    tool = ExecuteCrawlerSQLQueryTool()
    description = tool.function_schema["description"]
    assert "表字段契约" in description
    assert "PositionName" in description
    assert "DataTypePlan" in description  # 口径列进契约
    # 手写表说明已移除，不再有漂移文本
    assert "站点字段 StationCode/StationName/" not in description


def test_columns_hint_lists_real_columns(tmp_path, monkeypatch):
    _use_tmp_contracts(tmp_path, monkeypatch)
    tool = ExecuteCrawlerSQLQueryTool()
    hint = tool._columns_hint(["StationDay", "CityDay"])
    assert "StationDay: " in hint
    assert "PositionName" in hint
    assert "CO_Mark" in hint


def _make_unknown_column_error():
    """构造带 1054 语义的 SQLAlchemy 风格异常。"""
    import pymysql.err

    original = pymysql.err.OperationalError(
        1054, "Unknown column 'StationName' in 'field list'"
    )
    try:
        from sqlalchemy.exc import OperationalError as SAOperationalError

        return SAOperationalError(
            statement="SELECT StationName FROM StationDay",
            params={},
            orig=original,
        )
    except Exception:
        return original


@pytest.mark.asyncio
async def test_unknown_column_failure_attaches_real_columns(tmp_path, monkeypatch):
    _use_tmp_contracts(tmp_path, monkeypatch)
    tool = ExecuteCrawlerSQLQueryTool()

    async def _fail_run_query(sql, parameters=None, tables=None):
        raise _make_unknown_column_error()

    monkeypatch.setattr(tool, "_run_query", _fail_run_query)

    result = await tool.execute(sql="SELECT StationName FROM StationDay LIMIT 10")

    assert result["success"] is False
    summary = result["summary"]
    assert "1054" in summary or "Unknown column" in summary
    assert "真实字段" in summary
    assert "PositionName" in summary  # 修正依据：真实维度列
    assert "StationDay: " in summary


@pytest.mark.asyncio
async def test_non_column_failure_keeps_describe_guidance(tmp_path, monkeypatch):
    _use_tmp_contracts(tmp_path, monkeypatch)
    tool = ExecuteCrawlerSQLQueryTool()

    async def _fail_run_query(sql, parameters=None, tables=None):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(tool, "_run_query", _fail_run_query)

    result = await tool.execute(sql="SELECT Aqi FROM StationDay LIMIT 10")

    assert result["success"] is False
    assert "describe_table" in result["summary"]
    assert "真实字段" not in result["summary"]


def test_deployment_contract_matches_crawler_whitelist():
    """提交的契约文件必须覆盖采集库全部白名单表（防遗漏）。"""
    from app.tools.query.execute_crawler_sql_query.tool import CRAWLER_SQL_TABLES

    contracts = load_table_contracts(refresh=True)
    if contracts is None:
        pytest.skip("未配置 data_table_contracts.yaml")
    assert set(contracts["tables"]) == set(CRAWLER_SQL_TABLES)
    for table, info in contracts["tables"].items():
        names = []
        for key in ("time_columns", "dimension_columns", "value_columns", "mark_columns", "caliber_columns"):
            names.extend(info.get(key) or [])
        assert names, f"{table} 契约为空"
        assert "StationName" not in names or table in {"StationHour", "Station"}, (
            f"{table} 契约包含 StationName，但真实库该表无此列"
        )


def test_contract_column_types_available_for_whitelist_tables():
    """重生成后的契约包含 information_schema 精确类型（data_shape 依赖）。"""
    contracts = load_table_contracts(refresh=True)
    if contracts is None:
        pytest.skip("未配置 data_table_contracts.yaml")
    types = table_column_types("StationHour")
    assert types, "StationHour 缺少 column_types"
    assert types.get("TimePoint") == "datetime"
    assert types.get("Aqi") in {"int", "bigint", "float", "double", "decimal"}


def test_externalized_result_includes_exact_data_shape(monkeypatch):
    """外置结果的 data_shape 使用契约精确类型，派生列标注推断。"""
    tool = ExecuteCrawlerSQLQueryTool()
    rows = [
        {"TimePoint": "2026-10-03 08:00:00", "StationName": "许昌", "ratio": 0.5},
        {"TimePoint": "2026-10-03 09:00:00", "StationName": "郑州", "ratio": 0.6},
    ]
    result = tool._format_result(
        rows,
        "SELECT TimePoint, StationName, Aqi/100.0 AS ratio FROM StationHour",
        1000,
        None,
        tables=["StationHour"],
    )
    shape = result["data_shape"]
    assert shape["source"] == "db"
    types = {item["name"]: item["type"] for item in shape["columns"]}
    assert types["TimePoint"] == "datetime"
    assert types["StationName"] == "varchar"
    assert types["ratio"] == "float"
    assert "数据形状" in result["summary"]


def test_data_shape_builder_marks_inferred_source():
    shape = build_data_shape({"ratio": "float"}, 2, "inferred")
    assert shape["source"] == "inferred"
