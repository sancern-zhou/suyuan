// 省控站小时空气质量语义模型 — 一行 = 站点 × 小时（原始口径）
// 口径来源: DataCrawler.ShengkongStationHour（xuchang_shengkong_station_fetcher
// 抓取空气质量信息联网系统（许昌市空气质量管控平台）省控站，tstype=3&type=4 逐站查询，
// 仅保留最近 30 天）。
// 口径注意:
// - 平台省控站仅小时粒度（5 分钟各因子集实测均 0 行），为本表最优粒度;
// - 平台不发布 AQI/等级，AQI 与首要污染物需按 HJ633 由六参数推算，
//   结论须注明为推算值;
// - 8 站中襄城县政府/鄢陵县县政府自 2026-04 起通讯中断（疑撤并），
//   正常在线 6 站; 无 NO/NOX（平台省控因子集不返回，恒 null）;
// - 数值列用 NULLIF(x, -99) 排除平台无效值;
// - 数据窗口 2026-11-23 起滚动 30 天。
cube(`ShengkongHour`, {
  sql: `
    SELECT * FROM ShengkongStationHour WHERE IsAudit = 0
  `,

  measures: {
    count: { type: `count` },
    avgPm25: { type: `avg`, sql: `NULLIF(PM25, -99)` },
    avgPm10: { type: `avg`, sql: `NULLIF(PM10, -99)` },
    avgSo2: { type: `avg`, sql: `NULLIF(SO2, -99)` },
    avgNo2: { type: `avg`, sql: `NULLIF(NO2, -99)` },
    avgCo: { type: `avg`, sql: `NULLIF(CO, -99)` },
    avgO3: { type: `avg`, sql: `NULLIF(O3, -99)` },
    onlineSites: { type: `countDistinct`, sql: `Tsno` },
  },

  dimensions: {
    stationCode: { sql: `Tsno`, type: `string` },
    stationName: { sql: `StationName`, type: `string` },
    countyName: { sql: `CountyName`, type: `string` },
    dataTime: { sql: `CollectionTime`, type: `time` },
  },
});
