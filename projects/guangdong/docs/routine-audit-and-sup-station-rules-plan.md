# 例行工单每周审核与组分站审核规则扩展方案

> 生成时间：2026-10-25；**同日已确认并实施一期**（见文末"实施记录"）。业务决策：组分站与常规站审核流程一致，**拆分为两个每周定时任务**分别生成审核报告，便于维护与优化。

---

## 一、现状核查结论（实施前）

### 1.1 为什么这次部署没有看到每周例行审核任务

| 事项 | 核查结果 |
|---|---|
| 审核规则（常规站） | **已部署且在线**：共享层 `backend/app/services/ops_audit/`（30+ 规则模块、15 个配置、55+ 条规则目录），取数工具已本地化到 PG（428d8608），ops 模式提示词已引用，技能 `ops_work_order_audit` 存在于 `backend/docs/skills/` |
| 每周例行审核定时任务 | **从未存在过**：全仓库所有分支（guangdong/main/xuchang/jiangxi/jiangsu）的 `projects/guangdong/scheduled_tasks/` 均无该任务 JSON，本地数据库持久存储中也只有既有 5 个任务——不是本次部署丢失，是从来没有落过任务配置 |
| 本次新建任务 | `gd_routine_work_order_audit`（每周一 10:00）已创建并注册；首次手动触发在技能加载即失败（0.45 秒，未实际跑审核），原因=任务里技能 ID 写了连字符 `ops-work-order-audit`，磁盘文件是下划线 `ops_work_order_audit.md`。**已修复为下划线并离线验证解析通过** |
| 规则引擎基线 | 单测 224 通过 / 7 失败，失败全部为视觉证据/OCR 渲染类（本机环境差异，上一提交同样失败），核心确定性规则测试全绿 |

### 1.2 组分站规则的缺口是结构性的

- 常规站（主网）表单：一类表单一张表（RF_W_INSPECTION、RF_M_GASEOUSFLOWCHECK 等 33 张分表），规则引擎的取数清单 `RF_TABLES` 只含这些表。
- 组分站（SupCheck 组分网巡检等）表单：全部进**通用宽表 `sup_rf_common`**（Sup_RF_Common，306 列，一行=一张表单体）。实测今年窗口内已有 **10001 张 SupCheck 表单**（另有组分网停运单 15、温室巡检 61），`processtype` 列全空。
- 结论：现有 55+ 条规则中，绑定主网表单/字段的约 40 条对组分站**天然不命中**（表单不在取数范围），这是"还没有针对组分站搭建审核规则"的技术根源。

## 二、现有规则的通用性分类

| 类别 | 规则 | 组分站可复用性 |
|---|---|---|
| 工单-表单一致性 | RF_STATION_MISMATCH、RF_CHECK_TIME_OUTSIDE_RANGE | 复用（后者按字段名匹配检查日期，需把 sup_rf_common 的 `checkdate` 加入字段 profile） |
| 必填/低值/审核人 | RF_REQUIRED_FIELD_LOW_VALUE、RF_AUDITOR_EMPTY、RF_ABNORMAL_VALUE_NO_REMARK 等 | **字段 profile 加别名后复用**（sup_rf_common 有 prepareuserid/reviewuserid/audituserid/devicecode/devicebrand/devicemodel 等同义字段） |
| 附件 | ATTACHMENT_CERT/REPORT/REQUIRED_MISSING、照片水印时间类 | 复用（附件仍走 wo_commonfile） |
| 主网表单专属 | 各 RF_W_*/RF_M_*/RF_Q_* 表单上的量值、公式、单位、枚举、温湿度、颗粒物、多点线性、O3 传递等 ~40 条 + 照片视觉识别 | **不复用**（表结构与字段完全不同），组分站按二期新建 |

## 三、实施方案

### 一期：取数接入 + 通用规则覆盖组分站（预计 1~1.5 天）

1. **取数接入**：`ops_work_order_audit_local.py` 取数增加 `sup_rf_common`（按工单号过滤、order_type 限定 SupCheck/SupSECCheck），dataset 增加 `sup_forms` 键与覆盖统计（`sup_form_count`），证据包与报告展示同步。
2. **字段 profile 扩展**：`rf_field_profiles.yaml` 增加组分站字段别名组（人员=prepareuserid/reviewuserid/audituserid，时间=checkdate），使必填/审核人/时间窗类规则自动覆盖组分站表单。
3. **规则范围核对**：逐一确认附件规则内部无 order_type 白名单把 Sup* 排除；有的放开并补单测。
4. **每周任务即生效**：`gd_routine_work_order_audit` 提示词已按技能流程与卡片交付写好，一期合入后组分站工单获得通用规则覆盖，主网工单全量规则不变；组分站专属问题暂由语义复核与人工卡片兜底。

