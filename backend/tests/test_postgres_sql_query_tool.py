import asyncio

from app.agent.prompts.tool_registry import QUERY_FORECAST_TOOL_NAMES, QUERY_MONITORING_TOOL_NAMES
from app.db.database import engine
from app.db.sound_database import sound_engine
from app.db.weather_database import weather_engine
from app.tools import create_global_tool_registry
from app.tools.query.execute_postgres_sql_query.tool import (
    ALLOWED_SQL_TABLES,
    APP_SQL_TABLES,
    DATABASE_NAMES,
    MAIN_DATABASE,
    MAX_LIMIT,
    SOUND_DATA_DATABASE,
    SOUND_DB_SQL_TABLES,
    SOUND_DB_TABLE_PREFIXES,
    WEATHER_SQL_TABLES,
    ExecutePostgresSQLQueryTool,
)


def test_postgres_sql_tool_schema_exposes_database_selector():
    tool = ExecutePostgresSQLQueryTool()

    schema = tool.get_function_schema()
    properties = schema["parameters"]["properties"]

    assert tool.name == "execute_postgres_sql_query"
    assert schema["name"] == "execute_postgres_sql_query"
    assert properties["database"]["enum"] == list(DATABASE_NAMES)
    assert properties["database"]["default"] == MAIN_DATABASE
    assert "enum" not in properties["describe_table"]


def test_postgres_sql_tool_allows_permit_join_and_rejects_other_tables():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate(
        "SELECT l.enterprise_name, p.air_pollutant_types "
        "FROM permit_licenses l JOIN permit_pollution_details p ON p.license_id = l.id "
        "LIMIT 10"
    )
    assert valid is True
    assert error == ""

    valid, error = tool.sql_validator.validate("SELECT * FROM permit_crawl_runs LIMIT 10")
    assert valid is False
    assert "permit_crawl_runs" in error


def test_postgres_sql_tool_allows_sound_data_prefix_and_scattered_tables():
    tool = ExecutePostgresSQLQueryTool()

    for sql in (
        "SELECT * FROM noise_1m_2025_1771a_src WHERE station_code = '36010001' LIMIT 5",
        "SELECT * FROM noise_h_2025_1771a_app LIMIT 5",
        "SELECT * FROM noise_areastationdata_2025 LIMIT 5",
        "SELECT * FROM dat_station_day WHERE station_code = '36010001' LIMIT 5",
        "SELECT * FROM NoiseRecount LIMIT 5",
        "SELECT * FROM noisecalibrationrecords LIMIT 5",
    ):
        valid, error = tool.sql_validator.validate(sql)
        assert valid is True, f"{sql}: {error}"


def test_postgres_sql_tool_rejects_unlisted_sound_data_table():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate("SELECT * FROM random_unknown_table LIMIT 5")

    assert valid is False
    assert "random_unknown_table" in error


def test_postgres_sql_tool_rejects_mutating_sql_and_uses_postgres_limit():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate("DELETE FROM permit_licenses")
    assert valid is False
    assert "SELECT" in error

    safe_sql, error = tool._sanitize_limit("SELECT * FROM permit_licenses", 25)
    assert error is None
    assert safe_sql.endswith("LIMIT 25")

    safe_sql, error = tool._sanitize_limit(
        "SELECT * FROM permit_licenses LIMIT 99999", 25
    )
    assert error is None
    assert safe_sql.endswith(f"LIMIT {MAX_LIMIT}")


def test_postgres_sql_tool_routes_by_table_and_explicit_database():
    tool = ExecutePostgresSQLQueryTool()

    assert tool._select_engine(["observed_weather_data"]) is weather_engine
    assert tool._select_engine(["observed_weather_daily"]) is weather_engine
    assert tool._select_engine(["permit_licenses"]) is engine
    assert tool._select_engine(["sys_user"]) is engine
    assert tool._select_engine(["noise_1s"]) is sound_engine
    assert tool._select_engine(["dat_station_day"]) is sound_engine
    assert tool._select_engine(["NoiseRecount"]) is sound_engine
    assert tool._select_engine(["sys_operation_log"], MAIN_DATABASE) is engine
    assert tool._select_engine(["sys_operation_log"], SOUND_DATA_DATABASE) is sound_engine


