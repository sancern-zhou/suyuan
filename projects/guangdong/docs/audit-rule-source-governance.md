# 工单审核规则语义治理（源码口径）

> 2026-11-04 首版。适用对象：`backend/app/services/ops_audit/` 下主网 RF 周检范围规则。
> 目标：把“平台视图正常范围文本”固化为可执行的审核阈值，并让无法判定的事实可观测，而不是静默跳过。

## 0. 归属与分支

本套规则与配置**仅服务广东运维**，经确认保留在 `project/guangdong` 分支，**不按共享层回合 `main`**。
`backend/app/services/ops_audit/**` 虽位于共享路径且 `origin/main` 存在同名文件，该例外以本说明为准；后续改动只在广东工作树发布。

## 1. 权威口径与证据

1. 广东运维平台对 `RF_W_GASEOUSCHECK_CO/NOX/O3/SO2`、`RF_W_PMCHECK` **没有服务端数值校验**，前端也只有 `required` 必填；唯一权威阈值是视图“正常范围”列的 HTML 文本。
2. 证据文件（`D:/广东运维平台/trunk/SummerFresh.MVC/Views/ReportForms/`）：

| 表单 | 视图文件 | 阈值所在行 |
|---|---|---|
| CO | `RF_W_GASEOUSCHECK_CO.cshtml` | 165-302 |
| NOX | `RF_W_GASEOUSCHECK_NOX.cshtml` | 190-415 |
| O3 | `RF_W_GaseousCheck_O3.cshtml` | 157-265 |
| SO2 | `RF_W_GaseousCheck_SO2.cshtml` | 189-336 |
| PM | `RF_W_PmCheck.cshtml` | 53-75 |

3. `*CHECKROW` 是“异常时处理记录”输入框，`*REGION` 是人工填写的范围文本，**都不是阈值**，不建模为审核规则。
4. `DEVICEBRAND` 由设备主数据自动填充为品牌代码（`FPI`/`TE`/…），视图阈值写中文标签；映射统一维护在 `rf_range_profiles.yaml` 顶层 `brand_aliases`。
5. 源码中的可执行数值判定只有 QUL 质控模块（零点/跨度误差、多点校准）；其阈值存放在数据库 `COF_QUL`，不在源码常量里，本轮不复刻。

## 2. 品牌代码与中文标签

| 代码 | 中文标签 | 说明 |
|---|---|---|
| FPI | 聚光 / 聚光科技 | 设备主数据与代码分支均用 `FPI` |
| THERMO | 赛默飞 / 热电 / Thermo | 代码中 `TE` 亦指 Thermo |
| TH | 天虹 / 武汉天虹 | `DEVICEBRAND=="TH"` 时按型号 2001H-2004H 判天虹，否则按 THERMO |
| API | API | 视图文本 |
| EC | EC | 视图文本 |
| ESA | ESA | 视图文本 |
| DASIBI | 大西比 / Dasibi | 视图文本 |
| XH | 新先河 / 先河环保 / 先河 | 视图文本 |
| LD | 力合 / 力合科技 | 业务扩展，源码视图未给阈值（仅 CO 截距保留） |

## 3. 规则结构与行为

代码：`backend/app/services/ops_audit/rules/rf_range_rules.py`；配置：`configs/rf_range_profiles.yaml`。

| 规则 ID | 行为 |
|---|---|
| `RF_RANGE_OUT_OF_SPEC` | 周检字段值超出（表单、行项目、品牌）三元组阈值；带 `needs_semantic_review`，进入候选复核 |
| `RF_RANGE_BY_GAS_TYPE_MISMATCH` | `POLLUTANTTYPE` 与表期望气体不符 |
| `RF_RANGE_UNIT_MISMATCH` | 填报单位与阈值单位不可换算，无法比对（技术诊断，不计工单问题） |
| `RF_RANGE_BRAND_PROFILE_UNCOVERED` | 已填报值无对应品牌阈值，或品牌与型号冲突（技术诊断，用于发现建档缺口） |
| `RF_M_GASEOUS_FLOW_RANGE_MISSING` | 月度流量范围文本缺失 |

结构变更（2026-11-04）：

- 下线引用不存在列的旧配置 `check_value_fields`、`brand_ranges`；保留 `gas_type_mapping`。
- 周检结构化检查与月度流量检查**不再受旧配置总开关控制**（原 `if not check_value_fields: return` 会让有效规则一起停用）。
- 品牌别名改为顶层单一来源，CO/PM 补齐 `聚光` 等别名。
- 支持 `ranges.default`（PM 等无品牌差异字段），品牌为空时也可按默认区间审核。
- 品牌/区间未覆盖不再静默跳过，按表单聚合输出技术诊断。

