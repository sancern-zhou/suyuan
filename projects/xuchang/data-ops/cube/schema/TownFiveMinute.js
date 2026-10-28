// 乡镇站 5 分钟空气质量语义模型 — 一行 = 站点 × 5 分钟（原始口径）
// 口径来源: DataCrawler.TownStationFiveMinute（xuchang_town_five_minute_fetcher
// 抓取空气质量信息联网系统（旧云平台）替代源，TownStationData 2026-10-21 起停更
// 后启用，仅保留最近 30 天）。
// 口径注意:
// - 该平台 5 分钟数据无审核流，IsAudit 恒为 0（原始/未审核口径），schema 直接过滤;
// - 平台 5 分钟不发布 AQI/等级（AQI/ChiefPollutant/PollutionLevel 恒空），
//   AQI 与首要污染物需按 HJ633 由六参数推算，结论须注明为推算值;
// - 数值列用 NULLIF(x, -99) 排除平台无效值（-99 不参与统计）;
// - 数据窗口 2026-10-27 起滚动 30 天；乡镇站小时/日历史仍以 TownHour/TownDay 为准。
cube(`TownFiveMinute`, {
  sql: `
    SELECT * FROM TownStationFiveMinute WHERE IsAudit = 0
  `,

  measures: {
    count: { type: `count` },
    avgPm25: { type: `avg`, sql: `NULLIF(PM25, -99)` },
    avgPm10: { type: `avg`, sql: `NULLIF(PM10, -99)` },
    avgSo2: { type: `avg`, sql: `NULLIF(SO2, -99)` },
    avgNo2: { type: `avg`, sql: `NULLIF(NO2, -99)` },
    avgCo: { type: `avg`, sql: `NULLIF(CO, -99)` },
    avgO3: { type: `avg`, sql: `NULLIF(O3, -99)` },
    maxAqi: { type: `max`, sql: `NULLIF(AQI, -99)` },
    onlineSites: { type: `countDistinct`, sql: `Tsno` },
  },

  dimensions: {
    stationCode: { sql: `Tsno`, type: `string` },
    stationName: { sql: `StationName`, type: `string` },
    countyName: { sql: `CountyName`, type: `string` },
    dataTime: { sql: `CollectionTime`, type: `time` },
  },
});
