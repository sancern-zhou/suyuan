# 组分站审核规则开发计划（确定性规则优先）

> 依据：`projects/guangdong/docs/sup-station-audit-rules-expansion-plan.md`（已确认的完善方案）与
> `projects/guangdong/docs/sup-instrument-rules/`（22 类仪器规则转录）。
> 原则：**确定性规则先行**——能用代码直接判对错的（数值复算、范围、日期、必填、附件在位、及时性、异常未备注）
> 优先开发上线；人工复核/视觉类（备注语义、照片比对）沿用现有试点模式，本期不扩展。

## 实施进度（2026-10-27）

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| T0 tag 盘点 | ✅ 完成 | 新增 `backend/scripts/sup_tag_inventory.py`，产出 `docs/sup-instrument-rules/tag-inventory.md`（7 张分表、94 个 tag） |
| T1 档案修正 | ✅ 完成 | PANs 季度误差 ±10%→±2%（文档红字）；PANs 稳定性周检→年度/60 天；OCEC 氦甲烷周检→半年/45 天 |
| T2 规则代码 | ✅ 完成 | range_columns 支持 expression（计算型区间，含 6 位取整消浮点噪声）；date_columns 支持 not_past；formula_columns 支持 skip_if_inputs_zero（0 占位行跳过）；新增 SUP_ABNORMAL_NO_REMARK 规则（机制+测试就绪，待列极性确认后建档接线） |
| T2 通用表单族建档 | ✅ 完成（首批） | 流量核查族（DeviceFlowCheck，PM1/氨/BC/离子/重金属共用，PTRMS 别名）、温压核查族（AmbientTemperature，5 类仪器共用）、PM1 月巡查校准膜±5%、PANs 周检 R²≥0.995、PANs 多点标曲 R²≥0.999、HONO 周质控双通道 R²≥0.995、PANs 重复性 RSD≤3%、优泰月度验漏 ≤1mL/min |
| 90 天数据回放验证 | ✅ 通过 | 982 单回放：流量族 21 范围+2 公式+6 日期命中（约 5-7%，含 error=100%、检定证过期、上次检定日期填到未来等真实问题）；温压族 7+3 命中（含 -2.0 贴边浮点误判已修复）；PANs 周检 2 单 R²=0.992 真实命中；单测 38/38 通过 |
| T3 Excel 质控解析 | ⏳ 未开始 | 等模板样例文件 |
| T4 双周及时性口径 | ⏳ 未开始 | 等业务确认宽限天数 |
| T5 试点确认 | 🔄 新规则以 confirmed 标注试点 | 文档红字且列语义已验证的置 true（流量/温压/校准膜/PANs±2%）；列语义按样本推断的置 false（各 R² 列、验漏列、RSD 列），待业务核对后转 true |

待办移交：① `backend/tests` 全量 pytest 需在 backend_py311 环境执行（本机无该环境，案例回归 test_sup_case_regression.py 未在本机运行，夹具数据已人工核对不受影响）；② 部署按 AGENTS.md 走 deployment_preflight + web/worker 成对重启；③ 异常勾选规则（SUP_ABNORMAL_NO_REMARK）待 BC/PM1 巡检表 0/1 布尔极性经业务确认后接线建档。

## 任务总览

| 编号 | 任务 | 类型 | 工作量 | 依赖 |
| --- | --- | --- | --- | --- |
| T0 | 组分站表单 tag 盘点脚本增强与执行 | 前置 | 0.5-1 天 | 部署环境只读访问 |
| T1 | 现有档案口径修正（3 处冲突 + 浊度计补范围） | 确定性 | 0.5 天 | T1 中周期类修正参考 T0 |
| T2 | 通用表单族建档与规则扩展 | 确定性为主 | 2-3 天 | T0 |
| T3 | Excel 质控模板解析（4 个子任务） | 确定性 | 3-5 天 | T0 + 模板样例文件 |
| T4 | 及时性口径补全（双周等新周期） | 确定性 | 0.5 天 | 业务确认宽限天数 |
| T5 | 试点运行、命中率观察、阈值确认 | 流程 | 2-4 周日历 | T1-T4 分批上线 |

确定性规则全部完成后，人工复核类规则仅作为确定性触发的降级出口（超范围有备注、异常有备注等转人工），不新增视觉/语义类开发。

## T0 表单 tag 盘点（前置）

- 扩展 `backend/scripts/sup_profile_probe.py`：对 5 张组分站表单表（`sup_rf_common`、`sup_rf_pm1monitorinspection`、`sup_rf_deviceflowcheck`、`sup_rf_monitorinspection`、`sup_rf_ambienttemperature`）输出：
  - ruleitemtag 分布、近 90 天行数、每列填充率、样本行（脱敏）；
  - 与 `projects/guangdong/docs/sup-instrument-rules/` 表单标题的人工对照表（tag → 仪器 → 工单类型 → 文档分册章节）。
