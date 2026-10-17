// 站房动环语义模型 — 口径唯一来源: sync/datasets/mart_station_env_power.yaml + dbt 模型
cube(`StationEnvPower`, {
  sql: `select * from jiangsu_mart.mart_station_env_power`,

  measures: {
    count: { type: `count`, title: `动环数据点数` },
    avgValue: { type: `avg`, sql: `monvalue`, title: `平均动环值(数值点)` },
    maxValue: { type: `number`, sql: `max(monvalue)`, title: `最大动环值` },
    minValue: { type: `number`, sql: `min(monvalue)`, title: `最小动环值` },
  },

  dimensions: {
    cityName: { sql: `city_name`, type: `string` },
    stationCode: { sql: `station_code`, type: `string` },
    stationName: { sql: `station_name`, type: `string` },
    pollutantCode: { sql: `pollutant_code`, type: `string`, title: `动环指标编码` },
    timePoint: { sql: `timepoint`, type: `time`, title: `数据时间点` },
    mark: { sql: `mark`, type: `string`, title: `平台原始标记` },
  },
});
