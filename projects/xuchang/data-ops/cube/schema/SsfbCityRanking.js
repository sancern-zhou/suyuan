// 城市日排名语义模型 — 一行 = 城市组 × 自然日（18 组含济源）
// 口径来源: DataCrawler.SsfbCityRanking（xuchang_henan_ranking_recalc_fetcher 每日重算）。
// 口径注意:
// - **仅对官方发布日值排序展示**，不做任何聚合统计计算（月均/年均/百分位/
//   综合指数等一律以官方发布为准，不在本地生成）;
// - 排名规则: 数值越低排名越靠前（Rank* 升序，1 = 最优），相同值并列（1,1,3）;
// - 某城市某参数当日值缺失时不参与该参数排名（Rank* 为空）;
// - 仅日粒度（PeriodType='daily', Period=YYYY-MM-DD）。
cube(`SsfbCityRanking`, {
  sql: `SELECT * FROM SsfbCityRanking`,

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
    periodType: { sql: `PeriodType`, type: `string` }, // 仅 daily
    period: { sql: `Period`, type: `string` }, // YYYY-MM-DD
    city: { sql: `City`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    computedAt: { sql: `ComputedAt`, type: `time` },
  },
});
