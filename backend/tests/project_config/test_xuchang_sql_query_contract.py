"""execute_sql_query 许昌差异契约（project_id="xuchang"）。

共享默认契约在 backend/app/tools/query/execute_sql_query/tool_spec.py（默认部署
视角）；本文件只断言许昌 tool_options 注入后的路由/白名单差异，显式
project_id="xuchang" 构造，与部署环境变量无关。
"""

from app.tools.query.execute_sql_query.tool import ExecuteSQLQueryTool


def test_xuchang_schema_routes_station_long_history_to_crawler():
    tool = ExecuteSQLQueryTool(project_id="xuchang")
    description = tool.get_function_schema()["description"]

    assert "监测数据SQL Server查询工具（许昌）。" in description
    assert "改用 execute_crawler_sql_query" in description
    assert "国控站点日值（日及以上）优先 query_airdata_platform" in description
    assert "dat_station_hour" not in tool.sql_validator.ALLOWED_TABLES
    assert "dat_station_day" not in tool.sql_validator.ALLOWED_TABLES
    assert "dat_zhongda_station_hour" in tool.sql_validator.ALLOWED_TABLES
    assert "dat_station_hour（站点小时）和dat_station_day（站点日）" not in description
    # 受限白名单不含共享默认里的气象/抓取侧表
    assert "era5_reanalysis_data" not in tool.sql_validator.ALLOWED_TABLES
    assert "dust_forecasts" not in tool.sql_validator.ALLOWED_TABLES
