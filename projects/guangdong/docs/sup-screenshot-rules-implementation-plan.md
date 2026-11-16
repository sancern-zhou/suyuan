# 组分站截图规则实施方案：视觉/非视觉分轨 + 实证落档 + 真实工单验证（2026-11-14）

> 目标：把《组分仪器工单规则》（22 类仪器 239 张截图，核查报告见 `implementation-audit-2026-11-14.md`，约 466 条规则点）
> 落地为可运行审核规则，架构与常规站审核对齐——**非视觉（档案驱动确定性判定）与视觉（照片/水印多模态）分轨**，
> 并在真实工单窗口上验证：**识别真问题、不产噪音**。

## 1. 与常规站审核的对齐口径

常规站审核链路 = 非视觉块（rf_* 确定性规则）→ 视觉块（照片读数/水印多模态，`enable_visual` 开关）→ 语义复核 → 复核阶段分轨（`rule_review_stages.yaml`：semantic_remark / flow_visual / manual_visual_review / manual_evidence_review / technical_diagnostic / future_ocr / excluded）。

组分站对齐现状（引擎已具备，无需新架构）：

| 常规站机制 | 组分站对应 | 状态 |
|---|---|---|
| 非视觉确定性规则 | `sup_form_rules` + `sup_attachment_rules`，档案驱动（`sup_form_profiles.yaml` 按 RULEITEMTAG） | 已运行，本方案补档案 |
| 视觉块开关 | `OpsWorkOrderAuditConfig.enable_visual / enable_non_visual` 引擎级开关；组分站视觉目前=水印抽检试点（`sup_watermark_rules`，`manual_visual_review` 阶段） | 已运行 |
| 复核阶段分轨 | `rule_review_stages.yaml` 按 rule_id 通用映射（SUP_ATTACHMENT_WATERMARK_* 已在列），新规则按阶段登记即可 | 已运行 |
| 超范围备注降级 | range_columns 配 remark_column 后引擎自动"超范围+有效备注→中风险人工复核" | 已运行 |
| 语义批量复核 | 备注/文件名批量 LLM 复核器（不可用时回退确定性判定） | 已运行 |

**本方案新增的"分轨"动作**：把截图规则全集显式归入三类，并在档案中落 `review_track` 元数据注释（纯文档层），
保证任何一条截图规则的去向可追溯：本轮非视觉落地 / 视觉（试点或明确不做）/ 需新机制（立项排队）。

## 2. 截图规则三分类（466 条规则点的去向）

1. **非视觉-档案驱动（本轮主战场）**：数值范围、公式复算、日期档位/有效期、必填、勾选异常+备注、填写及时性、
   附件元数据（report/data_file 存在性）。判定输入全部来自表单列，无照片依赖。
2. **视觉-照片/水印（试点或明确不做）**：照片读数与表单一致性、维护时间与照片一致、水印地点/时间核验。
   当前引擎仅 `Sup_RF_Week_NMHCQC` 水印抽检试点。**本轮不新增视觉规则**——照片读数比对需要逐仪器模板与
   读数解析，噪音风险最高；统一进入批次 3 立项评估，档案中以 `visual_pending` 注释占位。
3. **需新机制**：质控 xlsx 内容判读（R²/偏差/-999/检出限）、条件式照片附件、跨工单频次、双阈值二选一
   （"≤±1%FS 或 10ppm"）、时分秒/科学计数法解析、指定模板符合性。登记在核查报告 §三，不在本轮实现。

## 3. 噪音控制八条军规（每条新规则必须逐条过）

1. **实证落档**：列语义必须"映射文档标签 + 数据分布"双证；未经实证的列不配规则。
2. **宁缺勿噪**：拿不准的规则宁可"未配清单留痕"，不上线猜测性判定。
3. **越界率门槛**：range 全量越界率 >5% 的规则不得直接判失败——配 `remark_column` 联动转人工复核，或暂缓待业务确认。
4. **勾选有据**：abnormal_columns 仅在勾选列有区分度（非全 0/全 1）且异常方向经数据确认后配置。
5. **品牌分档**：跨品牌混填（单位/量级不同）必须 `brand_ranges` 分档，品牌未命中直接跳过（宁漏报不误报）。
6. **红字为准**：阈值以文档红字/红框原文为准（核查报告已勘误转录错误）；转录与截图冲突以截图为准。
7. **附件门槛**：required_attachments 仅在近 90 天命中率 ≥5% 时纳入（避免把行业常态误报为问题，沿用既有口径）。
8. **confirmed 分级**：红字+双证 → `confirmed: true`；数据推断 → `confirmed: false`（问题降级人工复核口径待确认）。