### 二期：组分站专属规则（预计 2~3 天，依数据普查结果定）

1. **306 列语义普查**（0.5 天）：describe_table + 抽样 20 张 SupCheck 表单人工核对题目项列业务含义，产出 `configs/sup_field_profiles.yaml`（列名→业务字段→校验约束）。
2. **新规则**（1.5~2 天，按普查结果取舍）：
   - 巡检项漏填/异常项无备注（对应主网 RF_ABNORMAL_VALUE_NO_REMARK 的组分站版）；
   - 准备→复核→审核三时间戳完整性与顺序（sup_rf_common 头信息三组 user/time）；
   - 检查日期与工单创建窗口一致性（组分站版时间窗规则）；
   - 组分网校准单（SupDeviceCalibrate）多点数据规则：复用 RF_MULTIPOINT_* 阈值逻辑，数据源换 sup_rf_common 对应列。
3. **视觉规则**：组分站照片同样在附件流，按站点类型对照片时间/水印规则启用（视二期普查中照片量决定）。

### 验证策略（不跑全量审核）

| 层级 | 手段 | 成本 |
|---|---|---|
| 规则单测 | 既有 pytest 基线 + 一期改动补组分站用例 | 秒级 |
| 取数冒烟 | 直调 `fetch_dataset_local` 小窗口（近 2 天、仅 SupCheck）验证 sup_rf_common 接入与覆盖统计 | 秒级，纯本地查询 |
| 规则冒烟 | `run_rules(enable_visual=false)` 跑小样本确定性规则（无 LLM、无视觉） | 分钟级，本地计算 |
| 全量验收 | 一期合入后由你选择时间手动触发一次每周任务（预计 10~30 分钟） | 一次性 |

## 四、待确认问题

1. 一期范围是否认可（通用规则先行，组分站专属规则二期）？还是要求组分站专属规则与每周任务上线同步交付？
2. 每周任务当前为"每周一 10:00、窗口=上周创建、例行类型含组分网巡检"。窗口/时间/类型范围是否需要调整（如组分站单独拆一个每月任务）？
3. 二期普查出的规则清单（第三节的候选 5 类）是否需要业务方（运维考核口径）评审后再落规则阈值？
4. 每周任务当前 enabled=true（技能解析已修复）。若一期实施排期靠后，是否先置为 enabled=false 避免周一带着"组分站仅通用规则"的状态自动跑？

## 五、关联文件

- 任务定义：`projects/guangdong/scheduled_tasks/gd_routine_work_order_audit.json`
- 规则引擎：`backend/app/services/ops_audit/`（rules/configs/rule_engine.py）
- 本地取数：`backend/app/services/ops_work_order_audit_local.py`（RF_TABLES 清单）
- 技能：`backend/docs/skills/ops_work_order_audit.md`
- 组分站表单数据集契约：`projects/guangdong/data-ops/sync/datasets/sup_rf_common.yaml`

---

## 六、一期实施记录（2026-10-25，已落地）

### 业务决策（已确认）

组分站与常规站审核流程一致，拆分为**两个每周定时任务**分别取数、跑规则、成稿与提交卡片：

| 任务 | 调度 | 类型范围 | 表单来源 |
|---|---|---|---|
| `gd_routine_work_order_audit` 常规站 | 每周一 10:00 | Check、SECCheck、SECCheckCnemc、SECFlightCheck、Inspection、WorkRectify 六类例行工单；不按运维单位或站点筛选 | 主网 RF_W_*/RF_M_* 等 33 张分表，全量规则+视觉 |
| `gd_sup_station_work_order_audit` 组分站 | 每周一 11:30（错峰） | SupCheck / SupSECCheck；仅限 10 家运维单位短名精确匹配 | `sup_rf_common` 通用宽表，一期通用规则 |

### 一期代码改动（backend，本地 guangdong_mart 路径）

