# 组分站工单审核 · 业务待确认清单

> 生成时间：2026-11-09。维护者：审核规则侧（项目分支 `project/guangdong`）。
> 档案文件：`backend/app/services/ops_audit/configs/sup_form_profiles.yaml`。
> 用途：组分站例行工单审核（每周一 11:30 任务 `gd_sup_station_work_order_audit`）
> 的规则以本清单所列业务口径为前提。**每确认一项，规则即可收紧或落地一项**；
> 未确认项按"宁可不出结论、不产生误报"的原则暂时不判或宽判。

确认方式约定：
- **A 类**（已落规则、阈值待确认）：确认后把对应档案项的 `confirmed: false`
  改为 `true` 即生效，无需改代码；
- **B/C 类**（缺口径未落规则）：业务给出口径后由开发按本清单附的证据落规则；
- **D 类**（模板映射）：需提供各类型**表单模板截图或模板配置**（题目顺序），
  用于把实体题号映射到 `sup_rf_common` 宽表的 `string1..150` 列位。

优先级：P1 = 每周 ≥10 单受影响；P2 = 3~10 单；P3 = <3 单或纯未来覆盖。

---

## A 类：已落规则、阈值待确认（确认后置 `confirmed: true` 即收紧）

| 编号 | 类型（窗口单量） | 待确认项 | 当前规则口径 | 数据证据 | 需要确认的问题 |
|---|---|---|---|---|---|
| A1 | Sup_RF_Week_NMHCQC（P1，101 单） | 附件照片水印核验试点 | 抽检 30% + 问题触发全检，站点/时间不一致进人工核验 | 博罗石下案例：附件照片水印=河源站点 | 是否按此口径启用视觉水印核验（成本与抽检比例） |
| A2 | Sup_RF_Week_NMHCQC（P1） | 动态校准仪有效期档位 | 校准→有效期允许 30/90/180/365 天（容差 3 天）且须覆盖检查日期 | 真实数据 261~364 天多种填法并存；案例单 56 天被人工判"日期有误" | 档位表是否正确；标气有效期按"生产日期+1年"还是"启用日期+1年" |
| A3 | Sup_RF_Week_HONOQC（P2，11 单） | 双通道标线相关系数阈值 | string28/string38 ≥ 0.995 | 列语义由近 90 天样本推断 | 列位是否正确；0.995 是否为考核口径 |
| A4 | Sup_RF_Week_HONOCheck（P2，11 单） | 零点/跨度有效期覆盖 | time 对须覆盖检查日期 | 列语义待确认 | time 列语义确认 |
| A5 | Sup_RF_PANsFlowCheck（P2） | 流量设定误差公式 | （仪器读数−设定值）/设定值×100%，逐点复算 | 案例实证：潮州西园路单按流量计读数误算（点 2 填 0.5%，复算应 27.7%）已退回 | 公式分母口径（仪器读数 vs 流量计读数）与容差阈值 |
| A6 | Sup_RF_Month_YT_LeakChecking / Month_YT_FlowCalibration（P3） | 泄漏检查/流量校准区间 | 数据推断区间 | 样本推断 | 区间口径确认 |
| A7 | Sup_RF_OcecFlowVerificationCheck（P2） | ①参考流量计相关系数下限 ②校准前流量偏差 ±5% | ①≥0.99（为贴合数据放宽）②±5%（红字） | 计量认证一般要求 0.999，实际数据下限 0.99 | 相关系数是否收紧到 0.999 |
| A8 | Sup_RF_MSParticleSizeCalibration（P3） | 粒径校准相关系数阈值 | 按"参考范围"列常态 0.98 放宽 | 表单参考范围列即填 0.98 | 是否收紧（计量认证口径） |

---

## B 类：有数据、缺口径，无法落规则（给出口径即落）

| 编号 | 类型（窗口单量） | 现象与数据证据 | 需要业务确认的口径 |
|---|---|---|---|
| B1 | Sup_RF_DailyInspection（P1，25 单） | ①零气加热温度 `string1`：431℃×22、432℃×8 为稳定站内自设值，按文档 400℃ 标称区间判会误报 46/531（8.7%）；②输出压力 `string2/3`：MPa 与 psi 混填（`0.4` 与 `58psi` 并存） | ①各型号仪器零气加热温度的合格区间（是否按站点自设值放宽）；②压力填报单位约定（统一 MPa 还是 psi，或规则内做单位换算） |
| B2 | Sup_RF_GACWeekMaintain（P1，16 单） | ①柱压 `anion/cationpressureresult`：MPa/psi/裸数值混填（`1.86`、`1610`、`6.1Mpa` 并存）；②蒸汽发生器温度列整列填 1/0（状态位，文档标 280~320℃）；③淋洗液剩余量越界仅 2/207 | ①柱压单位与区间；②温度列为何填状态位（模板错位？）；③淋洗液剩余量随消耗降低是否设下限报警 |
| B3 | Sup_RF_GACWeekMaintainByMARGA（P2，5 单） | MARGA 柱压实测 3.77~11.0 离散分布（文档 7~9/4~5 Mpa），无稳定聚集 | MARGA 运行压力正常范围；文档区间是否适用该机型 |
| B4 | Sup_RF_URGWeekMaintain（P2，6 单） | 阳离子水峰流量双稳态聚集：0.25×44 与 0.38×24（文档 0.2~0.3ml/min，0.38 组占 30%） | URG9000D 水峰 0.38 是否属正常运行流量（若属，档位按双区间落） |
| B5 | Sup_RF_MonitorInspection 三变体（P1，Week 65 + Month 17 + Quarter 6 单） | `sup_rf_monitorinspection` 分表列语义化（weekdatacontrol/weekattribute/quarterleaktest 等），但《组分仪器工单规则》文档未给该表型的判定阈值；温湿度列（temperature/humidity）全量恒空 | 该表型的判定项与阈值（周检/月检/季检各查什么）；温湿度列是否为废弃列 |

