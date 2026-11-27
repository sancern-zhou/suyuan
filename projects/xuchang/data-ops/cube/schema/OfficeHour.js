// 办事处站官方小时空气质量语义模型 — 一行 = 站点 × 小时（原始口径）
// 与 OfficeFiveMinute 共用物理表，必须以 IsHour 隔离粒度，禁止混合聚合。
// 平台办事处站仅 PM2.5/PM10；AQI 如使用须按 HJ633 推算并注明。
cube(`OfficeHour`, {
  sql: `
    SELECT * FROM OfficeStationFiveMinute WHERE IsAudit = 0 AND IsHour = 1
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