def test_postgres_sql_tool_resolves_database_from_table_name():
    tool = ExecutePostgresSQLQueryTool()

    assert tool._resolve_database("sys_user", None) == MAIN_DATABASE
    assert tool._resolve_database("observed_weather_data", None) == "weather"
    assert tool._resolve_database("noise_1s", None) == SOUND_DATA_DATABASE
    assert tool._resolve_database("noise_1m_2025_1771a_src", None) == SOUND_DATA_DATABASE
    assert tool._resolve_database("NoiseRecount", None) == SOUND_DATA_DATABASE
    assert tool._resolve_database("sys_operation_log", None) == MAIN_DATABASE
    # explicit database always wins
    assert tool._resolve_database("sys_operation_log", SOUND_DATA_DATABASE) == SOUND_DATA_DATABASE
    assert tool._resolve_database("noise_1s", MAIN_DATABASE) == MAIN_DATABASE


def test_postgres_sql_tool_allows_observed_weather_query():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate(
        "SELECT time, temperature_2m, wind_speed_10m FROM observed_weather_data "
        "WHERE station_id = 'ZzMTA' AND time >= '2026-08-30' ORDER BY time LIMIT 48"
    )
    assert valid is True
    assert error == ""


def test_postgres_sql_tool_rejects_cross_database_join():
    tool = ExecutePostgresSQLQueryTool()

    sql = (
        "SELECT l.enterprise_name, n.station_name FROM permit_licenses l "
        "JOIN noise_1s n ON 1 = 1 LIMIT 10"
    )
    valid, _ = tool.sql_validator.validate(sql)
    assert valid is True

    result = asyncio.run(tool._execute_sql(sql, 10, None))
    assert result["success"] is False
    assert "跨库" in result["summary"]


def test_postgres_sql_tool_rejects_password_field():
    tool = ExecutePostgresSQLQueryTool()

    result = asyncio.run(tool._execute_sql("SELECT password FROM sys_user LIMIT 5", 5, None))

    assert result["success"] is False
    assert "password" in result["summary"]


def test_postgres_sql_tool_whitelist_partitions():
    # 共享白名单 = 平台库 + 气象库 + 声环境散表；声环境分表族走前缀放行；
    # 项目专属业务表（许昌路况时序/告警事件聚合等）经
    # backend.tool_options.execute_postgres_sql_query.allowed_tables_extra 注入。
    assert ALLOWED_SQL_TABLES == (
        list(APP_SQL_TABLES) + list(WEATHER_SQL_TABLES) + list(SOUND_DB_SQL_TABLES)
    )
    assert "sys_user" in APP_SQL_TABLES
    assert "noise_1s" not in APP_SQL_TABLES
    assert "noise_" in SOUND_DB_TABLE_PREFIXES
    assert "xuchang_station_alert_episodes" not in ALLOWED_SQL_TABLES


def test_postgres_sql_tool_is_registered_and_available_to_query_agents():
    registry = create_global_tool_registry()

    assert registry.get_tool("execute_postgres_sql_query") is not None
    # 共享层：报告 DAG 问数子模式直接挂载本工具；问数/专家模式由项目 manifest
    # （projects/<id>/project.yaml 的 agent_mode_tools）挂载。
    assert "execute_postgres_sql_query" in QUERY_MONITORING_TOOL_NAMES
    assert "execute_postgres_sql_query" in QUERY_FORECAST_TOOL_NAMES


def test_postgres_sql_tool_describe_table_lists_tables_per_database(monkeypatch):
    tool = ExecutePostgresSQLQueryTool()

    calls = {}

    async def fake_run_query(sql, parameters=None, tables=None, database=None):
        calls["database"] = database
        if "information_schema.tables" in sql:
            return [{"table_name": "noise_1s"}, {"table_name": "sys_operation_log"}]
        return []

    monkeypatch.setattr(tool, "_run_query", fake_run_query)

    result = asyncio.run(
        tool.execute(describe_table="tables", database=SOUND_DATA_DATABASE)
    )

    assert result["success"] is True
    assert result["data"]["database"] == SOUND_DATA_DATABASE
    assert calls["database"] == SOUND_DATA_DATABASE


