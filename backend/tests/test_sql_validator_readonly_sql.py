import asyncio

import pyodbc

from app.tools.query.execute_sql_query.tool import ExecuteOpsSQLQueryTool, ExecuteSQLQueryTool
from app.utils.sql_validator import SQLValidator


OPS_TABLES = ["working_orders", "working_order_details"]


def test_validator_accepts_case_when_and_union_select():
    validator = SQLValidator(max_limit=1000, allowed_tables=OPS_TABLES)

    sql = """
        SELECT WORKINGORDERID, CASE WHEN DDWORKINGORDERSTATUS = N'Finish' THEN 1 ELSE 0 END AS done
        FROM working_orders
        UNION ALL
        SELECT WORKINGORDERID, 0 AS done
        FROM working_order_details
    """

    is_valid, error = validator.validate(sql)

    assert is_valid, error


def test_validator_normalizes_markdown_sql_code_fence():
    validator = SQLValidator(max_limit=1000, allowed_tables=OPS_TABLES)

    sql = """
```sql
SELECT WORKINGORDERID
FROM working_orders
```
"""

    is_valid, error = validator.validate(sql)

    assert is_valid, error


def test_validator_accepts_single_outer_parentheses_around_select():
    validator = SQLValidator(max_limit=1000, allowed_tables=OPS_TABLES)

    sql = "(SELECT WORKINGORDERID FROM working_orders)"

    is_valid, error = validator.validate(sql)

    assert is_valid, error


def test_validator_still_rejects_multiple_statements_after_normalization():
    validator = SQLValidator(max_limit=1000, allowed_tables=OPS_TABLES)

    sql = """
```sql
SELECT WORKINGORDERID FROM working_orders;
SELECT WORKINGORDERDETAILID FROM working_order_details;
```
"""

    is_valid, error = validator.validate(sql)

    assert not is_valid
    assert error == "不能执行多条SQL语句"


def test_execute_ops_sql_query_allows_up_to_1000_rows():
    tool = ExecuteOpsSQLQueryTool()

    assert tool.sql_validator.max_limit == 1000
    assert "最大1000" in tool.function_schema["parameters"]["properties"]["limit"]["description"]


def test_execute_sql_query_allows_open_meteo_air_quality_forecast_tables():
    tool = ExecuteSQLQueryTool()

    for sql in (
        "SELECT TOP 1 forecast_time FROM OpenMeteoAirQualityForecast72h",
        "SELECT TOP 1 forecast_time FROM dbo.OpenMeteoAirQualityForecast72h",
    ):
        is_valid, error = tool.sql_validator.validate(sql)

        assert is_valid, error


def test_execute_sql_query_allows_xuchang_nmc_hourly_weather_forecast_tables():
    tool = ExecuteSQLQueryTool()

    for sql in (
        "SELECT TOP 56 forecast_time, temperature, humidity, wind_direction, wind_speed,"
        " precipitation_probability, weather_text FROM XuchangNmcHourlyWeatherForecast"
        " WHERE city_code = '411000' ORDER BY forecast_time",
        "SELECT TOP 1 forecast_time FROM dbo.XuchangNmcHourlyWeatherForecast",
    ):
        is_valid, error = tool.sql_validator.validate(sql)

        assert is_valid, error


def test_execute_sql_query_rejects_henan_city_accumulate_ranking_table():
    """省APP已停服，排名走 xuchang_cube_metrics；该表已从白名单移除。"""
    tool = ExecuteSQLQueryTool()

    for sql in (
        "SELECT TOP 30 city, city_rank, zong FROM HenanCityAccumulateRanking"
        " WHERE period_type = 'monthly' AND period = '2026-08' ORDER BY city_rank",
        "SELECT TOP 30 city, city_rank, zong FROM dbo.HenanCityAccumulateRanking"
        " WHERE period_type = 'yearly' AND period = '2026' ORDER BY city_rank",
    ):
        is_valid, error = tool.sql_validator.validate(sql)

        assert not is_valid, error


def test_xuchang_sql_tool_routes_crawler_station_history_before_execution():
    tool = ExecuteSQLQueryTool(project_id="xuchang")

    assert "dat_station_hour" not in tool.sql_validator.ALLOWED_TABLES
    assert "dat_station_day" not in tool.sql_validator.ALLOWED_TABLES
    assert "dat_zhongda_station_hour" in tool.sql_validator.ALLOWED_TABLES

    result = asyncio.run(
        tool.execute(sql="SELECT TOP 1 * FROM dbo.dat_station_hour")
    )

    assert result["success"] is False
    assert "execute_crawler_sql_query" in result["summary"]


def test_missing_city_table_does_not_get_station_crawler_hint(monkeypatch):
    tool = ExecuteSQLQueryTool(project_id="xuchang")

    def _raise_missing_table(sql, database):
        raise pyodbc.ProgrammingError(
            "42S02",
            "[42S02] Invalid object name 'CityAQIPublishHistory'",
        )

    monkeypatch.setattr(tool, "_execute_query", _raise_missing_table)
    result = asyncio.run(
        tool.execute(sql="SELECT TOP 1 * FROM dbo.CityAQIPublishHistory")
    )

    assert result["success"] is False
    assert "SQL执行失败" in result["summary"]
    assert "execute_crawler_sql_query" not in result["summary"]
    assert "describe_table='CityAQIPublishHistory'" in result["summary"]
