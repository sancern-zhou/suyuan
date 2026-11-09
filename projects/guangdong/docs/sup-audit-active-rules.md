# 工单审核已生效规则说明

> 更新时间：2026-11-09。分支 `project/guangdong` 工作树实测状态。
> 配套文档：规则扩展过程见 `routine-audit-and-sup-station-rules-plan.md`；
> 待业务确认项见 `sup-audit-pending-confirmations.md`。

---

## 一、运行载体与链路

| 任务 | 调度 | 覆盖范围 | 规则集 |
|---|---|---|---|
| `gd_routine_work_order_audit` 常规站 | 每周一 10:00 | Check/SECCheck/SECCheckCnemc/SECFlightCheck/Inspection/WorkRectify 六类主网工单，不限站点与运维单位 | 主网规则目录 77 条 |
| `gd_sup_station_work_order_audit` 组分站 | 每周一 11:30 | SupCheck/SupSECCheck，限 10 家运维单位短名 | SUP_ 档案驱动规则 + 通用规则 |

两个任务均为 `enabled=true`，产物为正式审核报告（`report_ready=true` 时出报告，
否则出待核验清单），不生成任务调度中心审核卡片。

数据链路：源库（Operation_SC_GD）→ `guangdong_ods`（sync_table 增量）→
`guangdong_mart`（dbt 透传/加工，应用只读出口）→ 审核取数
（`ops_work_order_audit_local`）。组分站表单载体 78 张 `sup_rf_*` 表已全部建模进
mart（`sync/gen_passthrough_models.py` 生成，`dbt build tag:daily` 日常刷新），
取数侧按工单号动态发现（`discover_sup_mart_form_tables`），新增分表无需改审核代码。

**执行模式说明**：每周定时任务 `enable_visual=false`，只跑非视觉规则；
照片水印核验、多点曲线视觉识别等视觉规则仅在手动触发（`enable_visual=true`）时执行。

---

## 二、常规站（主网）规则：目录 77 条，全部在线

规则代码位于 `backend/app/services/ops_audit/rules/`，目录登记于
`configs/rule_catalog.yaml`，由 `ops_work_order_audit_engine.audit_dataset` 统一调度。
最近一次真实执行（2026-11-03，377 单）规则命中正常，`report_ready=true`。

按类别分布（条数）：

| 类别 | 条数 | 代表规则 |
|---|---:|---|
| 表单数值逻辑 | 12 | RF_VALUE_FORMULA_MISMATCH（公式复算）、RF_MULTIPOINT_LINEARITY_OUT_OF_RANGE（多点线性）、RF_PM_TEMP_ERROR_MISMATCH（温度误差复算） |
| 表单结果合理性 | 10 | RF_RANGE_OUT_OF_SPEC（检查值超范围）、RF_PM_TEMP_ERROR_OUT_OF_RANGE（±2℃）、RF_PM_PRESSURE_ERROR_OUT_OF_RANGE（±1kPa）、RF_O3_TRANSFER_RESULT_INVALID |
| 时间合理性 | 9 | RF_CHECK_TIME_OUTSIDE_RANGE、RF_MULTIPOINT_DURATION_TOO_SHORT（单点≥7分钟）、RF_CALIBRATION_DATE_EXPIRED、RF_CALIBRATION_INTERVAL_TOO_LONG |
| 附件读数一致性 | 7 | ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH 等（照片读数 vs 表单值，视觉类） |
| 一致性 | 5 | RF_STATION_MISMATCH（表单站点与工单不一致，硬错误）、RF_RANGE_BY_GAS_TYPE_MISMATCH |
| 附件清单 | 3 | ATTACHMENT_REQUIRED_MISSING、ATTACHMENT_REPORT_MISSING |
| 附件时间一致性 | 3 | 两周清洗照片打卡时间、半年维护照片日期 |
| 表单填报一致性 | 3 | RF_ENUM_VALUE_INVALID、RF_POLLUTANT_TYPE_MISMATCH、RF_VISIBILITY_NO_DEVICE_FIELD_CONFLICT |
| 表单完整性 | 7 | RF_ENV_TEMP_HUMIDITY_EMPTY（组分站表已跳过，见误报治理）、RF_RANGE_VALUE_MISSING |
| 填报规范性 | 3 | RF_PM_TAPE_USAGE_INVALID 等 |
| 附件内容质量 | 4 | 多点曲线梯度/水印/O3 六点复核（视觉类） |
| 附件证据复核 / 跨工单 | 3 | O3 量值传递 XLS 缺失、上级标准历史冲突 |
| 其他（规范性/异常说明/语义/结果/一致性/附件质量/诊断） | 12 | RF_NO_DEVICE_WITHOUT_REMARK、REMARK_SEMANTIC_INCOMPLETE 等 |

