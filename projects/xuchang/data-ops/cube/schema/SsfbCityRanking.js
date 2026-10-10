// 城市排名语义模型（本地重算） — 一行 = 期次类型 × 期次 × 城市组（18 组含济源）
// 口径来源: DataCrawler.SsfbCityRanking（xuchang_henan_ranking_recalc_fetcher 每日重算）。
// 口径注意:
// - 省空气质量 APP 2026-09 起停服，本表为透明可复算的本地口径替代;
// - 综合指数 = HJ663 六项单项指数之和（SO2/60 + NO2/40 + PM10/70 + PM2.5/35
//   + O3-8h-90per/160 + CO-95per/4，GB3095-2012 二级限值）;
// - 排名规则: 数值越低排名越靠前（Rank* 升序，1 = 最优），相同值并列（1,1,3）;
// - PM10 缺口由小时均值补齐（与国标连续采样口径有差异，已在 validDays 语义中体现）;
// - OfficialZong/OfficialRank 为省 APP 官方对照（仅 ≤2026-08 有值），不可参与重算。
cube(`SsfbCityRanking`, {
  sql: `SELECT * FROM SsfbCityRanking`,

  measures: {
    count: { type: `count` },
    avgZong: { type: `avg`, sql: `Zong` },
    avgPm25: { type: `avg`, sql: `PM25` },
    avgPm10: { type: `avg`, sql: `PM10` },
    avgSo2: { type: `avg`, sql: `SO2` },
    avgNo2: { type: `avg`, sql: `NO2` },
    avgO38h90: { type: `avg`, sql: `O3_8H_90` },
    avgCo95: { type: `avg`, sql: `CO95` },
    rankZong: { type: `avg`, sql: `RankZong` },
    rankPm25: { type: `avg`, sql: `RankPM25` },
    rankPm10: { type: `avg`, sql: `RankPM10` },
    rankSo2: { type: `avg`, sql: `RankSO2` },
    rankNo2: { type: `avg`, sql: `RankNO2` },
    rankO3: { type: `avg`, sql: `RankO3` },
    rankCo: { type: `avg`, sql: `RankCO` },
    officialZong: { type: `avg`, sql: `OfficialZong` },
    officialRank: { type: `avg`, sql: `OfficialRank` },
  },

  dimensions: {
    periodType: { sql: `PeriodType`, type: `string` },
    period: { sql: `Period`, type: `string` },
    city: { sql: `City`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    days: { sql: `Days`, type: `number` },
    validDays: { sql: `ValidDays`, type: `number` },
    pmValidDays: { sql: `PmValidDays`, type: `number` },
    computedAt: { sql: `ComputedAt`, type: `time` },
  },
});
