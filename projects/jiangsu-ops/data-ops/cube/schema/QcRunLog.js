// 质控运行日志语义模型 — 口径唯一来源: sync/datasets/mart_qc_run_log_result.yaml + dbt 模型
cube(`QcRunLog`, {
  sql: `select * from jiangsu_mart.mart_qc_run_log_result`,

  measures: {
    count: { type: `count`, title: `运行日志条数` },
    errorCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.str_event = '错误'` }],
      title: `错误事件数`,
    },
    warnCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.str_event = '警告'` }],
      title: `警告事件数`,
    },
  },

  dimensions: {
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    rid: { sql: `rid`, type: `string`, title: `任务标识 rId` },
    poll: { sql: `poll`, type: `string`, title: `监测项` },
    qcType: { sql: `qc_type`, type: `string`, title: `质控类型` },
    eventType: { sql: `event_type`, type: `number`, title: `事件类型编码` },
    strEvent: { sql: `str_event`, type: `string`, title: `事件分类` },
    target: { sql: `target`, type: `string`, title: `执行环节` },
    userName: { sql: `user_name`, type: `string`, title: `操作用户` },
    recordTime: { sql: `record_time`, type: `time`, title: `事件时间` },
  },
});
