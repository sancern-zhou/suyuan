// 县市区空气质量月报语义模型 — 官方剔除沙尘口径（许昌 10 区域 × 月）
// 口径来源: DataCrawler.CountyMonthReport（2020-01~2026-09 自官方月报 xls 回补，
//   解析/导入脚本见 projects/xuchang/data-ops/backfill_county_month/，
//   源文件 /root/suyuan/data/县市区空气质量数据月报.zip）。
// 与实时链路(SsfbCounty*)的本质区别:
// - 本模型是官方发布的月度统计（月报原值,非明细聚合）: PM10/PM2.5/SO2/NO2 月均、
//   CO 第95百分位、O3-8h 第90百分位、优良天、重污染天(2023 起才有)、综合指数;
// - 剔除沙尘; 魏都区/开发区/东城区/示范区/建安区为国家平台数据,
//   鄢陵县/襄城县/禹州市/长葛市为省平台数据（RegionType 区分）;
// - 2020 年数值取自 2021 年月报"上年同期"列（SourceCol=prior）,其余为当年列;
// - 一行 = 区域 × 月份 × Scope，两 Cube 按 Scope 拆分避免当月/累计混算:
//   CountyMonth     (Scope='month') 当月值, 时间维度 dataMonth;
//   CountyMonthCum  (Scope='cum')   1-N月累计值, 时间维度 periodEnd(累计截止月末)。
// 累计口径注意: 优良天/重污染天为期间合计;浓度为期间平均;源文件 2021/2025/2026
// 个别区域累计值与当月值之和存在 1~2 天官方修订差,两口径均为官方原值,勿互相换算。
cube(`CountyMonth`, {
  sql: `SELECT * FROM CountyMonthReport WHERE Scope = 'month'`,

  measures: {
    count: { type: `count` },
    pm10: { type: `avg`, sql: `PM10` },
    pm25: { type: `avg`, sql: `PM25` },
    so2: { type: `avg`, sql: `SO2` },
    no2: { type: `avg`, sql: `NO2` },
    co95: { type: `avg`, sql: `CO` },
    o3_8h_90: { type: `avg`, sql: `O3_8H` },
    goodDays: { type: `avg`, sql: `GoodDays` },
    heavyDays: { type: `avg`, sql: `HeavyDays` },
    compositeIndex: { type: `avg`, sql: `CompositeIndex` },
  },

  dimensions: {
    region: { sql: `Region`, type: `string` },
    regionType: { sql: `RegionType`, type: `string` },
    dataMonth: { sql: `DataMonth`, type: `time` },
  },
});

cube(`CountyMonthCum`, {
  sql: `SELECT * FROM CountyMonthReport WHERE Scope = 'cum'`,

  measures: {
    count: { type: `count` },
    pm10: { type: `avg`, sql: `PM10` },
    pm25: { type: `avg`, sql: `PM25` },
    so2: { type: `avg`, sql: `SO2` },
    no2: { type: `avg`, sql: `NO2` },
    co95: { type: `avg`, sql: `CO` },
    o3_8h_90: { type: `avg`, sql: `O3_8H` },
    goodDays: { type: `avg`, sql: `GoodDays` },
    heavyDays: { type: `avg`, sql: `HeavyDays` },
    compositeIndex: { type: `avg`, sql: `CompositeIndex` },
  },

  dimensions: {
    region: { sql: `Region`, type: `string` },
    regionType: { sql: `RegionType`, type: `string` },
    periodEnd: { sql: `PeriodEnd`, type: `time` },
  },
});
