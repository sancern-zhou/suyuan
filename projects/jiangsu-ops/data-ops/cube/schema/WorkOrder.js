// 工单语义模型 — 口径唯一来源: sync/datasets/mart_work_order_analysis.yaml + dbt 模型
// 范围: 仅故障工单(dbt 过滤 ordertype='Fault', 2026-10-06 收敛); 例行单(巡检/校准等)不入本表,
// 巡检任务项走 Inspection cube。工单量/超期率等结论均只代表故障单口径。
// 注意两个"可评估分母"口径: 2h响应率仅对有到场节点单(约14%), 4h恢复率仅对有已解除
// 关联告警单(约27%)。rate 类指标返回百分数(0-100)。
cube(`WorkOrder`, {
  sql: `select * from jiangsu_mart.mart_work_order_analysis`,

  measures: {
    count: { type: `count` },
    overdueCount: { type: `count`, filters: [{ sql: `${CUBE}.is_overdue` }] },
    overdueRate: {
      type: `number`,
      sql: `100.0 * ${overdueCount} / nullif(${count}, 0)`,
      title: `超期率(%)`,
    },
    responseEvaluable: {
      type: `count`,
      filters: [{ sql: `${CUBE}.arrival_time is not null` }],
      title: `可评估响应的工单数`,
    },
    responseWithin2hCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_response_within_2h` }],
    },
    responseWithin2hRate: {
      type: `number`,
      sql: `100.0 * ${responseWithin2hCount} / nullif(${responseEvaluable}, 0)`,
      title: `2小时响应率(%,仅可评估单)`,
    },
    recoverEvaluable: {
      type: `count`,
      filters: [{ sql: `${CUBE}.recovery_time is not null` }],
      title: `可评估恢复的工单数`,
    },
    recoverWithin4hCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_recover_within_4h` }],
    },
    recoverWithin4hRate: {
      type: `number`,
      sql: `100.0 * ${recoverWithin4hCount} / nullif(${recoverEvaluable}, 0)`,
      title: `4小时恢复率(%,仅可评估单)`,
    },
    repeatFaultCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_repeat_fault` }],
    },
    repeatFaultRate: {
      type: `number`,
      sql: `100.0 * ${repeatFaultCount} / nullif(${count}, 0)`,
      title: `30天重复故障率(%)`,
    },
    avgResponseMinutes: { type: `avg`, sql: `response_minutes`, title: `平均响应时长(分钟)` },
    avgProcessMinutes: { type: `avg`, sql: `process_minutes`, title: `平均处理时长(分钟)` },
    avgRepairMinutes: { type: `avg`, sql: `repair_minutes`, title: `平均修复时长(分钟)` },
    avgLinkedAlarms1d: { type: `avg`, sql: `alarm_count_1d`, title: `平均关联告警数(前24h)` },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    cityCode: { sql: `city_code`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    orderStatus: { sql: `order_status_cn`, type: `string` },
    urgency: { sql: `urgency_type`, type: `string` },
    orderType: { sql: `order_type`, type: `string` },
    isOverdue: { sql: `is_overdue`, type: `boolean` },
    isRepeatFault: { sql: `is_repeat_fault`, type: `boolean` },
    repeatBasis: { sql: `repeat_fault_basis`, type: `string` },
    createTime: { sql: `create_time`, type: `time` },
    finishTime: { sql: `finish_time`, type: `time` },
  },
});
