# 广东 Agent 模式上线实施方案（对标江苏分支）

> 生成时间：2026-10-25
> 前置状态：后端数据治理与语义治理已完成（data-ops 三层管道上线、6 个 Cube 语义域、87 张源表、35 个 dbt 模型），本方案覆盖"模式层"——把数据/语义能力接到前端 Agent 模式上。
> 实施基础分支：`project/guangdong`（本地领先远端 8 个提交，含 428d8608 及此前全部治理成果）。

---

## 一、现状盘点（实施前必读）

### 1.1 广东现有模式配置

`projects/guangdong/project.yaml`：

- `agent_modes`: assistant / ppt / expert / query / report / board / ops（7 个通用壳）
- `agent_platform_layout: scenes`
- `mode_prompt_files`: 仅 `ops: projects/guangdong/prompts/ops.md`
- `agent_mode_extra_tools.ops`: execute_guangdong_mart_sql / guangdong_query_metrics / query_gd_suncere_station_hour_new / query_gd_suncere_station_day_new / station_operation_daily
- 调度任务 5 个：gd_station_operation_daily / gd_station_alarm_status_watch / gd_work_order_timeout_watch / gd_work_order_monthly_report / gd_fault_diagnosis_watch

### 1.2 江苏模式体系（对标参照）

`origin/project/jiangsu-ops:projects/jiangsu-ops/project.yaml`：

