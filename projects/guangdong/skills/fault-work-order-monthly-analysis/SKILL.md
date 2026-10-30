---
name: 故障工单月度分析
description: 广东故障工单月度综合分析与报告生成。基于广东工单分析宽表与流程明细，统计故障结构、响应与修复时效、重复故障、高频站点和单位对比，生成面向运维管理用户的正式报告。
aliases:
  - 故障工单月度分析
  - 故障工单月报
  - 站点故障频发分析
required_tools:
  - read_file
  - write_file
  - execute_python
  - create_report_package
  - call_sub_agent
  - run_agent_workflow
---

# 故障工单月度分析

## 适用范围

- 统计上一个完整自然月（或用户指定月份）广东省站故障工单，输出月度分析正式报告。
- 故障口径为 `Fault`（主网故障单）与 `SupFault`（组分网故障单），不含例行工单。
- 输出对象是省站运维统筹、考核和资源安排等管理用户。

## 数据来源与口径

- 主表 `mart_work_order_analysis`：`working_order_code`、`order_type`、`order_status_cn`、`station_code`、`station_name`、`city_name`、`device_code`、`device_type`、`create_time`、`finish_time`、`response_minutes`、`process_minutes`、`repair_minutes`、`first_alarm_reason`、`is_repeat_fault`、`repeat_count_30d`、`attachment_count`、`has_attachment`、`total_expense`。
- 流程明细 `working_order_details`：按工单号取 `process_step`、`process_start_time`、`process_end_time`、`alarm_reason`、`submit_remark`、`description_ta`。
- 附件索引 `wo_commonfile_links`：按工单号统计附件数量与类型。
- 站点台账 `dim_station`：按 `station_code` 关联 `operation_unit_name`、`city_name`、`station_type_name`。
- 设备台账 `dim_device`：按 `device_code` 关联品牌、型号。

口径红线：

- 工单量按 `order_type in ('Fault','SupFault')` 且 `order_status_cn='已完成'` 统计；必须声明统计月份、类型、状态和是否含作废单。
- 故障单没有计划完成时间，超期不可评估，报告不得出现故障单超期率。
- 响应时长仅故障单可评估（到站=首个故障处理步骤开始）；处理、修复时长按宽表原值，不重算。
- 重复故障=同站同设备前 30 天存在其他故障单，仅故障单口径。
- 工单数据为今年窗口同步层，非实时；数据截至时间必须写入报告。

## 执行顺序

1. **取数**：委派 `gd_ops_data_workorder` 按月份取故障工单宽表、流程明细和附件索引；站点归属委派 `gd_ops_data_station` 或直接使用 `dim_station`。同一域一次取数，不按城市或日期机械拆分。
2. **字段质量检查**：分别统计站点、城市、运维单位、设备编码、工单号、创建时间、完成时间缺失数量；没有创建/完成时间的记录不参与时效统计。
3. **故障类别统一**：优先使用 `first_alarm_reason`；为空时用流程明细的 `alarm_reason`；仍为空时按稳定关键词映射为站点断数、仪器断数、浓度超量程、供电/通信、其他，并保留原始原因。未命中标题进入"其他/待归类"。
4. **确定性统计**：总体、站点、城市、运维单位、设备维度分别计算数量、占比、站均故障量、平均/中位响应与修复时长、长尾工单数、设备品牌型号分布。计算由 `gd_ops_regular_analysis` 或 `execute_python` 完成。
5. **连续事件剔除**：同站点、同类别（停电/断数/通信/离线）事件连续间隔不超过 24 小时且至少 3 条时，从总体统计、时效均值和单位排名剔除；必须单列站点、时间范围、数量、工单号和剔除前后指标。未命中时只能写"本期未识别满足规则的连续簇"，不能写"没有重复故障"。
6. **重点工单复核**：对 TOP15 站点和长尾单位按工单号读取流程明细、附件索引和相关表单，核对响应、到场、维修、闭环节点；不能仅凭列表字段推断维修质量。
7. **报告成稿**：按下方结构组织，先固定数据截至时间与全部口径声明。
8. **交付**：调用 `create_report_package` 生成报告包。

## 报告结构与管理信息

报告按"结论先行—证据支撑—行动闭环"组织，执行摘要必须给出：

- 本期故障工单总量、涉及站点、平均/中位处理时长，以及与上月相比的方向和幅度，并声明数据完整性。
- 不超过 5 条核心发现，每条含影响范围、变化幅度和管理含义。
- 需省站优先关注的风险清单（高频重复、影响范围、长时间未闭环、维修后缺少性能验证），标注站点、城市、运维单位、工单数和证据状态。
- 需决策或督办的事项，含建议责任对象、完成时限和验收证据。

正文通常包含：全省态势、风险优先级、区域与单位对比、趋势与变化解释、闭环质量、结论与管理建议。数量变化同时给出占比、基数和环比；样本量过小时标注"样本有限"；突增突降按"已证实事实、待核查原因、所需补证"表述。

## 表达与边界

- 正文只写业务事实、指标、问题清单和管理建议；接口原文、工单号、字段缺失明细、剔除边界放附录。
- 不认定违规、造假或责任归属；结论与建议分开，事实不足写"待核查"。
- 建议形成"问题/对象—建议动作—责任对象—时限—验收证据—下月跟踪指标"表。
- 报告数据中保存：取数范围、字段缺失统计、原始工单数量、纳入/剔除数量、规则参数、重点清单和报告版本。

## 报告交付

1. 先读 `backend/app/tools/report/report_package/references/index.md`。
2. 组织完整 `report.qmd`，图表由分析节点生成静态图片后作为 `assets` 传入。
3. 调用 `create_report_package`：`report_type='analysis'`，`output_formats=['html','docx','share_html']`。
4. 广东工具链没有独立渲染、验收和发布工具，不调用 `render_report_package`、`validate_report_package` 或 `publish_report`；失败时生成数据门禁说明或如实报告失败原因，不输出"无异常"。
