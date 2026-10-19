// 许昌市年度空气质量目标 vs 实际（官方定版，2015-2026）
// 口径来源: DataCrawler.XuchangCityYearTarget（《00重要基础数据.zip》01 表，
//   解析/导入脚本见 projects/xuchang/data-ops/backfill_year_target/）。
// 与其他年度口径的关系:
// - 本模型是"上级下达目标 + 国家网口径实际值"的年度考核定版，目标值列(2015-2026)为
//   全库唯一目标数据源；
// - PM10/PM2.5 年均实际取"实际值"列（国家网/考核口径），源表另有省APP发布口径两列
//   （如 2016 PM10 122 vs APP 119），APP 列未入库，不要与中台/Ssfb 口径互算；
// - 2015-2020 平台预计算表 CityYearPm25Avg 的 Actual 列为实时未审核口径，
//   与本表考核定版值有 1~5 μg/m³ 差（2015: 82 vs 78），年度考核问题一律以本表为准；
// - SO2/NO2/CO/O3 年均仅 2015-2020 填有（2021 起源表未再填报 O3 年均）；
// - 重污染天为剔沙尘口径；O3ExceedDays 为臭氧超标天；
// - 2025 年 PM10 目标 70 为市定（Remark 注明），2026 年仅有目标值（在途年度）。
cube(`XuchangCityYearTarget`, {
  sql: `SELECT * FROM XuchangCityYearTarget`,

  measures: {
    count: { type: `count` },
    pm10Target: { type: `avg`, sql: `Pm10Target` },
    pm25Target: { type: `avg`, sql: `Pm25Target` },
    goodDaysTarget: { type: `avg`, sql: `GoodDaysTarget` },
    heavyDaysTarget: { type: `avg`, sql: `HeavyDaysTarget` },
    pm10: { type: `avg`, sql: `Pm10` },
    pm25: { type: `avg`, sql: `Pm25` },
    so2: { type: `avg`, sql: `So2` },
    no2: { type: `avg`, sql: `No2` },
    co95: { type: `avg`, sql: `Co` },
    o3: { type: `avg`, sql: `O3` },
    goodDays: { type: `avg`, sql: `GoodDays` },
    heavyDays: { type: `avg`, sql: `HeavyDays` },
    o3ExceedDays: { type: `avg`, sql: `O3ExceedDays` },
  },

  dimensions: {
    year: { sql: `Year`, type: `number` },
    remark: { sql: `Remark`, type: `string` },
  },
});
