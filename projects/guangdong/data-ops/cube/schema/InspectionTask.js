// 巡检计划任务项语义模型 — 口径唯一来源: sync/datasets/mart_inspection_task_analysis.yaml + dbt 模型
// 范围: 运维计划任务项（一行 = 一个任务项，PW_TASKITEM+PW_TASK 宽表化）。
// 完成 = FINISHDATETIME 非空或 STATE=1；超期 = 未完成且过计划结束日(EDTDATE)；
// 转工单 = FINISHWORKORDERCODE 非空。率类指标返回百分数(0-100)。
cube(`InspectionTask`, {
  sql: `select * from guangdong_mart.mart_inspection_task_analysis`,

  measures: {
    count: { type: `count`, title: `任务项数` },
    finishedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_finished` }],
    },
    finishedRate: {
      type: `number`,
      sql: `100.0 * ${finishedCount} / nullif(${count}, 0)`,
      title: `完成率(%)`,
    },
    overdueCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_overdue` }],
    },
    overdueRate: {
      type: `number`,
      sql: `100.0 * ${overdueCount} / nullif(${count}, 0)`,
      title: `超期率(%,分母=全部任务项)`,
    },
    toOrderCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_to_order` }],
    },
    toOrderRate: {
      type: `number`,
      sql: `100.0 * ${toOrderCount} / nullif(${count}, 0)`,
      title: `转工单率(%,分母=全部任务项)`,
    },
    distinctStations: {
      type: `countDistinct`,
      sql: `station_id`,
      title: `涉及站点数(去重)`,
    },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string`, title: `城市名` },
    stationCode: { sql: `station_code`, type: `string`, title: `站点编码` },
    stationName: { sql: `station_name`, type: `string`, title: `站点名` },
    ruleName: { sql: `rule_name`, type: `string`, title: `规则名` },
    ruleType: { sql: `rule_type`, type: `string`, title: `规则类型` },
    ruleCycle: { sql: `rule_cycle`, type: `string`, title: `周期(周/月/季等)` },
    itemFormTag: { sql: `item_form_tag`, type: `string`, title: `表单类型(RF_W_GaseousCheck等)` },
    pollutantType: { sql: `pollutant_type`, type: `string`, title: `监测项目(SO2/NOX/O3等)` },
    isFinished: { sql: `is_finished`, type: `boolean`, title: `是否已完成` },
    isOverdue: { sql: `is_overdue`, type: `boolean`, title: `是否已超期(未完成且过计划结束日)` },
    isToOrder: { sql: `is_to_order`, type: `boolean`, title: `是否已转工单` },
    planDate: { sql: `plan_date`, type: `time`, title: `计划日期(时间维度)` },
    finishDatetime: { sql: `finish_datetime`, type: `time`, title: `完成时间(时间维度)` },
  },
});
