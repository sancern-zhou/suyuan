// 河南省环境空气质量月报语义模型 — 官方口径（省/市/市辖区/县市）
// 口径来源: DataCrawler.ProvinceMonthReport（10 期官方月报 PDF 附表:
//   2025年第12期 + 2026年第1~9期; 解析脚本
//   projects/xuchang/data-ops/backfill_province_month/）。
// 说明:
// - Level=city 为 19 个省辖市（区）（含济源示范区、郑州航空港区）,官方月度/累计
//   统计含 PM2.5/PM10/O3/优良天/重污染天/综合指数 及各自同比——这是城市月度及
//   以上统计的**唯一官方来源**,替代此前本地手算(已停用);
// - Level=district 为 88 个省辖市所辖区, Level=county 为 101 个县（市）;
//   两者只有 PM2.5/PM10/O3(供暖季无)/综合指数 及同比、优良天,无 SO2/NO2/CO/重污染天;
// - Level=province 为全省（含济源、不含航空港）;
// - 同比列(Xxx_YoY)为官方同比变化率(%),不是上年绝对值;
// - 区域数量随期次变化(2025-12~2026-03 为 85区/103县市,2026-04 起 88区/101县市,
//   源报告区域调整所致);2026 年第1期无累计表(1 月累计=当月)。
// 时间维度: ProvinceMonth.dataMonth(当月), ProvinceMonthCum.dataMonth(截至该月累计)。
cube(`ProvinceMonth`, {
  sql: `SELECT * FROM ProvinceMonthReport WHERE Scope = 'month'`,

  measures: {
    count: { type: `count` },
    pm10: { type: `avg`, sql: `PM10` },
    pm10YoY: { type: `avg`, sql: `PM10_YoY` },
    pm25: { type: `avg`, sql: `PM25` },
    pm25YoY: { type: `avg`, sql: `PM25_YoY` },
    o3: { type: `avg`, sql: `O3` },
    o3YoY: { type: `avg`, sql: `O3_YoY` },
    goodDays: { type: `avg`, sql: `GoodDays` },
    goodDaysChange: { type: `avg`, sql: `GoodDays_Change` },
    goodDaysRatio: { type: `avg`, sql: `GoodDays_Ratio` },
    heavyDays: { type: `avg`, sql: `HeavyDays` },
    heavyDaysChange: { type: `avg`, sql: `HeavyDays_Change` },
    compositeIndex: { type: `avg`, sql: `CompositeIndex` },
    compositeIndexYoY: { type: `avg`, sql: `CompositeIndex_YoY` },
  },

  dimensions: {
    level: { sql: `Level`, type: `string` },       // city/district/county/province
    city: { sql: `City`, type: `string` },
    region: { sql: `RegionName`, type: `string` },
    dataMonth: { sql: `DataMonth`, type: `time` },
  },
});

cube(`ProvinceMonthCum`, {
  sql: `SELECT * FROM ProvinceMonthReport WHERE Scope = 'cum'`,

  measures: {
    count: { type: `count` },
    pm10: { type: `avg`, sql: `PM10` },
    pm10YoY: { type: `avg`, sql: `PM10_YoY` },
    pm25: { type: `avg`, sql: `PM25` },
    pm25YoY: { type: `avg`, sql: `PM25_YoY` },
    o3: { type: `avg`, sql: `O3` },
    o3YoY: { type: `avg`, sql: `O3_YoY` },
    goodDays: { type: `avg`, sql: `GoodDays` },
    goodDaysChange: { type: `avg`, sql: `GoodDays_Change` },
    goodDaysRatio: { type: `avg`, sql: `GoodDays_Ratio` },
    heavyDays: { type: `avg`, sql: `HeavyDays` },
    heavyDaysChange: { type: `avg`, sql: `HeavyDays_Change` },
    compositeIndex: { type: `avg`, sql: `CompositeIndex` },
    compositeIndexYoY: { type: `avg`, sql: `CompositeIndex_YoY` },
  },

  dimensions: {
    level: { sql: `Level`, type: `string` },
    city: { sql: `City`, type: `string` },
    region: { sql: `RegionName`, type: `string` },
    dataMonth: { sql: `DataMonth`, type: `time` },  // 取该月即 1-N 月累计
  },
});
