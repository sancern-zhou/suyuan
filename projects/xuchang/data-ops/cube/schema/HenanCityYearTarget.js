// 河南省 18 地市年度空气质量目标完成情况（省考核口径，2021-2025）
// 口径来源: DataCrawler.HenanCityYearTarget（《00重要基础数据.zip》03 表，
//   解析/导入脚本见 projects/xuchang/data-ops/backfill_year_target/）。
// 口径注意:
// - 省考核口径: 与许昌市自报口径偶有 1 μg/m³ 修订差（如 2022 许昌 PM2.5 省 47/市 46，
//   Remark 注明），横向 18 城比较用本表，许昌单市年度问题优先 XuchangCityYearTarget；
// - 优良天/重污染天: 2021-2022 与 2024 为天数(Target/Actual)，2023/2025 为比例%
//   (Ratio 列)，同一列不同年份口径不同，查询前先确认年份；
// - O3ExceedDays 为 5-9 月臭氧超标天(仅 2022-2023 有)，O3ExceedOver=超出目标天数；
// - 2025 年行源表未定稿（实际值列疑沿用 2024 草稿，Remark 已注明），仅目标与完成判定可用；
// - 目标空缺(2023 年 PM10/PM2.5 目标列)为源表原样，完成判定列仍有效。
cube(`HenanCityYearTarget`, {
  sql: `SELECT * FROM HenanCityYearTarget`,

  measures: {
    count: { type: `count` },
    pm10Target: { type: `avg`, sql: `Pm10Target` },
    pm10: { type: `avg`, sql: `Pm10` },
    pm25Target: { type: `avg`, sql: `Pm25Target` },
    pm25: { type: `avg`, sql: `Pm25` },
    goodDaysTarget: { type: `avg`, sql: `GoodDaysTarget` },
    goodDays: { type: `avg`, sql: `GoodDays` },
    goodDaysRatioTarget: { type: `avg`, sql: `GoodDaysRatioTarget` },
    goodDaysRatio: { type: `avg`, sql: `GoodDaysRatio` },
    heavyDaysTarget: { type: `avg`, sql: `HeavyDaysTarget` },
    heavyDays: { type: `avg`, sql: `HeavyDays` },
    heavyDaysRatioTarget: { type: `avg`, sql: `HeavyDaysRatioTarget` },
    heavyDaysRatio: { type: `avg`, sql: `HeavyDaysRatio` },
    o3ExceedDaysTarget: { type: `avg`, sql: `O3ExceedDaysTarget` },
    o3ExceedDays: { type: `avg`, sql: `O3ExceedDays` },
    o3ExceedOver: { type: `avg`, sql: `O3ExceedOver` },
    completedCount: { type: `avg`, sql: `CompletedCount` },
  },

  dimensions: {
    city: { sql: `City`, type: `string` },
    year: { sql: `Year`, type: `number` },
    pm10Completed: { sql: `Pm10Completed`, type: `string` },
    pm25Completed: { sql: `Pm25Completed`, type: `string` },
    goodDaysCompleted: { sql: `GoodDaysCompleted`, type: `string` },
    heavyDaysCompleted: { sql: `HeavyDaysCompleted`, type: `string` },
    remark: { sql: `Remark`, type: `string` },
  },
});