---

## C 类：标志位方向确认（落异常规则的前提）

| 编号 | 类型 | 现象 | 已确认/待确认 |
|---|---|---|---|
| C1 | Sup_RF_PM1MonitorInspection_Week | Vue 源码映射确认 **0=是/正常、1=否/异常**（2197/2230 行全 0，为 1 的 33 单全部有停运/故障备注） | ✅ 已确认并落规则 |
| C2 | Sup_RF_SpeedMeterMaintain | `*isitnormal` 列 **1=不正常**（=1 行备注"挪机安装调试中"），配对备注列+全局 remarks 豁免 | ✅ 已确认并落规则 |
| C3 | Sup_RF_PM1MonitorInspection_HalfYear | `leakwhether` 约 95% 为 1，与 Week 方向相反（疑 1=不漏气/正常） | ❌ 待确认：各标志位 0/1 语义方向 |
| C4 | Sup_RF_MonitorInspection / HeavyMetalInspection / Week_RadiationRecord 等 | 各分表的 `*isitnormal` / 状态列方向未逐一确认 | ❌ 待确认：逐表确认方向后可批量落 abnormal 规则 |

---

## D 类：表单模板映射需求（宽表类型，阻塞内容规则）

以下类型存于 `sup_rf_common` 306 列宽表，题目项落在 `string1..150 / bool_1..50`
通用列；源码映射文档给的是**实体列名**（如 thyb 的 `ms_1/fid_1/fsq_1`），与宽表
列位无对应关系，列语义文档均标注"占位列，需结合表单模板确认"。
**需要提供：各类型的表单模板（截图或模板配置，含题目顺序）**，用于建立
题号 → 宽表列位映射。已有先例：`Sup_RF_PANsWeekCheck` 即凭模板题号完成映射并落了区间规则。

| 类型 | 全量行数 | 窗口单量 | 备注 |
|---|---:|---:|---|
| Sup_RF_thybWeekCheck（谱育 VOCs 周检） | 279 | 11 | 周检模板已有多仪器分区题号（ms/fid/fsq/mpa/zftj），映射后可直接落十数条区间规则 |
| Sup_RF_VocsFlowCheck | 943 | 14 | |
| RF_D_GreenHouseCheck / RF_W_GreenHouseCheck | 295 | 17 | 温室气体系列，源码三层均未覆盖 |
| Sup_RF_Week_YT_Check | 274 | 4 | |
| Sup_RF_RULEITEMVOCs | 262 | 2 | bool 状态位题目含义需模板核对 |
| Sup_RF_HCHO 系列 4 类 | 各 128 | 0 | 甲醛 CollectPercent/DetectionLimit/MLinearError/RepeatTest |
| Sup_RF_TSI 系列 2 类 | 503 | 0 | TSIRoutineCheck/TSIFlowCheckRecord |
| 其余宽表类型约 20 类 | — | 0~1 | 见覆盖度脚本输出 |

---

## E 类：审核流程参数

| 编号 | 参数 | 当前值 | 依据 | 待确认 |
|---|---|---|---|---|
| E1 | 填写滞后宽限天数（SUP_CYCLE_TIMELINESS） | 周期结束 + 5 天 | 全局分布 ~87% 当天完成、≤4 天占 96.6%，5 天为试点值 | 是否按考核口径调整 |
| E2 | 附件必需类型的纳入门槛 | 近 90 天命中率 <5% 才纳入要求 | 避免把行业常态误报为问题 | 门槛是否认可 |
| E3 | 视觉水印试点范围 | Week_NMHCQC 抽检 30%，单轮 ≤20 任务/≤2 照片 | 控制视觉调用成本 | 抽检比例与扩面节奏（与 A1 合并确认） |

---

## 处理约定

1. 确认结果反馈后：A 类改 `confirmed: true`（规则立即收紧）；B/C 类由开发
   按清单所附证据落规则并补单测；D 类拿到模板后由开发做题号映射。
2. 每项确认请在原文档（或回复）中注明：**口径原文出处**（考核细则/仪器说明书/
   厂商培训材料），档案中会同步登记依据。
3. 本清单随建档进度滚动更新；已解决项会移入
   `routine-audit-and-sup-station-rules-plan.md` 的各批次实施记录。
