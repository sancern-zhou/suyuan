# 智能体项目 × 广东运维平台源码：语义缺口分析与补足计划

- 生成时间：2026-11-03。
- 背景：溯源 guangdong 分支的 `ops_audit` 对广东运维平台（OPA）数据做例行工单审核。凡涉及**源系统字段含义、表单结构、枚举取值、业务口径**的地方，广东运维平台源码（`D:\广东运维平台\trunk`，SummerFresh.* .NET 解决方案）是权威来源；此前多处依赖数据推断与案例反推（`confirmed: false`）。
- 方法：三层证据优先级——实体类 `<summary>` 注释 > cshtml 视图标签/`validator` > 省产品仓库 Vue 移植版注释；`column-semantics.md` 数据普查用于反证。
- 解析脚本（可重跑）：`.zcode/tmp/opa-audit-rules/`：`parse_gd_full.py`（组分站实体+视图）、`parse_gd_mainnet.py`（主网实体+视图）、`build_final_docs.py`（交付文档）、`apply_profile_updates.py`（档案回写）。

## 一、本轮已补足

| # | 缺口 | 补足结果 |
| --- | --- | --- |
| 1 | 组分站 170 个 tag 的动态列语义（stringN/boolN/timeN）依赖数据推断 | `opa-source-field-mappings.md`：169/170 tag 拿到实体注释+视图标签+平台校验器；`profile_reconciliation.md` 30 档案逐列核对（59 列中 57 列源码印证）；`sup_form_profiles.yaml` 已回写：**13 条证据链完整者 confirmed 化 + PANsWorkCurveCalibration 列位修正（string48→string44）**；另 5 处档案疑误（HONOQC 列位、HONOCheck 日期语义、YT 验漏审计对象、PANsFlowCheck 公式口径、NMHCQC 动态校准档位）保持 false 并列入修订建议 |
| 2 | 主网 RF 表单列语义仅有数据侧普查 | **新增** `rf-main-net-field-mappings.md`（3281 行）：73 个实体表（67 个带注释）+ 59 个视图模型，含各品牌阈值原文（如 CO 分析仪斜率 1±0.3(API)/0.85~1.15(聚光)/0.500~2.000(赛默飞)…） |
| 3 | `column-semantics.md`「主网表单题目项字典」误用 `RF_ITEM` | 源码实锤：`RF_ITEM`（实体 `RF_W_ITEM.cs`，class `RF_ITEM`）是**工单耗材/附件记录表**（ITEMID/ITEMNAME/ITEMNUM + IMGPATH，RFItemService 按 workingordercode+ruleitemtag+types 查询），非题目项字典。已更正 `form_semantics_census.py` 与普查文档标题/说明 |
| 4 | 表单名称字典手工维护、部分"待业务确认" | **新增** `form-name-dictionary-from-source.{json,md}`：Sup 336 类（183 个带标题）、ReportForms 73 类（65 个带标题）、ReportFormsEnum 全部枚举成员（W/M/Q/HY/Y/D/DRT/SEC 等，带中文描述与原值），可直接用于 `rf_form_names.py` 的 P2 合并 |

## 二、待补足（按优先级）

### P1 主网 `rf_*` 档案列语义核验（已核对，待回写）

已完成（2026-11-03）：`rf-main-net-reconciliation.md`——7 个主网档案共 213 条（表,列）引用逐条核对：**✅实体注释 102 + ✅视图标签 81（共 183 条源码印证）**、🟡实体存在无注释 13、⚠️源码未见 17。

关键发现：`rf_range_profiles.check_value_fields` 对 `RF_W_GASEOUSCHECK_{CO,NOX,O3,SO2}` 与 `RF_W_PMCHECK` 引用的 DISPLAYVALUE/MEASUREVALUE/SENSORVALUE（PM 前缀版）在 GD 实体、视图与数据侧列别名中**均不存在**——该规则对 5 张表实际空转；真实字段为 LDPYPPB/KDPY/LDSHOWVALUE/MCLPPM/MAINFLOWVALUE 等（视图标签含品牌阈值）。配置处已加注释标注，待业务确认后改用真实字段。

后续：主网档案（rf_*_profiles.yaml）无 `confirmed` 标记体系，无需翻转；剩余 🟡/⚠️ 条目按报告逐条业务确认。

### P2 表单类型名称字典自动化（已产出草案）

现状：`rf_form_names.py` 的 `RF_FORM_NAMES`（约 50 条）与 `SUP_FORM_NAMES`（约 100 条）为手工维护，部分标注"缩写含义待业务确认"。

可补资源（已提取）：
- `form-name-dictionary-from-source.md/.json`（本次产出）——`ReportFormsEnum` 全枚举成员描述 + Sup/ReportForms 实体类标题；
- 落地：按 `rf_form_names.py` 结构生成补丁时注意键名大小写（源码枚举为 `RF_W_Inspection`，现字典为 `RF_W_INSPECTION`）；合并后跑 `tests/test_sup_form_rules.py` 等回归。

### P3 枚举值字典核验（中）

现状：`rf_enum_profiles.yaml` 仅 66 行，`allowed_values` 多为 `["0","1"]`，含义靠命名推断。