## 4. 实施批次

### 批次 1（本轮，2026-11-14）：31 个高数据量 tag 的非视觉建档

按数据活跃度（近 120 天）选定为三组，由档案工程师按军规逐 tag 实证起草，主代理复核合并：

| 组 | tag（数据表） | 近120天 |
|---|---|---|
| A：NH3+浊度计 | NH3ConversionRate(17)、NH3DeviceMultipoint(7)、NH3GASEOUSCALIDEVICECHECK(4)、NH3AnalyzerInspection_HalfYear(9)、NH3InstrumentPrecision(2)、NH3MonthDeviceMaintain(34)、NH3ResponseTimeInspection(5)、Turbidimeter_Week/Month/Quarter/HalfYear(sup_rf_turbidimeter, 24) | — |
| B：CO2+臭氧雷达 | CO2Inspection 扩展(35)、CO2MulityPointCheck_Q(13)、Co2Analyzerinspection_HalfYear(4)、CO2DeviceMaintain(29)、CO2HalfYearDeviceMaintain(3)、CO2YearDeviceMaintain(0)、O3LaserRadarCheck(32)、O3LaserRadarMaintenance(12)、O3LaserRadarCalibration(7) | — |
| C：重金属+辐射+OCEC+PTR | HeavyMetalInspection(52)、LeakageRateCalibration_i(6)、Week_RadiationRecord(43)、Year_RadiationCalibration(7)、PTRMSWeekCheck(4)、OCECSingleCheck(16)、OCECMonthCheck(15)、OCECMultipointCheck(5)、OCECQuarterhCheck(2)、OCECHalfYearCheck(4)、OCECYearCheck(3) | — |

取数层零改动（`discover_sup_mart_form_tables` 已动态发现全部 sup_rf_% 分表，分表行自带 RULEITEMTAG）。

### 批次 2（本轮验证后视结果）：既有档案补勾选/日期（VOCs/NMHC/HONO/OCEC 周检勾选、PM1 Month/HalfYear 勾选等）
### 批次 3（立项评估）：视觉规则（照片读数比对、维护时间-照片一致、水印扩面）与需新机制清单（核查报告 §三）

## 5. 真实工单验证方案（噪音量化）

1. **窗口**：本地 guangdong_mart 近 8 周 SupCheck 工单（`create_time` 窗口，`order_types=["SupCheck"]`，
   `OPS_AUDIT_DATA_SOURCE=local`），先跑 `enable_visual=False`（隔离非视觉噪音），再全量。
2. **逐规则命中统计**：按 rule_id 统计命中单数/命中条数/涉及站点数，输出命中分布表。
3. **抽样核实**：每个新增规则抽 3~5 条命中，回查表单原始值与文档阈值，人工判定"真问题/误报/待确认"。
4. **治理准则**：
   - 抽检误报率 >50% 的规则：当场修正阈值或停用（`enabled: false` + 注明原因与日期）；
   - 命中集中于单一站点/单一品牌的规则：检查是否需要 brand_ranges/站点档位；
   - 命中率 100% 的"常态规则"（如全表都填某值）：视为判定口径错误，撤下；
   - 治理动作全部回写 YAML 注释与验证报告，保持可追溯。
5. **验收线**：新增规则无"系统性误报"（同一错误口径 ≥5 单）；抽检可解释率 ≥80%；整体新增命中量与
   站点/仪器分布合理（不集中于个别站）。

## 6. 产物清单

- 设计方案（本文档）
- `sup_form_profiles.yaml` 批次 1 新增/扩展档案（31 tag，逐条实证注释）
- 验证报告：窗口、逐规则命中统计、抽样核实结论、治理动作（`sup-batch1-validation-2026-11-14.md`）
- 守门：现有 `test_ops_audit_config_yaml_integrity.py` + sup 规则测试全绿
