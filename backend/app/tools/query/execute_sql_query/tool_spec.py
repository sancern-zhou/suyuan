"""execute_sql_query 契约（xuchang 分支）。

默认部署契约（test 1/2）断言共享默认描述；许昌路由/白名单契约（test 3）由
projects/xuchang/project.yaml 的 backend.tool_options.execute_sql_query 驱动
（显式 project_id="xuchang" 构造，与部署环境变量无关）。
"""

from app.tools.query.execute_sql_query.tool import ExecuteSQLQueryTool


def test_execute_sql_query_default_description_contract():
    description = ExecuteSQLQueryTool(project_id="default").get_function_schema()["description"]

    assert "监测数据SQL Server查询工具。二选一：describe_table 查表结构，或 sql 执行 SELECT。" in description
    assert "只允许 SELECT（禁写/DDL）；最大返回 1000 条" in description
    assert "database 默认 XcAiDb" in description
    assert "【常用表索引】XcAiDb：WeatherForecast7Day(7天预报)" in description
    assert "【高频表口径规则】字段清单用 describe_table 获取，此处只列硬规则。" in description
    assert "PM2.5 列名=PM2_5（非 PM25）" in description
    assert "data_type_plan='155th'（用错规划期返回空）" in description

    # 国控站小时/日长历史契约不进默认描述/白名单（归 execute_crawler_sql_query /
    # 项目配置层）——与共享 main 契约方向一致。
    assert "dat_station_hour" not in description
    assert "dat_station_day" not in description
    allowed = {table.lower() for table in ExecuteSQLQueryTool(project_id="default").sql_validator.ALLOWED_TABLES}
    assert "dat_station_hour" not in allowed
    assert "dat_zhongda_station_hour" in allowed


def test_execute_sql_query_falls_back_to_shared_guide_for_unlisted_fields():
    description = ExecuteSQLQueryTool(project_id="default").get_function_schema()["description"]

    assert "字段清单用 describe_table 获取" in description


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