生效方式说明：目录中带"视觉/OCR/复核"字样的规则属视觉类或语义复核类，
定时任务不执行；确定性规则（区间、复算、时间、一致性、清单）定时任务全量执行。
规则命中后按 `configs/rule_review_stages.yaml` 分流：semantic_remark 进语义复核、
technical_diagnostic 只进诊断统计不进报告、其余进入最终问题清单。

主网两项关键治理（2026-11-09）：
1. `RF_ENV_TEMP_HUMIDITY_EMPTY` 跳过 `SUP_` 前缀表——组分站分表的同名温湿度列
   为源库恒空列，此前造成组分站报告 81% 误报；
2. `FORM_DATA_MISSING` 只判已闭环工单，且归入技术诊断（数据管道覆盖缺口不再
   以"问题工单"名义进入报告，仍在诊断统计可见）。

---

## 三、组分站规则：档案驱动，6+3 个机制，68 个类型建档

组分站规则不看表名看 `ruleitemtag`（表单类型编码），每个类型的题目列语义、
阈值、公式、日期对、异常取值、必需附件都登记在
`configs/sup_form_profiles.yaml`（当前 68 个类型，其中 38 个带内容规则）。

### 3.1 规则机制（9 条，均已登记规则目录并在线）

| 规则 ID | 判定逻辑 | 级别 |
|---|---|---|
| SUP_RANGE_OUT_OF_SPEC | 档案标注阈值列或计算表达式超 min/max；超范围有备注降级人工复核，无备注判失败；支持按 `devicebrand` 分档取区间（品牌无档位则跳过判定） | 高 |
| SUP_FORMULA_RECALC | 档案标注公式列复算（如 PANs 设定误差=（读数−设定值）/设定值×100%），与填写值偏差超容差判失败 | 高 |
| SUP_REQUIRED_VALUE_EMPTY | 档案标注必填数值列为空（"/"+说明备注豁免） | 高 |
| SUP_DATE_REASONABLENESS | 日期对区间/有效期覆盖检查、单日期越界（not_future/not_past） | 高 |
| SUP_ABNORMAL_NO_REMARK | 档案声明异常取值（如标志位=1、勾"异常"），命中且配对备注列与全局备注均空即问题 | 中 |
| SUP_CYCLE_TIMELINESS | 周期表单填写滞后超宽限（周期结束+5 天，试点值）；质控数据文件过期 | 高 |
| SUP_ATTACHMENT_REQUIRED_MISSING | 维护检定类表单按档案要求 report/data_file 类附件，仅有过程照片不满足 | 高 |
| SUP_ATTACHMENT_ITEM_MATCH | 附件文件名/typecode 与表单监测项目、设备类型匹配 | 高 |
| SUP_ATTACHMENT_WATERMARK_STATION | 照片水印地点/坐标/时间与工单站点、检查日期比对（视觉，仅手动触发，试点） | 中 |

### 3.2 已落内容规则的 38 个类型

"验证"列含义：**全量核验**=对该类型全量真实数据逐行验证过阈值（含误报率核查）；
**冒烟命中**=在审核窗口真实数据中产出过正确命中；**单测**=行为由单元测试锁定；
**历史在线**=本会话之前已在线运行。

