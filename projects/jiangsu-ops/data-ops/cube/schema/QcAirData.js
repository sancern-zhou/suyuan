// 质控监测曲线语义模型 — 口径唯一来源: sync/datasets/mart_qc_air_data_result.yaml + dbt 模型
cube(`QcAirData`, {
  sql: `select * from jiangsu_mart.mart_qc_air_data_result`,

  measures: {
    count: { type: `count`, title: `曲线点数` },
    avgDataValue: {
      type: `avg`,
      sql: `nullif(datavalue, '')::double precision`,
      title: `平均监测值(数值点)`,
    },
    maxDataValue: {
      type: `number`,
      sql: `max(nullif(datavalue, '')::double precision)`,
      title: `最大监测值`,
    },
    minDataValue: {
      type: `number`,
      sql: `min(nullif(datavalue, '')::double precision)`,
      title: `最小监测值`,
    },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    poll: { sql: `poll`, type: `string`, title: `监测项` },
    qcType: { sql: `qc_type`, type: `string`, title: `质控类型` },
    timePoint: { sql: `timepoint`, type: `time`, title: `监测时间点` },
    unit: { sql: `unit`, type: `string`, title: `单位` },
    isQCing: { sql: `isqcing`, type: `boolean`, title: `质控进行中` },
    dataMark: { sql: `datamark`, type: `string`, title: `数据标记` },
  },
});