1. **组分站取数分支**（`ops_work_order_audit_local.py`）：请求类型全部为 SupCheck/SupSECCheck 时进入 sup_mode——绕过主网 `EXCLUDED_AUDIT_ORDER_TYPES`（此前 SupCheck 被引擎显式排除，即组分站无规则的代码根源），RF 表单改查 `sup_rf_common`（SELECT * + 头信息列大写化），以 `SUP_RF_COMMON` 键进入 `rf_forms`，规则引擎/证据包/报告全链路通用消费，无需改规则分发。
2. **常量**（`ops_work_order_audit_engine.py`）：`SUP_AUDIT_ORDER_TYPES`、`SUP_RF_COMMON_TABLE`；主网请求误传 SupCheck 仍被既有口径剔除，两任务互不影响。
3. **字段档案**（`rf_field_profiles.yaml`）：人员组加组分站三段流转字段 PREPAREUSERID/REVIEWUSERID/AUDITUSERID（实测空值率 0%/16.5%/28.6%，为真实业务问题信号）；检查时间字段 CHECKDATE 原已覆盖。
4. **表单显示名**（`rf_form_names.py`）：SUP_RF_COMMON="组分网巡检表单（通用数据体，组分站）"。
5. **单测**：`ops_work_order_audit_local_sup_test.py`（请求判定/大写化/主网口径不变），4/4 通过；规则引擎回归 176 通过、5 个失败均为预存视觉/OCR 环境问题。

### 验证结果（不跑全量）

- **取数冒烟**：近 2 天真实库查询 → 19 张 SupCheck 工单、15 张组分站表单，头字段（工单号/检查日期/三段人员/设备/站点编码）就位。
- **规则冒烟**（无视觉、无 LLM，14 天窗口 120 工单/56 表单）：确定性规则命中 3 张工单"复核人/审核人为空"，`report_ready=True`、`report_input.items=3`——通用规则对组分站端到端生效。
- **已知一期限制**：备注/题目项列未做语义规则（列语义普查后二期落）。

### 部署同步

- worker 重启后 sync 自动创建组分站任务；常规站任务因持久存储不覆盖 seed，已通过任务 API 同步 name/skill_id/prompt。
- 二期（列语义普查 + 组分站专属规则）按第三节计划另行排期。

### 2026-11-02 审核范围校正

- 常规站：恢复 Check、SECCheck、SECCheckCnemc、SECFlightCheck、Inspection、WorkRectify 六类例行工单；`ops_audit_fetch_dataset` 不传 `operation_units`/`station_ids`，窗口内全部主网例行工单纳入审核。
- 组分站：固定 `operation_units` 为 10 家短名（202805贝瑟、202805博之越、202805科迪隆、202805蓝盾、202805力合科技、202805鹏宇、202805武汉天虹、202805祥得、202805壹点、202805中科光电），仅按短名精确匹配，名单外单位不纳入；该名单已固化到 seed。
- 运行库 `backend_data_registry_guangdong/scheduled_tasks/tasks.json` 与 seed 同步修正；长期记忆中的常规站范围事实同步更正。

### 2026-11-09 组分站报告误报治理

**问题**：2026-11-02 组分站正式审核生成 287 条报告问题，其中 232 条（81%）来自单个规则的
结构性误报，真实业务问题（超范围、周期超期、日期不合理、附件缺失等）被严重稀释。

**根因 1｜主网温湿度规则命中组分站分表**
`RF_ENV_TEMP_HUMIDITY_EMPTY` 无表范围限制，按主网字段清单匹配 `temperature`/`humidity`
列名，恰好命中 `sup_rf_pm1monitorinspection`、`sup_rf_monitorinspection`、
`sup_rf_deviceflowcheck` 三张组分站专用分表的同名列。这三列在源库为恒空列
（全量 2931/1638/1531 行，非空计数均为 0），规则因此 100% 命中。
实测一个窗口内 298 条命中 / 118 张工单，占该窗口全部有问题工单的 54%。

修复：`rf_required_rules.py` 增加 `SUP_FORM_TABLE_PREFIX = "SUP_"`，
`_check_env_temp_humidity` 与 `_has_complete_env_temp_humidity` 跳过 SUP 前缀表。
组分站温湿度语义由 `sup_form_profiles.yaml` 按 `ruleitemtag` 单独建档，不需主网规则代劳。

**根因 2｜无表单护栏把未闭环工单当问题**
`FORM_DATA_MISSING` 对未提交表单的工单一律判问题，但未闭环工单（Doing/Wait）
本就允许表单尚未提交。实测 74 条命中中 48 条（65%）是 Doing 单。
进一步核查：剩余 26 条中，20 条的表单实际存在于 ODS 但未建模进 mart
（组分网 100 张表单表，mart 仅 9 张），17 条全库无表单但有附件——
绝大多数是数据管道覆盖问题，不是被审工单的业务缺陷。

修复（两层）：
1. `form_presence_rules.py` 只对已闭环工单（Finish 等）输出，证据带 `order_status`；
   `ops_work_order_audit_engine.py` 的 `no_form_data_records` 统计口径同步收敛，
   记录的 `order_status` 字段一并补上。
