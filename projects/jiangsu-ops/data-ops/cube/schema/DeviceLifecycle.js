// 设备生命周期语义模型 — 口径唯一来源: sync/datasets/mart_device_lifecycle_analysis.yaml + dbt 模型
// 一行=一条生命周期事件(event_id: log_*/scrap_*)。来源: log_device 状态变更日志 + dev_scrap 报废审批。
// station_code 为事件站点优先、回退台账归属站; working_order_code 可关联故障工单。
cube(`DeviceLifecycle`, {
  sql: `select * from jiangsu_mart.mart_device_lifecycle_analysis`,

  measures: {
    count: { type: `count` },
    distinctDevices: { type: `countDistinct`, sql: `device_id` },
    startEvents: { type: `count`, filters: [{ sql: `${CUBE}.event_type = 'DeviceStart'` }] },
    repairEvents: { type: `count`, filters: [{ sql: `${CUBE}.event_type = 'DeviceRepair'` }] },
    stopEvents: { type: `count`, filters: [{ sql: `${CUBE}.event_type = 'DeviceStop'` }] },
    scrapEvents: { type: `count`, filters: [{ sql: `${CUBE}.event_source = 'dev_scrap'` }] },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    cityCode: { sql: `city_code`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    deviceCode: { sql: `device_code`, type: `string` },
    deviceTypeName: { sql: `device_type_name`, type: `string` },
    eventType: { sql: `event_type`, type: `string` },
    stateAfter: { sql: `state_after`, type: `string` },
    eventSource: { sql: `event_source`, type: `string` },
    eventTime: { sql: `event_time`, type: `time` },
  },
});