- 产出：`projects/guangdong/docs/sup-instrument-rules/tag-inventory.md`，作为 T2/T3 建档清单的唯一依据。
- 验收：周窗口真实数据跑通；没有数据支撑的表单明确标注"暂不建档"。

## T1 现有档案修正（确定性，立即可做）

改 `backend/app/services/ops_audit/configs/sup_form_profiles.yaml` + `backend/tests/test_sup_form_rules.py`：

1. `Sup_RF_PANsFlowCheck`：设定误差范围 ±10% → **±2%**（文档红字），复算容差维持 0.5。
2. `Sup_RF_PANsStabilityCheck`：周期 week/7 天 → **year/60 天**（文档为年度稳定性核查，测试结果≤5%）；若盘点确认重复性核查是独立 tag，新增档案（RSD≤3%）。
3. `Sup_RF_OcecHeliumMethaneCheck`：周期 week/7 天 → **halfyear/45 天**；按通道补双阈值（氦甲烷±5%、其余±10%，每通道一条 range_columns）。
4. `Sup_RF_TurbidiMeterRoutineCheck`：补三波长零点差值 ±2Mm⁻¹。
5. `Sup_RF_TurbidiMeterCalibration`：补跨度核查 ±10%（(本-标)/标×100%，可用 formula_columns 复算）。
6. 以上项业务确认后 `confirmed: true`；确认前以 `confirmed: false` 上线试点。

验收：单测更新并通过；用历史 4 周窗口回放，命中率与人工复盘案例一致（潮州西园路 PANs 案例应命中 ±2% 规则）。

## T2 通用表单族（确定性为主，一次开发多仪器受益）

按 T0 对照表分批建档，全部落在 `sup_form_profiles.yaml`；代码扩展集中一次做：

- **T2a 年度维护检定报告（22 类仪器，确定性）**：按 tag 批量建档 `required_attachments: report`，沿用豁免关键词（"无需送检"等）。零代码改动。
- **T2b 流量核查族（约 14 类仪器，确定性复算）**：每 tag 建档
  - 相对误差单表达式复算：`(({显示值}*{斜率}+{截距})-{设定值})/{设定值}*100`，容差按文档（通用 ±5%）；
  - 示值误差 ±2%；校准后行同理。现有 formula 引擎支持四则与多输入，无需改代码。
  - 变体单独标注：OCEC 半年通道流量（氦甲烷±5%/其余±10%）、PANs 季度（±2%，T1 已含）、NH3 动态校准仪（0.99≤斜率≤1.01、r>0.999、截距≤±1%FS）、AMA 标态换算（先跳过判定，转人工）。
- **T2c 温压核查族（6 类仪器，确定性 + 小代码扩展）**：±2℃/±1kPa range_columns；
  - 代码扩展①：range_columns 支持 `skip_when`（如"是否校准=否/传感器读数填 0/备注含'无传感器'"时跳过判定）；
  - 代码扩展②：date_columns 的 `single_date_rule` 增加 `not_past`（参考流量计/温度计"下次校准日期"不得早于检查日期；"上次校准日期"不得晚于检查日期用现有 not_future）。
- **T2d 多点/标曲线性族（确定性）**：按仪器建档 r / 斜率 / 截距阈值（CO2、NH3 用 HJ 1393 口径：r>0.999、0.95≤斜率≤1.05、截距≤±1%FS；质控 Excel 标曲阈值归 T3）。
- **T2e 异常勾选未备注（新通用规则，确定性触发+人工复核出口）**：
  - `sup_form_rules.py` 新增 `SUP_ABNORMAL_NO_REMARK`：档案声明 abnormal_columns（列 + 异常值清单["异常","未执行","不合格","×","否"] + 备注列），命中异常值且备注为空 → 中严重度，提示"异常项需备注并上传照片"。
  - 覆盖文档中几乎所有勾选类表单的红字要求，是本期唯一的规则代码新增。

改动文件：`sup_form_profiles.yaml`、`backend/app/services/ops_audit/rules/sup_form_rules.py`（扩展①②+T2e）、`backend/tests/test_sup_form_rules.py`（新增用例）。
验收：每族至少 2 个真实历史工单回放用例（1 正 1 反）；新增单测通过；命中率报告无系统性误报（同 tag 命中率 >30% 时暂停该 tag 规则排查列语义）。

## T3 Excel 质控模板解析（确定性数值判定）

