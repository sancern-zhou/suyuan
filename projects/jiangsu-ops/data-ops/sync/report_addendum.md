
---

## 附录：2026-10-04 全库活跃表复盘（含 log_device 纳入同步）

用户确认将设备生命周期表 `opa_product_data.log_device` 纳入同步后，对三个源库做了"仍在活跃写入但不在同步范围"的全量扫描
（方法：dm_db_partition_stats 取行数 → 过滤空表/年份分区壳 → 逐表对最优时间列取 MAX，阈值 ≥2026-09-01）。
扫描与取样脚本：`sync/survey_active_tables.py`、`sync/sample_candidates.py`、`sync/find_lifecycle_tables.py`。

### 本次新纳入同步

| 表 | 内容 | 同步方式 |
|---|---|---|
| opa_product_data.log_device | 设备生命周期状态变更日志（deviceidstate×eventstate 流转，WorkingOrderCode 可关联故障工单；DeviceSpare×778=备机事件，解锁"备机更换及时性"场景） | 每日全量，窗口 ≥2026-07-01（窗口内 693 行）；已入 sync_config.json + sync-daily.cmd + dbt sources.yml |

同步引擎顺手修复：SQL Server nchar 列携带 NUL(\x00) 字符导致 PostgreSQL 拒写——`sync_table.py` upsert 路径增加通用 NUL 清洗（log_device 的 orderid/remarks/WorkingOrderCode/OperationUnitId 大量命中）。
验证：642 条带工单号的日志 100% 精确 join `jiangsu_ods.mtc_working_order.workingordercode`。

### 扫描发现的活跃未同步表（按价值分类，均未纳入，待排期决策）

**A. 监测数据层（= 2026-09-23 评估过的"数据获取率/有效率"缺口的成品原料，批次3候选）**

| 表 | 内容 | 窗口内行数 | 活跃度 |
|---|---|---|---|
| dat_station_day | 站点×日 聚合：so2/no2/pm10/co/o3/pm2_5 等 + 气象五参 + 每项 _mark 审核标记 | 157,401 | 每日更新(max 10-04) |
| dat_district_day / dat_city_day（+_ns 变体） | 区县/地市 日聚合 | 348k/168k | 每日更新 |
| dat_district_hour / dat_city_hour（+_ns） | 区县/地市 小时聚合（7.3M/3.2M 全量，需窗口） | — | 活跃 |
| aud_stationstate / aud_stationstatelog | 站点数据审核状态流转（待复核/已审核/待上传，operator 留痕） | 16,499 / — | 实时(分钟级) |
| aud_audit_hourinvaliddata / lastingdata / outlierdata / revisingdata / xgboostdata / aijudgeresult | 数据审核结论：无效/恒值/离群/修订/AI审核（每天 02:00 批量产生） | 640/76/1027/47/636/194 | 每日 |
| air_livedata | 实时分钟数据缓存表（~200站×14因子，滚动覆盖，全表仅 ~2,819 行） | 2,819 | 分钟级 |

注：air_livedata 是滚动覆盖型快照表（id 已自增到 1900 万但仅存最新），同步需整表快照方式；且设计上实时数据走平台 API，是否同步需用户拍板。

**B. 质控域**

| 表 | 内容 | 窗口内行数 | 备注 |
|---|---|---|---|
| qc_backorderarrangelog | 质控补测/回调安排日志 | 10,248 | 此前误判为 stale，实际仍在活跃写入(10-03) |
| bsd_supply | 质控耗材/备件台账（滤膜等，挂站点与工单号） | 767 | 活跃 |
| bsd_parts | 配件字典 | 29 | 小字典 |

**C. 设备/诊断域**

| 表 | 内容 | 备注 |
|---|---|---|
| bsd_moniter_parameter | 设备型号×监测参数阈值字典（上下限/预警限/单位，如加热杆温度、流量校准系数） | 428 行，对 station_fault_diagnosis 有直接价值 |
| DEV_SCRAP | 设备报废审批（SCRAPREASON，1 行） | 生命周期终点环节，随 log_device 场景可选 |
| mtc_StationhandoverDevices | 站点设备交接（0 行空表） | 排除 |

**D. 平台内部/按设计排除（确认维持排除）**

- VDO_*（CameraOnline 69M、DeviceOnline 18M、Alarm/AlarmEvent/AlarmCallbackSource ~65万、OfflineAnaysis）：视频域，实时状态走平台 API
- mot_log 1.3M / mot_performancelog 1.15M / mot_performance / mot_server：平台服务日志（mot_log 最后写入 09-20，疑似平台侧已迁移）
- task_calc* / task_scheduler / task_syncconfig / task_synclog / coveraqmsstationdataqueue / BSD_DirectNet_Log / OPA_log_allsys：平台计算引擎与调度内部表
- aud_dataauditlog 68万：审计流水大表，如需审核明细下钻再议（其结论已由 aud_audit_* 小表承载）

扫描误报说明：mtc_WorkingOrder/mtc_WorkingOrderDetail/opa_kqattendancemanagement/OPA_UserInfo 已在同步范围（配置键带下划线导致未匹配）。

### 运维事件：10-03 每日 dbt 构建静默漏跑（已处置）

- 现象：10-03 02:30 每日链里 FULLLIST 同步、对账、dq 都执行了，但 `dbt snapshot + build tag:daily` 段没有任何输出，5 张每日模型停留在 10-02 13:19（dbt 化后首次计划内每日运行即中招）；当时 dq 年龄 13.2h 未超 SLA 所以 fail=0，直到 10-04 才以 freshness FAIL 暴露。
- 处置：手动补跑 snapshot+build tag:daily（PASS=19/PASS=32，唯一 WARN 为已知 CAL 站点空码）；sync-daily.cmd 在两个 dbt 步骤后追加 `exit=%errorlevel%` 显式记录，失败时任务 LastTaskResult 非 0，当晚即可发现。
- 遗留观察：今晚 02:30 运行是否复现；若复现，查任务计划程序操作日志与 360 拦截记录（该机 360 有删除计划任务前科）。
- 附带发现：alm_rule 对账 MISMATCH(源 18/本地 19)——上游删规则不删行，daily_full upsert 无删除检测，属已知机制限制；如需精确可引入快照对比剔除（alm_rule 的 SCD2 快照已具备该能力）。