2. `FORM_DATA_MISSING` 归入 `technical_diagnostic` 评审阶段
   （`configs/rule_review_stages.yaml` + `config.py` 默认值同步），
   仍可在本轮诊断统计中看到，但不进入正式报告问题清单。

**效果**（同一窗口 10-19~11-03，10 家单位，400 单，无视觉）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 有问题工单数 | 218 | 31 |
| 正式报告问题条数 | 421 | 30 |
| 温湿度误报 | 298 | 0 |
| 无表单护栏条目 | 74（进报告） | 26（转技术诊断，不进报告） |
| report_ready | True | True |

正式报告问题构成变为：`SUP_CYCLE_TIMELINESS` 11、`SUP_RANGE_OUT_OF_SPEC` 10、
`SUP_ATTACHMENT_ITEM_MATCH` 8、`SUP_DATE_REASONABLENESS` 6、
`SUP_ATTACHMENT_REQUIRED_MISSING` 3、`SUP_REQUIRED_VALUE_EMPTY` 1——全部为组分站专属业务规则。

**回归保护**：`backend/tests/test_sup_false_positive_guards.py`（7 例）锁住
"主网同名列仍命中、SUP 表跳过、Doing/Wait 不判无表单、Finish 无表单仍提示"。

**遗留（未纳入本次修复）**：组分网 100 张表单表在 mart 层只建模 9 张，
其余整体缺失导致组分站专属规则（如 OCEC、NH3、Chromatotec 系列）无法生效；
这是取数/建模侧工作，建议单独立项。

### 2026-11-09 mart 层组分网表单表建模补齐

**背景**：组分网 78 张 `sup_rf_*` 表单表全部同步进了 `guangdong_ods`，但 `guangdong_mart`
只建模了 7 张，审核取数按工单号读 mart，导致窗口内 119 单被 `FORM_DATA_MISSING`
判为"无表单"，组分站专属规则（OCEC/NH3/GAC/Chromatotec 系列）无法生效。

**先确认的架构事实**：审核链路里 mart 层是纯透传（`select 列..., now() as refreshed_at
from ods.同表`），不产生数据价值，只提供索引、GRANT 与刷新戳。真正卡住规则生效的是
**语义档案**而非建模——68 张新表接入后，只有 3 张对应的 tag 在
`sup_form_profiles.yaml` 里已建档，绝大多数新表单仍零命中。

**决策**（业务方确认）：保持 `AGENTS.md` 的"应用只读 mart"规范不变，不以 ODS 直读
绕过分层，建模与建档分线推进。

**改动**：

1. **模型生成器** `sync/gen_passthrough_models.py`：读 ODS 实际列生成透传模型，
   与既有 `sup_rf_deviceflowcheck.sql` 同款（id 唯一索引 + `workingordercode` 索引 +
   GRANT agent_reader + refreshed_at）。跳过缺 `workingordercode` 的 3 张表
   （`sup_rf_nmhc_qualitycontroldatadetail`、`sup_rf_ruleitemtask`、
   `sup_rf_vocqualitycontroldatadetail`）——审核取数按工单号过滤，缺该列查询必报错。
2. **生成 68 张模型** + `dbt_project.yml` 补 `+tags: ["daily"]`，随
   `sync-daily.cmd` 的 `dbt build --select tag:daily` 自动物化。
3. **取数侧动态发现** `ops_work_order_audit_local.discover_sup_mart_form_tables()`：
   原 `SUP_MART_FORM_TABLES` 硬编码 5 张改为运行时按 mart 实际存在的 `sup_rf_%`
   （且含 `workingordercode` 列）动态发现，`sup_rf_common` 固定排最前；
   发现失败退回兜底清单。以后新增分表只需生成模型 + dbt build，审核侧零改动。

**验证**（同窗口 10-19~11-03，10 家单位，400 单，无视觉）：

| 指标 | 补齐前 | 补齐后 |
|---|---|---|
| 发现表单载体表 | 5 | 75 |
| 有表单数据的表 | 5 | 38 |
| 窗口内取到表单的工单 | 296 | 347 |
| 无表单护栏（Doing 已剔除） | 26 | 18 |
| 正式报告问题条数 | 30 | 30 |
| 规则命中构成 | 不变 | 不变（无新增误报） |

报告问题数不变是预期结果：新表拿到的表单所属 tag 多数尚未建档，规则读不到配置即
不产出。**下一步的真实工作量在档案建档**，按窗口工单量排序前几类为
`Sup_RF_WaterSolubleIons*`（3 表各 30 单，无 ruleitemtag 需先确认标识）、
`Sup_RF_DailyInspection`(25)、`Sup_RF_NH3Calibration`(18)、
`Sup_RF_GACWeekMaintain`(16)。

