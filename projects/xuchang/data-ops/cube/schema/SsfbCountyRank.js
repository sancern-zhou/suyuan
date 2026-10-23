// 区县小时单项浓度排名语义模型 — 一行 = 区县 × 小时（190 区县含济源/功能区）
// 口径来源: DataCrawler.SsfbCountyHour 经 MySQL 8 窗口函数现算排名（实时，无采集依赖）。
// 与河南省实时发布系统"区县"页签小时排名同口径（升序并列）：
// - 数值越低排名越靠前（Rank* 升序，1 = 最优）；
// - 相同值并列（RANK：1,2,2,4）；NULL 浓度不参与排名（Rank* 为空）；
// - 排名分区为同一 DataTime 的 190 区县；常见用法：
//   filters: dataTime=某小时 + county=栾川县，取 rankAqi/rankPm25。
cube(`SsfbCountyHourRank`, {
  sql: `
    SELECT
      DataTime,
      County,
      City,
      CityCode,
      GroupID,
      Quality,
      MainPollutant,
      AQI AS aqi_val,
      PM25 AS pm25_val,
      PM10 AS pm10_val,
      O3 AS o3_val,
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
      COUNT(*) OVER (PARTITION BY DataTime) AS county_count
    FROM SsfbCountyHour
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
    countyCount: { type: `avg`, sql: `county_count` },
  },

  dimensions: {
    county: { sql: `County`, type: `string` },
    city: { sql: `City`, type: `string` },
    cityCode: { sql: `CityCode`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    quality: { sql: `Quality`, type: `string` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataTime: { sql: `DataTime`, type: `time` },
  },
});

// 区县日排名 — 与平台"区县排名"完全同口径（2026-10-10 全省 188 区县
// 逐位核对：栾川/南湾 19 并列第1 … 永城 88 第187、通许 89 第188）。
// 平台日值 O3 列即 O3-8H 滑动值，故 rankO3 取 O3_8H。
cube(`SsfbCountyDayRank`, {
  sql: `
    SELECT
      DATE(DataTime) AS data_date,
      County,
      City,
      CityCode,
      GroupID,
      Quality,
      Grade,
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
      COUNT(*) OVER (PARTITION BY DATE(DataTime)) AS county_count
    FROM SsfbCountyDay
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
    countyCount: { type: `avg`, sql: `county_count` },
  },

  dimensions: {
    county: { sql: `County`, type: `string` },
    city: { sql: `City`, type: `string` },
    cityCode: { sql: `CityCode`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    quality: { sql: `Quality`, type: `string` },
    grade: { sql: `Grade`, type: `number` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataDate: { sql: `data_date`, type: `time` },
  },
});
