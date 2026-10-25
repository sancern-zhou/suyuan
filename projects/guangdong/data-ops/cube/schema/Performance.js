// 站点绩效语义模型 — 口径唯一来源: sync/datasets/mart_performance_analysis.yaml + dbt 模型
// 范围: 站点×月绩效考核（2026 合同年度）。得分与金额均为平台考核口径原值，不重算；
// 平台每日 10:15 左右重算。金额单位元。率类指标返回百分数(0-100)。
cube(`Performance`, {
  sql: `select * from guangdong_mart.mart_performance_analysis`,

  measures: {
    count: { type: `count`, title: `站点月数` },
    distinctStationCount: {
      type: `countDistinct`,
      sql: `station_id`,
      title: `涉及站点数(去重)`,
    },
    avgTotalScore: {
      type: `avg`,
      sql: `total_score`,
      title: `平均总分(平台考核口径)`,
    },
    below60Count: {
      type: `count`,
      filters: [{ sql: `${CUBE}.total_score < 60` }],
      title: `低于60分站点月数`,
    },
    sumDeductionAmount: {
      type: `sum`,
      sql: `deduction_amount`,
      title: `核减金额合计(元)`,
    },
    sumPenaltyAmount: {
      type: `sum`,
      sql: `penalty_amount`,
      title: `扣款金额合计(元)`,
    },
    sumPaidAmount: {
      type: `sum`,
      sql: `paid_amount`,
      title: `实发金额合计(元)`,
    },
    avgQcQualifiedRate: {
      type: `avg`,
      sql: `qc_qualified_rate`,
      title: `平均质控合格率(平台口径)`,
    },
  },

  dimensions: {
    performanceMonth: { sql: `performance_month`, type: `string`, title: `考核月份(如 2026年09月)` },
    cityName: { sql: `city_name`, type: `string`, title: `城市名` },
    stationCode: { sql: `station_code`, type: `string`, title: `站点编码` },
    stationName: { sql: `station_name`, type: `string`, title: `站点名` },
    stationTypeName: { sql: `station_type_name`, type: `string`, title: `站点类型中文名` },
    operationUnitName: { sql: `operation_unit_name`, type: `string`, title: `运维单位中文名` },
    contractName: { sql: `contract_name`, type: `string`, title: `合同名` },
    contractCode: { sql: `contract_code`, type: `string`, title: `合同编号` },
    statusCode: { sql: `status_code`, type: `number`, title: `状态码(原文)` },
    deductionRemark: { sql: `deduction_remark`, type: `string`, title: `扣减规则说明(原文)` },
    contractStartDate: { sql: `contract_start_date`, type: `time`, title: `合同开始日期(时间维度)` },
  },
});