**回归保护**：`ops_work_order_audit_local_sup_test.py` 增 2 例
（动态发现排序 / 失败兜底），与 `tests/test_sup_false_positive_guards.py` 合计 13 例通过。

### 2026-11-09 组分站表单档案建档（第二批：NH3 校准 / 日巡检）

**前提**：mart 建模补齐后表单数据已可获取，但规则引擎档案驱动，未建档的 tag 零命中。
本轮从窗口工单量靠前的类型中选两类建档。

**Sup_RF_NH3Calibration（NH3 分析仪校准，231 行 / 231 单，窗口内 18 单）**
- 依据：《组分仪器工单规则》颗粒物组分/NH3分析仪.docx 红字区间 +
  `opa-source-field-mappings.md` 源码字段映射 + 全量 231 行分布核对。
- 落 4 条区间规则：采样流量 `string1` 0.35~0.9 LPM、反应室温度 `string6` 300~350℃、
  转化炉温度 `string7` 725~800℃、反应室压力 `string8` 50~150 mmHg。
- 数据形态：值为"数值+单位"混填（`0.730` / `326.3℃` / `88.9mmhg`），
  `parse_form_number` 取首个数字可正确解析。全量 231 行仅 11 条越界，
  逐条抽检确认均为真实异常，非系统性误报。
- `Sup_RF_NH3CalibrationCX` 为同一张分表的 CX 变体，共用同一套题目项列，
  用 YAML 锚点合并复用同一档案。

**Sup_RF_DailyInspection（NMHC/VOCs 日巡检，531 行 / 531 单，窗口内 25 单）**
- 依据：`opa-source-field-mappings.md` cshtml 标签逐列映射 + 平台校验器 required 清单。
- **只落及时性口径，数值区间刻意不落**（全量 531 行实证后决定）：
  - `string1` 零气加热温度：431/432℃ 是稳定站内自设值（22+8 条），
    按文档 400℃ 标称区间判会误报 46/531（8.7%），属站点仪器差异而非填报错误；
  - `string2/3` 输出压力：MPa 与 psi 混填（`0.4` 与 `58psi` 并存），单一区间无法判定。
  - 两类待业务确认站点设定值与单位口径后再落规则，档案内已留说明。

**验证**（同窗口 10-19~11-03，10 家单位，400 单，无视觉）：

| 指标 | 本轮前 | 本轮后 |
|---|---|---|
| 正式报告问题条数 | 30 | 32 |
| `SUP_RANGE_OUT_OF_SPEC` | 10 | 11（+1，NH3 整行错位真实错误） |
| `SUP_CYCLE_TIMELINESS` | 11 | 12（+1，日巡检及时性生效） |

新增命中均为真实问题：`CH2610311793461806845` 反应室温度填 95.4℃、转化炉温度填
325.8℃、反应室压力填 780.2mmHg（整行数值错位），属应报问题。

**回归保护**：`tests/test_sup_form_rules.py` 增 4 例（合规值不命中 / 越界命中 /
CX 变体复用 / 日巡检数值区间不落规则），该文件 58 例全通过。

**下一批建议**（按窗口工单量）：`Sup_RF_GACWeekMaintain`(16)、
`Sup_RF_EquipmentStatus`(8)、`Sup_RF_SpeedMeterMaintain`(11)、
`Sup_RF_thybWeekCheck`(9，已有档案可直接验证)、
`Sup_RF_Week_RadiationRecord`(8)。

### 2026-11-09 组分站表单档案建档（第三批：GAC 水溶性离子周维护）

**Sup_RF_GACWeekMaintain（水溶性离子周维护，207 行，窗口内 16 单）**

建档过程中发现一个必须扩展引擎才能正确处理的问题：**同一题号的合格区间随色谱柱
规格变化，而表里没有柱规格字段**。

全量 207 行实证：
- `Pengyuchangya` / `ZF-PKU-GAC` 填 2mm 柱口径：柱流量 0.25~0.30 ml/min、
  抑制器电流 10~11 mA；
- `TH` / `TH-GAC-IC3000` 填 4mm 柱口径：柱流量 0.5~0.7、抑制器电流 20~30。

若按文档统一的 4mm 区间（柱流量 0.5~0.75、抑制器 15~35 mA）判定，
柱流量会误报 **110/207（53%）**、抑制器电流误报 **115/207（56%）**。

