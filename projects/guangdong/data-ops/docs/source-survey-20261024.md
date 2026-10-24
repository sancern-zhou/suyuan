# 广东运维源库（Operation_SC_GD）表单勘察与同步范围评估

勘察时间：2026-10-24 深夜（数据时点见附录原始输出）
方法：只读元数据枚举（642 表 + 17 视图）→ 逐表时间列 MAX 探测 → 关键表今年行数核对。
原始输出：`source-survey-tables-20261024.txt`（表/视图/行数）、`source-survey-activity-20261024.txt`（活跃度探测）。

## 总体结论

- 源库 642 张表中，真实活跃业务表约 **110 张**（当天或本周有新数据）；约 100+ 张是带
  `_bak/_back/日期后缀` 的归档副本，约 200 张是小配置表。
- 当前 ODS 同步 5 张（工单域）。按江苏的覆盖面对标，建议**分两期扩展约 25 张**：
  一期（告警/设备/任务/巡检/停运）直接支撑告警、设备生命周期、巡检、停运四个分析域；
  二期（绩效/月报/资产/字典）补齐管理与台账。
- 实时监测值（STN_AIRREALTIMEVALUE 等）**不纳入**：站点监测数据已有 query_gd_suncere
  API 工具链覆盖，同步进来只会重复。

## 一期：建议纳入（活跃、分析价值明确，对齐江苏已验证域）

| # | 源表 | 行数(总/今年) | 活跃度(最新数据) | 业务域 / 对应江苏能力 |
|---|---|---|---|---|
| 1 | ALM_ALARM | 71.9万 / 19.97万 | 当天 | 站点告警事件 → 告警域 mart（未处理率/转工单率，对标 AlarmEvent cube） |
| 2 | LOG_DEVICE | 50.5万 / 7.44万 | 当天 22:45 | 设备状态变更日志 → 设备生命周期（对标 DeviceLifecycle） |
| 3 | Sup_RF_Common | 4.1万 / 3,054 | 当天 | 非故障单表单体 → 工单审核取数（对标 rf_common，ops_audit 依赖） |
| 4 | PW_TASK | 10.8万 / 活跃 | 当天 | 运维计划任务 → 巡检计划域（对标 Inspection） |
| 5 | PW_TASKITEM | 64.3万 / 持续生成 | 当天 00:07 | 计划任务项（完成率/超期率的明细基础） |
| 6 | MTC_ORDERTASKITEM | 70.9万 / - | 计划时间到 10-26 | 工单任务项关联；无 CREATETIME，增量列需确认（备选 PLANFINISHTIME 或 daily_full） |
| 7 | Sup_Mtc_TaskItem | 14.4万 / 活跃 | 当天 | 组分网任务项 |
| 8 | RF_W_INSPECTION / _INSPECTIONSUMMARY | 5.5万+5.8万 / 当天 | 当天 21:07 | 巡检表单（附件 type_code 指向的实体表） |
| 9 | RF_W_GASEOUSCHECK_SO2/NO2/CO/O3 | 各5.5万 / 当天 | 当天 21:08 | 气态检查表单 |
| 10 | RF_W_OTHERDEVICECHECK / RF_W_PMCHECK | 5.5万+11万 / 当天 | 当天 21:07 | 其他设备检查/PM 表单 |
| 11 | SEC_BLACKOUTREPORT | 3,108 | 需用 createDATETIME | 停运报告（列名大小写混乱，建模时注意） |
| 12 | SEC_BlackOutReportDetail / _Timespan | 55.6万 / 6,074 | 10-22 | 停运报告明细/时段 |
| 13 | SEC_QcBlackOut | 3.5万 | Month 到 2026-09 | 质控停运月度汇总 |
| 14 | QUL_QUALITYDATE | 7.8万 / 2,227 | 当天 | 质控评价日期 |
| 15 | Sup_DeviceDayCheck | 28.3万 / 4,040 | 当天 15:33 | 设备日检查 |
| 16 | OPA_DataReceiveRate | 1.1万 | 每日生成 | 数据到报率（平台统计口径） |
| 17 | Alm_Home | 314 | 当天 22:30 | 当前告警态势快照（小表，daily_full） |

