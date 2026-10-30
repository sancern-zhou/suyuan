---
name: 备机季度分析
description: 广东备机合规与使用季度分析。基于广东设备生命周期事件、故障工单与设备台账数据集，统计备机启用时效、连续运行超期和站点更换频次，生成面向运维统筹管理用户的正式报告。
aliases:
  - 备机季度分析
  - 备机使用分析
  - 备机超期分析
required_tools:
  - read_file
  - write_file
  - execute_python
  - create_report_package
  - call_sub_agent
  - run_agent_workflow
---

# 备机季度分析

## 适用范围

- 分析上一个完整自然季度（或用户指定季度）广东省站运维备机的投入、启用、使用和更换情况。
- 输出对象是运维统筹、合规监督和资源安排等管理用户，不输出取数过程和技术字段。
- 不适用：单台设备故障诊断、单张工单审核、站点监测数据质量分析。

## 数据来源与边界

只使用广东运维本地数据集，数据窗口为今年滚动窗口（年初至查询时点），窗口前历史不可查：

- 设备生命周期事件：`mart_device_lifecycle_analysis`，一行一条设备事件，字段含 `event_time`、`event_type_cn`（周检/月检/季检/半年检/年检/启用/新增/停用/信息更新）、`state_after`（`DeviceNormal`/`DeviceSpare` 等源系统枚举）、`device_code`、`station_code`、`station_name`、`city_name`、`device_type`、`order_id`。
- 故障工单：`mart_work_order_analysis`，一行一张工单，字段含 `working_order_code`、`order_type`、`order_status_cn`、`station_code`、`device_code`、`create_time`、`finish_time`、`first_alarm_reason`。
- 设备台账：`dim_device`（`device_code`、`device_type`、`device_brand`、`device_model`、`station_id`、`device_id_state`、`enable_time`）。
- 站点台账：`dim_station`（`station_code`、`station_name`、`city_name`、`operation_unit_name`）。

取数规则：

- 季度按自然季度切分，计算前先按月各查一次故障工单和生命周期事件，核对三个月是否均有数据；任一月为空必须在报告中声明覆盖缺口，不得直接写"无异常"。
- 故障单只取 `order_type in ('Fault','SupFault')` 且 `order_status_cn='已完成'`；工单量必须声明类型与作废口径。
- 设备事件按 `device_code` 与故障工单关联；同一设备存在多条启用/停用事件时按时间排序使用。
- 生命周期事件与站点/设备无法匹配的记录不得静默丢弃，单列"未关联记录"并说明数量。

## 备机识别口径

- 备机身份以设备状态枚举 `DeviceSpare` 为准：取 `dim_device.device_id_state` 或生命周期事件 `state_after`。
- 启用事件指 `event_type_cn in ('启用','新增')`；停用事件指 `event_type_cn='停用'`（状态枚举中的停用值以实际数据为准）。
- 广东数据集没有江苏的 `originalMachine`、`masterSlaveNum` 等备机备案字段，不得虚构备案合规结论；没有备机状态或启用时间的记录进入"无法判定"清单。

## 确定性计算规则

计算必须通过 `execute_python` 或委派 `gd_ops_regular_analysis` 节点完成，禁止心算或由模型改写规则：

1. **故障后 48 小时启用**：同一站点、同一设备类型，故障工单完成时间之后 48 小时内出现启用/新增事件，记为及时启用；超过 48 小时或季度内无启用事件记为未及时启用。
2. **连续运行不超过 30 天**：从启用事件到同一设备下一次停用事件（无停用则按季度截止日）计算连续运行天数；超过 30 天记为超期使用，并标注"截至季度末仍在使用"。
3. **站点更换频次**：同一站点在同一季度内的启用/新增事件数；按站点汇总并标记高频更换站点。
4. **无法判定**：缺少设备编码、备机身份或启用时间的记录单独统计原因分布，不参与合规结论。

计算输入、去重规则、可分析记录数、无法判定原因分布必须写入报告数据留存。

## 编排方式

在运维分析模式由 `operations_analysis` 父 Agent 加载：

- 设备生命周期与站点台账委派 `gd_ops_data_device`；故障工单委派 `gd_ops_data_workorder`；同一数据域一次取数，跨域数据各建节点。
- 计算与分析委派 `gd_ops_regular_analysis`，复用取数节点产物，传入季度范围、口径和阈值；父 Agent 只核对口径与整合结论。
- 简单问题可用 `call_sub_agent` 串行取数与计算；正式报告用 `run_agent_workflow` 编排。
- 节点预算沿用广东配置：并发 3、累计节点 12、总时长 1200 秒；不得另建工作流绕过预算。

## 报告结构

报告面向省站管理用户，通常包含：

- 执行摘要：季度备机投入规模、及时启用情况、超期使用与高频更换的重点结论。
- 总体保障：备机数量、涉及站点、启用与停用规模。
- 启用时效：故障后 48 小时启用比例、未及时启用清单及影响。
- 连续运行：超过 30 天使用清单、仍在使用设备。
- 区域与单位对比：按城市、运维单位对比保障能力与风险集中度。
- 季度趋势：与上一季度相比的总量和结构变化（仅在上季度数据可得时）。
- 管理建议：备机储备、调拨、维修协同和制度执行建议，区分事实、判断与待核查项。

正文只写业务事实、管理指标和建议，不出现表名、字段名、SQL、脚本、文件路径和工具名称。逐设备明细、判定参数和数据缺口放附录。

## 报告交付

1. 先读 `backend/app/tools/report/report_package/references/index.md`。
2. 组织完整 `report.qmd`，图表使用业务图表工具或 Python 生成静态图片并通过资源引用传入 `assets`。
3. 调用 `create_report_package`：`report_type='analysis'`，`output_formats=['html','docx','share_html']`，一次完成渲染。
4. 广东工具链没有独立的渲染、验收和发布工具，不调用 `render_report_package`、`validate_report_package` 或 `publish_report`；以报告包返回的产物和验收结果为准，失败时如实说明失败原因，不宣称报告已完成。
