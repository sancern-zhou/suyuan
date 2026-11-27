// 许昌县市区年度空气质量目标 vs 实际（官方考核定版，2020-2025）
// 口径来源: DataCrawler.XuchangCountyYearTarget（《00重要基础数据.zip》05 表 + 剔沙尘表，
//   解析/导入脚本见 projects/xuchang/data-ops/backfill_year_target/）。
// 与 CountyMonth/CountyMonthCum 的区别:
// - 本模型是年度考核定版（目标值 + 完成判定），县级年度目标值全库唯一；
// - 重污染天为剔沙尘口径: 2023 年与 CountyMonthReport 月报值系统性差 3~4 天
//   （2023-03 沙尘，月报未剔沙尘）——年度考核/目标完成问题一律以本表为准，
//   逐月过程分析才用 CountyMonth；个别区域源表间有 1 天出入以 05 表为准(Remark 注明)；
// - 2020 年仅有重污染天(剔沙尘表)；2025 年许昌市 PM10 目标为市定未下达(NULL)；
// - RegionType 与 CountyMonthReport 同口径: city=全市/urban=市辖区(国家平台)/
//   county=县市(省平台)，两平台数据源不同勿直接横比。
cube(`XuchangCountyYearTarget`, {
  sql: `SELECT * FROM XuchangCountyYearTarget`,

  measures: {
    count: { type: `count` },
    pm10Target: { type: `avg`, sql: `Pm10Target` },
    pm10: { type: `avg`, sql: `Pm10` },
    pm25Target: { type: `avg`, sql: `Pm25Target` },
    pm25: { type: `avg`, sql: `Pm25` },
    goodDaysTarget: { type: `avg`, sql: `GoodDaysTarget` },
    goodDays: { type: `avg`, sql: `GoodDays` },
    heavyDaysTarget: { type: `avg`, sql: `HeavyDaysTarget` },
    heavyDays: { type: `avg`, sql: `HeavyDays` },
  },

  dimensions: {
    region: { sql: `Region`, type: `string` },
    regionType: { sql: `RegionType`, type: `string` },
    year: { sql: `Year`, type: `number` },
    pm10Completed: { sql: `Pm10Completed`, type: `string` },
    pm25Completed: { sql: `Pm25Completed`, type: `string` },
    goodDaysCompleted: { sql: `GoodDaysCompleted`, type: `string` },
    heavyDaysCompleted: { sql: `HeavyDaysCompleted`, type: `string` },
    remark: { sql: `Remark`, type: `string` },
  },
});
