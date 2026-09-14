---
name: 工单轨迹合理性分析
description: 江苏运维签到轨迹月度分析，生成正式报告并创建人工复核待办。
---
# 工单轨迹合理性分析 SOP
1. 统计上一个自然月，调用 `jiangsu_analyze_work_order_tracks`；不得自行替代工具计算。
2. 先核对工具结果 `metadata.pagination.complete`、`record_count`、`total_count` 和 `source_status`。接口失败、签到为空或分页未覆盖全量时，报告只能输出“数据不可用/待补数”及范围和接口信息，不得输出“无异常”或创建复核待办。数据完整后，速度超过250km/h，或不同站点间隔小于10分钟且距离超过1km，标记疑似线索。GPS距站点超过500米仅写报告，不生成待办。
3. 按 `backend/app/tools/report/report_package/references/index.md` 生成完整 QMD，调用 `create_report_package`，再调用 `render_report_package` 生成 HTML 和 DOCX，最后调用 `validate_report_package`；校验失败不得宣称报告完成。
4. 报告必须包含周期、覆盖量、按人员/单位统计、异常明细、计算参数、原始证据引用和数据质量说明；结论统一为疑似线索。
5. 仅对跨区域串单和多站点签到线索按人员聚合，每人每月调用一次 `submit_task_review`。`subject_id` 使用 `工单轨迹-{YYYY-MM}-{人员稳定标识}`，保证幂等。
6. 待办写明“需人工复核，不代表确认代签或造假”，包含异常时间线、工单和复核建议。无这两类线索时不创建待办。
7. 长期记忆只保存人工复核经验、误报模式和证据组合，不改变本 SOP 或自动升级结论。
