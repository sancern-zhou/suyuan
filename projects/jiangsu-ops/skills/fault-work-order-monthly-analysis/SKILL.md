---
name: fault-work-order-monthly-analysis
description: 江苏故障工单月度综合分析与报告生成。
---
# 故障工单月度分析

确定性计算必须通过 `execute_python` 调用 `app.services.jiangsu_operations_reports.build_fault_monthly_report`。禁止由 Agent 临时重写聚合、异常剔除或时长统计规则；计算返回值直接写入 `report_data.json`。`execute_python` 在隔离沙箱运行，禁止读取相对路径或报告参考文档；不要在脚本中读取 `backend/app/tools/report/report_package/references/index.md`。脚本只做数据标准化、调用上述函数和输出 JSON；如计算脚本失败，记录错误并停止重试，不得重复生成不同脚本。

## 执行顺序

1. 使用江苏部署环境文件（`backend/.env.jiangsu-ops`）调用 `jiangsu_fetch_fault_work_orders`，查询上一个自然月 `Fault + Finish` 工单；必须使用 `fetch_all=true`，记录接口、请求范围、`total_count`、`returned_records` 和 `source_data_complete`。
2. 先做字段质量检查：站点、城市、运维单位、设备编号、工单标题、创建时间、完成时间、工单号缺失分别计数；没有创建/完成时间的记录不得参与时效统计。
3. 统一故障类别：优先使用平台故障类型字典；当前接口只有标题时，按稳定关键词映射为站点断数、仪器断数、浓度超量程、供电/通信、其他，并保留原始标题。未命中的标题进入“其他/待归类”，不得强行归类。
4. 计算总体、站点、城市、运维单位和设备维度：数量、占比、站均故障量、平均/中位处理时长、长尾工单数、设备品牌/型号分布。
5. 异常剔除：同站点、同类断电/停电/断数/通信/离线事件，连续间隔不超过 24 小时且至少 3 条，从总体统计、时效均值和单位排名剔除；必须单列站点、时间范围、数量、工单号和剔除前后指标。若未命中，只能写“本期未识别满足规则的连续簇”，不能写“没有重复故障”。
6. 对 TOP15 站点和高长尾单位调用工单详情，核对响应、到场、维修、闭环节点和 RF/性能检查附件；不能仅凭列表字段推断维修质量。
7. 生成正式报告，至少包含：统计口径、数据质量、故障结构、高频站点、重复故障专项、处理时效、单位/城市对比、设备维修轨迹、RF 覆盖、同比（上月数据可得时）、结论和建议。
8. 严格按 `create_report_package -> render_report_package(docx) -> validate_report_package(require_html=true, require_docx=true) -> publish_report` 收口。校验失败不得发布；接口失败、数据不完整或关键字段缺失时生成数据门禁说明，不得输出“无异常”。

## 输出和案例要求

- 报告结论只写事实、统计异常和待核查线索，不直接认定违规、造假或责任归属。
- `report_data.json` 必须保存源接口元数据、字段缺失统计、原始工单数量、纳入数量、剔除数量、规则参数、重点清单和报告版本。
- 任务执行结束后写入一条任务案例，记录周期、接口总量、数据完整性、剔除结果、报告 ID、失败/修复点和下一期检查项；案例用于下一次执行的质量复盘，不替代本期数据。
