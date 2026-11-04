# sup_form_profiles 无档案类型扩面记录（2026-11-03）

- 背景：扩面前档案仅覆盖 sup_rf_common 94 个 ruleitemtag 中的 26 个，全量行覆盖 53.7%；
  近 60 天活跃类型中 28 个无档案（工单进来只走通用检查，表单内容零审核）。
- 列语义证据：`opa-source-field-mappings.md`（运维平台实体注释 + cshtml 视图标签），
  并逐列经 `guangdong_mart.sup_rf_common` 数据分布复核（取值区间/枚举分布/备注列互证）；
  阈值优先取视图标签自带判据，其次《组分仪器工单规则》红字（±5% 流量误差，与
  Sup_RF_DeviceFlowCheck 同口径），无据可查的不设阈值并标 `confirmed: false`。
- 引擎扩展：`sup_form_rules.check_date_columns` 新增 `single_date_rule: max_age_days`
  （单参考日期时效，如"防雷检定日期+有效期1年"）；原 `not_past` 语义是"日期不得早于
  检查日"，用于存检定日期的字段会 88% 误报（407 行分布：中位 174 天，404 行 ≤370 天）。
- 布尔勾选列两条铁律（本次数据实证得出，后续建档沿用）：
  1. 数据全 0 的 bool 列 = 运维未使用勾选框，一律不设异常值规则（WeekSecurityCheck 37 项、
     VocsSceneCheck 25 项均因此跳过）；
  2. 周期性"执行标记"类 bool（维护/更换是否执行，常态为 0）不设规则（PRInspectionRecord
     bool_7~12、MSRoutineCheck bool_13）；仅状态类 bool（常态 ≥90% 为 1）配 `values: ["0"]`。

## 本次新增（28 个 tag，档案 30→56）

带内容检查（11 个）：
- Sup_RF_HP_DalyHealth（日检）：加热盒/腔室温度 45±1℃、腔压 140±1 Torr、H2O<0.05%（标签自带阈值）
- Sup_RF_WeekSecurityCheck（周检）：站房温度 25±5℃、湿度 ≤80%、防雷检定 max_age_days=370
- Sup_RF_PRInspectionRecord（周检）：仪器状态/接收头清洁/水汽/夜间信号/微量泵/气密性 6 项 bool=0 异常
- Sup_RF_HP_StationCheck（周检）：站房 29 项检查 bool=0 转人工复核
- Sup_RF_VocsSceneCheck（周检）：站房温度 <25℃、湿度 <80%（remark1/2 备注降级）
- Sup_RF_MSRoutineCheck（周检）：质谱 11 项状态 bool=0 异常
- Sup_RF_Month_YT_FlowCalibration（月）：氦气通道流量误差 ±5%；参考流量计校准有效期覆盖检查日
- Sup_RF_OCECJGMultipointCheck（季）：蔗糖溶液有效期覆盖检查日
- Sup_RF_OcecFlowVerificationCheck（半年）：相关系数 ≥0.99、校准前偏差 ±5%
- Sup_RF_MSQualityCalibration（季）：四个质量数结果填"异常/不合格"即问题；校准有效期覆盖检查日
- Sup_RF_MSParticleSizeCalibration（季）：粒径校准 R2 ≥0.98（表单参考范围列常态值，待业务确认收紧）

仅及时性口径（17 个）：VocsFlowCheck、Week_YT_Check、thybWeekCheck、Month_HONOCheck、
Month_HONOTest、PTR_MSQuality、Week_THLiDAR、Week_FKXLiDAR、HONOConsumablesReplace、
OCECWeekCheck（实体自定义列名 tb1bz*，common 投影未覆盖）、HP_Comparability、
Year_YT_AccuracyRecord、Month_THLiDAR、RULEITEMVOCs、VOCsAMASamplingFlowRecord（含校准有效期对）、
RF_D/R_W_GreenHouseCheck（源码三层未覆盖，周期按数据间隔推断）。

## 干跑验证（2026-09-01 以来真实表单，规则单跑不含附件/水印）

| 类型 | 表单数 | 命中 |
| --- | --- | --- |
| HP_DalyHealth | 442 | 及时性 34 高；范围 6 中 + 1 高（H2O 0.5，有备注降级复核） |
| WeekSecurityCheck | 423 | 温度/湿度 3 高；防雷检定超 370 天 3 高（修复前 not_past 误报 371） |
| PRInspectionRecord | 101 | 仪器状态=0 无备注 3 中 |
| VocsSceneCheck | 45 | 温度超 25℃ 1 中（有备注）+ 1 高 |
| 其余 | - | 0 命中（Month_YT_FlowCalibration 1 例"有效期早于起始日期"为真实填写错误） |

## 扩面后覆盖

- 档案 58 个；tag 覆盖 54/94；全量行覆盖 53.7% → **95.6%**；近 60 天行覆盖 **100%**（2537/2537）。
- 待办：① 40 个存量休眠 tag（2021-2023 旧表单）暂不建档；② 17 个仅及时性档案待补内容规则
  （前提：分表接入或源码补充列语义）；③ MS 粒径 R2、OCEC 流量相关系数等阈值待业务确认；
  ④ string150"数据文件名称"类表单（MS 系列/激光雷达巡检）可评估加 data_file 附件要求
  （需先核附件历史满足率，避免放量）。