可补资源：GD 视图 radio 绑定（如 `IsCalibrated`：`RadioButtonFor(m => m.T_IsCalibrated, 1)是 / 0否`）、`Enum/*.cs`（`ImageType`（附件图片类型：停电图片/调研申请图片…）、`RF_TaskItem_Status`、`PlanEnum`（计划类型/计划状态）、`SECEnum` 等）。可扩展出"0/1 中文含义 + 是否含其他合法值"的字典，降低误报。

### P4 品牌码 → 表单变体选择（中）

现状：Sup 表单按 `mtc_taskitem.brandcode` 选择品牌专属模板（如 AmbientTemperature 的 `_METROHM`/`_SUNSET` 变体），审核侧当前不看 brandcode，所有品牌共用一套列规则。

可补资源：`Sup_QCDeviceBrand`（BrandCode/BrandName/厂家/批次）、`Sup_DeviceBrand`、`BSD_DEVICEBRAND` 实体；变体命名可在 cshtml/Vue 文件名中枚举（`_TH`/`_SUNSET`/`_METROHM`/`_MAGEE`/`_TSI`/`_EC` 等）。落地：建档 `brandcode→品牌名→适用表单变体`，在审核取数时带出品牌，按变体细分规则（尤其水溶性离子/OCEC/浊度计的多品牌差异）。

### P5 附件口径核验（中）

现状：`attachment_requirements.yaml` 的类别/关键词（report/data_file）为人工定义。

可补资源：`WO_COMMONFILE` 实体（附件记录）、各表单 cshtml 上传控件与 `ImageType` 枚举、`Sup_ReferenceMaterialCommonFiles` 等 Json 附件字段——可核对"该类工单平台实际要求上传什么"，与审计附件规则对齐。

### P6 计划/及时性口径（中，需业务确认兜底）

现状：`timeliness.plan_late_grace_days = 5` 为试点值；`planfinishtime`（计划完成日）语义未在审计侧建档。

可补资源：`PW_TASK`/`PW_TASKITEM`（含 `BASEDATE=计划项的基准日期` 注释）、`Sup_Mtc_TaskItem`/`Sup_Pw_Taskitem`、`Services/PlanService.cs`、`OperationService.Quartz` 计划生成任务。注意：`PW_TASK` 多数列注释为空，源码只能补"生成规则/步骤"，宽限天数仍需业务确认。

### P7 工单时长规则扩展（中）

现状：`work_order_duration_rules.py` 目前仅 1 条（"月度动态校准" CheckOrder 步骤 ≤5 分钟判异常）。

可补资源：`Workflow/` 目录、`MtcWorkingOrderService`、`wfl_workflow`/`wfl_workflowtask`（工单类型与步骤定义）——可定义更多"形式化完成"规则（秒级提交、同人批量、步骤跳步），但阈值仍需案例校准。

### P8 主网"题目项字典"不存在（认知修正，已处理）

结论：`RF_ITEM` 不是题目项字典；主网表单的"题目文本"只能来自视图标签（已由 `rf-main-net-field-mappings.md` 覆盖）。若后续需要 APP 端题目文本，应从 `Areas/OSApp` 或移动端接口取。

## 三、GD 源码资源索引

| 资源 | 路径 | 用途 |
| --- | --- | --- |
| 组分站实体（403 类） | `SummerFresh.Maintenance/Entity/Sup/**` | 列语义（`<summary>`）、存储表（`[Table]`）、宽表/分表判定 |
| 主网实体（73 表） | `SummerFresh.Maintenance/Entity/ReportForms/**` | 主网列语义、表单标题 |
| 工单/附件/设备 | `Entity/WorkingOrder`、`Entity/DEV`、`Entity/BSD`、`Entity/Sup/QCDevice` | 工单模型、附件（WO_COMMONFILE）、品牌字典 |
| 组分站视图（298） | `SummerFresh.MVC/Areas/Sup/Views/QcForm/**` | 中文标签、validator、品牌变体、红字阈值 |
| 主网视图 | `SummerFresh.MVC/Views/ReportForms`、`Views/MtcWorkingOrder` | 主网标签与品牌阈值 |
| 枚举字典 | `SummerFresh.Maintenance/Enum/**`（ReportFormsEnum/PlanEnum/SECEnum…） | 表单类型中文名、状态/图片类型枚举 |
| 服务/任务 | `Services/Sup`、`Services/QC`、`Services/PlanService.cs`、`Workflow/`、`OperationService.Quartz` | 计算口径、计划生成、流程步骤 |
| 数据库定义 | `SummerFresh.MVC/Database Definition/{Tables,Views,Store Procedures,...}` | 建表/索引/序列（核验 sync 层表结构） |

## 四、建议落地顺序

1. P2 表单名称字典：草案已产出（`form-name-dictionary-from-source.md`），下一步与 `rf_form_names.py` diff 合入（注意键名大小写）；
2. P1 主网档案逐列核对（1~2 天，复用组分站核对脚本，对照 `rf-main-net-field-mappings.md`）；
3. P3 枚举字典核验（1 天）；
4. P4 品牌变体字典（1 天，需与业务确认品牌规则差异）；
5. P5~P7 需业务输入配合（阈值/宽限/时长），源码提供结构，确认项照旧保持 `confirmed: false`。
