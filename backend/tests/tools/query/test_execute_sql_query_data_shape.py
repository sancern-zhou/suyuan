"""execute_sql_query 的 _build_data_shape：离事件循环执行、schema 过滤、跨库缓存隔离。"""

import threading
from types import SimpleNamespace

import pytest

from app.tools.query.execute_sql_query.tool import BaseSQLQueryTool


def make_tool():
    tool = BaseSQLQueryTool.__new__(BaseSQLQueryTool)
    tool.tool_name = "execute_sql_query"
    tool._table_types_cache = {}
    tool.sql_validator = SimpleNamespace(extract_tables=lambda sql: ["dbo.station_info"])
    return tool


@pytest.mark.asyncio
async def test_build_data_shape_queries_information_schema_off_event_loop():
    tool = make_tool()
    worker_threads = set()
    captured_sql = []

    def fake_execute_query(sql, database):
        worker_threads.add(threading.current_thread())
        captured_sql.append((sql, database))
        return [{"COLUMN_NAME": "Aqi", "DATA_TYPE": "float"}]

    tool._execute_query = fake_execute_query

    shape = await tool._build_data_shape(
        [{"Aqi": 72.0}], "SELECT Aqi FROM dbo.station_info", "AirPollutionAnalysis"
    )

    assert shape["source"] == "db"
    assert shape["columns"] == [{"name": "Aqi", "type": "float"}]
    assert shape["row_count"] == 1
    # schema 过滤：显式 dbo 前缀落到 TABLE_SCHEMA 条件
    sql, database = captured_sql[0]
    assert "TABLE_SCHEMA = 'dbo'" in sql
    assert "TABLE_NAME = 'station_info'" in sql
    assert database == "AirPollutionAnalysis"
    # 元数据查询必须离开事件循环线程（与主查询同为 to_thread 路径）
    assert worker_threads
    assert threading.current_thread() not in worker_threads


@pytest.mark.asyncio
async def test_build_data_shape_caches_per_database_not_per_table_name():
    tool = make_tool()
    captured = []
    type_sets = {
        "XcAiDb": [{"COLUMN_NAME": "Aqi", "DATA_TYPE": "decimal"}],
        "AirPollutionAnalysis": [{"COLUMN_NAME": "Aqi", "DATA_TYPE": "float"}],
    }

    def fake_execute_query(sql, database):
        captured.append(database)
        return type_sets[database]

    tool._execute_query = fake_execute_query

    shape_xcai = await tool._build_data_shape([{"Aqi": 1}], "SELECT Aqi FROM dbo.station_info", "XcAiDb")
    shape_air = await tool._build_data_shape([{"Aqi": 1}], "SELECT Aqi FROM dbo.station_info", "AirPollutionAnalysis")

    # 同名表分属两库：不得复用缓存，各自拿到本库列类型
    assert captured == ["XcAiDb", "AirPollutionAnalysis"]
    assert shape_xcai["columns"] == [{"name": "Aqi", "type": "decimal"}]
    assert shape_air["columns"] == [{"name": "Aqi", "type": "float"}]

    # 同库二次查询命中缓存，不再触发元数据查询
    await tool._build_data_shape([{"Aqi": 1}], "SELECT Aqi FROM dbo.station_info", "XcAiDb")
    assert captured == ["XcAiDb", "AirPollutionAnalysis"]


@pytest.mark.asyncio
async def test_build_data_shape_failure_falls_back_to_inferred():
    tool = make_tool()

    def failing_execute_query(sql, database):
        raise RuntimeError("network unreachable")

    tool._execute_query = failing_execute_query

    shape = await tool._build_data_shape([{"Aqi": 72.0}], "SELECT Aqi FROM dbo.station_info", "XcAiDb")
    assert shape["source"] == "inferred"
    assert shape["columns"] == [{"name": "Aqi", "type": "float"}]
    # 失败结果同样缓存，避免反复重试拖垮事件循环
    assert tool._table_types_cache["XcAiDb|dbo.station_info"] == {}
