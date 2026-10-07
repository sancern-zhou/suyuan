// 质控任务安排语义模型 — 口径唯一来源: sync/datasets/mart_qc_arrangement_analysis.yaml + dbt 模型
// 一行=一条安排的质控任务。status_cn 为平台状态文本(已过期/等待中/运行中/任务已删除);
// 质控执行结果(合格判定)走 QcExecution cube, 本模型只回答"任务安排与过期积压"。
cube(`QcArrangement`, {
  sql: `select * from jiangsu_mart.mart_qc_arrangement_analysis`,

  measures: {
    count: { type: `count` },
    expiredCount: { type: `count`, filters: [{ sql: `${CUBE}.status_cn = '已过期'` }] },
    waitingCount: { type: `count`, filters: [{ sql: `${CUBE}.status_cn = '等待中'` }] },
    runningCount: { type: `count`, filters: [{ sql: `${CUBE}.status_cn = '运行中'` }] },
    deletedCount: { type: `count`, filters: [{ sql: `${CUBE}.status_cn = '任务已删除'` }] },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    cityCode: { sql: `city_code`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    pollutant: { sql: `pollutant`, type: `string` },
    taskType: { sql: `task_type`, type: `string` },
    statusCn: { sql: `status_cn`, type: `string` },
    plannedTime: { sql: `planned_time`, type: `time` },
  },
});