**引擎扩展**：`sup_form_rules.check_range_columns` 新增 `brand_ranges` 支持——
range spec 可按 `devicebrand` 分档取 min/max；品牌未命中任何档位时**跳过判定**
（用错档位宁可不出结论，也不产生系统性误报）。违规证据里同时带上 `brand`，
便于人工复核时确认用的哪一档。

**落规则**（分档后全量越界 0 条）：
| 题号 | 含义 | Pengyuchangya | TH |
|---|---|---|---|
| `anioncolumnresult` | 阴离子柱流量 | 0.2~0.35 | 0.45~0.8 |
| `cationcolumnresult` | 阳离子柱流量 | 0.2~0.35 | 0.45~0.8 |
| `anionsuppressorresult` | 阴离子抑制器电流 | 8~30 | 15~35 |
| `cationsuppressorresult` | 阳离子抑制器电流 | 8~14 | 15~35 |

**刻意不落的题号**（档案内已注明原因）：
- `steamgeneratorresult`（文档标 280~320℃）：实际整列填 1/0，是 bool 状态位不是温度；
- `anion/cationpressureresult`（柱压）：MPa / psi / 裸数值混填（1.86 / 1610 / 6.1Mpa）；
- `anion/cationiceluentresult`（淋洗液剩余量）：越界仅 2/207，且需确认随时间消耗的低值是否正常。

**Sup_RF_thybWeekCheck（谱育 VOCs 周检查，18 行）—— 本轮不落内容规则**

原因：该类型存于 `sup_rf_common` 宽表，题目项落在 `string1..150` / `bool_1..50`
通用列；源码映射文档给的是**实体列名**（`ms_1`/`fid_1`/`fsq_1`/`mpa_1`/`zftj_1`），
两者没有可验证的对应关系——列语义文档对该类型全部 string/bool 列都标
"占位列，需结合表单模板确认"。实证 `string1=24.9`（疑似站房温度）、
`string2=45.2`（疑似湿度）也无法确认题号。缺模板题号→宽表列位映射时落区间
必然误报，故只保留及时性口径，待拿到映射后补。

**验证**：正式报告问题 32 条、构成不变（GAC 规则在全量数据上零越界，符合预期）；
直接单测确认规则真实生效（正常值不命中 / 错档位命中 / 未知品牌跳过）。
测试 384 通过，6 个失败仍为既有视觉/OCR 环境问题。

**回归保护**：`tests/test_sup_form_rules.py` 增 4 例覆盖品牌分档
（2mm 通过 / 4mm 通过 / 错档命中 / 未知品牌跳过），该文件 62 例全通过。

### 2026-11-09 组分站表单档案建档（第四批：PM1 监测仪巡查三变体）

这一批修正了上一批的一个判断：PM1 的 Week / Month / HalfYear **不是同结构变体**，
不能用一个档案复用。

**实证（sup_rf_pm1monitorinspection 全量 2932 行）**：
- `_Week`（2230 行）：只有 3 个检查标志位有变化，数值列（merror/flowdvalue/
  temperature 等）全量空；
- `_Month`（610 行）：有 `merror`（567 行填充）、`originalvalue`、`currentvalue`、
  `calibrationpoint`，另有 7 个清洗/漏气标志位；
- `_HalfYear`（92 行）：清洗标志位同月检，但无 `merror` 数值。

**关键发现：标志位方向在两个变体间相反。** `opa-source-field-mappings.md` 的 Vue
映射明确写「bool_1 至 bool_3 分别为数据传输、仪器参数、纸带；true = 原表单 0（是），
false = 原表单 1（否）」——即落库 **0 = 是/正常，1 = 否/异常**。全量验证吻合：
Week 2230 行中 2197 行三项全 0，33 行为 1 的工单全部在 `otherremarks` 填了
停运/故障说明。而 Month 的 `leakwhether` 87% 为 1（1 = 不漏气/正常），方向相反。
因此两变体分别建档，不共用异常方向。

**落规则**：
| 变体 | 规则 | 依据 |
|---|---|---|
| `_Week` | `abnormal_columns` 3 项（数据传输/仪器参数/纸带，values=["1"]，备注豁免 `otherremarks`） | PM1.docx 周巡检条目 + Vue 映射 |
| `_Month` | `range_columns` merror ±5%（`confirmed: true`） | PM1.docx 月巡检红字「误差在±5%以内」 |
| `_HalfYear` | 仅及时性（30 天） | 标志位方向与 Week 不同，未确认前不落异常规则 |

