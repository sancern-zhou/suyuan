// 城市累计统计与排名语义模型（**本地计算，非官方口径**）
// 一行 = 期次类型 × 期次 × 城市组（18 组含济源）
// 口径来源: DataCrawler.SsfbCityRanking（xuchang_henan_ranking_recalc_fetcher 每日重算）。
// 口径注意:
// - **本表为本地计算结果，不代表官方口径**，仅供省内城市横向对比参考；
//   月度及以上环境统计的官方口径以河南省生态环境厅发布为准;
// - 单项浓度: SO2/NO2/PM10/PM2.5 为算术月均/年均，O3 取日最大 8 小时值
//   第 90 百分位，CO 取日均值第 95 百分位;
// - 修约: 银行家算法（四舍六入五成双），PM2.5 与 CO 保留一位小数，
//   PM10/SO2/NO2/O3 取整数; 排名基于修约后的值;
// - 排名规则: 数值越低排名越靠前（Rank* 升序，1 = 最优），相同值并列（1,1,3）;
// - 期次: periodType=daily（单日原值排序）/monthly（月累计）/yearly（年累计）;
// - 差异声明: 官方统计基于审核后数据与官方有效性审核规则（无法外部复现），
//   本地计算与官方已发布结果存在 ±0.5 μg/m³ 级别差异（2026-08 回验:
//   PM2.5 平均绝对差 0.41），正式场合引用官方发布数据。
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
    periodType: { sql: `PeriodType`, type: `string` }, // daily/monthly/yearly
    period: { sql: `Period`, type: `string` }, // YYYY-MM-DD / YYYY-MM / YYYY
    city: { sql: `City`, type: `string` },
    groupId: { sql: `GroupID`, type: `number` },
    computedAt: { sql: `ComputedAt`, type: `time` },
  },
});
