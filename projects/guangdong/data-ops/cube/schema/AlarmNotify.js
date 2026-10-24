// 告警通知语义模型 — 口径唯一来源: sync/datasets/mart_alarm_notify_analysis.yaml + dbt 模型
// 范围: 站点告警通知流水（一行 = 一条通知，含短信/邮件渠道）。
// 注意: 通知流水无处理闭环状态，"未处理率/处理时长"不可评估（勿与江苏 AlarmEvent 语义混淆）；
// 站点当前告警态势（正常/紧急）见 StationAlarmStatus cube。
cube(`AlarmNotify`, {
  sql: `select * from guangdong_mart.mart_alarm_notify_analysis`,

  measures: {
    count: { type: `count`, title: `告警通知量` },
    distinctStationCount: {
      type: `countDistinct`,
      sql: `station_id`,
      title: `涉及站点数(去重)`,
    },
    distinctDayCount: {
      type: `countDistinct`,
      sql: `notify_date`,
      title: `涉及天数(去重)`,
    },
  },

  dimensions: {
    alarmType: { sql: `alarm_type`, type: `string`, title: `告警类型(站点断数等,自CONTENT解析)` },
    cityName: { sql: `city_name`, type: `string`, title: `城市名(经alm_home补充,覆盖率以推送为准)` },
    stationTypeName: { sql: `station_type_name`, type: `string`, title: `站点类型中文名` },
    stationCode: { sql: `station_code`, type: `string`, title: `站点编码` },
    stationName: { sql: `station_name`, type: `string`, title: `站点名` },
    notifyChannels: { sql: `notify_channels`, type: `string`, title: `发送渠道(SMS,Mail等)` },
    notifyTime: { sql: `notify_time`, type: `time`, title: `告警时间(时间维度)` },
  },
});
