// 巡检语义模型 — 口径唯一来源: sync/datasets/mart_inspection_analysis.yaml + dbt 模型
// status_cn 按数据分布推断(0=未开始/1=处理中/2=已完成, 待业务确认)。
cube(`Inspection`, {
  sql: `select * from jiangsu_mart.mart_inspection_analysis`,

  measures: {
    count: { type: `count`, title: `巡检任务项数` },
    finishedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_finished` }],
    },
    finishedRate: {
      type: `number`,
      sql: `100.0 * ${finishedCount} / nullif(${count}, 0)`,
      title: `巡检完成率(%)`,
    },
    overdueCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_overdue` }],
    },
    overdueRate: {
      type: `number`,
      sql: `100.0 * ${overdueCount} / nullif(${count}, 0)`,
      title: `巡检超期率(%)`,
    },
    linkedOrderCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.has_linked_order` }],
    },
    toWorkOrderRate: {
      type: `number`,
      sql: `100.0 * ${linkedOrderCount} / nullif(${count}, 0)`,
      title: `巡检转工单率(%)`,
    },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    ruleType: { sql: `rule_type_cn`, type: `string`, title: `周期类型` },
    statusCn: { sql: `status_cn`, type: `string` },
    isFinished: { sql: `is_finished`, type: `boolean` },
    isOverdue: { sql: `is_overdue`, type: `boolean` },
    taskDate: { sql: `task_date`, type: `time` },
  },
});
