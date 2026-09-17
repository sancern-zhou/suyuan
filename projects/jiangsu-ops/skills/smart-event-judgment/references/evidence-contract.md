# 智能事件证据包契约

当前证据包为 `jiangsu_smart_event_evidence/v1`，主要字段如下：

- `event_id`、`event_context`：事件、站点、主线索和原始告警标识。
- `profile`：按主线索选择的取证范围；它描述采集策略，不是最终事件类型。
- `time_windows.event`、`time_windows.hour`、`time_windows.day`：事件窗口、前后扩展查询窗口和自然日合规窗口。
- `sources`：监测、站房报警、数采报警、仪器状态、动环、质控、工单、片区对比和气象等来源。每个来源检查 `success`、`status`、`summary`、`record_count`、`metadata` 和 `data`。片区对比（comparison）中：`data` 保留本站与同区周边站点的逐小时六项污染物原始记录；`regional_deltas` 提供事件窗口均值差、`event_hourly_alignment`（事件窗口前后各 3 小时本站与周边站点逐小时对齐序列）、`event_trend_comparison`（事件窗口趋势一致性）和 `trend_comparison`（全天趋势一致性）。核验异常开始、持续、结束的同步性时优先使用 `event_hourly_alignment` 的小时级数值；只有 comparison 为空、失败或未接入时才可声明缺少周边站点数据。
- `gaps`：视频未接入、接口不可用、空结果或其他证据缺口；`empty`、`failed`、`unavailable` 不得混为一谈。
- `persisted_path`：证据包 `index.json` 的路径；来源明细按数据类型存放在同目录 `sources/<name>.json`，按需读取。
- `ai_judgment`：任务完成后由系统回写的研判结果，不作为本次研判的先验事实。

## 文件的物理布局

证据包在磁盘上按数据类型拆分为多个 JSON，避免一次加载整包：

```
evidence-<digest>/
  index.json                 # 事件上下文、profile、time_windows、gaps、source_status，
                             # 以及 sources.<name> 的 status/summary/record_count/metadata 索引
  sources/
    monitoring.json          # {"event_id","source","data"}，data 为该来源的映射投影
    instrument_status.json
    comparison.json
    ...
```

`evidence_package_path`/`persisted_path` 指向 `index.json`。先读 index 掌握来源全貌，再只读研判需要的 `sources/<name>.json`；不要把单个来源的部分内容当成整包。详情接口在服务端会把 index 与各来源重组成完整 `sources`，因此前端仍按完整包展示。

## 大接口的映射投影

对一次返回大量逐行记录的接口，证据包内联的是**映射投影**，不是原始行；不要按逐行字段去读，也不要因看不到原始行而判定证据缺失。目前：

- `instrument_status.data` 为 `instrument_status_series/v1`：原始为「污染物×仪器参数×时间点」长表；按分辨率（`five_minute`、`hour`）投影，每个分辨率含 `station_*` 站点头部、`pollutants` 污染物品牌/序列和 `series`。每条 `series` 含 `p`（污染物）、`param`（参数）、`unit`、`n`、时间跨度、`min/max/mean/first/last`，仅在 `mark` 非 `N` 时附带 `abnormal`（`t` 时间、`v` 原始值、`m` 标记）。判断仪器是否异常时看各参数量程与 `abnormal`，不要要求逐行原始值；`metadata.projection` 与 `metadata.raw_record_count` 记录投影类型和原始行数。
- `monitoring` 宽表已剔除 `id`、`createTime`、`modifyTime` 及 `*_IAQI` 派生列；被剔除的列名见对应来源的 `dropped_fields`。污染物序列字段与 `timePoint` 保持原样，时间序列口径不变。
- 需要原始逐行数据时，另行调用已配置的江苏只读接口即时查询，不把投影当作完整明细。

先核对事件上下文与证据包事件编号和站点编码，再解释业务时间。`metadata.time_range` 是查询范围，不能直接当作故障发生时间。没有小时/五分钟数据时可以分析报警，但必须把数据影响标为“待确认”；气象为空或失败时不能写成“没有气象影响”。

事件起止时间取全部线索的最早、最晚时间；`latest_occurrence_time` 只是最新发生时间的展示字段，不可替代事件起点。查询窗口可以扩展到小时或自然日，按实际 `time_windows` 和各来源 `metadata.time_range` 使用，不把整个查询范围当作影响区间。

`system_data_impact` 是系统初判，`ai_task_priority` 是队列优先级；相关字段可能位于事件上下文中。系统检测标签需要结合原始数据核验，不能把初判作为证据本身。

## 来源可得性与必需证据

研判前先对与候选类型相关的来源调用已配置的江苏只读接口。按来源实际返回区分：`success` 且有有效记录作为可用证据；`empty` 表示本次窗口没有该来源记录，不代表相关事实不存在；`failed`、`unavailable` 或未接入表示接口/接入缺口，不得臆造结果。

只有成功取得的证据才构成当前事件的约束。空、失败、不可用、未接入的来源不属于本次研判的必需证据集合，也不能作为排除某个类型的依据。若其他可用证据已形成支持某一类型的事实链，直接完成分类；在结论中列出未获取来源和剩余不确定性。仅当可用证据之间互相矛盾，或可用证据本身不足以支持任何类型时，才使用“数据异常待研判”或“其他待人工复核”。

人员进站/门禁在当前平台可能返回空结果或无法获取，保持为非必需证据。先尝试接口；有记录时用于核对人员活动时段，无记录、失败或不可用时只登记非阻断性缺口，不得因此否定人员活动，也不得阻止其他证据已经支持的定类。

合规工单应查询事件站点自然日内的全部工单类型，不得只查故障单；重点核对巡检/例行运维、现场检查、进站申请、停电、质控、质量保证、校准、数据补录等记录。工单存在本身不是结论，仍需核对工单时间、对象、任务内容与事件线索是否吻合。

数采报警进入证据包前只保留可支持数据链路判断的告警：数据重发堆积、数据上报失败、网络/通讯失败、监测设备离线、采样与质控链路、供电和站房环境等。主机 CPU/内存/网络流量阈值、软件内存/线程/句柄/错误日志、数据库打开/空间/CPU/IO、泛化的数据库超时或语句错误、软件自动更新失败属于软件自监控噪声，不得作为数据受影响或公共系统异常的证据，也不因其存在选择“数据异常待研判”；这类记录不在证据包中保留，需要追溯时直接查询报警数据库。

工单附件是证明具体维修、校准、现场操作或报备内容的补充材料，不是智能事件默认必需证据。工单清单和正文已经足以支持判断时，不要为获取附件阻塞研判；仅当工单正文不足以核对具体操作，或需要审计留痕时，才按工单号打开详单并尝试下载附件。附件为空、下载失败或格式无法解析时记录为非阻断性缺口。