def test_postgres_sql_tool_describe_table_fuzzy_match_hints(monkeypatch):
    tool = ExecutePostgresSQLQueryTool()

    async def fake_find_tables(keyword, database):
        return ["NoiseRecount"]

    monkeypatch.setattr(tool, "_find_tables", fake_find_tables)

    result = asyncio.run(
        tool.execute(describe_table="Recount", database=SOUND_DATA_DATABASE)
    )

    assert result["success"] is True
    assert result["data"]["database"] == SOUND_DATA_DATABASE
    assert result["data"]["tables"] == ["NoiseRecount"]


def test_postgres_sql_tool_describe_table_rejects_unknown_table(monkeypatch):
    tool = ExecutePostgresSQLQueryTool()

    async def fake_run_query(sql, parameters=None, tables=None, database=None):
        return []

    monkeypatch.setattr(tool, "_run_query", fake_run_query)
    monkeypatch.setattr(tool, "_find_tables", lambda keyword, database: _empty())

    result = asyncio.run(tool.execute(describe_table="not_a_real_table"))

    assert result["success"] is False
    assert "不在白名单" in result["summary"]


def test_postgres_sql_tool_allows_alert_result_queries():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate(
        "SELECT completed_at, station_name, conclusion, broadcast_message "
        "FROM scheduled_task_results "
        "WHERE task_id = 'task_any_project_task' "
        "ORDER BY completed_at DESC LIMIT 20"
    )
    assert valid is True
    assert error == ""


def _xuchang_postgres_options():
    return {
        "allowed_tables_extra": [
            "traffic_snapshot",
            "traffic_section",
            "v_station_traffic_hourly",
            "xuchang_station_alert_episodes",
        ],
        "schema_notes": (
            "【许昌路况时序】traffic_snapshot 路况快照；【站点快速告警结论】"
            "task_id = 'task_xuchang_station_deviation_alert'；【站点编码】许昌站 ZzMTA。"
        ),
    }


def test_postgres_sql_tool_project_options_extend_whitelist_and_notes(monkeypatch):
    from app.tools.query.execute_postgres_sql_query import tool as pg_tool

    # 未注入配置的默认部署基线（在 monkeypatch 之前构造）
    default_tool = pg_tool.ExecutePostgresSQLQueryTool()
    assert "xuchang_station_alert_episodes" not in default_tool.sql_validator.ALLOWED_TABLES
    assert "【项目扩展口径】" not in default_tool.get_function_schema()["description"]

    # 许昌扩展（allowed_tables_extra + schema_notes）经项目配置注入——
    # 这里 monkeypatch 配置加载以在共享测试环境确定性验证注入行为。
    monkeypatch.setattr(pg_tool, "_load_postgres_tool_options", _xuchang_postgres_options)
    xuchang_tool = pg_tool.ExecutePostgresSQLQueryTool()

    assert "xuchang_station_alert_episodes" in xuchang_tool.sql_validator.ALLOWED_TABLES
    assert "traffic_snapshot" in xuchang_tool.sql_validator.ALLOWED_TABLES
    description = xuchang_tool.get_function_schema()["description"]
    assert "【项目扩展口径】" in description
    assert "task_xuchang_station_deviation_alert" in description

    valid, error = xuchang_tool.sql_validator.validate(
        "SELECT started_at, station_name, target_pollutant, status, "
        "peak_station_value, peak_deviation_ratio "
        "FROM xuchang_station_alert_episodes ORDER BY started_at DESC LIMIT 50"
    )
    assert valid is True
    assert error == ""


def test_postgres_sql_tool_rejects_alert_weather_cross_database_join(monkeypatch):
    from app.tools.query.execute_postgres_sql_query import tool as pg_tool

    monkeypatch.setattr(pg_tool, "_load_postgres_tool_options", _xuchang_postgres_options)
    tool = pg_tool.ExecutePostgresSQLQueryTool()

    sql = (
        "SELECT e.station_name, o.temperature_2m FROM xuchang_station_alert_episodes e "
        "JOIN observed_weather_data o ON 1 = 1 LIMIT 10"
    )
    result = asyncio.run(tool._execute_sql(sql, 10, None))
    assert result["success"] is False
    assert "跨库" in result["summary"]


async def _empty():
    return []
