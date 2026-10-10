// 许昌县级站小时/日空气质量语义模型 — 一行 = 站点 × 小时（或自然日）
// 口径来源: DataCrawler.SsfbSiteHour / SsfbSiteDay
//（xuchang_henan_ssfb_site_publish_fetcher 采集，源为河南实时发布系统"县级"体系，
//  已剔除国控站；站点目录见 SsfbDimSite，区县归属 County 字段）。
cube(`SsfbSiteHour`, {
  sql: `SELECT * FROM SsfbSiteHour`,

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
    onlineSites: { type: `countDistinct`, sql: `SiteID` },
  },

  dimensions: {
    siteId: { sql: `SiteID`, type: `number` },
    siteName: { sql: `SiteName`, type: `string` },
    onlineType: { sql: `OnlineType`, type: `string` },
    city: { sql: `City`, type: `string` },
    county: { sql: `County`, type: `string` },
    area: { sql: `Area`, type: `string` },
    quality: { sql: `Quality`, type: `string` },
    grade: { sql: `Grade`, type: `number` },
    primaryPollutant: { sql: `MainPollutant`, type: `string` },
    dataTime: { sql: `DataTime`, type: `time` },
  },
});

cube(`SsfbSiteDay`, {
  sql: `SELECT * FROM SsfbSiteDay`,

  measures: {
    count: { type: `count` },
    avgPm25: { type: `avg`, sql: `PM25` },
    avgPm10: { type: `avg`, sql: `PM10` },
    avgO38h: { type: `avg`, sql: `O3_8H` },
    avgNo2: { type: `avg`, sql: `NO2` },
    avgSo2: { type: `avg`, sql: `SO2` },
    avgCo: { type: `avg`, sql: `CO` },
    onlineSites: { type: `countDistinct`, sql: `SiteID` },
  },

  dimensions: {
    siteId: { sql: `SiteID`, type: `number` },
    siteName: { sql: `SiteName`, type: `string` },
    onlineType: { sql: `OnlineType`, type: `string` },
    city: { sql: `City`, type: `string` },
    county: { sql: `County`, type: `string` },
    quality: { sql: `Quality`, type: `string` },
    dataDate: { sql: `DataTime`, type: `time` },
  },
});