- 10 个模式 + `default_agent_mode: ops` + `agent_platform_layout: coordinator`（首页"苏环智管"统筹，greeting/quick_prompts/attention_task_ids）
- 每模式三件套：**专属提示词**（prompts/*.md）+ **工具白名单**（agent_mode_tools）+ **welcome 文案**（name/short_name/description/features）
- 核心架构 `operations_analysis`：父 Agent 委派 **agent_workflow_modes**（10 个子模式，其中 7 个按数据域拆分的取数节点），配置含 positioning/scope/boundary/outputs/max_iterations/timeout_seconds；父级 budget（max_concurrency=3/max_nodes=16/max_retries=3/timeout=1200）在 `agent_workflow_parents`
- 设计动机（yaml 注释原文）：上周运维报告的数据台账任务在 8 次迭代内取不齐 8 个数据域（run_20261012 timeout）→ 按域拆子模式后父 Agent 无法把跨域任务塞给单个节点

### 1.3 广东数据/语义资产（模式的"弹药"）

| 数据域 | Cube | 核心宽表 | 口径红线（registry 已登记，提示词必须继承） |
|---|---|---|---|
| 工单 | WorkOrder | mart_work_order_analysis | 全类型含作废单，量/时效结论必须按 order_type/order_status 声明口径；超期率分母只计 plan_finish_time 非空单，例行维护单该口径失真（源系统 order_overtime 全 0），例行单超期以 orderOvertime 标记为准；响应类仅故障单可评估（到站=首个 FaultProcess）；重复故障仅故障单口径 |
| 告警通知 | AlarmNotify | mart_alarm_notify_analysis | 通知流水无处理闭环状态，**未处理率不可评估**；类型实测四类（站点断数/仪器断数/质控异常/小时浓度超标）；ALM_SUMMARY 已停更禁用 |
| 告警态势 | StationAlarmStatus | mart_station_alarm_status | 源系统只推送告警中站点（63/332），"未推送=无告警"不成立，只能表述"推送范围内" |
| 设备生命周期 | DeviceLifecycle | mart_device_lifecycle_analysis | 事件动作中文映射（周检/月检/季检/半年检/年检/启用/新增/停用/信息更新）；QuaryCheck 为源系统拼写（季检） |
| 巡检任务 | InspectionTask | mart_inspection_task_analysis | 完成态滞后于创建（每日全量刷新），最近 1-2 天"未完成"可能是尚未到时点；转工单率分母=全部任务项 |
| 绩效 | Performance | mart_performance_analysis | 平台口径原值不重算；每日 10:15 重算；金额单位元（合同/核减/扣款/实发）；扣减争议以 deduction_remark 原文为准；组分站无运维单位信息 |
| 通用 | — | dim_station（432 站主网+组分网，城市全站覆盖）/ dim_user（1,036 账号，敏感列已排除）/ dim_device | 城市/处理人/运维单位中文全可解析 |

工具面：`guangdong_query_metrics`（语义点查，6 cube，返回 semantic_context + quality_status）、`execute_guangdong_mart_sql`（31 表白名单受控 SQL）、`execute_ops_sql_query`（源库实时核对）、`query_gd_suncere` 系列（站点监测数据，**环境空气监测类一律走接口不入库**）、`station_operation_daily`、`ops_audit_*`（审核规则，取数已本地化）。

数据限制（提示词须声明）：今年窗口（{year_start}-01-01 滚动），窗口前历史不可查；组分站无经纬度/运维单位。

---

## 二、上线清单与依据

### 第一批（数据已就位，直接实施）

#### 1. `gd_query` 运维问数生图 ⭐ 首选起点

- **定位**（对标 jiangsu_query"运维问数生图智能体"）：广东运维指标查询、统计分析、图表生成；面向运维统筹与管理者
- **支撑**：6 Cube 全覆盖 + 语义点查 + mart 受控 SQL + gd_suncere 站点数据 + 图表工具
- **提示词要点**：
  - 指标类问题优先 `guangdong_query_metrics`（语义层口径唯一），明细/口径核对用 `execute_guangdong_mart_sql`
  - 继承 registry 全部口径红线（上表）+ semantic_context 必读（quality_status=blocked 时不形成业务结论）
  - 站点监测数据走 query_gd_suncere，不与工单库混用
  - 用户不暴露表名/SQL/工具名
- **工具白名单**：guangdong_query_metrics / execute_guangdong_mart_sql / query_gd_suncere_city_hour / query_gd_suncere_city_day / query_gd_suncere_district_day / query_gd_suncere_district_report / query_gd_suncere_regional_comparison / query_city_standard_report / query_city_standard_yoy_report / query_station_standard_report / analyze_city_pollutant_rankings / get_5min_data + 共享图表类（create_business_chart / aggregate_data 等按现有 query 模式）
- **welcome 文案**：name=广东运维问数智能体；description=查询广东运维工单、告警、巡检、绩效等指标并生成专业图表；features 列四类典型问题
- **工作量**：1-2 天（提示词 + project.yaml 模式定义/白名单 + 前端验证）

#### 2. `ops` 运维工单审核（已有，升级）

- **现状**：ops.md 已有完整工单语义字典 + 数据路由；ops_audit 已本地化提速
- **升级点**（半天）：
  - project.yaml 的 ops extra_tools 加 `guangdong_query_metrics`
  - ops.md 数据路由一节补语义层路由（现只有提示词内嵌目录，非提示词级工具引用）；补审核常用绩效/巡检对照口径
  - welcome 文案（若 scenes 布局支持）

#### 3. `station_fault_diagnosis` 站点故障诊断（交互模式）

- **定位**：用户按站点/工单即席诊断，与每日 07:30 调度扫描互补
- **支撑**：运维工单知识库（knowledge.bindings.station_fault_diagnosis 已映射）+ DeviceLifecycle 检修历史 + AlarmNotify 告警对照 + 故障原因语义字典（docs/work-order-semantics/02）+ 故障诊断提示词模板（ops.md 认知地图章节已有基础）
- **提示词要点**：先图谱检索形成候选原因 → 工单/设备事件/告警证据核验 → 输出必须含诊断路径/已查证据/原因排序/支持与否定证据/缺失信息/处置建议；图谱候选标注"候选、需现场核验"
- **工具白名单**：execute_guangdong_mart_sql / guangdong_query_metrics / knowledge_graph_query / knowledge_graph_build（如建图谱）+ 会话文件工具
- **工作量**：1 天

### 第二批

#### 4. `operations_analysis` 运维分析（重头戏，对标江苏）

- **架构**：父 Agent + agent_workflow_modes 子模式。按广东数据域拆 7 个取数节点 + 2 个分析节点：

| 子模式 | positioning | scope 摘要 |
|---|---|---|
| gd_ops_data_workorder | 工单数据准备 | 全类型工单批量指标/受控明细；口径=按类型与状态声明；响应类仅故障单 |
| gd_ops_data_alarm | 告警数据准备 | 通知流水四类分布/站点覆盖；态势快照（推送范围内）；禁止未处理率 |
| gd_ops_data_inspection | 巡检数据准备 | 任务项完成率/超期率/转工单率（按周期/监测项/站点）；完成态滞后口径 |
| gd_ops_data_performance | 绩效数据准备 | 站点×月考核得分/金额；平台口径不重算；金额四件套 |
| gd_ops_data_device | 设备数据准备 | 生命周期事件/检定执行/启停；状态枚举原文 |
| gd_ops_data_station | 站点数据准备 | 432 站名录/城市/运维单位/处理人解析；组分站信息缺口声明 |
| gd_ops_data_rates | 平台率值数据准备 | OPA_DataReceiveRate 到报率；率值以平台统计为准禁止自算 |
| gd_ops_regular_analysis | 常态监管专题分析 | 复用共享数据回答一个运维问题，不成稿 |
| gd_ops_risk_analysis | 风险线索专题分析 | 核验风险假设，要求反证（require_counter_evidence） |

- **父级 budget 起步值**：max_concurrency 3 / max_nodes 12 / max_retries 3 / timeout 1200（江苏 16 节点是 10 子模式成熟后的值，广东 9 个子模式先 12）
- **boundary 写法模板**照抄江苏：只取数和确定性整理，不作风险认定、不生成正式报告；跨域取数列入 data_gaps 交父 Agent 委派
- **前置依赖**：先完成 gd_query/ops 验证语义层在各模式下稳定可用；workflow 子模式机制需确认共享层 `agent_workflow_modes` 在 scenes 布局下的可用性（江苏是 coordinator，需读共享层代码确认是否与布局解耦）
- **工作量**：2-3 天

#### 5. `knowledge` 知识问答

- **前置**：`knowledge.collections` 目前为空——需创建知识库集合并上传文档；现成素材：work-order-semantics 三份字典 + 历史会商/报告
- 知识图谱（station_fault_diagnosis 依赖）需先 build：用故障原因字典 + DeviceLifecycle 事件做 KG 边（knowledge_graph_build 工具已在全局注册）
- **工作量**：1 天（含 KG 构建）

#### 6. coordinator 协调者首页（"广东智管"）

- `agent_platform_layout` scenes → coordinator，配置 name/greeting/placeholder/quick_prompts/attention_task_ids
- quick_prompts 建议：今日运维态势（接 gd_station_alarm_status_watch 数据）/ 工单超时预警 / 本月绩效概况
- attention_task_ids：gd_work_order_timeout_watch / gd_fault_diagnosis_watch
- **前端配套**：需按 coordinator 布局改造前端（江苏有现成实现可参照 frontend diff）；涉及前端发版
- **工作量**：后端配置半天，前端改造视前端排期

### 不上线 / 暂缓（含理由，避免后续重复讨论）

| 模式 | 理由 |
|---|---|
| device_control | 广东源库无设备控制接口，无数据与权限支撑 |
| smart_event_external / smart_event_instrument | 广东无智能事件平台数据接入（江苏依赖专门同步） |
| ppt / report / board 项目专属化 | 通用模式已可用，等真实场景反馈再定制 |
| 独立质控子模式 | 广东质控数据仅评价日期/设备日检查，无质控执行曲线（监测类走接口），不支撑独立域；并入工单/巡检分析 |
| expert | 广东有 expert 模式壳，暂保留现状，等 operations_analysis 上线后视需要把气象研判类并入 |

---

## 三、实施顺序与验收

```
第1步 gd_query（1-2天）      → 产出 prompts/gd_query.md + project.yaml 模式定义 + 白名单 + welcome
第2步 ops 升级（0.5天）      → ops extra_tools 加语义层工具；ops.md 路由补齐
第3步 station_fault_diagnosis（1天）→ 提示词 + 知识库/图谱就绪检查
第4步 operations_analysis（2-3天）→ 9 个 workflow 子模式 + 父级 budget + 提示词
第5步 knowledge（1天）       → collections 建库 + KG 构建
第6步 coordinator（0.5天+前端）→ 布局切换 + 前端改造
```

每步验收标准：
1. `load_project_context('guangdong')` 加载新配置无错、模式出现在 manifest
2. 该模式下工具白名单在 web 日志 `get_react_agent_tool_registry_debug` 中与配置一致（多/少工具都要查原因）
3. 用典型问题实测该模式对话：指标类问题走语义层且返回 semantic_context；口径红线被遵守（如问"告警未处理率"应被口径拦截）
4. 提交到 `project/guangdong` 分支（模式配置+提示词均属项目分支）

## 四、关键注意事项

1. **project.yaml 归属**：模式配置全在 `projects/guangdong/project.yaml`（项目分支），不碰共享层
2. **提示词语言规范**：沿用 ops.md 的强制规范——面向业务用户不出现技术语言；数据缺失如实说明缺口
3. **口径红线必须从 registry 继承到每个提示词**（各数据域 caveats 是硬约束不是参考），特别注意：告警无未处理率、态势仅推送范围、例行单超期口径、绩效平台口径不重算
4. **工具白名单收敛原则**（江苏注释原文值得照抄）："该白名单同时用于提示词和函数 schema；新增工具必须经过项目评审后加入"；每模式只放本模式链路必需工具
5. **workflow 子模式与布局解耦性待确认**：实施第 4 步前先读共享层 agent_workflow_modes 的加载代码（backend/app/agent/ 下 workflow mode 相关），确认 scenes 布局可用；不可用则第 4 步与第 6 步绑定（一起切 coordinator）
6. **前端**：新模式的 welcome/features 文案写进 project.yaml 后，需确认前端 scenes 布局会读取 manifest 渲染（江苏 agent_modes 下每模式的 name/description/welcome 结构就是给前端用的）；模式卡片不出现时查前端 manifest 消费逻辑
7. **测试**：project.yaml 变更后跑 `backend/tests/project_config/test_routing.py` 与 `test_mode_prompt_overrides.py` 防回归

## 五、本方案引用的关键文件

- 模式配置：`projects/guangdong/project.yaml`（现 97 行，改前先备份结构）
- 现有提示词模板：`projects/guangdong/prompts/ops.md`（语言规范/语义字典/数据路由的范本）
- 口径事实源：`projects/guangdong/data-ops/semantic/registry.yaml`（提示词口径红线的唯一来源，改口径先改这里）
- 数据集契约：`projects/guangdong/data-ops/sync/datasets/*.yaml`（各表 grain/guide/limitations）
- 江苏参照（只读，不要改动）：`origin/project/jiangsu-ops:projects/jiangsu-ops/project.yaml` 与 `projects/jiangsu-ops/prompts/*.md`
- 治理总览：`projects/guangdong/data-ops/README.md`、`projects/guangdong/data-ops/docs/source-survey-20261024.md`

---

## 六、实施记录（2026-10-25）

### 已实施（本分支提交）

| 步骤 | 状态 | 产出 |
|---|---|---|
| 第1步 gd_query | ✅ 配置完成 | `prompts/gd_query.md` + `agent_mode_tools.gd_query`（全量白名单）+ welcome 文案 |
| 第2步 ops 升级 | ✅ 配置完成 | extra_tools 此前已含语义层工具；`ops.md` 补绩效/巡检对照口径；welcome 文案 |
| 第3步 station_fault_diagnosis | ✅ 配置完成 | `prompts/station_fault_diagnosis.md` + 白名单（图谱/语义层/站点数据/会话文件） |
| 第4步 operations_analysis | ✅ 配置完成 | 父提示词 + 9 个子模式提示词（`prompts/internal/`）+ `agent_workflow_modes`/`agent_workflow_parents`（并发3/节点12/重试3/补图2/1200s） |
| 第5步 knowledge | ⚠️ 配置完成，建库待部署环境 | `prompts/knowledge.md` + welcome；`bindings.station_fault_diagnosis` 已配置；collections 建库与文档上传、故障诊断图谱构建需在运行系统执行（见下） |
| 第6步 coordinator | ⛔ 被共享层阻塞（见下） | 未改动布局，仍为 scenes |
| 前端 | ✅ 源码完成 | `frontend/src/config/agentModes.js` 静态目录补 gd_query/station_fault_diagnosis/operations_analysis 三条目（knowledge 原有）；需在部署环境 `cd frontend && npm run build:standalone` 重建发版 |
| 测试 | ✅ 新增 | `backend/tests/project_config/test_guangdong_modes.py`（manifest/白名单/提示词/workflow 契约断言） |

### 实施中发现的关键约束（与原计划的差异）

1. **新模式 id 必须全量声明 `agent_mode_tools`**：共享 `get_tools_by_mode` 对不在共享模式表内的 id，只有声明了 `agent_mode_tools` 才能解析（`agent_mode_extra_tools` 只对共享已有模式生效）。因此 gd_query / station_fault_diagnosis / operations_analysis / 9 个子模式全部走 `agent_mode_tools` 全量白名单，`ask_user_question` 已显式写入各交互模式白名单（新模式不在共享 `INTERACTIVE_QUESTION_MODES` 内，不会自动追加）。
2. **workflow 校验强制**：`run_agent_workflow` 必须出现在父模式的 `agent_mode_tools`（不含 extra_tools）；子模式必须同时有 `agent_mode_tools` 与 `mode_prompt_files` 条目、不得声明委派工具、不得出现在 `frontend.agent_modes`——均已满足。
3. **第 4 步解耦性已确认**：`agent_workflow_modes`/`agent_workflow_parents` 的加载（`backend/app/agent/workflow/project_policy.py`）不读 `agent_platform_layout`，scenes 布局下 operations_analysis 可正常编排子模式，第 4 步无需与第 6 步绑定。
4. **前端静态目录**：manifest overrides 只能覆盖既有静态条目，新 id 必须在 `frontend/src/config/agentModes.js` 有条目否则模式卡片被过滤（`getAgentMode` 返回 null）。已在项目分支补条目（沿用江苏分支同一做法；回合 main 时注意与江苏条目合并）。

### 第 6 步 coordinator 阻塞详情

当前共享层（main 与本分支）`agent_platform_layout: Literal["scenes", "environment-grid"]` 不含 `coordinator`；前端 `AgentPlatform.vue` 只实现 scenes 渲染路径。coordinator 的完整支持（models.py 的 CoordinatorManifest 扩展、前端首页改造）目前在 `project/jiangsu-ops` 分支。**上线 coordinator 必须先把江苏分支的 coordinator 共享层改动回合 main，再在广东切布局**；在那之前不得把 `coordinator` 写进 project.yaml（会被 Literal 校验拒绝导致 manifest 加载失败）。

### 待部署环境执行的验收与运行时动作

1. 重启 web/worker 后：`load_project_context('guangdong')` 加载无错、新模式出现在 manifest；web 日志 `get_react_agent_tool_registry_debug` 核对各模式白名单。
2. 跑 `backend/tests/project_config/test_guangdong_modes.py` 与既有 `test_routing.py`、`test_mode_prompt_overrides.py` 回归。
3. 典型问题实测：gd_query 指标类问题走语义层且返回口径说明；问"告警未处理率"应被口径拦截；operations_analysis 试一次多域报告编排（注意 max_nodes=12 预算）。
4. 第 5 步运行时动作：创建知识库集合并上传 work-order-semantics 三份字典与历史会商/报告；用 `knowledge_graph_build` 以故障原因字典 + DeviceLifecycle 事件构建故障诊断图谱（绑定名"广东运维工单知识"需解析到启用图谱的知识库）。
5. 前端重建发版：`cd frontend && npm run build:standalone`，并按 AGENTS.md 校验构建产物。
