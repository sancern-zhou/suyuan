// 质控任务状态语义模型 — 口径唯一来源: sync/datasets/mart_qc_task_status_result.yaml + dbt 模型
cube(`QcTaskStatus`, {
  sql: `select * from jiangsu_mart.mart_qc_task_status_result`,

  measures: {
    count: { type: `count`, title: `质控任务量(快照数)` },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    uniqueCode: { sql: `unique_code`, type: `string` },
    poll: { sql: `poll`, type: `string`, title: `监测项` },
    qcType: { sql: `qc_type`, type: `string`, title: `质控类型` },
    rStart: { sql: `rstart`, type: `time`, title: `任务开始时间` },
    sStart: { sql: `sstart`, type: `time`, title: `计划开始时间` },
    rid: { sql: `rid`, type: `string`, title: `任务标识 rId` },
  },
});
