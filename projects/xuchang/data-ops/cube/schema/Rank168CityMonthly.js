// 生态环境部 168 重点城市排名（2026 年逐月 + 1-N 月累计）
// 口径来源: DataCrawler.Rank168CityMonthly（《00重要基础数据.zip》许昌市2026年1-7月
//   168城市排名统计，解析/导入脚本见 projects/xuchang/data-ops/backfill_year_target/）。
// 口径注意:
// - 一行 = 城市 × PeriodType(month当月/cum累计) × 月份；当月行 DataMonth=当月1日，
//   累计行 DataMonth=截止月1日、PeriodEnd=截止月月末；
// - 这是全国排名口径（综合指数+PM2.5 倒序，1=最差），与省内排名 SsfbCityRanking
//   （18 城市组，正参与排序）不可混算；排名并列时排名值可重复；
// - 浓度/综合指数为部发布值，与本地中台/月报口径有细微出入——查许昌浓度绝对值
//   用本地口径 Cube，本模型仅用于全国排名与横向对比；
// - 覆盖 2026-01 ~ 2026-07，后续期次需人工回补（无自动采集）。
cube(`Rank168CityMonthly`, {
  sql: `SELECT * FROM Rank168CityMonthly`,

  measures: {
    count: { type: `count` },
    compositeIndex: { type: `avg`, sql: `CompositeIndex` },
    compositeIndexRank: { type: `avg`, sql: `CompositeIndexRank` },
    pm25: { type: `avg`, sql: `Pm25` },
    pm25Rank: { type: `avg`, sql: `Pm25Rank` },
  },

  dimensions: {
    city: { sql: `City`, type: `string` },
    periodType: { sql: `PeriodType`, type: `string` },
    periodLabel: { sql: `PeriodLabel`, type: `string` },
    dataMonth: { sql: `DataMonth`, type: `time` },
    periodEnd: { sql: `PeriodEnd`, type: `time` },
  },
});
