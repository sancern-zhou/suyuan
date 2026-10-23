// 城市小时单项浓度排名语义模型 — 一行 = 城市组 × 小时（18 组含济源）
// 口径来源: DataCrawler.SsfbCityHour 经 MySQL 8 窗口函数现算排名（实时，无采集依赖）。
// 口径注意:
// - 排名规则与日/月粒度一致：**数值越低排名越靠前**（Rank* 升序，1 = 最优），
//   相同值并列（RANK：1,2,2,4）；NULL 浓度不参与排名（Rank* 为空）;
// - 排名分区为同一 DataTime 的 18 城市组；常见用法：
//   filters: dataTime=某小时 + city=许昌市，取 RankAqi/RankPm25;
// - AQI 与六参数浓度各自独立排名（分项浓度低 ≠ AQI 低）。
cube(`SsfbCityHourRank`, {
  sql: `
    SELECT
      DataTime,
      City,
      CityCode,
      GroupID,
      Quality,
      MainPollutant,
      NULLIF(AQI, -99) AS aqi_val,
      NULLIF(PM25, -99) AS pm25_val,
      NULLIF(PM10, -99) AS pm10_val,
      NULLIF(O3, -99) AS o3_val,
      NULLIF(NO2, -99) AS no2_val,
      NULLIF(SO2, -99) AS so2_val,
      NULLIF(CO, -99) AS co_val,
      CASE WHEN NULLIF(AQI, -99) IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY CASE WHEN NULLIF(AQI, -99) IS NULL THEN 999999 ELSE NULLIF(AQI, -99) END ASC) END AS rank_aqi,
      CASE WHEN NULLIF(PM25, -99) IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY CASE WHEN NULLIF(PM25, -99) IS NULL THEN 999999 ELSE NULLIF(PM25, -99) END ASC) END AS rank_pm25,
      CASE WHEN NULLIF(PM10, -99) IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY CASE WHEN NULLIF(PM10, -99) IS NULL THEN 999999 ELSE NULLIF(PM10, -99) END ASC) END AS rank_pm10,
      CASE WHEN NULLIF(O3, -99) IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY CASE WHEN NULLIF(O3, -99) IS NULL THEN 999999 ELSE NULLIF(O3, -99) END ASC) END AS rank_o3,
      CASE WHEN NULLIF(NO2, -99) IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY CASE WHEN NULLIF(NO2, -99) IS NULL THEN 999999 ELSE NULLIF(NO2, -99) END ASC) END AS rank_no2,
      CASE WHEN NULLIF(SO2, -99) IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY CASE WHEN NULLIF(SO2, -99) IS NULL THEN 999999 ELSE NULLIF(SO2, -99) END ASC) END AS rank_so2,
      CASE WHEN NULLIF(CO, -99) IS NULL THEN NULL
           ELSE RANK() OVER (PARTITION BY DataTime ORDER BY CASE WHEN NULLIF(CO, -99) IS NULL THEN 999999 ELSE NULLIF(CO, -99) END ASC) END AS rank_co,
      COUNT(*) OVER (PARTITION BY DataTime) AS city_count
    FROM SsfbCityHour
  `,

  measures: {
    count: { type: `count` },
    rankAqi: { type: `avg`, sql: `rank_aqi` },
    rankPm25: { type: `avg`, sql: `rank_pm25` },
    rankPm10: { type: `avg`, sql: `rank_pm10` },
    rankSo2: { type: `avg`, sql: `rank_so2` },
    rankNo2: { type: `avg`, sql: `rank_no2` },
    rankO3: { type: `avg`, sql: `rank_o3` },
    rankCo: { type: `avg`, sql: `rank_co` },
    avgAqi: { type: `avg`, sql: `aqi_val` },
    avgPm25: { type: `avg`, sql: `pm25_val` },
    avgPm10: { type: `avg`, sql: `pm10_val` },
    avgO3: { type: `avg`, sql: `o3_val` },
    avgNo2: { type: `avg`, sql: `no2_val` },
    avgSo2: { type: `avg`, sql: `so2_val` },
    avgCo: { type: `avg`, sql: `co_val` },
    cityCount: { type: `avg`, sql: `city_count` },
  },

  dimensions: {
    city: { sql: `City`, type: `string` },
    cityCode: { sql: `CityCode`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    quality: { sql: `Quality`, type: `string` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataTime: { sql: `DataTime`, type: `time` },
  },
});
