// 站点日概况语义模型 — 口径唯一来源: sync/datasets/mart_station_daily_profile.yaml + dbt 模型
// 一行=站点×自然日(2026-07-01 起, 仅含有活动记录的站点日), 趋势/对比/异常日识别用。
// 工单计数仅故障单口径(来源 mart_work_order_analysis 已过滤 ordertype='Fault');
// 当日数据在次日刷新前不完整; attendance_signins 源数据稀疏。
cube(`StationDaily`, {
  sql: `select * from jiangsu_mart.mart_station_daily_profile`,

  measures: {
    count: { type: `count` },
    activeStations: { type: `countDistinct`, sql: `station_code` },
    createdSum: { type: `sum`, sql: `work_orders_created` },
    finishedSum: { type: `sum`, sql: `work_orders_finished` },
    overdueCreatedSum: { type: `sum`, sql: `overdue_orders_created` },
    alarmsSum: { type: `sum`, sql: `alarms` },
    signinsSum: { type: `sum`, sql: `attendance_signins` },
  },

  dimensions: {
    profileDate: { sql: `profile_date`, type: `time` },
    cityName: { sql: `city_name`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
  },
});
