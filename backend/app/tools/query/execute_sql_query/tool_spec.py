"""execute_sql_query 共享默认契约（默认部署视角，无项目 tool_options 注入）。

断言锚点 = 当前默认描述（基础文案 + AIR_QUALITY_SCHEMA_GUIDE）的真实内容：
国控站小时/日长历史（dat_station_*）契约已从默认描述与白名单移除（归
execute_crawler_sql_query / 项目配置层），与 xuchang 分支契约方向一致。
许昌的路由/白名单差异契约属 xuchang 分支自持 spec——其配置来自
projects/xuchang/project.yaml 的 backend.tool_options.execute_sql_query。
"""

from app.tools.query.execute_sql_query.tool import ExecuteSQLQueryTool


def test_execute_sql_query_default_description_contract():
    description = ExecuteSQLQueryTool(project_id="default").get_function_schema()["description"]

    # 基础文案与硬约束
    assert "监测数据SQL Server查询工具。二选一：describe_table 查表结构，或 sql 执行 SELECT。" in description
    assert "只允许 SELECT（禁写/DDL）；最大返回 1000 条" in description
    assert "database 默认 XcAiDb" in description
    assert "质控/站点基础信息用 AirPollutionAnalysis" in description

    # 高频表索引
    assert "【常用表索引】XcAiDb：WeatherForecast7Day(7天预报)" in description
    assert "XuchangNmcHourlyWeatherForecast(NMC逐3小时气象)" in description
    assert "dat_zhongda_station_minute·hour·city_hour(中大平台)" in description
    assert "city_168_statistics_*·province_statistics_*(全国省级统计)" in description

    # 口径硬规则（AIR_QUALITY_SCHEMA_GUIDE）
    assert "【高频表口径规则】字段清单用 describe_table 获取，此处只列硬规则。" in description
    assert "不得把 {city_name}/{city_code} 模板变量原样写进 SQL" in description
    assert "城市小时优先中大审核表 dat_zhongda_city_hour（滞后约1天）" in description
    assert "站点5分钟数据中大独有" in description
    assert "未来逐3小时气象预报优先 XuchangNmcHourlyWeatherForecast（NMC 官方，7天）" in description
    assert "PM2.5 列名=PM2_5（非 PM25）" in description
    assert "无效值站点表 -99 / 城市表 -999" in description
    assert "data_type_plan='155th'（用错规划期返回空）" in description

    # 国控站小时/日长历史（dat_station_*）不进默认描述——长历史路由归
    # execute_crawler_sql_query / 项目配置层，与 xuchang 分支契约方向一致。
    assert "dat_station_hour" not in description
    assert "dat_station_day" not in description

    # 未在索引中的字段仍走 describe_table
    assert "字段清单用 describe_table 获取" in description


def test_execute_sql_query_default_tables_exclude_station_long_history():
    tool = ExecuteSQLQueryTool(project_id="default")
    allowed = {table.lower() for table in tool.sql_validator.ALLOWED_TABLES}

    assert "dat_station_hour" not in allowed
    assert "dat_station_day" not in allowed
    assert "dat_zhongda_station_hour" in allowed
    assert "dat_zhongda_city_hour" in allowed
    assert "currentairquality" in allowed
