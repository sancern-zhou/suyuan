# 事件证据包契约

证据包 `schema_version: 1` 包含：

- `event_id`、`created_at`：事件标识与证据包生成时间。
- `station`：`station_code`、站名、城市、区县。站点编码是主匹配键。
- `trigger`：触发源、原始记录、告警类型、级别、发生时间和摘要。
- `monitoring_hour_records`：事件站点的有界小时原始序列；可能为空。
- `monitoring_collection`：小时数据补抓状态、错误和记录数。
- `station_alarm_logs`：站房设备告警、统计与当前状态。
- `historical_fault_work_orders`：近期相同站点故障工单。
- `auto_inspection`：设备和小时值自动巡检快照。
- `quality_control_history`：事件站点近七天质控任务历史。
- `collection_notes`：采集限制及诊断约束。

## 校验顺序

1. 确认 `event_id` 与事件上下文一致。
2. 确认 `station.station_code` 与触发原始记录一致。
3. 将各数据源的 `queried_at`、业务时间和事件时间分开使用；`queried_at` 不是故障发生时间。
4. 检查每个补充结果的 `success/status/summary`。失败、空结果、未接入是三种不同状态。
5. 若小时记录为空，允许分析设备告警，但必须将监测影响列为待核实。

## 监测异常 finding

- `data_stale`：最新数据超过配置时限，优先检查通信、采集和供电。
- `data_missing`：站点在整个回看窗口内无记录；仅在省级查询覆盖率正常时生成。
- `invalid_value`：出现负值等无效值，检查仪器状态、质控标记和采集解析。
- `peer_aggregate_deviation`：站点 24 小时聚合值与同城站点偏离，阈值按污染物和浓度水平确定。
- `persistent_peer_bias`：站点至少 6 个有效小时持续高于或低于同城站点。
- `trend_inconsistency`：至少 12 个同小时配对点显示站点变化趋势与同城整体不一致。
- `flatline`：至少 6 个连续有效小时完全一致，且同城至少两个站点同期仍有变化。
- `quality_flag`：平台质量标记非空，必须结合标记含义和质控记录解释。

同城少于 3 个有效站点时不执行横向比较。低级别的污染物协同关系提示不单独触发故障事件。规则命中只表示需要诊断，不代表根因已经确定。