| 类型 | 显示名 | 规则构成 | 阈值确认 | 验证 |
|---|---|---|---|---|
| Sup_RF_AmbientTemperature | 仪器环境温度和压力校准 | 区间4（温度±2℃/气压±1kPa）+日期2 | 6 确认 | 历史在线 |
| Sup_RF_DeviceFlowCheck（含 PTRMS 变体） | 仪器采样流量核查校准 | 区间4（流量相对误差±5%/示值±2%）+公式4+日期2 | 10 确认 | 历史在线 |
| Sup_RF_HP_DalyHealth | 高精度温室气体每日健康检查 | 区间4 | 4 确认 | 历史在线 |
| Sup_RF_HP_StationCheck | 温室气体站房周检查 | 异常29 | 待确认 | 历史在线 |
| Sup_RF_PANsWeekCheck | PANs 分析仪周巡检 | 区间6（R2≥0.995 等）+异常4 | 6 确认 | 历史在线 |
| Sup_RF_PANsFlowCheck | PANs 流量季度检查 | 区间3+公式3 | 3 确认 3 待确认（A5） | 历史在线 |
| Sup_RF_PANsRepeatabilityCheck | PANs 重复性年度核查 | 区间1（RSD≤3%） | 1 确认 | 历史在线 |
| Sup_RF_PANsWorkCurveCalibration | PANs 工作曲线月校准 | 区间1 | 1 确认 | 历史在线 |
| Sup_RF_OCECJGWeekCheck | OCEC 周巡检（升温程序） | 区间3 | 3 确认 | 历史在线 |
| Sup_RF_OCECJGMultipointCheck | OCEC 多点核查 | 日期1 | 1 确认 | 历史在线 |
| Sup_RF_MSRoutineCheck | 单颗粒质谱日常检查 | 异常11 | 待确认 | 历史在线 |
| Sup_RF_MSQualityCalibration | 单颗粒质谱质量校准 | 异常4+日期1 | 1 确认 | 历史在线 |
| Sup_RF_MSParticleSizeCalibration | 单颗粒质谱粒径校准 | 区间1+日期1 | 1 确认 1 待确认（A8） | 历史在线 |
| Sup_RF_Month_YT_FlowCalibration | 优泰流量传递月校准 | 区间1+日期1 | 1 确认 1 待确认 | 历史在线 |
| Sup_RF_Month_YT_LeakChecking | 甲烷/非甲烷验漏（月） | 区间2 | 2 待确认（A6） | 历史在线 |
| Sup_RF_VocsSceneCheck | VOCs 现场周检查 | 区间2 | 2 确认 | 历史在线 |
| Sup_RF_WeekSecurityCheck | 站房周安全检查 | 区间2+日期1 | 3 确认 | 冒烟命中 |
| Sup_RF_Week_NMHCQC | 甲烷/非甲烷总烃周质控 | 日期2+附件1 | 1 确认 1 待确认（A1/A2） | 冒烟命中 |
| Sup_RF_Week_HONOQC | HONO 质控每周记录 | 区间2 | 2 待确认（A3） | 历史在线 |
| Sup_RF_Week_HONOCheck | HONO 周检查/校准 | 日期1 | 1 待确认（A4） | 历史在线 |
| Sup_RF_VOCsAMASamplingFlowRecord | VOCs 采样流量核查（AMA） | 日期1 | 1 确认 | 历史在线 |
| Sup_RF_PDLIYearCheck | 激光雷达/颗粒物年度检定 | 附件1（缺报告） | — | 冒烟命中 |
| Sup_RF_VocsSinglePoint | VOCs 单点核查每周记录 | 附件1 | — | 历史在线 |
| Sup_RF_WaterSolubleIonsQuality | 水溶性离子质控每周记录 | 附件1 | — | 历史在线 |
| Sup_RF_HeavyMetalQuality | 重金属质控每周记录 | 附件1 | — | 历史在线 |
| Sup_RF_Week_YT_SingleQC | YT 单点质控每周记录 | 附件1 | — | 历史在线 |
| Sup_RF_NH3Calibration（含 CX 变体） | NH3 分析仪校准 | 区间4（流量0.35~0.9/反应室300~350℃/转化炉725~800℃/压力50~150mmHg） | 4 确认 | 全量核验+冒烟命中（2026-11-09） |
| Sup_RF_EquipmentStatus | 设备状态检查 | 区间2（brand_ranges 按 TiH200 分档） | 档位经全量核验 | 冒烟命中（2026-11-09） |
| Sup_RF_GACWeekMaintain | 水溶性离子周维护 | 区间4（brand_ranges 按柱规格双档） | 分档经全量核验（统一区间会误报 53~56%） | 全量核验（2026-11-09） |
| Sup_RF_SpeedMeterMaintain | 速度计维护 | 异常17（isitnormal=1，配对+全局备注豁免） | 方向经数据确认 | 全量核验（2026-11-09） |
| Sup_RF_CO2Inspection | CO2 巡检 | 区间3（气压/流量/内温宽区间） | 3 确认 | 全量核验（2026-11-09） |
| Sup_RF_URGWeekMaintain | URG 周维护 | 区间1（柱压 1500~2500psi） | 1 确认 | 全量核验（2026-11-09） |
| Sup_RF_PM1MonitorInspection_Week | PM1 周巡检 | 异常3（0=正常/1=异常，Vue 映射确认） | 方向确认 | 全量核验+单测（2026-11-09） |
| Sup_RF_PM1MonitorInspection_Month | PM1 月巡查 | 区间1（校准膜±5%） | 1 确认 | 全量核验（2026-11-09） |
| Sup_RF_OcecFlowVerificationCheck | OCEC 流量传递核查 | 区间2 | 2 待确认（A7） | 历史在线 |

