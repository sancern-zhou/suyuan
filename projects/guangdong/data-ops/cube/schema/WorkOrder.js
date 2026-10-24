// 工单语义模型 — 口径唯一来源: sync/datasets/mart_work_order_analysis.yaml + dbt 模型
// 范围: 全类型运维工单（含作废单），与江苏 WorkOrder cube（仅故障单）不同。
// 工单量/时效等结论必须结合 orderType/orderStatus 维度过滤口径后表述。
// 广东特有: 工单有计划完成时间, 超期可评估; 分母只计 plan_finish_time 非空的单
// (overdueEvaluable), 分母为零按不可评估回答。响应类指标仅故障单可评估
// (到站 = 首个 FaultProcess 步骤开始)。率类指标返回百分数(0-100)。
cube(`WorkOrder`, {
  sql: `select * from guangdong_mart.mart_work_order_analysis`,

  measures: {
    count: { type: `count` },
    finishedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_finish` }],
      title: `已完成工单数`,
    },
    finishRate: {
      type: `number`,
      sql: `100.0 * ${finishedCount} / nullif(${count}, 0)`,
      title: `完成率(%,含作废单基数,剔除作废请配合 orderStatus 维度过滤)`,
    },
    overdueEvaluable: {
      type: `count`,
      filters: [{ sql: `${CUBE}.overdue_evaluable` }],
      title: `超期可评估工单数(计划完成时间非空)`,
    },
    overdueCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_overdue` }],
    },
    overdueRate: {
      type: `number`,
      sql: `100.0 * ${overdueCount} / nullif(${overdueEvaluable}, 0)`,
      title: `超期率(%,仅按有计划完成时间的单评估;例行维护单计划时间非考核截止,该类超期以orderOvertime标记为准)`,
    },
    responseEvaluable: {
      type: `count`,
      filters: [{ sql: `${CUBE}.arrival_time is not null` }],
      title: `可评估响应的工单数(故障单)`,
    },
    responseWithin2hCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_response_within_2h` }],
    },
    responseWithin2hRate: {
      type: `number`,
      sql: `100.0 * ${responseWithin2hCount} / nullif(${responseEvaluable}, 0)`,
      title: `2小时响应率(%,仅故障单可评估)`,
    },
    faultCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.order_type in ('Fault','SupFault')` }],
      title: `故障工单数(Fault/SupFault)`,
    },
    repeatFaultCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.is_repeat_fault` }],
    },
    repeatFaultRate: {
      type: `number`,
      sql: `100.0 * ${repeatFaultCount} / nullif(${faultCount}, 0)`,
      title: `30天重复故障率(%,分母=故障单)`,
    },
    hasAttachmentCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.has_attachment` }],
      title: `有附件的工单数`,
    },
    attachmentRate: {
      type: `number`,
      sql: `100.0 * ${hasAttachmentCount} / nullif(${count}, 0)`,
      title: `附件完整率(%,有附件工单/工单数)`,
    },
    avgResponseMinutes: { type: `avg`, sql: `response_minutes`, title: `平均响应时长(分钟,仅故障单)` },
    avgProcessMinutes: { type: `avg`, sql: `process_minutes`, title: `平均到站后处理时长(分钟)` },
    avgRepairMinutes: { type: `avg`, sql: `repair_minutes`, title: `平均全程修复时长(分钟)` },
    avgNodeCount: { type: `avg`, sql: `node_count`, title: `平均流转节点数` },
    avgExpense: { type: `avg`, sql: `total_expense`, title: `平均工单费用(元)` },
  },

  dimensions: {
    orderType: { sql: `order_type`, type: `string`, title: `工单类型代码(28种,字典见语义字典01)` },
    orderStatus: { sql: `order_status_cn`, type: `string`, title: `工单状态(已完成/处理中/待处理/已作废)` },
    urgency: { sql: `urgency_type`, type: `string`, title: `紧急程度` },
    maintenanceType: { sql: `maintenance_type`, type: `string`, title: `维护周期` },
    orderOvertime: { sql: `order_overtime`, type: `string`, title: `源系统超时标记(原文;例行单超期以此为准,勿用overdueRate)` },
    totalOvertime: { sql: `total_overtime`, type: `string`, title: `源系统累计超时标记(原文)` },
    stationCode: { sql: `station_code`, type: `string`, title: `站点编码` },
    stationName: { sql: `station_name`, type: `string`, title: `站点名` },
    stationType: { sql: `station_type`, type: `string`, title: `站点类型(源库代码原文)` },
    stationTypeName: { sql: `station_type_name`, type: `string`, title: `站点类型中文名(经alm_home补充,覆盖率以推送为准)` },
    cityName: { sql: `city_name`, type: `string`, title: `城市名` },
    cityCode: { sql: `city_code`, type: `string`, title: `城市行政区码` },
    createUserName: { sql: `create_user_name`, type: `string`, title: `创建人名(经dim_user)` },
    currentUserName: { sql: `current_user_name`, type: `string`, title: `当前处理人名(经dim_user)` },
    regionId: { sql: `region_id`, type: `string`, title: `区域ID(无区域字典)` },
    deviceCode: { sql: `device_code`, type: `string`, title: `设备编码` },
    deviceType: { sql: `device_type`, type: `string`, title: `设备类型(源库代码原文)` },
    isFinish: { sql: `is_finish`, type: `boolean`, title: `是否已完成` },
    isOverdue: { sql: `is_overdue`, type: `boolean`, title: `是否超期(仅计划完成时间非空的单有意义)` },
    isRepeatFault: { sql: `is_repeat_fault`, type: `boolean`, title: `是否30天内重复故障(仅故障单口径)` },
    createTime: { sql: `create_time`, type: `time`, title: `创建时间(时间维度)` },
    finishTime: { sql: `finish_time`, type: `time`, title: `完成时间(时间维度)` },
  },
});
