---
name: backup-quarterly-analysis
description: 江苏备机合规与使用季度分析。
---
# 备机季度分析

确定性计算必须通过 `execute_python` 调用 `app.services.jiangsu_operations_reports.build_backup_quarterly_report`。禁止由 Agent 临时重写 48 小时、30 天或站点频次规则；计算返回值直接写入 `report_data.json`。`execute_python` 在隔离沙箱运行，禁止读取相对路径或报告参考文档；脚本只做数据标准化、调用上述函数和输出 JSON。如计算脚本失败，记录错误并停止重试，不得重复生成不同脚本。

数据处理允许两类时间来源：设备更换/维修记录中的上架下架时间，或设备台账 `useDate/stopDate` 加上可识别的备机属性（`is_backup`、`backup_role`、`originalMachine`、`masterSlaveNum`）。报告按统一的备机业务口径正常输出结果；证据来源和身份字段保留在明细/方法数据中用于追溯，不作为报告主标题或主要结论。没有设备台账获取能力时不得声称完成备机分析，只能标注“生命周期数据待接入”。

仅对 `analyzable=true` 的记录计算故障后 48 小时启用、连续运行不超过 30 天和站点更换频次；`stopDate` 为空时按报告截止日计算，并明确标注仍在使用。缺少备机身份或启用时间时进入“无法判定”清单，不得生成合规结论。有效备案只豁免违规判定，不删除原始证据。

## 真实接口取数流程

上一季度必须拆成 3 个自然月分别调用故障工单接口，固定传 `order_types=["Fault"]`、`workflow_statuses=["Finish"]`、`order_statuses=["Finish"]`、`fetch_all=true`，再按工单号/唯一编码去重合并。不要直接用完整季度作为一个时间范围调用；实测该接口可能返回空清单而单月有数据。每个月记录 `total_count`、`returned_records`、`source_data_complete` 和错误信息。

合并故障站点后再调用设备台账接口获取 `useDate`、`stopDate` 和设备身份字段。若季度三个月均无工单，生成数据门禁报告，不输出“无超期/无违规”等结论。

## 正式报告结构

正式报告必须包含：执行摘要、季度取数概况（月度记录数及完整性）、故障站点基础分布、备机启用时效、连续运行超期、站点更换频次、无法判定记录、数据质量与下期动作。即使生命周期数据不足，也要保留真实故障基础统计和字段覆盖率；“无数据”与“无异常”不得混用。

只有三个月均无故障工单时才允许以数据门禁为主报告。存在故障工单但设备生命周期尚未关联时，应输出基础统计和“待关联”结果，不得生成 0 个超时/超期的业务结论。

报告数据中必须保存：每月接口元数据、去重规则、设备台账查询站点数、useDate/stopDate/备机身份字段覆盖率、可分析记录数、无法判定原因分布。严格执行 `create_report_package -> render_report_package(docx) -> validate_report_package(require_html=true, require_docx=true) -> publish_report`，校验失败不得发布。
