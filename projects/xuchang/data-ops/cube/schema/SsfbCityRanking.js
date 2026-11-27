// 城市日排名语义模型（官方发布日值升序排序，取原值不聚合）
// 一行 = 日期 × 城市组（18 组含济源）
// 口径来源: DataCrawler.SsfbCityRanking（xuchang_henan_ranking_recalc_fetcher 每日重算）。
// 口径注意:
// - 仅 period_type='daily'：对官方发布日值直接排序展示，不做修约与聚合；
// - 排名规则: 数值越低排名越靠前（Rank* 升序，1 = 最优），相同值并列（1,1,3）;
// - 城市**月/年累计**统计已改为官方月报口径（ProvinceMonth/ProvinceMonthCum，
//   源 DataCrawler.ProvinceMonthReport）；本地手算 monthly/yearly 已停用并删除。
cube(`SsfbCityRanking`, {
  sql: `SELECT * FROM SsfbCityRanking WHERE PeriodType = 'daily'`,

  measures: {
    count: { type: `count` },
    avgPm25: { type: `avg`, sql: `PM25` },
    avgPm10: { type: `avg`, sql: `PM10` },
    avgSo2: { type: `avg`, sql: `SO2` },
    avgNo2: { type: `avg`, sql: `NO2` },
    avgCo: { type: `avg`, sql: `CO` },
    avgO38h: { type: `avg`, sql: `O3_8H` },
    rankPm25: { type: `avg`, sql: `RankPM25` },
    rankPm10: { type: `avg`, sql: `RankPM10` },
    rankSo2: { type: `avg`, sql: `RankSO2` },
    rankNo2: { type: `avg`, sql: `RankNO2` },
    rankO3: { type: `avg`, sql: `RankO3` },
    rankCo: { type: `avg`, sql: `RankCO` },
  },

  dimensions: {
    periodType: { sql: `PeriodType`, type: `string` }, // daily/monthly/yearly
    period: { sql: `Period`, type: `string` }, // YYYY-MM-DD / YYYY-MM / YYYY
    city: { sql: `City`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    computedAt: { sql: `ComputedAt`, type: `time` },
  },
});
