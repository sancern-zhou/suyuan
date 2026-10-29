# 组分站例行工单审核二期开发计划（基于真实问题案例提炼）

> 生成时间：2026-10-25。素材：三份人工排查的问题案例文档（2026-09-14~09-20、09-21~09-30、未注明区间，共 **18 条案例**，原文归档于 `docs/sup-audit-cases/`），辅以文档内 20 张问题表单系统截图的多模态识别，并逐单反查 `sup_rf_common` / `wo_commonfile` 本地数据实证。

---

## 一、案例库与多模态识别结论

### 1.1 表单形态（截图识别）

| 截图证据 | 表单形态 | 关键结构 |
|---|---|---|
| BC 监测仪年度维护检定记录（丰顺八乡山） | 年度维护检定类 | 头信息（市/站点/运维单位/检查日期/设备品牌型号编号/送检时间）+ 附件清单（过程照片 jpg 逐张上传）；人工红框标注"缺完整维护报告" |
| 甲烷/非甲烷总烃质控结果每周记录（博罗石下） | 周质控类 | 钢瓶信息/动态校准/峰面积数值列 + **Excel 质控数据附件**；附件照片带**时间+地点+经纬度水印**（截图实证：工单站点=惠州博罗石下，照片水印=河源市源城区·河源中学，23.72N/114.69E） |
| 激光雷达周巡检记录表（OCEC 升温程序） | 数值巡检类 | 题目项=参数×单位×标准范围×实测值×备注说明（如"实际升温程序温度偏差"按 OC/EC/甲烷定量/无氧/有氧/内标分阶段，标准 ±10%） |
| PANs 校准仪流量季度检查（潮州西园路） | 流量核查类 | 设定值/仪器读数/流量计读数/修正标况读数/**设定误差**（可复算公式列） |
| 质控任务周视图（深圳莲花山等） | 周期计划总览 | 站点×设备类型×频次×质控任务矩阵，周期日未完成标橙——"填写不及时"的人工判定来源 |

### 1.2 数据结构实证（本地库反查）

- **`sup_rf_common.ruleitemtag` 即表单类型编码**（45 种，组分站专属 43 种，如 `Sup_RF_Week_NMHCQC`、`Sup_RF_PDLIYearCheck`、`Sup_RF_PANsFlowCheck`）——二期规则的"表名"维度，等价主网 RF 分表名。
- **题目项列是通用命名**：string×150、bool×50（如 string3=人员姓名、string50/51/52=数值），列语义必须**按 ruleitemtag 逐类型建档**。
- **附件表 `wo_commonfile.typecode` = ruleitemtag**，文件名业务可读（"仪器内部清洁.jpg"、"NMHC监测仪零气空白等质控数据-9月23日.xlsx"）；一张工单可挂多个表单体（丰顺八乡山同单挂 BC 年维护 + 激光雷达年检两份表单）。
- 18 条案例工单全部在本地数据集命中，涉及 **15 种表单类型**；甲烷/非甲烷周质控（`Sup_RF_Week_NMHCQC`）与激光雷达年度检定（`Sup_RF_PDLIYearCheck`）是问题高发类型。

### 1.3 案例问题分类（18 条 → 7 类）

| 问题类 | 案例数 | 典型案例（工单号后 10 位） |
|---|---|---|
| ① 缺报告/证明类附件 | 7 | 丰顺八乡山 BC 年检缺维护报告（0216699673，附件仅 7 张 jpg 无报告）；湛江吴川振文 3 单缺年度预防报告；韶关八中 NH3 采样管检查附件缺失；龙川细坳换滤膜附件缺失 |
| ② 填写不及时/周期超期 | 4 | 云浮牧羊 NH3 季度、湛江海大甲烷半年、深圳莲花山/盐田港多任务、惠州江北周质控超期（8748201535） |
| ③ 数值公式/阈值填写错误 | 3 | PANs 设定误差公式可复算填错（8520167552）；N2O 示值误差>±2% 未重新校准；OCEC 温度偏差列填了绝对温度 |
| ④ 附件与站点/项目不一致 | 2 | 博罗石下附件照片水印为河源中学（0563610130）；惠州江北 BC 工单缺 BC 仪器附件 |
| ⑤ 必填数值空白 | 1 | 韶关八中 OCEC 升温程序数值空白（9542767165） |
| ⑥ 日期错误 | 2 | 动态校准仪日期有误；甲醛标准溶液有效期应一个月内填错 |
| ⑦ 超范围未备注 | 1 | 江门鹤山水溶性离子柱压超范围未备注（8101238626） |

---

## 二、案例提炼的审核规则清单（二期新增）

档案驱动，统一落 `configs/sup_form_profiles.yaml`（按 ruleitemtag：列名→业务标签/角色/单位/公式/阈值/备注要求 + 必需附件类型），判定框架复用主网规则引擎的档案机制。

| 规则 ID | 对应问题类 | 判定逻辑 | 数据来源 | 案例实证 |
|---|---|---|---|---|
| SUP_ATTACHMENT_REQUIRED_MISSING | ① | 维护检定类表单（年/半年周期）按档案要求 report/certificate 类附件（pdf/doc/docx/xls），仅 jpg 过程照片 → fail | wo_commonfile（typecode=ruleitemtag，文件名+扩展名分类） | 丰顺八乡山 7 jpg 无报告；吴川振文 3 单 |
| SUP_ATTACHMENT_ITEM_MATCH | ④ | 附件文件名/类型码与表单监测项目（pollutanttype）、设备类型匹配；周质控表单要求含 Excel 数据文件 | wo_commonfile + sup_rf_common | 惠州江北 BC 工单无 BC 附件 |
| SUP_ATTACHMENT_WATERMARK_STATION（视觉试点） | ④ | 附件照片水印（地点/经纬度/时间）与工单站点、检查日期比对；不一致 → fail（需现场核验） | 附件照片 + 视觉识别管线（复用主网 visual_evidence） | 博罗石下照片水印=河源中学；照片时间 vs checkdate 偏离 |
| SUP_FORMULA_RECALC | ③ | 档案标注公式列（如设定误差=(修正读数-设定值)/设定值×100%），复算与填写值偏差超容差 → fail | sup_rf_common 数值列 | PANs 设定误差填 0% |
| SUP_RANGE_OUT_OF_SPEC | ③⑦ | 档案标注阈值列（标准范围），超范围且有备注 → uncertain，超范围无备注 → fail | sup_rf_common 数值列 | N2O 示值误差>±2%；柱压超范围未备注 |
| SUP_REQUIRED_VALUE_EMPTY | ⑤ | 档案标注必填数值列（分阶段表单支持"/"+说明备注豁免 → uncertain） | sup_rf_common | OCEC 升温程序数值空白 |
| SUP_DATE_REASONABLENESS | ⑥ | 档案标注日期列（有效期/检定日期/校准日期）：有效期<检查日期、检定日期晚于检查日期、日期晚于填写日 → fail | sup_rf_common 日期列 | 甲醛标液有效期；动态校准仪日期 |
| SUP_CYCLE_TIMELINESS | ② | 周期任务未在周期窗口内完成填写（前置：核实质控计划数据源；备选口径=checkdate 距 createtime 偏离、周期窗口末未完成） | 工单+表单侧（质控计划表待核实） | 云浮牧羊/湛江海大/深圳莲花山 |

一期已覆盖并继续生效：流程链（FLOW_*）、生命周期闭环、三段流转人员必填（RF_REQUIRED_FIELD_LOW_VALUE 人员组）、站点一致性（RF_STATION_MISMATCH）、检查日期存在性。

---

## 三、二期开发计划

### 阶段 2.1 表单档案建设（约 3~4 天，关键路径）

- 产出 `configs/sup_form_profiles.yaml`：P0 = 案例涉及 15 种 ∪ 表单量 Top10（PANsStabilityCheck、Week_BJCCheck、OcecHeliumMethaneCheck、VoCsTianHongCheck、Quarter_YT_NMHCRecord、OcecOrganicCarbonCheck、TurbidiMeterRoutineCheck/Calibration、OCECSamplingFlowCheck、HP_Precision 等），**约 20 种、覆盖组分站表单体约 70%**。
- 方法：逐类型抽样 3~5 份表单核对 string/bool 列与截图页面字段，标注角色（formula/range/date/required/remark_required）与阈值；**阈值类需业务确认**（±2%、±10%、C1/C2 等以页面注明与运维考核口径为准）。
- 每类型 0.5 天（含抽样核列与确认记录）；分两批交付（案例高发 6 种先行）。

### 阶段 2.2 确定性规则实现（约 2~3 天）

- 新增 `rules/sup_form_rules.py`（SUP_FORMULA_RECALC / SUP_RANGE_OUT_OF_SPEC / SUP_REQUIRED_VALUE_EMPTY / SUP_DATE_REASONABLENESS）与 `rules/sup_attachment_rules.py`（SUP_ATTACHMENT_REQUIRED_MISSING / SUP_ATTACHMENT_ITEM_MATCH），全部档案驱动、支持按 ruleitemtag 启用开关；复用 Issue/证据结构与 `rf_form_names` 显示名（45 种类型补全中文显示名）。
- 单测：每条规则至少 2 例（命中/豁免），并以 18 条案例构造回归夹具（注意其中 4 条案例工单"已退回修改"，回归口径以案例描述时点为准）。

### 阶段 2.3 视觉水印一致性试点（约 1~2 天）

- 复用主网视觉证据管线，选 `Sup_RF_Week_NMHCQC`（周质控、案例实证、表单量大）试点：附件照片水印地点/经纬度与工单站点比对，输出人工核验任务（先"抽检+问题触发"模式，不做全量，控制视觉调用成本）。

### 阶段 2.4 及时性规则（约 0.5~1 天，依赖核实）

- 核实质控周期计划数据源（源系统质控计划/任务表是否已同步本地；截图周视图来自质控模块）；若计划数据不可得，一期先落"表单侧口径"（checkdate 与 createtime 偏离、周期窗口末未完成）并在综述声明口径差异。

### 阶段 2.5 验证与上线（约 1 天）

- 18 案例回归：预期命中 ≥ 14 条（②类 4 条视数据源核实结果）；无视觉规则冒烟（沿用一期方法）；组分站每周任务手动触发一次全量验收（由你择时），确认卡片与综述质量。

### 里程碑与总量

| 批次 | 内容 | 预计 |
|---|---|---|
| M1 | 案例高发 6 种表单档案 + R1/R5 规则（附件缺失、必填空白） | 2.5 天 |
| M2 | P0 其余类型档案 + R4/R6 规则（公式/阈值/日期） | 3 天 |
| M3 | 视觉水印试点 + 及时性规则 | 2~3 天 |
| M4 | 回归验证 + 全量验收 | 1 天 |

合计约 **8.5~9.5 个工作日**（业务阈值确认会另计）。

## 四、待确认问题

1. 阈值口径来源：±2%、±10%、C1≤0.1ppm 等以表单页面注明的厂商/方法标准为准，还是另有运维考核细则文件？建议业务方提供一份组分站质控指标阈值表，档案按其校准。
2. 视觉水印试点范围：仅 Week_NMHCQC 抽检，还是扩到全部年维护检定类（附件量更大）？
3. "填写不及时"的判定基准：以质控计划周期为准（需核实计划数据可得性）还是以工单创建/检查日期偏离为准（可立即落）？
4. 组分站设备台账缺失（一期已知）是否同期解决：若能提供组分站设备台账同步，设备一致性规则可一并纳入二期。

---

## 五、阶段 2.1 + 2.2 实施记录（2026-10-25，已落地）

M1+M2 批次（表单档案 + 确定性规则）已实现并通过 18 案例回归，视觉水印试点（阶段 2.3）与设备台账类规则未含。

### 代码改动（backend，分支 project/guangdong）

1. **表单档案** `backend/app/services/ops_audit/configs/sup_form_profiles.yaml`（新增）：22 种 ruleitemtag 建档，覆盖 18 案例涉及类型 ∪ 表单量 P0 类型。档案驱动项：必需附件类（report/data_file，含命中率依据）、公式列（PANs 设定误差=（仪器读数-设定值）/设定值×100%，三流量点）、阈值列（OCEC 升温程序温度偏差 ±10%、PANs 误差 ±10%）、必填数值列（OCEC 炉温/偏差，"/"+备注豁免）、日期对（NMHC 钢瓶有效期/动态校准仪校准周期、HONO 标液 30 天有效期）、周期及时性参数。推断性阈值均标 `confirmed: false` 待业务校准；加载器 `config.load_sup_form_profiles()`。
2. **表单规则** `rules/sup_form_rules.py`（新增）：SUP_FORMULA_RECALC（表达式 AST 白名单安全复算）、SUP_RANGE_OUT_OF_SPEC（超范围无备注=高、有备注=中人工复核）、SUP_REQUIRED_VALUE_EMPTY（空白=高、"/"无备注=中、"/"+备注豁免）、SUP_DATE_REASONABLENESS（日期对标准周期档位/覆盖检查日期/先后顺序）、SUP_CYCLE_TIMELINESS（表单侧口径：填写滞后+质控数据文件日期过期，文件名支持"2026年8月30日/9月23日/2026-10-12至2026-10-18"等格式并取区间末）。
3. **附件规则** `rules/sup_attachment_rules.py`（新增）：SUP_ATTACHMENT_REQUIRED_MISSING（按 typecode=ruleitemtag_监测项目 匹配附件，报告/数据文件缺失判失败，"无需送检"等备注豁免）、SUP_ATTACHMENT_ITEM_MATCH（全部附件监测项目后缀与表单 pollutanttype 不符判失败）。
4. **引擎接入**（`ops_work_order_audit_engine.py`）：两规则挂入 enable_non_visual 分支，仅处理带 RULEITEMTAG 的表单，主网 RF 分表零影响（有专项测试）。7 条规则登记 rule_catalog/scoring 硬错误/taxonomy 分类；`rf_form_names.py` 补全组分站 94 种类型中文显示名（`sup_form_display_name`）。
5. **档案建设工具** `backend/scripts/sup_profile_probe.py`：列语义/公式统计推断脚本（阶段 2.1 后续建档复用）。

### 案例回归与验证

- **单测 33 个**（规则命中/豁免/引擎分发/主网不受影响）全通过；全量 ops_audit 回归 509 测试，24 个失败经 git stash 基线对照确认**全部为预存问题**（12 个与基线一致 + 12 个一期已记录的视觉/OCR 环境差异），SUP 相关零失败。
- **18 案例回归**（`tests/test_sup_case_regression.py`，案例时点状态重建）：**14/18 工单命中**（达到计划 ≥14 口径；12 条案例 + 吴川 3 单分别计数），命中分布：附件缺失 5（丰顺/吴川×3/江东）、及时性 4（深圳/云浮/湛江海大/惠州江北数据过期）、公式 1（PANs）、阈值 1（清远 OCEC）、必填 1（韶关 OCEC）、日期 2（惠州下埔 56 天/东莞东城标液 61 天）。
- **确定性盲区 4 条+1**（逐条注明原因）：惠州江北 BC 附件（需组分站设备台账，待确认问题 4）、吴川 N2O 示值误差（表单类型未定位+阈值待业务确认）、韶关 NH3 采样管/龙川换滤膜（bool 题目项级要求且表单未同步）、江门柱压（数值在 xlsx 数据文件内，需数据文件读数规则扩展）、博罗石下水印（属阶段 2.3 视觉试点）。
- **真实库冒烟**（近 14 天 400 单/325 表单/4024 附件）：SUP 命中 8 单（2%），噪声修正（钢瓶区间档位检查移除——"生产日期/启用日期+1年"两种填法并存产生系统性误报；文件名区间日期取区间末）后余留命中均为可解释问题（PANs 复算不符 3、填写滞后/数据过期 3、动态校准仪 61 天 1、OCEC"/"无备注 2）。

### 遗留与后续

- 阶段 2.3 视觉水印试点、阶段 2.4 质控计划数据源核实、水溶性离子柱压 xlsx 读数规则（复用 O3 量值传递 XLS 模式）另行排期。
- 全部 `confirmed: false` 阈值（PANs 误差 ±10%/容差 0.5、OCEC ±10%、动态校准仪周期档位、标液 30 天、及时性滞后天数）待业务方按第四节问题 1 提供口径后校准。

---

## 六、阶段 2.3 视觉水印试点实施记录（2026-10-25，已落地）

### 前置修复（关键）

`ocr_adapter` 的独立视觉调用在 go 网关下全部 400 失败——根因是缺少 OpenCode Go 网关要求的 `x-opencode-session` 路由头（`llm_service` 主链路已带该头，视觉适配层漏掉）。已在 `_call_vision_model` 补充网关头（User-Agent + 会话 ID），**deepseek-v4.1-flash 实测支持多模态图片输入**，修复同时生效于主网全部视觉规则。

### 代码改动

1. **`rules/sup_watermark_rules.py`（新增）**：`SUP_ATTACHMENT_WATERMARK_STATION`（水印与站点/检查日期不一致 → 中严重度人工核验，不直接判失败）与 `SUP_ATTACHMENT_WATERMARK_READ_FAILED`（识别失败 → 低严重度技术诊断，不进报告问题清单）。比对维度：站点名/城市/地址与水印地点字符重合（2 字滑窗）、站点坐标与水印坐标距离（组分站坐标缺失时自动跳过）、水印时间落在检查日前 `time_window_days` 窗口。
2. **抽检+问题触发模式**：工单已被其他规则命中 → 照片全检（每单上限 `max_photos_per_order`）；其余按工单号稳定哈希抽样（`sample_rate`，同单跨次运行判定一致）；每次运行视觉调用量由 `max_tasks_per_run` 硬顶（近 14 天触发口径共 115 个候选任务，运行硬顶保护生效）。均可由 `OPS_AUDIT_SUP_WATERMARK_*` 环境变量覆盖。
3. **试点范围**：仅 `Sup_RF_Week_NMHCQC`（档案 `watermark_check` 开关）；照片按 `typecode=tag_监测项目` 精确归属表单。
4. **取数扩展**：`fetch_dataset_local` 站点投影增加 CITYNAME/ADDRESS/LONGITUDE/LATITUDE，`_station_meta_by_id` 透传——城市/地址参与地点比对，解决"东城站照片水印=东莞市大气环保体验馆"这类站名与水印无字面重合的系统性误报。
5. 规则目录/复核阶段（manual_visual_review、technical_diagnostic）/taxonomy 登记完成。

### 真实验证

- **单测 45 个**（含水印试点 12 个，视觉调用全 mock）全通过；既有全量回归零新增失败。
- **8 个代表性站点 29 张真实照片批量验证**（视觉调用成功率 29/29）：博罗石下（整改后水印=博罗县·石下屯村）、东城（城市匹配修复后）、下埔、紫马岭、牧羊、从化天湖、鹤山花果山共 27 张正确通过；龙川细坳 2 张标记 time_outside_window——核查发现该单检查日期填了 **2026-10-30（未来日期）**，标记属实且额外暴露"检查日期填未来日期"数据质量问题，非误报。
- **端到端链路**：audit_dataset(enable_visual=True) 全窗运行成功，运行级调用量硬顶（cap=6）生效；产物与生产 `latest_*` 文件隔离（`backend/output/sup_phase2_acceptance/`）。
- 案例锚点说明：博罗石下案例的原错误照片（水印=河源中学）已随退回整改被替换，当前数据无真实"跨站水印"样本；错站误报路径由单测夹具（博罗站×河源水印）覆盖，视觉读取真实性由 29 张真实照片验证。

### 遗留

- 组分站坐标（dim_station.longitude/latitude）当前全空，坐标比对自动跳过；台账/坐标补齐后距离比对自动生效。
- `time_window_days=7`、`sample_rate=0.3`、`distance_km_threshold=5` 为试点参数，待业务确认。
- 明日（周一 11:30）组分站每周任务将自动带全部二期规则运行，跑后核查产物即可替代手动全量验收。

---

## 七、阶段 2.4 及时性计划口径实施记录（2026-10-25，已落地）

### 数据源核实结论（原"待核实"项已解决）

质控计划任务表**已同步本地**：`guangdong_mart.sup_mtc_taskitem`（2.7 万行，1.29 万工单），按工单号+ruleitemtag+监测项目提供 `planfinishtime`（周期计划完成日）与 `finishtime`（实际完成）。全局分布：约 87% 当天完成、≤4 天占 96.6%，超 5 天属少数异常。

### 代码改动

1. **取数**（`ops_work_order_audit_local.py`）：sup 模式增取 `sup_mtc_taskitem`（工单号过滤）→ 数据集 `sup_taskitems` 键。
2. **及时性规则升级**（`rules/sup_form_rules.py`）：有计划任务项时按**计划口径**——表单创建晚于 `planfinishtime` 超过宽限 `plan_late_grace_days`（默认 5，档案 `defaults.timeliness`，confirmed: false）判"填写不及时"；无任务项时**回退**原表单侧口径（检查日期滞后），数据文件过期检查不变。evidence 声明所用口径。
3. 真实对照（14 天 606 单）：计划口径命中 3 条 plan_overdue（2 条为表单口径漏抓的真实超期）+ 4 条数据文件过期；原表单口径误判的台山端芬单被计划口径正确豁免（计划允许更晚完成）。已知答案回归 12/12 持平。

### 丰顺工单同步缺口核查结论（原遗留项已查明）

案例工单 CH2609241790216699673（BC 年检缺报告）**不是同步漏单**：源系统侧该工单已被删除（人工判定后退回作废），本地 `working_orders` 同步如实删除；`sup_rf_common`/`wo_commonfile`/`sup_mtc_taskitem` 无级联清理，遗留孤儿行。审核以工单表为锚跳过该单属正确行为。**数据运维改进项**：为 sup_rf_common/wo_commonfile/sup_mtc_taskitem 增加孤儿行级联清理（workingordercode 不在 working_orders 时删除），避免脏数据累积。

### 后续待办

- 代码提交（共享层 `backend/app/services/ops_audit` 的分支归属口径待定）；
- 周一 11:30 组分站每周任务自动全量运行后核查产物（等效验收）；
- 业务方阈值口径表（校准全部 confirmed: false 项）、组分站设备台账/坐标同步。

---

## 八、审核窗口与视觉开关口径修正（2026-10-25，业务确认后落地）

1. **审核窗口**：`weekly_created` 预设由"周三锚、仅创建时间"修正为业务口径——周一审核**上上周完整自然周（周一 00:00 至下周一 00:00）创建且完成**的工单（如 10-26 运行审核 10-12~10-18）。改动：`audit_window.yaml`/`audit_window.py`（周一锚 + 完成时间窗口）、`dataset_fetcher`（应用完成窗口）、任务提示词与工具描述。新增窗口单测 4 个。
2. **视觉识别默认关闭**：`ops_audit_run_rules` 的 `enable_visual` 默认值改为 **false**，定时审核与常规审核只跑非视觉规则；视觉审核（主网照片读数规则 + 组分站水印核验）仅由用户明确要求时手动触发（`enable_visual=true`，可配 `visual_rule_id` 单独触发某条，枚举已补 `SUP_ATTACHMENT_WATERMARK_STATION`）。技能文档与两个任务提示词（仓库 JSON + 持久化存储）同步更新。
