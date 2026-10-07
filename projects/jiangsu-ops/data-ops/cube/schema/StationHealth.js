// 站点健康语义模型 — 口径唯一来源: sync/datasets/mart_station_device_health.yaml + dbt 模型
// 一行=一个站点(当前态势快照, 全省含无事件站点)。
// 工单侧统计仅故障单口径(宽表来源 mart_work_order_analysis 已过滤 ordertype='Fault');
// risk_level 为代理规则(高/中/低/稳定), 阈值待业务确认后可调整。
cube(`StationHealth`, {
  sql: `select * from jiangsu_mart.mart_station_device_health`,

  measures: {
    count: { type: `count` },
    highRiskCount: { type: `count`, filters: [{ sql: `${CUBE}.risk_level = '高'` }] },
    midRiskCount: { type: `count`, filters: [{ sql: `${CUBE}.risk_level = '中'` }] },
    totalOrders30d: { type: `sum`, sql: `work_orders_30d` },
    totalOverdue30d: { type: `sum`, sql: `overdue_orders_30d` },
    totalRepeatFault30d: { type: `sum`, sql: `repeat_fault_orders_30d` },
    avgOverdueRate30d: { type: `avg`, sql: `100.0 * overdue_rate_30d` },
    avgResponseMinutes30d: { type: `avg`, sql: `avg_response_minutes_30d` },
    totalAlarms7d: { type: `sum`, sql: `alarms_7d` },
    totalAlarms30d: { type: `sum`, sql: `alarms_30d` },
    totalUnresolvedAlarms: { type: `sum`, sql: `unresolved_alarms` },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    riskLevel: { sql: `risk_level`, type: `string` },
    stationStatus: { sql: `station_status`, type: `string` },
    isMonitor: { sql: `is_monitor`, type: `boolean` },
    lastAlarmTime: { sql: `last_alarm_time`, type: `time` },
  },
});
