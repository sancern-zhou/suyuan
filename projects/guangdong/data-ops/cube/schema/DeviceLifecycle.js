// 设备生命周期语义模型 — 口径唯一来源: sync/datasets/mart_device_lifecycle_analysis.yaml + dbt 模型
// 范围: 设备状态/事件日志（一行 = 一条事件）。事件动作含 周检/月检/季检/半年检/年检/
// 启用/新增/停用/信息更新；变更后状态 DeviceNormal/DeviceSpare 等保留原文。
cube(`DeviceLifecycle`, {
  sql: `select * from guangdong_mart.mart_device_lifecycle_analysis`,

  measures: {
    count: { type: `count`, title: `生命周期事件数` },
    distinctDevices: {
      type: `countDistinct`,
      sql: `device_id`,
      title: `涉及设备数(去重)`,
    },
    checkEventCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.event_type in ('WeekCheck','MonthCheck','QuaryCheck','HYCheck','YearCheck')` }],
      title: `周期检查事件数(周/月/季/半年/年检)`,
    },
    lifecycleEventCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.event_type in ('DeviceStart','DeviceAdd','DeviceStop','DeviceUpdata')` }],
      title: `启用/新增/停用/更新事件数`,
    },
    stopEventCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.event_type = 'DeviceStop'` }],
      title: `停用事件数`,
    },
  },

  dimensions: {
    eventType: { sql: `event_type`, type: `string`, title: `事件动作(原文)` },
    eventTypeCn: { sql: `event_type_cn`, type: `string`, title: `事件动作(中文)` },
    stateAfter: { sql: `state_after`, type: `string`, title: `变更后状态(DeviceNormal/DeviceSpare等)` },
    cityName: { sql: `city_name`, type: `string`, title: `城市名` },
    stationCode: { sql: `station_code`, type: `string`, title: `站点编码` },
    stationName: { sql: `station_name`, type: `string`, title: `站点名` },
    deviceCode: { sql: `device_code`, type: `string`, title: `设备编码` },
    deviceType: { sql: `device_type`, type: `string`, title: `设备类型(源库代码原文)` },
    orderRef: { sql: `order_id`, type: `string`, title: `关联工单` },
    eventTime: { sql: `event_time`, type: `time`, title: `事件时间(时间维度)` },
  },
});
