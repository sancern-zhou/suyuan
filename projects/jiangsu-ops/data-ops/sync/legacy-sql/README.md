# legacy-sql — 已被 dbt 取代的 psql 建表脚本

2026-10-02 起，mart/dim 层由 dbt 项目（`E:\Tools\suyuan-jiangsu\dbt`）负责，
sync-all.cmd / sync-daily.cmd 不再调用本目录脚本。

迁移时因一次 cmd `move` 误操作（目标目录不存在时 move 退化为重命名并逐个覆盖），
以下 10 个脚本的原件丢失；**逻辑与注释已完整移植到对应 dbt 模型**，如需回溯以模型为准：

| 原脚本 | 现位置 |
|---|---|
| dim_station.sql | dbt\models\dim_station.sql |
| dim_device.sql | dbt\models\dim_device.sql |
| mart_work_order.sql | dbt\models\mart_work_order_analysis.sql |
| mart_alarm_event.sql | dbt\models\mart_alarm_event_analysis.sql |
| mart_station_health.sql | dbt\models\mart_station_device_health.sql |
| mart_station_daily_profile.sql | dbt\models\mart_station_daily_profile.sql |
| mart_qc_execution.sql | dbt\models\mart_qc_execution_analysis.sql |
| mart_qc_arrangement.sql | dbt\models\mart_qc_arrangement_analysis.sql |
| mart_inspection_analysis.sql | dbt\models\mart_inspection_analysis.sql |
| mart_performance_analysis.sql | dbt\models\mart_performance_analysis.sql |

仅 mart_blackout_analysis.sql 原件幸存，同样已被 dbt 模型取代，留作纪念。

setup_agent_guardrails.sql 仍在上级目录（一次性护栏初始化，不属于刷新链路）。
