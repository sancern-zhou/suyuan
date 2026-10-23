// 乡镇站日空气质量语义模型 — 一行 = 站点 × 自然日 × 口径（原始/审核）
// 口径来源: DataCrawler 视图 view_dat_town_day_src（原始，2024-08-01 起，2025 年起完整）/
// view_dat_town_day_app（审核，2024-09-01 起，2025 全年与 2026-01~10 已回补）。
// 口径注意:
// - caliber 维度必须二选一过滤（src=原始 / app=审核），否则重复计数；
//   官方结论优先 caliber='app'（审核口径）;
// - 数值列已用 NULLIF(x, -99) 排除平台无效值;
// - o3_8h 源数据无值，未建模;
// - 站点区县归属从 stationName 前缀解析（如"建安区小召乡"），或用
//   xuchang_station_catalog（action=lookup, station_type=township）解析。
cube(`TownDay`, {
  sql: `
    SELECT 'src' AS caliber, t.* FROM view_dat_town_day_src t
    UNION ALL
    SELECT 'app' AS caliber, t.* FROM view_dat_town_day_app t
  `,

  measures: {
    count: { type: `count` },
    avgPm25: { type: `avg`, sql: `NULLIF(pm2_5, -99)` },
    avgPm10: { type: `avg`, sql: `NULLIF(pm10, -99)` },
    avgSo2: { type: `avg`, sql: `NULLIF(so2, -99)` },
    avgNo2: { type: `avg`, sql: `NULLIF(no2, -99)` },
    avgCo: { type: `avg`, sql: `NULLIF(co, -99)` },
    avgO3: { type: `avg`, sql: `NULLIF(o3, -99)` },
    maxAqi: { type: `max`, sql: `NULLIF(aqi, -99)` },
    onlineSites: { type: `countDistinct`, sql: `code` },
  },

  dimensions: {
    caliber: { sql: `caliber`, type: `string` },
    stationCode: { sql: `code`, type: `string` },
    stationName: { sql: `name`, type: `string` },
    quality: { sql: `qualitytype`, type: `string` },
    primaryPollutant: { sql: `primarypollutant`, type: `string` },
    dataDate: { sql: `timepoint`, type: `time` },
  },
});
