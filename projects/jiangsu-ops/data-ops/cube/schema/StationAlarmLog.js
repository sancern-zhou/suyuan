// 站房/仪器告警语义模型 — 口径唯一来源: sync/datasets/mart_station_alarm_log.yaml + dbt 模型
cube(`StationAlarmLog`, {
  sql: `select * from jiangsu_mart.mart_station_alarm_log`,

  measures: {
    count: { type: `count`, title: `告警量` },
    severeCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.alarm_grade = 2` }],
      title: `严重告警量`,
    },
    urgentCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.alarm_grade = 3` }],
      title: `紧急告警量`,
    },
    unresolvedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.resume_time IS NULL` }],
      title: `未恢复告警量`,
    },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    alarmGrade: { sql: `alarm_grade_cn`, type: `string`, title: `告警级别` },
    alarmType: { sql: `alarm_type`, type: `number`, title: `告警类型编码` },
    subcatalog: { sql: `subcatalog`, type: `string`, title: `告警子类` },
    source: { sql: `source`, type: `string`, title: `告警来源` },
    alarmStatus: { sql: `alarm_status`, type: `string`, title: `告警状态(平台原值)` },
    description: { sql: `description`, type: `string` },
    alarmTime: { sql: `alarm_time`, type: `time` },
  },
});
