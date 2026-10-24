// 站点告警态势语义模型 — 口径唯一来源: sync/datasets/mart_station_alarm_status.yaml + dbt 模型
// 范围: 站点当前告警态势快照（一行 = 一个站点，每日刷新，覆盖面以源系统推送为准，当日 63 站）。
// 快照语义：只回答"当前"，不回答历史；历史通知流水用 AlarmNotify。
cube(`StationAlarmStatus`, {
  sql: `select * from guangdong_mart.mart_station_alarm_status`,

  measures: {
    count: { type: `count`, title: `快照站点数` },
    alarmingCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_alarming` }],
      title: `当前告警站点数(状态≠正常)`,
    },
  },

  dimensions: {
    alarmStatus: { sql: `alarm_status`, type: `string`, title: `告警状态(正常/紧急)` },
    isAlarming: { sql: `is_alarming`, type: `boolean`, title: `是否告警中` },
    cityName: { sql: `city_name`, type: `string`, title: `城市名` },
    stationTypeName: { sql: `station_type_name`, type: `string`, title: `站点类型中文名` },
    stationCode: { sql: `station_code`, type: `string`, title: `站点编码` },
    stationName: { sql: `station_name`, type: `string`, title: `站点名` },
    managerName: { sql: `manager_name`, type: `string`, title: `运维管理人` },
    latestAlarmDesc: { sql: `latest_alarm_desc`, type: `string`, title: `最新告警描述` },
    latestAlarmTime: { sql: `latest_alarm_time`, type: `time`, title: `最新告警时间(时间维度)` },
  },
});
