// 告警语义模型 — 口径唯一来源: sync/datasets/mart_alarm_event_analysis.yaml + dbt 模型
cube(`AlarmEvent`, {
  sql: `select * from jiangsu_mart.mart_alarm_event_analysis`,

  measures: {
    count: { type: `count`, title: `告警量` },
    unresolvedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_unresolved` }],
    },
    unresolvedRate: {
      type: `number`,
      sql: `100.0 * ${unresolvedCount} / nullif(${count}, 0)`,
      title: `未处理率(%)`,
    },
    convertedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.linked_work_orders_24h > 0` }],
      title: `转化工单的告警数(24h内同站建单)`,
    },
    toWorkOrderRate: {
      type: `number`,
      sql: `100.0 * ${convertedCount} / nullif(${count}, 0)`,
      title: `告警转工单率(%,代理口径)`,
    },
    avgDurationMinutes: { type: `avg`, sql: `duration_minutes`, title: `平均告警持续(分钟,已解除)` },
    avgHandleMinutes: { type: `avg`, sql: `handle_minutes`, title: `平均处理时长(分钟,已处理)` },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    alarmLevel: { sql: `alarm_level_cn`, type: `string`, title: `告警级别` },
    alarmState: { sql: `alarm_state_cn`, type: `string`, title: `处理状态` },
    ruleType: { sql: `rule_type`, type: `string` },
    isUnresolved: { sql: `is_unresolved`, type: `boolean` },
    alarmTime: { sql: `alarm_time`, type: `time` },
  },
});