一期新增今年同步量估算：约 45~55 万行（ALM 20万 + LOG_DEVICE 7.4万 + 任务项族 ~15万 +
RF 表单族 ~5万 + 其他小表），按现有 hourly/daily 两个频道的容量没有压力。

## 二期：纳入（管理/台账/字典，小表 daily_full 为主）

| 域 | 表 | 说明 |
|---|---|---|
| 绩效 | OPA_Performance（3.6万，**无时间列**→daily_full）、OPA_STATIONPERFORMANCESCORE（1.3万）、OPA_Lock_PerformanceScore（1.6万） | 工单步骤级绩效得分与核减金额（HTJE/SJJE） |
| 报告 | OPA_MONTHLYREPORT（2.6万/今年3,531）、Sup_MonthReport | 月度报告数据 |
| 台账 | Sup_Device（565）、Sup_Station（100）、Sup_Contract*、zc_asset_base（3.3万）/zc_assettype | 运维设备/站点/合同/资产台账 |
| 用户 | SYS_USER（1,036）、SYS_DEPARTMENT（114）、SYS_DEPARTMENTSTATION（518）、SYS_USERSTATION（3,659） | **工单处理人中文名解析**（当前 mart 只有 user_id，审核报告可读性直接受益） |
| 字典 | SYS_DATADICTIONARY（130）+SYS_DATADICTIONARYITEMS（724）、BSD_POLLUTANT（122）、BSD_SUPPLY（214）、BSD_DEVICEMODEL（161）、BSD_INSBRANDINFO（543） | 站点类型/污染物/供应商/品牌型号字典 |

## 不纳入（明确排除）

- **实时监测值**：STN_AIRREALTIMEVALUE（979万，当天）、STN_REALTIMEVALUE（979万，**2020 年已停更**）、
  BSD_StationMonitorValueHour（54万/今年3.9万）——监测数据走 query_gd_suncere API 工具链，
  不同步进 ops 库；若未来需要小时级聚合再评估。
- **系统日志/消息**：SYS_ACCESSLOG（1,353万）、SYS_MessageItem（191万）、vinson_msg（80万）、
  SYS_LOGINLOG、LOG_ALLSYS、TASK_JOBLOG、Dog_*（探针）。
- **归档/备份副本**：约 100+ 张 `_bak/_back/日期后缀` 表（如 MTC_WORKINGORDER_20250310、
  Sup_VOCs_*_back、WO_COMMONFILE0709）。
- **组分网质控原始数据（暂缓）**：Sup_VOCs_InternalStandard（68万/活跃 10-22）、
  Sup_VOCs_CurveVerificationPoint（78万）、Sup_VOCs_SystemBlank（13万）及 NMHC/HeavyMetal/
  PTR_MS 等质控曲线族——量大且属组分网质控专业域，若后续启动"组分网质控分析"场景再作为
  三期评估（江苏同样把获取率/质控曲线类放在后批次）。

## 已同步 5 张的核对结论

working_orders(26.2万)/working_order_details(99.8万)/wo_commonfile_links(161万，**实为
WO_COMMONFILE 的视图**，物理表当天仍活跃)/base_station/base_device——5 张均为源库活跃表，
现有水位同步正确；附件索引继续走视图即可。

## 落地路径（对齐现有 data-ops 管道）

1. 每表在 `sync/sync_config.json` 加条目（增量列/今年窗口/类型映射），跑 `sync_table.py <t>` 首拉对账；
2. dbt 按域加 mart（alarm_event_analysis / device_lifecycle_analysis / inspection_analysis /
   blackout_analysis ...），列名契约进 `sync/datasets/*.yaml`；
3. 语义层加 AlarmEvent/DeviceLifecycle/Inspection 等 cube，registry 登记口径（limitations 照江苏模式写清）；
4. DQ 的 FRESHNESS/NULL/UNIQUE 清单同步扩充。
注意：MTC_ORDERTASKITEM、OPA_Performance 无可靠增量列，走 daily_full（两者今年量都可控）。