**验证**：同窗口正式报告仍 32 条、构成不变——符合预期：窗口内 108 条周检标志位
全为 0（全正常），merror 全量 610 行 0 越界。规则确实生效由单测直接验证
（三项全 0 不命中 / 异常有备注不命中 / 异常无备注命中 / merror 7.2% 命中 /
merror 0.9% 不命中 / 半年检不落异常规则）。

**回归保护**：`tests/test_sup_form_rules.py` 增 6 例，该文件 68 例全通过；
整体 390 通过，6 个失败仍为既有视觉/OCR 环境问题。

**顺带修正上一批的表述**：此前说 PM1 周检可从月检档案「复用」，实际核对后
二者题目组与标志位方向均不同，不能复用，已按新证据分别建档。

### 2026-11-09 建档收益摸底（按可抓问题排序替代按工单量排序）

**方法**：写临时扫描脚本解析 `opa-source-field-mappings.md` 里的题号区间
（覆盖 23 个类型），对全部未建档类型的真实数据计算数值列越界率；对高命中项
逐个甄别，区分「真实可抓问题 / 状态位假线索 / 单位或型号口径差异」。

**甄别结论**（扫描 A 组 9 个高命中类型的去向）：

| 类型 | 扫描命中 | 甄别结论 | 处置 |
|---|---|---|---|
| Sup_RF_RULEITEMVOCs | 100% | `bool_7/8` 是 0/1 状态位，179.5~180.5℃ 是题目标签不是列值 | 不落（假线索） |
| Sup_RF_SpeedMeterMaintain | 79% | 全表 17 个 `isitnormal` 标志位，解析器把 0/1 当数值比温度区间 | 改落 abnormal 规则（方向已确认 1=不正常） |
| Sup_RF_EquipmentStatus | 64% | TiH200 与 Model4050 的 string4/5 是**不同题目**（后者填电压 640v） | 按 brand_ranges 只给 Etraninc(TiH200) 落区间 |
| Sup_RF_GACWeekMaintainByMARGA | 85% | 压力值 3.77~11.0 无聚集，单值离散，疑测量波动或单位口径 | 不落（待业务确认） |
| Sup_RF_VoCsChromatotecCheck | 100% | 同 RULEITEMVOCs，bool 状态位 | 不落（假线索） |
| Sup_RF_TurbidiMeterCalibration | 100% | 文档给 bool_5/string5 实体列名，分表是 zp/sp 语义化列，映射不成立 | 不落（映射失效） |
| Sup_RF_URGWeekMaintain | 14% | 柱压真实数值列；水峰 0.25x44 / 0.38x24 双稳态聚集 | 只落柱压区间；水峰待业务确认 |
| Sup_RF_CO2Inspection | 1% | 真实数值列，宽区间健康检查型，7/705 越界 | 落 3 条区间 |
| Sup_RF_N2OAnalyzerinspection_Week | 0% | 数据干净 | 落区间（未来覆盖） |

**本轮建档 4 个类型**（档案 64→68，带规则 34→38）：

1. `Sup_RF_SpeedMeterMaintain`：17 个 isitnormal 标志位的 abnormal 规则
   （values=["1"]，配对备注列 + 全局 remarks 豁免）。全量 118 行中 28 行有
   标志位为 1 且有说明，方向证据：`dctisitnormal=1` 行 remarks=「挪机安装调试中」。
2. `Sup_RF_CO2Inspection`：气压 250~1000mmHg / 采样流量 0.35~1.5L/min /
   内部温度 8~47℃（文档红字宽区间，全量 705 个解析值仅 7 条越界）。
3. `Sup_RF_EquipmentStatus`：Etraninc(TiH200) 蠕动泵双流量区间（brand_ranges）；
   SDL(Model4050) 无档位自动跳过。
4. `Sup_RF_URGWeekMaintain`：阳离子柱压 1500~2500psi；水峰双稳态不落，待业务确认。

**引擎小扩展**：`column_remark_text` 支持备注列列表（`remark_column` 可传数组），
配对备注列与全局备注列同时豁免（SpeedMeter 的挪机说明在全局 `remarks` 列，
配对列 `dctremarks` 为空，单列机制会误报该类行）。

**验证**：同窗口正式报告 32→33 条，新增 1 条为
`Sup_RF_EquipmentStatus` 抓到的真实越界（TiH200 蠕动泵2 流量填 0.6，
标准 0.22~0.26，无备注）。测试 400 通过（含新增 10 例），6 个失败仍为
既有视觉/OCR 环境问题。

**重要方法论修正**：扫描 A 组的 9 个"高命中"类型中 5 个是假线索（状态位、
映射失效），真正能落规则的只有 4 个且 2 个需要 brand_ranges。**结论：对剩余
类型，"解析文档阈值→算越界率"只适合专用分表上的语义化列类型；宽表
（sup_rf_common）类型与状态位表都不适用，需模板映射或业务确认，不要按工单量
批量硬建。**

