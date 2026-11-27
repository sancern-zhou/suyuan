// 办事处站 5 分钟空气质量语义模型 — 一行 = 站点 × 5 分钟（原始口径）
// 口径来源: DataCrawler.OfficeStationFiveMinute（xuchang_office_five_minute_fetcher
// 抓取空气质量信息联网系统（许昌市空气质量管控平台）办事处站，tstype=9&type=5 逐站查询，
// 仅保留最近 30 天）。
// 口径注意:
// - 平台办事处站仅 PM2.5/PM10 两因子（SO2/NO2/CO/O3 恒 null，schema 不建这些成员）;
// - 平台不发布 AQI/等级，AQI 与首要污染物需按 HJ633 由 PM2.5/PM10 两因子推算，
//   结论须注明为推算值;
// - 数值列用 NULLIF(x, -99) 排除平台无效值;
// - 数据窗口 2026-11-23 起滚动 30 天。
cube(`OfficeFiveMinute`, {
  sql: `
    SELECT * FROM OfficeStationFiveMinute WHERE IsAudit = 0
  `,

  measures: {
    count: { type: `count` },
    avgPm25: { type: `avg`, sql: `NULLIF(PM25, -99)` },
    avgPm10: { type: `avg`, sql: `NULLIF(PM10, -99)` },
    onlineSites: { type: `countDistinct`, sql: `Tsno` },
  },

  dimensions: {
    stationCode: { sql: `Tsno`, type: `string` },
    stationName: { sql: `StationName`, type: `string` },
    countyName: { sql: `CountyName`, type: `string` },
    dataTime: { sql: `CollectionTime`, type: `time` },
  },
});
