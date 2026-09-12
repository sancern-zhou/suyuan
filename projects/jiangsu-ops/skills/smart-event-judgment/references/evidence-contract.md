# 智能事件证据包契约

当前证据包为 `jiangsu_smart_event_evidence/v1`，主要字段如下：

- `event_id`、`event_context`：事件、站点、主线索和原始告警标识。
- `profile`：按主线索选择的取证范围；它描述采集策略，不是最终事件类型。
- `time_windows.event`、`time_windows.hour`、`time_windows.day`：事件窗口、前后扩展查询窗口和自然日合规窗口。
- `sources`：监测、站房报警、数采报警、仪器状态、动环、质控、工单、片区对比和气象等来源。每个来源检查 `success`、`status`、`summary`、`record_count`、`metadata` 和 `data`。
- `gaps`：视频未接入、接口不可用、空结果或其他证据缺口；`empty`、`failed`、`unavailable` 不得混为一谈。
- `persisted_path`：证据包独立 JSON 文件路径；当内联 payload 被压缩时优先读取该文件。
- `ai_judgment`：任务完成后由系统回写的研判结果，不作为本次研判的先验事实。

先核对事件上下文与证据包事件编号和站点编码，再解释业务时间。`metadata.time_range` 是查询范围，不能直接当作故障发生时间。没有小时/五分钟数据时可以分析报警，但必须把数据影响标为“待确认”；气象为空或失败时不能写成“没有气象影响”。

事件起止时间取全部线索的最早、最晚时间；`latest_occurrence_time` 只是最新发生时间的展示字段，不可替代事件起点。查询窗口可以扩展到小时或自然日，按实际 `time_windows` 和各来源 `metadata.time_range` 使用，不把整个查询范围当作影响区间。

`system_data_impact` 是系统初判，`ai_task_priority` 是队列优先级；相关字段可能位于事件上下文中。系统检测标签需要结合原始数据核验，不能把初判作为证据本身。
