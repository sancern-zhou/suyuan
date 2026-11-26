// 生态环境部 168 重点城市官方月度定版排名（2026 年逐月 + 1-N 月累计）
// 口径来源: DataCrawler.Rank168CityMonthly（《00重要基础数据.zip》许昌市2026年1-7月
//   168城市排名统计，解析/导入脚本见 projects/xuchang/data-ops/backfill_year_target/）。
// 口径注意:
// - 一行 = 城市 × PeriodType(month当月/cum累计) × 月份；当月行 DataMonth=当月1日，
//   累计行 DataMonth=截止月1日、PeriodEnd=截止月月末；
// - 这是全国排名口径（综合指数+PM2.5 倒序，1=最差），与省内排名 SsfbCityRanking
//   （18 城市组，正参与排序）不可混算；排名并列时排名值可重复；
// - 排名方向与表述规范：*RankDesc 为倒序名次，1=污染最重（浓度最高），数值越大污染越轻；
//   对外表述只用"倒序排名第N位（污染第N重）"，禁止换算为"第N好/由好到差第N名"，
//   禁止据倒序排名得出"空气质量较好/表现最优"类结论（许昌排名靠前=污染重）；
// - 浓度/综合指数为部发布值，与本地中台/月报口径有细微出入——查许昌浓度绝对值
//   用本地口径 Cube，本模型仅用于全国排名与横向对比；
// - 覆盖 2026-01 ~ 2026-07（人工回补），2026-08 起 mee_rank168_monthly fetcher
//   从 mee.gov.cn 月度新闻发布自动采集入库（SourceFile=mee.gov.cn:*）。
// - 与中台实时排名的关系：中台报表接口 airdata_calc_report_summary(is_rank=true)
//   基于发布数据实时计算 168 城排名，实时更新但仅作参考、非官方定版；
//   官方结论/历史月份以本模型（部逐月发布定版）为准。
cube(`Rank168CityMonthly`, {
  sql: `SELECT * FROM Rank168CityMonthly`,

  measures: {
    count: { type: `count` },
    compositeIndex: { type: `avg`, sql: `CompositeIndex` },
    compositeIndexRank: { type: `avg`, sql: `CompositeIndexRankDesc` },
    pm25: { type: `avg`, sql: `Pm25` },
    pm25Rank: { type: `avg`, sql: `Pm25RankDesc` },
  },

  dimensions: {
    city: { sql: `City`, type: `string` },
    periodType: { sql: `PeriodType`, type: `string` },
    periodLabel: { sql: `PeriodLabel`, type: `string` },
    dataMonth: { sql: `DataMonth`, type: `time` },
    periodEnd: { sql: `PeriodEnd`, type: `time` },
  },
});