## 4. 逐表单阈值（源码视图 → YAML）

> 以下仅列与源码对齐后的口径；完整映射见 `rf_range_profiles.yaml` 各字段上方的视图行号注释。

### CO（`RF_W_GASEOUSCHECK_CO`）

字段：`GYCHECKVALUE` 测量信号、`PMTCHECKVALUE` 参比信号、`CBCHECKVALUE` 测量/参比、`CYYLCHECKVALUE` 采样压力、`CYLLCHECKVALUE` 采样流量、`FYCHECKVALUE` 样品温度、`GSWDCHECKVALUE` 光室温度、`GFCCHECKVALUE` 相关轮温度、`YLCHECKVALUE` 斜率、`JGCHECKVALUE` 截距。

| 字段 | API | FPI（聚光） | 赛默飞 | 天虹 | 大西比 | 新先河 | ESA |
|---|---|---|---|---|---|---|---|
| 测量信号 | 2500-4800 mV | 1-4 V | — | 2000-10000 mV | — | 300-3000 mV | — |
| 参比信号 | 2500-4800 mV | 1-4 V | — | 2000-10000 mV | 5000-9000 mV | 300-3000 mV | — |
| 测量/参比 | 1.17-1.22 | 1.1-1.3 | — | — | 两组，不建模 | 2000-4900 mV | — |
| 采样压力 | 25-35 In-Hg-A | 7-15 psia | 250-1000 mmHg | 50-110 kPa | 79-106 kPa | 50-102 kPa | — |
| 采样流量 | 720-880 ml/min | 720-880 sccm | 0.35-1.5 L/min | 300-1200 ml/min | 0.8-1.2 L/min | 900-1100 ml/min | — |
| 样品温度 | 44-52 ℃ | 15-55 ℃ | 8-47 ℃ | — | 20-45 ℃ | 47-49 ℃ | — |
| 光室温度 | 46-50 ℃ | 47-49 ℃ | 40-52 ℃ | 0-60 ℃ | 40-45 ℃ | 47-49 ℃ | 380-500 mV |
| 相关轮温度 | 66-70 ℃ | 66-70 ℃ | — | — | 43-45 ℃ | 58-78 ℃ | — |
| 斜率 | 0.7-1.3 | 0.85-1.15 | 0.5-2 | 0.5-2 | — | 0.7-1.3 | — |
| 截距 | -5~5 mV | -200~500（单位待确认） | >-10.75 ppm | -5~5 ppm | — | -6~6 umol/mol | — |

### NOX（`RF_W_GASEOUSCHECK_NOX`）

| 字段 | API | FPI（聚光） | EC | 赛默飞 | 天虹 | 大西比 | 新先河 | ESA |
|---|---|---|---|---|---|---|---|---|
| 采样流量 | 450-550 ml/min | 350-650 sccm | 0.35-0.7 SLPM | 0.35-0.9 L/min | 300-800 ml/min | 0.15-0.5 L/min | 450-550 ml/min | — |
| 臭氧流量 | 65-95 ml/min | 72-88 sccm | — | >50 mL/min | 30-120 ml/min | 0.02-0.071 L/min | 65-95 ml/min | — |
| 参考 PMT | 0-5000 mV | 1.5-4.096 V | — | — | — | — | -100~5000 mV | 0-9999 mV |
| 高压电源 | 450-900 V | 450-900 V | 640-700 V | -1200~0 V | -1100~-500 V | 500-900 V | — | 500-950 V |
| 反应室温度 | 49-51 ℃ | 49-51 ℃ | 47-53 ℃ | 48-52 ℃ | 45-55 ℃ | 42.5-43.5 ℃ | 49-51 ℃ | 不建模（mV 信号） |
| 转化炉温度 | 310-320 ℃ | 305-350 ℃ | 315-335 ℃ | 300-350 ℃ | 180-360 ℃ | 260-290 ℃ | 310-320 ℃ | — |
| 反应室压力 | <10 In-Hg-A | 0-15 psia | 源码注释，不建模 | — | — | — | 13-34 kPa | 133-433 mV |
| 采样压力 | 25-30 In-Hg-A | 0-15 psia | 75-375 TORR | 150-300 mmHg | 60-110 kPa | 8-40 kPa | 84-102 kPa | 408-610 mV |
| NOx 斜率 | 0.7-1.3 | 0.85-1.15 | — | 0.5-2 | 0.5-2 | — | 0.7-1.3 | — |
| NOx 截距 | -10~150 mV | -20~50 ppb | — | >0 | -50~50 ppb | — | -100~100 mV | — |
| NO 斜率 | 0.7-1.3 | 0.85-1.15 | — | 0.5-2 | 0.5-2 | — | 0.7-1.3 | — |
| NO 截距 | -50~150 mV | -20~50 ppb | — | >0 | -50~50 ppb | — | >=-160 mV | — |