新文件 `backend/app/services/ops_audit/rules/sup_xls_qc_rules.py`（复用 `o3_value_pass_xls_rules.py` 的按标签提取与缓存模式），按模板从易到难分四个子任务，**每个子任务独立上线**：

| 子任务 | 仪器/表单 | 确定性判定 | 前置 |
| --- | --- | --- | --- |
| T3a | 重金属质控（纸带空白/膜片/能量/全膜/标准曲线） | 空白：≥80% 元素低于检出限；膜片：±10%；能量：±0.5%；全膜：≥70% 元素 ±10% 以内；标准曲线：R≥0.98；缺失/不监测填 -999 约定 | 模板样例 |
| T3b | 水溶性离子周质控 | 单点偏差 ±10%；空白 < 检出限；标曲 R²≥0.995；标物证书页签/附件存在性 | 模板样例 |
| T3c | 甲烷/非甲烷周质控 | 零点空白限值（甲烷≤0.1ppm 等）；单点 C2≤±10%；标曲 R2≥0.999 | 模板样例 |
| T3d | VOCs / PTR-MS 周质控 | 标曲 R²≥0.98；内标响应整周覆盖（文件日期区间 vs 检查日期）；-999 约定 | 模板样例 |

两步上线：先"软校验"（必需 Excel 附件存在、工作表在位、必填列非空）→ 再数值判定。软校验即确定性规则，不依赖模板细节，可先行。
改动文件：新增 `sup_xls_qc_rules.py`、`sup_form_profiles.yaml`（每 tag 增加 xls_qc 配置段）、新测试文件 `backend/tests/test_sup_xls_qc_rules.py`（用样例文件做 fixture）。
外部依赖：**需向平台/业务索取 5 套模板样例与若干真实填写文件**；拿不到模板的子任务顺延。

## T4 及时性口径补全（确定性）

- 新建档统一携带 `cycle` + `max_fill_lag_days`（周 7 / 双周 14（待确认）/ 月 10 / 季 31 / 半年 45 / 年 60）。
- 双周工单（甲醛双周、OCEC 双周空白单点）宽限天数需业务确认（方案确认项 5）；计划口径（`sup_mtc_taskitem` + 5 天宽限）已实现，随档案自动生效。
- 验收：及时性规则对新档案生效，历史回放无整批误报。

## T5 试点与阈值确认（流程，随上线持续）

- 新规则统一 `enabled: true, confirmed: false` 起步；每周例行审核综述观察各 tag 命中分布与误报；
- 试点 2-4 周后按业务确认结论（方案第四节 8 项）逐项 `confirmed: true`；
- 每月回顾一次：命中率 <5% 的报告类要求维持现状，>30% 的暂停排查；
- 文档同步：更新 `projects/guangdong/docs/sup-station-audit-rules-guide.md`（业务版说明）与方案文档状态。

## 里程碑

| 里程碑 | 内容 | 时间 |
| --- | --- | --- |
| M1（第 1 周） | T0 盘点产出对照表；T1 修正上线 | 开发 1-1.5 天 |
| M2（第 2-3 周） | T2a→T2b/T2c→T2d/T2e 分批上线 | 开发 2-3 天 |
| M3（第 3-4 周） | T3 软校验先行，数值判定按模板到位情况推进 | 开发 3-5 天 |
| M4（持续） | T4、T5 试点回顾与 confirmed 收敛 | 2-4 周日历 |

总开发量约 **7-10 人天**（不含试点观察期）。

## 上线与回归清单（每个任务通用）

1. `conda activate backend_py311`；跑相关测试（`backend/tests/test_sup_*.py`）。
2. 配置改动仅涉及 `sup_form_profiles.yaml` 时无需改代码；涉及规则代码时同步补测试。
3. 部署按 AGENTS.md：web 与 worker 成对重启（独立会话、nohup + PID 文件），重启前跑 `python -m app.utils.deployment_preflight --env-file <env-file>`。
4. 上线后用最近一个周窗口真实数据回放一次，核对命中工单与规则消息可读性（业务语言）。
5. 提交归属：`backend/app/services/ops_audit/**` 与 `backend/scripts/sup_profile_probe.py` 为共享路径，按 AGENTS.md 判定准则归 main；如组分站规则最终划归广东项目分支，需先确认仓库布局再提交（当前工作树非 git 仓库，提交动作在代码仓库执行）。

## 明确暂缓（非确定性，本期不做）

- 照片"参数与上传图片一致"的视觉比对；
- 水印核验扩量（维持现有抽检+问题触发试点）；
- 备注语义深度判断（沿用现有"超范围有备注转人工"出口）；
- 品牌特有列的语义适配（VOCs/水溶性离子/甲醛多品牌），T0 盘点时标注，列缺失自动跳过。
