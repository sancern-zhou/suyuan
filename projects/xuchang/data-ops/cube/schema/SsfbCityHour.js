// 城市小时空气质量语义模型 — 一行 = 城市组 × 小时（河南实时发布系统，18 组含济源）
// 口径来源: DataCrawler.SsfbCityHour（xuchang_henan_ssfb_city_publish_fetcher 采集）
// PM10 缺失口径见 CityDay 模型说明。
cube(`SsfbCityHour`, {
  sql: `SELECT * FROM SsfbCityHour`,

  measures: {
    count: { type: `count` },
    avgPm25: { type: `avg`, sql: `PM25` },
    avgPm10: { type: `avg`, sql: `PM10` },
    avgO3: { type: `avg`, sql: `O3` },
    avgO38h: { type: `avg`, sql: `O3_8H` },
    avgNo2: { type: `avg`, sql: `NO2` },
    avgSo2: { type: `avg`, sql: `SO2` },
    avgCo: { type: `avg`, sql: `CO` },
    maxAqi: { type: `max`, sql: `AQI` },
  },

  dimensions: {
    city: { sql: `City`, type: `string` },
    cityCode: { sql: `CityCode`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    quality: { sql: `Quality`, type: `string` },
    grade: { sql: `Grade`, type: `number` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataTime: { sql: `DataTime`, type: `time` },
  },
});