### O3（`RF_W_GASEOUSCHECK_O3`）

| 字段 | API | FPI | ESA | 赛默飞 | 天虹 | 大西比 | 新先河 | EC |
|---|---|---|---|---|---|---|---|---|
| 测量/参比信号 A/B | 2500-4800 mV | 1.5-4.096 V | 500-4800 mV | 45000-150000 HZ | 2300-5200 mV | — | 2000-4900 mV | — |
| 压力 | <=32 In-Hg-A（语义待确认） | 7-15 psia | — | 200-1000 mmHg | 50-110 kPa | 90-106 kPa | 50-102 kPa | 400-800 TORR |
| 采样流量 A/B | 720-880 ml/min | 720-880 sccm | — | 0.4-1.4 L/min | 300-1200 ml/min | 1.2-1.7 L/min | 720-880 ml/min | 0.25-0.55 LPM |
| 样品温度 | 10-50 ℃ | — | — | 15-45 ℃ | 30-70 ℃ | 20-43 ℃ | 0-55 ℃ | — |
| 斜率 | -0.5~2.5 | 0.85-1.15 | — | 0.5-2 | 0.5-2 | — | 0.5-1.5 | — |
| 截距 | -5~5 ppb | -20~50 ppb | — | >-26.5 | -50~50 | — | -5~5 mV | — |

### SO2（`RF_W_GASEOUSCHECK_SO2`）

| 字段 | API | FPI | 赛默飞 | 天虹 | 大西比 | EC | 新先河 | ESA |
|---|---|---|---|---|---|---|---|---|
| 采样压力 | 25-30 In-Hg-A | 7-15 psia | 400-1000 mmHg | 50-105 kPa | 13-79 kPa | 400-800 TORR | 50-102 kPa | — |
| 室采样流量 | 585-715 ml/min | 580-720 sccm | 0.35-0.75 L/min | 300-800 ml/min | 0.5-0.8 L/min | 0.4-0.8 SLPM | 585-715 ml/min | — |
| 参考 PMT | 0-5000 mV | 1.5-4.096 V | — | — | 0-200 mV | 11.6-12.2 V | 0-5000 mV | — |
| 紫外灯光强 | 700-4000 mV | 1.5-4.096 V | 40-100% | 300-5000 mV | 3.5-9.0 V | 1.5-3.5 V | — | 2.0-9.0 V |
| 斜率 | 0.7-1.3 | 0.85-1.15 | 0.5-2 | 0.4-2 | — | — | 0.5-1.5（override，见 §5） | — |
| 截距 | <250 mV | -20~50 ppb | >0 | -50~50 ppb | — | — | <250 mV | — |
| 高压电源 | 400-900 V | 400-900 V | -1200~-500 V | -1100~-500 V | 600-900 | 630-730 V | 450-900 V | — |
| 反应室温度 | 49-51 ℃ | 45-55 ℃ | 43-47 ℃ | 45-55 ℃ | 32-45 ℃ | 47-53 ℃ | 49-51 ℃ | — |

### PM（`RF_W_PMCHECK`）

| 字段 | 阈值 | 说明 |
|---|---|---|
| `MAINFLOWVALUE` 流量 | 15.87-17.54 L/min | `default`，不区分品牌 |
| `AIRTEMPVALUE` 采样管温度 | <=50 ℃ | `default`，不区分品牌 |

## 5. 显式 override 与待业务确认

| # | 条目 | 源码口径 | 当前处置 | 待确认 |
|---|---|---|---|---|
| 1 | CO 截距 FPI | `-200～500`，未标单位 | 暂按数值区间 `-200~500` 审核 | 单位是 mV 还是 ppm |
| 2 | SO2 新先河斜率 | `0.1～0.3` | **override 保留 0.5~1.5**（源码疑为笔误，避免大面积误判） | 是否确为 0.1-0.3 |
| 3 | O3 API 采样压力 | “环境压力-2 In-Hg-A” | 保留 `<=32 In-Hg-A` | 精确语义 |
| 4 | NOX EC 反应室压力 | 源码 `75-300 TORR` 被 Razor 注释 | 不建模 | 是否恢复 |
| 5 | NOX ESA 反应室温度 | 源码给 `1350～1450 mV`（信号，非温度） | 不建模，仅技术诊断 | 是否需要按 mV 审核 |
| 6 | CO 大西比测量/参比 | 零气/标气两组区间 | 不建模，仅技术诊断 | 是否需要双区间建模 |

