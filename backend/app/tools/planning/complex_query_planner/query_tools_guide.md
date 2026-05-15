# 复杂查询工具策略手册

此手册只注入 `complex_query_planner` 的内部 LLM 上下文，不注入主 Agent 常驻上下文。

## 总原则

1. 用户问城市统计报表、综合指数、达标率、超标天数、首要污染物比例时，优先使用 `query_city_standard_report`。
2. `query_city_standard_report` 直接调用广东联网统计报表接口；`ns_type=2` 为新国标，`ns_type=1` 为旧国标。
3. 用户问城市同比、环比、双时段变化、改善/恶化时，优先使用 `query_city_standard_yoy_report`。
4. 不要用日报、小时数据或 `execute_python` 本地重算城市新/旧国标统计指标或本地同比。
5. 用户问 168 城市全国排名、排名变化或全国发布数据时，优先用 `execute_sql_query` 查询预计算统计表，不要使用广东省内查询工具代替全国排名。
6. 用户问小时级、站点级或区域对比时，选择对应的小时、站点或区域工具，不要用城市日报工具硬凑。
7. 缺少时间范围、城市范围或标准口径时，计划中返回 `error` 和 `warnings`，不要编造参数。

## result vs report_data_id

- `result` 是接口返回的统计报表记录，报告生成、趋势分析和问答解释应优先读取它。
- `report_data_id` 保存完整接口报表，可用 `read_data_registry` 读取 `cities`、`raw`、`result` 视图。
- `data` 只是前 24 条预览，不代表完整结果。

## 统计报表策略

- 新国标统计：`query_city_standard_report(ns_type=2, ...)`
- 旧国标统计：`query_city_standard_report(ns_type=1, ...)`
- 新旧标准同周期对比：分别查询 `ns_type=2` 和 `ns_type=1` 的接口结果，只基于接口字段做差值说明，不本地重算空气质量统计指标。
- 同比/环比：`query_city_standard_yoy_report(ns_type=2 或 1, time_point=[...], contrast_time=[...])`，直接使用接口返回的 Compare/Increase/Rank 字段。
- `pollutant_codes` 默认不传/为空，让接口返回全部字段；只有用户明确要求筛选 SO2、综合指数等特定字段时才传入字段列表。
- 站点新/旧国标统计：`query_station_standard_report(ns_type=2 或 1, ...)`
- 站点同比/环比：`query_station_standard_yoy_report(ns_type=2 或 1, time_point=[...], contrast_time=[...])`

## 日数据、小时数据与聚合

- 用户明确要逐日数据、日期列表、日变化曲线时，用 `query_gd_suncere_city_day_new` 或旧标准日数据工具。
- 用户要小时变化、小时峰值或日内过程时，用 `query_gd_suncere_city_hour` 或 `query_gd_suncere_station_hour_new`。
- 用户要月度分组统计时，优先按月份拆分调用 `query_city_standard_report`；不要把一个累计结果误当成月序列。

## SQL 查询策略

`execute_sql_query` 适合：

- 168 城市全国排名、全国发布数据、预计算排名字段。
- 需要直接访问统计表中的字段。
- 需要 CTE、窗口函数、JOIN 或复杂筛选，并且专用工具不能覆盖。

SQL 约束：

- 使用 SQL Server 语法。
- 中文字符串加 `N` 前缀，例如 `N'广州'`。
- 表结构不确定时，计划中应先调用表结构查询或说明需要 `describe_table`/数据字典，而不是猜字段。
- 已预计算的排名字段优先直接查询，不要重复用窗口函数计算。

## 常见误用

- 错误：为了统计超标天数，先查日数据再让主 Agent 手算。正确：优先 `query_city_standard_report`。
- 错误：为了同比，分别查两个单时段报表再本地计算。正确：优先 `query_city_standard_yoy_report`。
- 错误：全国排名使用广东省内查询工具。正确：使用全国统计表或全国空气质量工具。
- 错误：重复查询全省和部分城市。正确：如果已查询更大城市集合，从结果中提取子集。
- 错误：只返回调用计划，不告诉主 Agent 读取哪个字段。正确：在 `result_usage` 和 `field_paths` 中写清楚。
