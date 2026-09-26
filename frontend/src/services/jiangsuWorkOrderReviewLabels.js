// 工单审核界面术语表：后端标识 → 面向环境管理用户的中文表达。
// 约定（UI 设计规范 §5）：内部字段名、状态码、枚举原值一律不得直接渲染，
// 必须经本模块转换；未登记的值回退为业务化兜底文案，而不是原样透出。

export const SOURCE_STATUS_LABELS = {
  success: '已获取',
  empty: '无数据',
  partial: '部分获取',
  failed: '获取失败',
  unavailable: '暂不可用',
  skipped: '未采集',
}

export const CHECK_STATUS_LABELS = {
  pass: '通过',
  fail: '不通过',
  uncertain: '不确定',
  not_applicable: '不适用',
}

export const CHECK_SCOPE_LABELS = {
  core: '核心',
  rebuttal: '反证',
  auxiliary: '辅助',
}

export const DECISION_LABELS = {
  pass: '通过',
  confirm: '通过',
  reject: '退回',
  needs_evidence: '退回补证',
}

export const DATA_IMPACT_LABELS = {
  exclude: '剔除',
  partial_exclude: '部分剔除',
  include: '保留',
  none: '无影响',
  pending: '待确认',
}

export const OPERATION_ACTION_LABELS = {
  feedback: '反馈',
  archive: '归档',
  reject: '退回',
  reopen: '重新打开',
  start_disposal: '转入处置',
}

export const WORK_ORDER_FACT_LABELS = {
  workingOrderCode: '工单号',
  orderTitle: '标题',
  orderContent: '内容',
  describe: '描述',
  deviceInfo: '设备',
  faultDevice: '故障设备',
  createTime: '创建时间',
  completeTime: '办结时间',
  orderStatus: '状态',
  statusStr: '状态',
  siteName: '站点',
  stationName: '站点',
  address: '地址',
  orderType: '类型',
  emergencyLevel: '紧急程度',
  urgency: '紧急程度',
  windowStart: '开始时间',
  windowEnd: '结束时间',
  pollutant: '污染物',
}

const ENV_POWER_COLUMN_LABELS = {
  StationTemp: '站房温度',
  StationHum: '站房湿度',
  IA: 'IA 电流',
  IB: 'IB 电流',
  IC: 'IC 电流',
  VA: 'VA 电压',
  VB: 'VB 电压',
  VC: 'VC 电压',
  PipeTemp: '总管温度',
  PipeHum: '总管湿度',
  SamplePipeSPress: '总管静压',
  SampleFlow: '采样流量',
  SamplePipeStay: '滞留时间',
  SO2GasPressAD: 'SO₂ 钢瓶压力',
  NOxGasPressAD: 'NOx 钢瓶压力',
  COGasPressAD: 'CO 钢瓶压力',
  SmokeState: '烟感状态',
  SampleTemp: '采样温度',
  SampleHumi: '采样湿度',
  HeatPower: '加热功率',
  HeatTemp: '加热温度',
  PumpPower: '采样泵功率',
  SampleAirTemp: '采样气温度',
  SampleAirHumi: '采样气湿度',
}

export const TABLE_COLUMN_LABELS = {
  time: '时间',
  timePoint: '时间',
  value: '数值',
  alarmTime: '告警时间',
  alarmContent: '告警内容',
  alarmLevel: '告警级别',
  qcType: '质控类型',
  sStart: '开始时间',
  sEnd: '结束时间',
  result: '质控结果',
  min: '同城最低',
  median: '同城中位',
  max: '同城最高',
  target: '本站',
  ...ENV_POWER_COLUMN_LABELS,
}

export const TABLE_PREFERRED_COLUMNS = {
  alarms: ['alarmTime', 'alarmContent', 'alarmLevel'],
  qc: ['qcType', 'sStart', 'sEnd', 'result'],
  band: ['time', 'target', 'min', 'median', 'max'],
  env_power: ['timePoint'],
}

function normalize(value) {
  return String(value ?? '').trim()
}

function labelFrom(map, key, fallback = '') {
  const text = normalize(key)
  if (!text) return fallback
  return map[text] || fallback
}

export function sourceStatusLabel(status) {
  return labelFrom(SOURCE_STATUS_LABELS, status, '状态未知')
}

export function checkStatusLabel(status) {
  return labelFrom(CHECK_STATUS_LABELS, status, '未知')
}

export function checkScopeLabel(scope) {
  return labelFrom(CHECK_SCOPE_LABELS, scope, '辅助')
}

export function decisionLabelOf(decision) {
  return labelFrom(DECISION_LABELS, normalize(decision).toLowerCase(), '—')
}

export function dataImpactLabel(decision) {
  return labelFrom(DATA_IMPACT_LABELS, normalize(decision).toLowerCase(), '待确认')
}

export function operationActionLabel(action, providedLabel) {
  return normalize(providedLabel) || labelFrom(OPERATION_ACTION_LABELS, action, '操作')
}

export function workOrderFactLabel(key) {
  return labelFrom(WORK_ORDER_FACT_LABELS, key, '')
}

