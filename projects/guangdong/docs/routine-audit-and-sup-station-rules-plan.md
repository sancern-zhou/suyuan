# 例行工单每周审核与组分站审核规则扩展方案（待确认）

> 生成时间：2026-10-25。本文档回答"已有常规站点审核规则和每周任务，为什么部署里没有"，并给出组分站规则扩展与例行审核上线的实施方案，**待确认后实施**。

---

## 一、现状核查结论

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
| 流程链 | FLOW_MISSING / FLOW_NO_CREATE / FLOW_NO_CHECK | **直接复用**（scope=工单主表/明细，组分网流程环节 SupCheck_Check/Review/Approve 已在语义字典） |
| 生命周期闭环 | LIFECYCLE_FINISH_NEAR_DEADLINE / FINISH_WITHOUT_EFFECTIVE_CLOSURE | **直接复用** |
| 工单-表单一致性 | RF_STATION_MISMATCH、RF_CHECK_TIME_OUTSIDE_RANGE | 复用（后者按字段名匹配检查日期，需把 sup_rf_common 的 `checkdate` 加入字段 profile） |
| 必填/低值/审核人 | RF_REQUIRED_FIELD_LOW_VALUE、RF_AUDITOR_EMPTY、RF_ABNORMAL_VALUE_NO_REMARK 等 | **字段 profile 加别名后复用**（sup_rf_common 有 prepareuserid/reviewuserid/audituserid/devicecode/devicebrand/devicemodel 等同义字段） |
| 附件 | ATTACHMENT_CERT/REPORT/REQUIRED_MISSING、照片水印时间类 | 复用（附件仍走 wo_commonfile） |
| 设备一致性 | RF_DEVICE_IDENTITY_INCONSISTENT | 复用（表单内品牌/型号/编号 vs 设备维度表） |
| 主网表单专属 | 各 RF_W_*/RF_M_*/RF_Q_* 表单上的量值、公式、单位、枚举、温湿度、颗粒物、多点线性、O3 传递等 ~40 条 + 照片视觉识别 | **不复用**（表结构与字段完全不同），组分站按二期新建 |

## 三、实施方案

### 一期：取数接入 + 通用规则覆盖组分站（预计 1~1.5 天）

1. **取数接入**：`ops_work_order_audit_local.py` 取数增加 `sup_rf_common`（按工单号过滤、order_type 限定 SupCheck/SupSECCheck），dataset 增加 `sup_forms` 键与覆盖统计（`sup_form_count`），证据包与报告展示同步。
2. **字段 profile 扩展**：`rf_field_profiles.yaml` 增加组分站字段别名组（人员=prepareuserid/reviewuserid/audituserid，时间=checkdate，设备=devicecode/devicebrand/devicemodel），使必填/审核人/时间窗/设备一致性类规则自动覆盖组分站表单。
3. **规则范围核对**：逐一确认流程链/生命周期/附件规则内部无 order_type 白名单把 Sup* 排除；有的放开并补单测。
4. **每周任务即生效**：`gd_routine_work_order_audit` 提示词已按技能流程与卡片交付写好，一期合入后组分站工单获得通用规则覆盖，主网工单全量规则不变；组分站专属问题暂由语义复核与人工卡片兜底。

### 二期：组分站专属规则（预计 2~3 天，依数据普查结果定）

1. **306 列语义普查**（0.5 天）：describe_table + 抽样 20 张 SupCheck 表单人工核对题目项列业务含义，产出 `configs/sup_field_profiles.yaml`（列名→业务字段→校验约束）。
2. **新规则**（1.5~2 天，按普查结果取舍）：
   - 巡检项漏填/异常项无备注（对应主网 RF_ABNORMAL_VALUE_NO_REMARK 的组分站版）；
   - 准备→复核→审核三时间戳完整性与顺序（sup_rf_common 头信息三组 user/time）；
   - 检查日期与工单创建窗口一致性（组分站版时间窗规则）；
   - 设备品牌/型号/编号与站点设备台账一致性（复用设备一致性阈值）;
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
