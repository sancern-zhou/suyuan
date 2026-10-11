// 全省区县小时/日空气质量语义模型 — 一行 = 区县 × 小时（或自然日）
// 口径来源: DataCrawler.SsfbCountyHour / SsfbCountyDay
//（xuchang_henan_county_publish_fetcher 采集，源为河南实时发布系统
//  城市组接口区县口径 queryType=2，全集 = 区县树 189 叶子 + 济源 218
//  = 190 区县（含经开区/示范区等功能区），与平台"区县"页签同源）。
cube(`SsfbCountyHour`, {
  sql: `SELECT * FROM SsfbCountyHour`,

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
    onlineCounties: { type: `countDistinct`, sql: `GroupID` },
  },

  dimensions: {
    county: { sql: `County`, type: `string` },
    city: { sql: `City`, type: `string` },
    cityCode: { sql: `CityCode`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    quality: { sql: `Quality`, type: `string` },
    grade: { sql: `Grade`, type: `number` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataTime: { sql: `DataTime`, type: `time` },
  },
});

cube(`SsfbCountyDay`, {
  sql: `SELECT * FROM SsfbCountyDay`,

  measures: {
    count: { type: `count` },
    avgPm25: { type: `avg`, sql: `PM25` },
    avgPm10: { type: `avg`, sql: `PM10` },
    avgO38h: { type: `avg`, sql: `O3_8H` },
    avgNo2: { type: `avg`, sql: `NO2` },
    avgSo2: { type: `avg`, sql: `SO2` },
    avgCo: { type: `avg`, sql: `CO` },
    onlineCounties: { type: `countDistinct`, sql: `GroupID` },
  },

  dimensions: {
    county: { sql: `County`, type: `string` },
    city: { sql: `City`, type: `string` },
    cityCode: { sql: `CityCode`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    quality: { sql: `Quality`, type: `string` },
    grade: { sql: `Grade`, type: `number` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataDate: { sql: `DataTime`, type: `time` },
  },
});