// 源平台工单详单（wo 主表）字段补充标签：命中 WORK_ORDER_FACT_LABELS 的沿用原标签。
export const WO_DETAIL_LABELS = {
  workingOrderCode: '工单号',
  orderTitle: '工单标题',
  orderContent: '工单内容',
  otherContent: '补充内容',
  describe: '描述',
  faultPhenomenon: '故障现象',
  faultReason: '故障原因',
  treatAdvice: '处理建议',
  dealContent: '处置内容',
  dealTime: '处置时间',
  finishTime: '办结时间',
  finishUserName: '办结人',
  createUserName: '创建人',
  updateUserName: '更新人',
  handler: '处理人',
  handlerName: '处理人',
  modifyTime: '更新时间',
  updateTime: '更新时间',
  orderStatusStr: '工单状态',
  orderTypeStr: '工单类型',
  urgencyTypeStr: '紧急程度',
  operationUnitName: '运维单位',
  issuedTypeStr: '下发方式',
  orderCreateTypeStr: '创建方式',
  workFlowStatusStr: '流程状态',
  currentPointName: '当前节点',
  currentPoint: '当前节点',
  prevPoint: '上一节点',
  city: '城市',
  emergency: '紧急程度',
  emergencyDegree: '紧急程度',
  orderSource: '工单来源',
  // 站点编码只认字符串字段；wo.stationCode 是平台序列化残留（System.Collections…），不登记即不渲染
  stationCodeStr: '站点编码',
  uniqueCode: '站点唯一编码',
  remark: '备注',
  isMakeup: '是否补录',
  deviceInfo: '设备',
  processStepName: '流程节点',
  processTimeStr: '处理时间',
  processEdtTime: '处理完成时间',
  processUserName: '处理人',
  submitRemark: '处置说明',
  deviceTypeName: '设备类型',
  deviceBrand: '设备品牌',
  deviceModel: '设备型号',
  deviceCode: '设备编号',
  deviceStats: '设备状态',
  useDate: '启用日期',
}

export const WO_FIELD_ORDER = [
  'workingOrderCode', 'orderTitle', 'orderTypeStr', 'orderType', 'urgencyTypeStr', 'emergencyLevel', 'urgency',
  'orderStatusStr', 'orderStatus', 'statusStr', 'createTime', 'finishTime', 'completeTime',
  'operationUnitName', 'siteName', 'stationName', 'stationCodeStr', 'stationCode', 'uniqueCode', 'address', 'city',
  'deviceInfo', 'faultPhenomenon', 'faultReason', 'orderContent', 'otherContent', 'describe',
  'dealContent', 'treatAdvice', 'remark',
  'createUserName', 'handler', 'handlerName', 'finishUserName', 'currentPointName', 'currentPoint', 'prevPoint',
  'workFlowStatusStr', 'issuedTypeStr', 'orderCreateTypeStr', 'modifyTime', 'updateTime',
]

export const DEVICE_SECTION_LABELS = {
  faultDevice: '故障设备',
  changeDevice: '更换设备',
}

export const WORKFLOW_STATUS_LABELS = {
  0: '未开始',
  1: '进行中',
  2: '已完成',
  3: '已跳过',
  '-1': '已取消',
  done: '已完成',
  doing: '进行中',
  todo: '未开始',
}

// 处置过程（details）行的时间/处理人/内容/节点候选字段（源平台实际字段：processTimeStr/processUserName/submitRemark/processStepName）
export const DETAIL_TIME_KEYS = ['processTimeStr', 'processEdtTime', 'createTime', 'timePoint', 'handleTime', 'dealTime', 'updateTime']
export const DETAIL_USER_KEYS = ['processUserName', 'handlerName', 'userName', 'createUserName', 'operatorName', 'handler', 'dealUserName']
export const DETAIL_CONTENT_KEYS = ['submitRemark', 'processContent', 'content', 'description', 'dealContent', 'handleContent', 'remark']
export const DETAIL_STEP_KEYS = ['processStepName', 'stepName', 'taskName', 'nodeName']

// 平台枚举原值 → 中文（payload 里没有对应 *Str 字段时兜底翻译，避免 Doing / DeviceFault 这类原值透出）
export const WO_ENUM_VALUE_LABELS = {
  Fault: '故障单',
  Doing: '处理中',
  Done: '已办结',
  Finish: '已办结',
  Finished: '已办结',
  ToAssign: '待分配',
  Normal: '正常',
  Urgent: '紧急',
  DeviceFault: '设备故障',
  DeviceNormal: '设备正常',
  DeviceStop: '设备停用',
  Manual: '手动',
  Auto: '自动',
  True: '是',
  False: '否',
}

// payload 里同时存在原值与 *Str 中文字段时，原值字段直接丢弃（不参与渲染）。
export const WO_RAW_ENUM_KEYS = new Set([
  'orderType', 'orderStatus', 'workFlowStatus', 'urgencyType', 'orderCreateType', 'issuedType',
  'processType', 'faultProcessType', 'userType', 'deviceStatus',
])

export function woValueLabel(value) {
  const text = normalize(value)
  return WO_ENUM_VALUE_LABELS[text] || text
}

export function woDetailLabel(key) {
  // 未登记字段一律不渲染（规范 §5：内部字段名不得原样透出），而不是回退成原始键名。
  return labelFrom(WORK_ORDER_FACT_LABELS, key, '') || labelFrom(WO_DETAIL_LABELS, key, '')
}

export function workflowStatusLabel(status) {
  if (status == null || status === '') return { text: '', key: 'unknown' }
  const raw = typeof status === 'number' ? status : normalize(status)
  const text = WORKFLOW_STATUS_LABELS[raw]
  if (text) return { text, key: text === '已完成' ? 'ok' : (text === '进行中' ? 'info' : 'unknown') }
  return { text: String(status), key: 'unknown' }
}

export function columnLabel(key) {
  return labelFrom(TABLE_COLUMN_LABELS, key, '')
}
