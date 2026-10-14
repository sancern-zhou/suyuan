// 质控执行语义模型 — 口径唯一来源: sync/datasets/mart_qc_execution_analysis.yaml + dbt 模型
// 合格判定直接采用平台 qcresult 文本前缀, 不重算;
// 覆盖范围=站点名录启用的省控站(2026-10-14 时点101个, 不含超站7099A与40开头试点站)。
// is_qualified 可空(任务失败/终止/校准类未判定), 合格率分母=已判定数(合格+不合格)。
cube(`QcExecution`, {
  sql: `select * from jiangsu_mart.mart_qc_execution_analysis`,

  measures: {
    count: { type: `count`, title: `质控执行量` },
    assessedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_qualified is not null` }],
      title: `已判定数(合格+不合格)`,
    },
    qualifiedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_qualified` }],
    },
    qualifiedRate: {
      type: `number`,
      sql: `100.0 * ${qualifiedCount} / nullif(${assessedCount}, 0)`,
      title: `质控合格率(%)`,
    },
    avgInaccuracy: { type: `avg`, sql: `inaccuracy`, title: `平均不准确度` },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    pollutant: { sql: `pollutant`, type: `string` },
    taskType: { sql: `task_type`, type: `string`, title: `任务类型(零点/跨度/O3/校准类)` },
    resultCn: { sql: `result_cn`, type: `string` },
    isQualified: { sql: `is_qualified`, type: `boolean` },
    qcDate: { sql: `qc_date`, type: `time` },
  },
});
