import asyncio

from app.agent.prompts.tool_registry import QUERY_FORECAST_TOOL_NAMES, QUERY_MONITORING_TOOL_NAMES
from app.db.database import engine
from app.db.weather_database import weather_engine
from app.tools import create_global_tool_registry
from app.tools.query.execute_postgres_sql_query.tool import (
    ALERT_RESULT_SQL_TABLES,
    ALLOWED_SQL_TABLES,
    MAX_LIMIT,
    PERMIT_SQL_TABLES,
    WEATHER_SQL_TABLES,
    XUCHANG_TRAFFIC_SQL_TABLES,
    ExecutePostgresSQLQueryTool,
)


def test_postgres_sql_tool_schema_covers_whitelisted_tables():
    tool = ExecutePostgresSQLQueryTool()

    schema = tool.get_function_schema()

    assert tool.name == "execute_postgres_sql_query"
    assert schema["name"] == "execute_postgres_sql_query"
    assert schema["parameters"]["properties"]["describe_table"]["enum"] == ALLOWED_SQL_TABLES


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


def test_postgres_sql_tool_rejects_mutating_sql_and_uses_postgres_limit():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate("DELETE FROM permit_licenses")
    assert valid is False
    assert "只允许SELECT查询" in error

    safe_sql, error = tool._sanitize_limit("SELECT * FROM permit_licenses", 25)
    assert error is None
    assert safe_sql.endswith("LIMIT 25")

    safe_sql, error = tool._sanitize_limit("SELECT * FROM permit_licenses LIMIT 99999", 25)
    assert error is None
    assert safe_sql.endswith(f"LIMIT {MAX_LIMIT}")


def test_postgres_sql_tool_routes_weather_tables_to_weather_engine():
    tool = ExecutePostgresSQLQueryTool()

    assert tool._select_engine(["observed_weather_data"]) is weather_engine
    assert tool._select_engine(["permit_licenses"]) is engine


def test_postgres_sql_tool_allows_observed_weather_query():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate(
        "SELECT time, temperature_2m, wind_speed_10m FROM observed_weather_data "
        "WHERE station_id = 'ZzMTA' AND time >= '2026-08-30' ORDER BY time LIMIT 48"
    )
    assert valid is True
    assert error == ""

    valid, error = tool.sql_validator.validate(
        "SELECT DISTINCT station_id, station_name FROM observed_weather_data LIMIT 30"
    )
    assert valid is True
    assert error == ""


def test_postgres_sql_tool_rejects_cross_database_join():
    tool = ExecutePostgresSQLQueryTool()

    sql = (
        "SELECT l.enterprise_name, o.temperature_2m FROM permit_licenses l "
        "JOIN observed_weather_data o ON 1 = 1 LIMIT 10"
    )
    valid, _ = tool.sql_validator.validate(sql)
    assert valid is True

    result = asyncio.get_event_loop().run_until_complete(tool._execute_sql(sql, 10, None))
    assert result["success"] is False
    assert "跨库" in result["summary"]


def test_postgres_sql_tool_is_registered_and_available_to_query_agents():
    registry = create_global_tool_registry()

    assert registry.get_tool("execute_postgres_sql_query") is not None
    # 共享层：报告 DAG 问数子模式直接挂载本工具；问数/专家模式由项目 manifest
    # （projects/xuchang/project.yaml 的 agent_mode_tools）挂载。
    assert "execute_postgres_sql_query" in QUERY_MONITORING_TOOL_NAMES
    assert "execute_postgres_sql_query" in QUERY_FORECAST_TOOL_NAMES


def test_postgres_sql_tool_whitelist_partitions():
    assert ALLOWED_SQL_TABLES == (
        PERMIT_SQL_TABLES + WEATHER_SQL_TABLES + XUCHANG_TRAFFIC_SQL_TABLES + ALERT_RESULT_SQL_TABLES
    )


def test_postgres_sql_tool_allows_alert_result_queries():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate(
        "SELECT started_at, station_name, target_pollutant, status, "
        "peak_station_value, peak_deviation_ratio "
        "FROM xuchang_station_alert_episodes ORDER BY started_at DESC LIMIT 50"
    )
    assert valid is True
    assert error == ""

    valid, error = tool.sql_validator.validate(
        "SELECT completed_at, station_name, conclusion, broadcast_message "
        "FROM scheduled_task_results "
        "WHERE task_id = 'task_xuchang_station_deviation_alert' "
        "ORDER BY completed_at DESC LIMIT 20"
    )
    assert valid is True
    assert error == ""


def test_postgres_sql_tool_alert_tables_route_to_main_engine():
    tool = ExecutePostgresSQLQueryTool()

    assert tool._select_engine(["scheduled_task_results"]) is engine
    assert tool._select_engine(["xuchang_station_alert_episodes"]) is engine


def test_postgres_sql_tool_rejects_alert_weather_cross_database_join():
    tool = ExecutePostgresSQLQueryTool()

    sql = (
        "SELECT e.station_name, o.temperature_2m FROM xuchang_station_alert_episodes e "
        "JOIN observed_weather_data o ON 1 = 1 LIMIT 10"
    )
    result = asyncio.get_event_loop().run_until_complete(tool._execute_sql(sql, 10, None))
    assert result["success"] is False
    assert "跨库" in result["summary"]
