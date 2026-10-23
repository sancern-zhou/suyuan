// 乡镇站小时空气质量语义模型 — 一行 = 站点 × 小时 × 口径（原始/审核）
// 口径来源: DataCrawler 视图 view_dat_town_hour_src（原始）/ view_dat_town_hour_app（审核）
// （中台同构视图，2025-2026 乡镇数据已回补完整）。
// 口径注意:
// - caliber 维度必须二选一过滤（src=原始 / app=审核），否则同站同时刻
//   原始与审核两条记录重复计数；官方结论优先 caliber='app'（审核口径）;
// - 数值列已用 NULLIF(x, -99) 排除平台无效值（-99 不参与统计）;
// - o3_8h 源数据无值（恒 -99），未建模;
// - 数据范围 2024-01-01 起（审核口径 2024-08-26 起），更新至实时。
cube(`TownHour`, {
  sql: `
    SELECT 'src' AS caliber, t.* FROM view_dat_town_hour_src t
    UNION ALL
    SELECT 'app' AS caliber, t.* FROM view_dat_town_hour_app t
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
    dataTime: { sql: `timepoint`, type: `time` },
  },
});
