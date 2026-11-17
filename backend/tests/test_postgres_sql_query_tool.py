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
    assert tool._select_engine(["era5_reanalysis_data"]) is weather_engine
    assert tool._select_engine(["permit_licenses"]) is engine


def test_postgres_sql_tool_allows_observed_weather_query():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate(
        "SELECT time, temperature_2m, wind_speed_10m FROM observed_weather_data "
        "WHERE station_id = 'DwzZf' AND time >= '2026-08-30' ORDER BY time LIMIT 48"
    )
    assert valid is True
    assert error == ""

    valid, error = tool.sql_validator.validate(
        "SELECT DISTINCT station_id, station_name FROM observed_weather_data LIMIT 30"
    )
    assert valid is True
    assert error == ""

    valid, error = tool.sql_validator.validate(
        "SELECT time, temperature_2m, boundary_layer_height FROM era5_reanalysis_data "
        "WHERE lat = 23.25 AND lon = 113.25 ORDER BY time LIMIT 48"
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

    result = asyncio.run(tool._execute_sql(sql, 10, None))
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
    # 共享白名单只保留所有部署共有的表；项目专属业务表（许昌路况时序/告警事件
    # 聚合等）经 backend.tool_options.execute_postgres_sql_query.allowed_tables_extra 注入。
    assert ALLOWED_SQL_TABLES == (
        PERMIT_SQL_TABLES + WEATHER_SQL_TABLES + ALERT_RESULT_SQL_TABLES
    )
    assert "scheduled_task_results" in ALERT_RESULT_SQL_TABLES
    assert "xuchang_station_alert_episodes" not in ALLOWED_SQL_TABLES


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


def test_postgres_sql_tool_alert_tables_route_to_main_engine():
    tool = ExecutePostgresSQLQueryTool()

    assert tool._select_engine(["scheduled_task_results"]) is engine


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
