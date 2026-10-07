# 站点运行监控日报

共用实现：`backend/app/services/station_operation_monitor/`。部署配置和项目站点名单由对应项目分支维护，运行状态始终存储到显式配置的 `DATA_REGISTRY_DIR/station_operation_monitor`。

## 配置与运行

将项目配置部署为 registry 下的 `station_operation_monitor/config.json`。配置字段：
- `stations`：去重后的 `code/name/city/type`；`type` 为国控或省控。`confirmed=true` 时 `active` 为经确认的在运状态；未确认候选站只在实际取得记录后纳入监控，无记录者单列待核实。
- `sources`：来源名称、`base_url/token_endpoint/hour_endpoint`、`username_env/password_env`、可选headers与`station_types`。凭据仅从环境变量读取，不能写入配置或快照。
- `national_sources`：国控回补核查来源列表；必须有一个来源完整补齐全部缺失小时的六参数，才算已回补；不能拼接两个不完整来源冒充单源完成。
- `provincial_source`：省控唯一回补核查来源。
- `collection_cron`：默认北京时间每小时25分；`arrival_grace_minutes` 默认20分钟。`bootstrap_hours`默认48，后续`lookback_hours`默认6，同时复查历史未回补区间。
- `report_title/organization`：报告抬头；未提供期号、编制和校核信息时标为待人工确认。

工具 `station_operation_daily(action="report")` 会刷新至当日10时，计算昨日10时到今日10时的24个小时结束标签，并生成不可覆盖的JSON和Word产物。定时任务使用custom模式显式绑定该工具，安排每天10:30开始，由Agent完整调用并交付。无需调用子Agent。取数不完整仍可生成明确标注“待核实”的报告，但不得声称全部运行正常。

CLI：从项目根运行 `python backend/scripts/station_operation_monitor.py --env-file backend/.env collect` 或 `report`。显式路径统一通过`resolve_agent_path`解析；工具结果路径通过`format_agent_path`格式化。

小时采集由既有worker的FetcherScheduler执行。默认fetcher配置下，只有上述部署配置存在才自动加入`station_operation_monitor`；项目采用显式fetcher列表时须将该名称加入allowlist。不要另起使用不同registry的web/worker。启用新工具及fetcher需要重启对应部署的worker。

## 判定与边界

- 连续整站小时数据缺失超过4小时纳入事件，正常0值不属于缺失。带括号质量标记的数值应分别保存数值和标记，不将其解析失败视作离线。
- 有任一六参数数值表示数据传输已有返回；六参数全部数值补齐表示数据完整回补；质量标记是否影响有效性另行核实，不能等同于离线。
- SQLite保留首次缺失时间，即使后来回补也不删除原事件证据。采集原文保存在不可覆盖gzip快照中。失败查询、格式异常、空城市响应与疑似截断响应不改变站点缺数状态。
- 恢复与回补分别计算。前日及更早仍未恢复/未回补的事件继续出现在日报；历史已结事件仅在本统计窗口或本日发现回补时展示。
- 此处“离线”为小时数据缺失的运行监控口径，无法据此证明设备物理离线。无法回补需要额外确认依据，当前脚本不会因持续缺数直接给出无法回补。
- 城市聚合小时数据不能推断具体站点状态；独立站点发布源未接入时，报告必须披露国控单源限制。
- 首次运行无法还原此前已经回补的缺口；未确认名单不能声称代表全省正式在运总数。

测试：`python -m pytest backend/tests/station_operation_monitor -q`。覆盖窗口边界、质量标记、查询失败、名录、跨日未结跟进、双源完整回补、部分回补、乱序重查和Word输出。
