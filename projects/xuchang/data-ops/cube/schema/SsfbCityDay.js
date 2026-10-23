// 城市日空气质量语义模型 — 一行 = 城市组 × 自然日（18 组含济源）
// 口径来源: DataCrawler.SsfbCityDay。
// 口径注意:
// - 济源在国控发布历史（CityDayAQIPublishHistory）中长期缺失，本表是
//   唯一含济源的全量城市日数据源（2026-10-03 起）;
// - 源接口 2026-10 起日值不发布 PM10，重算链路（SsfbCityRanking）用
//   小时均值补齐，本表 PM10 保留源样（可能为空）。
cube(`SsfbCityDay`, {
  sql: `SELECT * FROM SsfbCityDay`,

  measures: {
    count: { type: `count` },
    avgPm25: { type: `avg`, sql: `PM25` },
    avgPm10: { type: `avg`, sql: `PM10` },
    avgO38h: { type: `avg`, sql: `O3_8H` },
    avgNo2: { type: `avg`, sql: `NO2` },
    avgSo2: { type: `avg`, sql: `SO2` },
    avgCo: { type: `avg`, sql: `CO` },
  },

  dimensions: {
    city: { sql: `City`, type: `string` },
    cityCode: { sql: `CityCode`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    quality: { sql: `Quality`, type: `string` },
    grade: { sql: `Grade`, type: `number` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataDate: { sql: `DataTime`, type: `time` },
  },
});