### 3.3 仅及时性口径的 30 个类型

`Sup_RF_DailyInspection`（日巡检，数值区间待业务确认 B1）、`RF_D/W_GreenHouseCheck`、
`Sup_RF_VocsFlowCheck`、`Sup_RF_thybWeekCheck`（缺模板映射，见 D 类）、
`Sup_RF_OCECWeekCheck`、`Sup_RF_Week_YT_Check`、`Sup_RF_HY_NMHCMaintenanceRecord`、
`Sup_RF_Month_HONOCheck/Test`、`Sup_RF_PM1MonitorInspection_HalfYear`（标志位方向待确认 C3）、
`Sup_RF_PTR_MSQuality`、`Sup_RF_RULEITEMVOCs`、浊度计 2 类、激光雷达 3 类、
HONO 耗材更换、HP 精度/可比性、OCEC 采样流量/氦甲烷/有机碳、PANs 稳定性、
天虹 VOCs、BJC 检查、YT 季度 NMHC/年度准确度、NMHC 分析仪记录等。
这些类型当前只执行 SUP_CYCLE_TIMELINESS（填写滞后判定），不产出内容判定。

### 3.4 通用护栏

- `FORM_DATA_MISSING`：已闭环工单在数据集中取不到任何表单时，记入技术诊断
  （不进报告问题清单）。补齐 mart 建模后组分站窗口内从 74 降至 18。
- `RF_STATION_MISMATCH` / `check_form_data_missing` / 附件清单规则对两类任务通用。

---

## 四、运行验证状态（2026-11-09 实测）

**任务调度**：两任务在 `backend_data_registry_guangdong/scheduled_tasks/tasks.json`
注册且启用，`suyuan-worker` 服务运行中，下次触发每周一 10:00 / 11:30。

**最近窗口冒烟（10-19~11-03，10 家单位，400 单，无视觉）**：
正式报告 33 条问题 / 26 张工单，`report_ready=true`，构成：
附件项目不匹配 8、周期超期 12、日期异常 6、附件缺失 3、数值超范围 3、必填空 1。
全部为组分站业务规则命中，无结构性误报。

**测试基线**：`app/services/ops_audit/` + 组分站相关用例共 400 通过
（含 `tests/test_sup_form_rules.py` 78 例、`tests/test_sup_false_positive_guards.py` 7 例、
取数分支与动态发现 `ops_work_order_audit_local_sup_test.py` 6 例）；6 个失败均为
本机视觉/OCR 渲染环境问题，与规则逻辑无关（改动前即存在）。

**误报治理基线**（组分站报告问题数变化）：
2026-11-02 实跑 287 条（81% 为温湿度误报）→ 治理后 30 条 → 建档四批后 33 条，
新增命中均为真实问题（NH3 整行错位、设备蠕动泵超流量、日巡检/NH3 及时性等）。

---

## 五、如何复验

```bash
# 单元测试（规则逻辑）
cd backend
M:/suyuan-tools/envs/backend_py311/Scripts/python.exe -m pytest \
  app/services/ops_audit/ tests/test_sup_form_rules.py \
  tests/test_sup_false_positive_guards.py -q

# 端到端冒烟（取数+跑规则+出最终问题清单，不落盘）
#   参照 routine-audit-and-sup-station-rules-plan.md 各批次记录中的脚本要点：
#   fetch_dataset_local(WorkOrderDatasetFilter(...)) -> run_rule_engine(ds, enable_visual=False)

# 手动触发一次完整审核（含取数、规则、语义复核、报告）
#   通过任务调度中心 API 或前端"例行工单审核/组分站工单审核"入口手动执行。
```

新类型建档路径：确认业务口径 → `sup_form_profiles.yaml` 增档案（附证据注释）→
补 `tests/test_sup_form_rules.py` 用例 → 重跑冒烟核对误报率。