## 6. 行为变化清单（2026-11-04）

| 表单 | 字段 | 变更前 | 变更后 |
|---|---|---|---|
| CO | 采样流量 FPI | 400-1200 sccm | **720-880 sccm** |
| CO | 光室温度 FPI | 46-50 ℃ | **47-49 ℃** |
| CO | 斜率 FPI | 0.7-1.3 | **0.85-1.15** |
| CO | 截距 FPI | 1-1.5 ppm | **-200~500（单位待确认）** |
| CO | 测量信号/参比信号/测量参比/样品温度/相关轮温度 | 未配置 | **新增，按视图品牌阈值** |
| NOX | 采样流量 FPI | 400-600 | **350-650** |
| NOX | 臭氧流量 FPI | 60-100 | **72-88** |
| NOX | 参考 PMT FPI | 0-4.096 V | **1.5-4.096 V** |
| NOX | 高压 FPI | 400-1200 V | **450-900 V** |
| NOX | 反应室温度 FPI | 48-52 ℃ | **49-51 ℃** |
| NOX | 反应室压力 FPI | 0-6 psia | **0-15 psia** |
| NOX | 采样压力 FPI | 7-15 psia | **0-15 psia** |
| NOX | NOx/NO 斜率 FPI | 0.7-1.3 | **0.85-1.15** |
| NOX | 反应室压力/温度 新先河 | 未配置 | **13-34 kPa / 49-51 ℃** |
| O3 | 采样流量 FPI | 400-1200 sccm | **720-880 sccm** |
| O3 | 斜率 FPI | 0.7-1.3 | **0.85-1.15** |
| SO2 | 采样流量 FPI | 350-1000 sccm | **580-720 sccm** |
| SO2 | 参考 PMT FPI | 0-4.096 V | **1.5-4.096 V** |
| SO2 | 紫外灯光强 FPI | 1-4.096 V | **1.5-4.096 V** |
| SO2 | 斜率 FPI | 0.7-1.3 | **0.85-1.15** |
| SO2 | 反应室温度 FPI | 48-52 ℃ | **45-55 ℃** |
| PM | 流量 FPI | 15.84-17.50 L/min | **default 15.87-17.54 L/min** |
| PM | 采样管温度 | 仅 THERMO<=50℃ | **default <=50℃（全品牌）** |

## 7. 验证

- 新增参数化测试：`backend/app/services/ops_audit/rules/test_rf_range_source_alignment.py`（覆盖 5 张表 × 品牌 × 字段边界、别名归一、default 区间、诊断规则）。
- 更新：`rf_range_rules_test.py`（NOX XH/ESA 用例、FPI 视图口径）、`backend/tests/test_ops_audit_rule_coverage.py`、`backend/tests/test_ops_audit_phase2_modularization.py`（移除 DISPLAYVALUE 旧路径断言）。
- 运行：`cd backend && D:\conda\python.exe -m pytest tests app -q`（需同时收集 `tests` 以加载 fcntl 打桩）。
- 结果：规则相关测试集从基线 13 failed / 264 passed → 10 failed / 357 passed；剩余 10 个失败均为本次无关的既有问题（`select_final_rf_form_versions`、附件/评分/多点视觉用例）。
- 影子回算：本机未配置 `OPS_MART_DATABASE_URL`，无法跑 90 天回放；边界单测已覆盖阈值两侧。部署机具备 mart 时建议按表单分批回算，重点观察 CO（新增 6 字段）和 FPI 流量收紧带来的候选量。

## 8. 后续（不在本轮）

- 组分站 5 处 `confirmed=false` 疑误（HONOQC 列位、HONOCheck 日期、YT 验漏、PANsFlowCheck 公式、NMHCQC 档位）仍需业务确认。
- QUL 零点/跨度漂移规则未复刻（阈值在数据库 `COF_QUL`）。
- `ops_work_order_audit_engine.py` 内 `FORM_RANGE_PROFILES` 等死代码与 `select_final_rf_form_versions` 空实现待单独清理。