### 2026-11-09 常规站 RF_REQUIRED_FIELD_LOW_VALUE 规则下线

2026-11-09 常规站周审核复盘（2026-10-26~11-02 窗口，355 单）发现：
候选级 1776 项中该规则独占 1119 项、覆盖 318/324 个"问题订单"（其中 118 单
仅被它标记），绝大多数命中为"周检表单备注.REMARK 为空"——一切正常时不填
备注属常态操作，属系统性误报；且下游语义审核与最终问题清单对该规则确认数
为 0（管线已在过滤它），但"324 单存在问题"的订单级判定仍由它决定。

**处理**：整体下线，不再使用（业务决定，2026-11-09）。两个引擎的发射点
（`rules/rf_required_rules.py::_check_low_value_fields`、
`ops_work_order_audit_engine.py::check_form_common_fields`）、规则目录
（`rule_catalog.yaml`、`ops_work_order_audit.py`）、评分配置
（`common_pattern_eligible_rules`）、字段档案（`low_value_field_groups`，
config 默认与 `rf_field_profiles.yaml`）、语义候选集、最终清单排除分支
（`_required_field_issue_is_remark_only`）与报告排除集引用一并移除。
`LOW_VALUE_REMARKS` 词表保留（人员/车辆格式、异常备注等规则仍在使用）。

**回归保护**：`test_ops_audit_rule_coverage.py::test_rf_required_and_time_rules_are_detected`
翻转断言（备注空/低价值不再命中）、`test_ops_audit_phase2_modularization.py`
断言 `low_value_field_groups` 不再出现在字段档案、
`test_ops_audit_rules.py` 保留"切割头 CleaningRemark=/ 不命中"守门。

**影响预估**：按 2026-11-09 窗口回放，候选级"有问题"订单 324→约 206；
最终问题清单不受影响（该规则确认数本为 0）。

### 2026-11-09 品牌正常范围未配置提醒降为技术诊断

`RF_RANGE_BRAND_PROFILE_UNCOVERED`（本周 99 项/39 单，最终清单单项最多）
按业务决定不再生成"待配置提醒"。决策依据：核查原始运维库
`Operation_SC_GD.BSD_INSBRANDINFO`（监测联网侧权威品牌阈值源，
`AlarmSamplingService` 告警与联网核对实际在用，543 行），该表仅覆盖
API/EC/ESA/FPI/METONE/TE/TH/XH 8 品牌 37 型号（编码 100=SO2、101=NO2、
102=O3、103=CO、104=PM10、105=PM2.5），**LD（力合）、峰悦奥瑞、福瞳、
怡特、蓝盾、API T 系列、先河气态非 B/E 型号、METONE BAM1020 等在网品牌
均未配置**——监测联网侧无配置即业务上无配置，持续提醒属噪音。

**处理**：加入 `rule_review_stages.yaml` 的 `technical_diagnostic` 阶段
（与同族 `RF_RANGE_UNIT_MISMATCH` 同口径）。规则目录 rationale、发射点
evidence（`report_classification: technical_diagnostic`、
`counts_as_work_order_issue: false`）早已声明该意图，本次是把阶段配置
对齐；规则仍发射并保留在审计 JSON 的 `technical_diagnostics` 中，不进入
`audit_level`、评分、最终问题清单与正式报告。后续若业务供数或
BSD_INSBRANDINFO 同步接入（可作 `rf_range_profiles.yaml` 的权威交叉
校验源，model 级粒度），再评估升档与建档。

**影响预估**：按 2026-11-09 窗口回放，最终清单 95 单中仅因该规则上榜的
21 单摘除；剩余约 72~74 单为经复核的实际填报/超范围问题。

### 业务待确认清单

各批次建档过程中积累的业务口径问题（已落规则的阈值确认、缺口径未落规则、
标志位方向、宽表模板映射、流程参数）已汇总为独立清单：
**`projects/guangdong/docs/sup-audit-pending-confirmations.md`**。
含 A~E 五类共 20+ 项，每项附数据证据、影响面（窗口单量）与所需确认内容；
确认后 A 类改 `confirmed: true` 即生效，B/C 类按清单证据落规则。

### 已生效规则清单文档

常规站 77 条目录规则与组分站 68 个类型（38 个带内容规则）的在线状态、
规则构成、验证情况与运行基线，已汇总为独立说明：
**`projects/guangdong/docs/sup-audit-active-rules.md`**。
