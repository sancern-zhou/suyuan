// 全省站点小时/日单项浓度排名语义模型 — 一行 = 站点 × 小时（或自然日）
// 口径来源: DataCrawler.SsfbSiteHour / SsfbSiteDay 经 MySQL 8 窗口函数现算排名
//（实时，无采集依赖）。站点全集为平台实际发布数据的省控站（约 241 个，
//  市控站挂树无数据）；排名规则与城市/区县一致：数值越低越靠前（升序），
//  相同值并列（RANK：1,2,2,4），NULL 不参与排名。
// 注意：站点排名口径为本系统统一规则，平台前端无站点排名页。
cube(`SsfbSiteHourRank`, {
  sql: `
    SELECT
      DataTime,
      SiteID,
      SiteName,
      City,
      County,
      Quality,
      MainPollutant,
      AQI AS aqi_val,
      PM25 AS pm25_val,
      PM10 AS pm10_val,
      O3_8H AS o3_8h_val,
      NO2 AS no2_val,
      SO2 AS so2_val,
      CO AS co_val,
      CASE WHEN AQI IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY AQI ASC) END AS rank_aqi,
      CASE WHEN PM25 IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY PM25 ASC) END AS rank_pm25,
      CASE WHEN PM10 IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY PM10 ASC) END AS rank_pm10,
      CASE WHEN O3_8H IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY O3_8H ASC) END AS rank_o3,
      CASE WHEN NO2 IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY NO2 ASC) END AS rank_no2,
      CASE WHEN SO2 IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY SO2 ASC) END AS rank_so2,
      CASE WHEN CO IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY CO ASC) END AS rank_co,
      COUNT(*) OVER (PARTITION BY DataTime) AS site_count
    FROM SsfbSiteHour
  `,

  measures: {
    count: { type: `count` },
    rankAqi: { type: `avg`, sql: `rank_aqi` },
    rankPm25: { type: `avg`, sql: `rank_pm25` },
    rankPm10: { type: `avg`, sql: `rank_pm10` },
    rankO3: { type: `avg`, sql: `rank_o3` },
    rankNo2: { type: `avg`, sql: `rank_no2` },
    rankSo2: { type: `avg`, sql: `rank_so2` },
    rankCo: { type: `avg`, sql: `rank_co` },
    avgAqi: { type: `avg`, sql: `aqi_val` },
    avgPm25: { type: `avg`, sql: `pm25_val` },
    avgPm10: { type: `avg`, sql: `pm10_val` },
    avgO38h: { type: `avg`, sql: `o3_8h_val` },
    avgNo2: { type: `avg`, sql: `no2_val` },
    avgSo2: { type: `avg`, sql: `so2_val` },
    avgCo: { type: `avg`, sql: `co_val` },
    siteCount: { type: `avg`, sql: `site_count` },
  },

  dimensions: {
    siteId: { sql: `SiteID`, type: `number` },
    siteName: { sql: `SiteName`, type: `string` },
    city: { sql: `City`, type: `string` },
    county: { sql: `County`, type: `string` },
    quality: { sql: `Quality`, type: `string` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataTime: { sql: `DataTime`, type: `time` },
  },
});

cube(`SsfbSiteDayRank`, {
  sql: `
    SELECT
      DATE(DataTime) AS data_date,
      SiteID,
      SiteName,
      City,
      County,
      Quality,
      MainPollutant,
      AQI AS aqi_val,
      PM25 AS pm25_val,
      PM10 AS pm10_val,
      O3_8H AS o3_8h_val,
      NO2 AS no2_val,
      SO2 AS so2_val,
      CO AS co_val,
      CASE WHEN AQI IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DATE(DataTime) ORDER BY AQI ASC) END AS rank_aqi,
      CASE WHEN PM25 IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DATE(DataTime) ORDER BY PM25 ASC) END AS rank_pm25,
      CASE WHEN PM10 IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DATE(DataTime) ORDER BY PM10 ASC) END AS rank_pm10,
      CASE WHEN O3_8H IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DATE(DataTime) ORDER BY O3_8H ASC) END AS rank_o3,
      CASE WHEN NO2 IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DATE(DataTime) ORDER BY NO2 ASC) END AS rank_no2,
      CASE WHEN SO2 IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DATE(DataTime) ORDER BY SO2 ASC) END AS rank_so2,
      CASE WHEN CO IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DATE(DataTime) ORDER BY CO ASC) END AS rank_co,
      COUNT(*) OVER (PARTITION BY DATE(DataTime)) AS site_count
    FROM SsfbSiteDay
  `,

  measures: {
    count: { type: `count` },
    rankAqi: { type: `avg`, sql: `rank_aqi` },
    rankPm25: { type: `avg`, sql: `rank_pm25` },
    rankPm10: { type: `avg`, sql: `rank_pm10` },
    rankO3: { type: `avg`, sql: `rank_o3` },
    rankNo2: { type: `avg`, sql: `rank_no2` },
    rankSo2: { type: `avg`, sql: `rank_so2` },
    rankCo: { type: `avg`, sql: `rank_co` },
    avgAqi: { type: `avg`, sql: `aqi_val` },
    avgPm25: { type: `avg`, sql: `pm25_val` },
    avgPm10: { type: `avg`, sql: `pm10_val` },
    avgO38h: { type: `avg`, sql: `o3_8h_val` },
    avgNo2: { type: `avg`, sql: `no2_val` },
    avgSo2: { type: `avg`, sql: `so2_val` },
    avgCo: { type: `avg`, sql: `co_val` },
    siteCount: { type: `avg`, sql: `site_count` },
  },

  dimensions: {
    siteId: { sql: `SiteID`, type: `number` },
    siteName: { sql: `SiteName`, type: `string` },
    city: { sql: `City`, type: `string` },
    county: { sql: `County`, type: `string` },
    quality: { sql: `Quality`, type: `string` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataDate: { sql: `data_date`, type: `time` },
  },
});
