from app.tools.query.execute_sql_query.tool import (
    TABLE_CALIBER_NOTES,
    ExecuteSQLQueryTool,
)


def _mock_columns() -> list[dict]:
    return [
        {"COLUMN_NAME": "station_id", "DATA_TYPE": "nvarchar", "CHARACTER_MAXIMUM_LENGTH": 16, "IS_NULLABLE": "NO", "COLUMN_DEFAULT": None, "TABLE_SCHEMA": "dbo"},
        {"COLUMN_NAME": "forecast_time", "DATA_TYPE": "datetime2", "CHARACTER_MAXIMUM_LENGTH": None, "IS_NULLABLE": "NO", "COLUMN_DEFAULT": None, "TABLE_SCHEMA": "dbo"},
        {"COLUMN_NAME": "publish_time", "DATA_TYPE": "datetime2", "CHARACTER_MAXIMUM_LENGTH": None, "IS_NULLABLE": "YES", "COLUMN_DEFAULT": None, "TABLE_SCHEMA": "dbo"},
        {"COLUMN_NAME": "wind_direction_degrees", "DATA_TYPE": "float", "CHARACTER_MAXIMUM_LENGTH": None, "IS_NULLABLE": "YES", "COLUMN_DEFAULT": None, "TABLE_SCHEMA": "dbo"},
    ]


def _mock_sample() -> list[dict]:
    return [{
        "station_id": "ZzMTA",
        "forecast_time": "2026-11-13 12:00:00",
        "publish_time": "2026-11-13 10:26:18",
        "wind_direction_degrees": 135.0,
    }]


def test_describe_table_injects_nmc_forecast_caliber_note():
    tool = ExecuteSQLQueryTool(project_id="xuchang")
    tool._execute_query = lambda sql, database: _mock_columns() if "INFORMATION_SCHEMA" in sql else _mock_sample()

    result = tool._describe_table("XuchangNmcHourlyWeatherForecast", "XcAiDb")

    assert result["success"] is True
    summary = result["summary"]
    assert "口径注记" in summary
    assert "(station_id, forecast_time) 唯一" in summary
    assert "无需按 publish_time 去重" in summary
    assert "不要写 MAX(publish_time)" in summary
    # 注记位于字段清单之后、样例之前
    assert summary.index("口径注记") < summary.index("最新数据样例")


def test_describe_table_schema_prefixed_name_gets_same_note():
    tool = ExecuteSQLQueryTool(project_id="xuchang")
    tool._execute_query = lambda sql, database: _mock_columns() if "INFORMATION_SCHEMA" in sql else _mock_sample()

    result = tool._describe_table("dbo.XuchangNmcHourlyWeatherForecast", "XcAiDb")

    assert result["success"] is True
    assert "无需按 publish_time 去重" in result["summary"]


def test_describe_table_without_note_stays_unmodified():
    tool = ExecuteSQLQueryTool(project_id="xuchang")
    tool._execute_query = lambda sql, database: _mock_columns() if "INFORMATION_SCHEMA" in sql else _mock_sample()

    result = tool._describe_table("WeatherForecast7Day", "XcAiDb")

    assert result["success"] is True
    assert "口径注记" not in result["summary"]


def test_caliber_notes_only_covers_existing_tables():
    tool = ExecuteSQLQueryTool(project_id="xuchang")
    whitelisted = set(tool.sql_validator.ALLOWED_TABLES)
    for table in TABLE_CALIBER_NOTES:
        assert table in whitelisted, f"注记表 {table} 必须在白名单内"
