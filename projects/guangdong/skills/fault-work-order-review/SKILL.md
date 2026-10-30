---
name: 故障工单审核
description: 广东故障工单人工复核。按工单号、站点或时间窗口核对故障单的处置流程、响应与修复时效、附件与表单证据、告警与设备事件、站点监测佐证，输出接口事实、复核建议和尚需补充证据三类结论。
aliases:
  - 故障工单审核
  - 故障单复核
  - 工单审核闭环
required_tools:
  - read_file
  - write_file
  - guangdong_station_catalog
  - execute_guangdong_mart_sql
  - execute_ops_sql_query
  - query_gd_suncere_station_hour_new
  - query_gd_suncere_station_day_new
  - create_report_package
---

# 故障工单审核

## 适用范围

- 审核广东省站 `Fault`（主网故障单）与 `SupFault`（组分网故障单），按工单号、站点、时间窗口或状态筛选。
- 用于人工复核响应时效、处置过程、附件与表单完整性、故障原因与站点数据是否吻合，辅助人工确认归档。
- 本技能只做证据核对与复核建议，不执行工单流转、不创建或关闭工单。

## 取证顺序

1. **解析站点**：用户给的是站点名称或简称时，先用 `guangdong_station_catalog` 解析站点编码、城市、站点类型、运维单位和人员；不得把站点名当编码猜测关联。组分站无运维单位/人员的缺口如实声明。
2. **读取工单主记录**：`execute_guangdong_mart_sql` 查 `mart_work_order_analysis`，按 `working_order_code` 或站点+时间范围定位，取工单类型、状态、创建/完成时间、响应/处理/修复时长、故障根因、重复故障标记、附件计数、费用、设备编码和站点归属。
3. **核对流程链**：`working_order_details` 按工单号取全部流程步骤，核对步骤是否完整、开始与结束时间是否倒置、处理人、故障原因和处理描述。首个 `FaultProcess` 步骤开始时间为"到站"代理口径；工单已完成但流程缺处理步骤或缺少有效闭环说明时列为疑点。
4. **核对附件与表单**：`wo_commonfile_links` 按工单号统计附件数量与类型；需要看表单内容时按表单类型查对应表（`rf_w_*`、`sup_rf_common` 等，长尾表单用 ODS 兜底契约并先 `describe_table`）。附件完整率只覆盖附件索引，附件本体在源系统，不得据此断言照片内容。
5. **核对告警与设备事件**：同站点、同时间窗查 `mart_alarm_notify_analysis` 的告警类型与时间分布；查 `mart_device_lifecycle_analysis` 的启停、检定和更新事件；当前告警态势查 `mart_station_alarm_status`，只能表述为"推送范围内"。
6. **站点监测佐证**：需要核对断数、突变或恢复时间时，用 `query_gd_suncere_station_hour_new` 或 `query_gd_suncere_station_day_new` 取同站点、最小必要时间窗的小时/日数据。监测数据只作佐证，不与工单数据混算，不把时间吻合直接写成因果。
7. **实时状态核对**：工单当前流转状态或刚发生的变化用 `execute_ops_sql_query` 直查运维源库，结论以源库为准并说明数据截至时间；本地数据集为非实时同步层。

## 审核口径（硬约束）

- 工单历史窗口为今年，今年之前不可查；查询必须带 LIMIT 并只查白名单表。
- 故障单没有计划完成时间，超期不可评估；不得输出故障单超期率。
- 响应类指标仅故障单可评估，到站=首个故障处理步骤开始。
- 重复故障=同站同设备前 30 天存在其他故障单，仅故障单口径。
- 告警通知无处理闭环状态，不得推断"已处理/未处理"或处理时长。
- 工单文字中的"已处理""已恢复""未受影响"是待核验声明，不能替代流程记录、附件或监测证据。
- 附件计数只说明索引中存在附件，不能证明附件内容齐全或合规。

## 输出要求

结论必须区分三类，不得混写：

1. **接口/数据返回事实**：取到了什么、时间范围、缺失了什么；数值来自工具原值，不重算。
2. **人工复核建议**：哪些环节需要人工确认，依据是哪条记录或哪项证据；按风险优先级排序。
3. **尚需补充的证据**：缺哪些字段、附件、表单或时间窗，补齐后能判断什么。

补充要求：

- 证据落到工单号、站点名称、流程步骤、表单名称、附件记录和时间点，便于前端审核结果对照。
- 不认定违规、造假或责任归属；证据不足只报疑点。
- 不调用 `submit_task_review`：广东故障复核的人工确认通过报告交付和对话回复完成，聊天内不提交待办。
- 不调用江苏专用工具或事件证据包；所有取证限定广东数据集、源库和站点数据工具。

## 正式报告（用户要求时）

1. 先读 `backend/app/tools/report/report_package/references/index.md`。
2. 组织 `report.qmd`，正文只保留"审核范围"和"问题/疑点工单明细"两章，证据写入明细行。
3. 调用 `create_report_package`：`report_type='government'`，`output_formats=['html','docx','share_html']`。
4. 不调用 `render_report_package`、`validate_report_package` 或 `publish_report`；失败时如实说明，不宣称报告完成。
