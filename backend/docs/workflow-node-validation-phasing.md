# DAG 节点验收分级与失败语义——分阶段放宽方案

状态：第一步已实施（2026-11-05，待重启生效）；第二、三步待观察数据后另行实施。
背景：2026-11-04 夜间广东两次助手 DAG（`qingyuan-oct-pollution-source-brief`、`qingyuan-oct-brief-v2`）
与 11-05 凌晨 `qingyuan-oct2026-pollution-tracing` 共 4 次运行、6 个节点失败的归因分析
（journal：`workflow_journal.db`；运行记录：`assistant_runs/4535f3ba…/delegation_*.json`）。

## 0. 故障归因结论（已核实）

同一份"产物形态"意图被三层机制表达（goal 文字、result_schema/deliverables、output_contract），
其中最严厉的执行点位于子代理最难修复的位置，导致高失败率：

| 层 | 机制 | 11-04/05 失败案例 |
| --- | --- | --- |
| 提交时校验 | submit_result 内 schema + deliverables 机械核对 | 11-05 新增，违规打回轮内修复（此前无此层，事后才发现） |
| 事后结构化校验 | call_sub_agent 提取最终答复 → schema + deliverables 核对 → 修复轮 ≤2 → 仍违规判死 | station 节点占位路径（path="a"）两轮未修复 |
| 资源契约 | input/output contract 的 `assert_resource_contracts` 一票否决、无重试（failure_policy=null） | qy-weather/qy-station：goal 要求 CSV、子代理交 JSON → format/fields 不符即死 |

另有数据面根因：采集库 MySQL（StationHour/StationDay）在本部署不存在，
`execute_crawler_sql_query` 每次取数必失败（已禁用）；站点逐小时六参数明细在监测体系内
无可用源，"交付逐小时 CSV"类 goal 客观不可满足，子代理只能如实声明缺口。

## 1. 已上线（2026-11-05 01:41 重启起）

| 项 | 内容 | 落点 |
| --- | --- | --- |
| 提交时校验前移 | submit_result execute 内即时执行 schema + deliverables 核对；失败提交 success=False（runtime 终止判定跳过失败提交），错误明细随 observation 回给子 Agent 轮内修复 | `app/tools/agent_tools/submit_result_tool.py` |
| deliverables fields 降档 | csv 表头与 records 列表 JSON 保持硬核对；报表包顶层键 JSON、图片等不可核对格式不再判死 | `app/agent/workflow/resource_contract.py::validate_deliverable_entries` |
| crawler 禁用 | 采集库 MySQL 非本部署数据源，项目级 `disabled_tools` 移除（许昌不受影响） | `projects/guangdong/project.yaml` |
| 交付规范提示词 | deliver 阶段描述与通用清单补"真实路径/fields 限制"一句 | `mode_workflows.py`、`delivery_checklists.py` |

## 2. 本次实施（第一步：资源契约形态不符降档）

**原则（已确认的产品决策）**：产物形态要求合理，但不应作为硬性指标导致节点失败；
缺数据直接失败并返回原因说明；结果合格性由父 Agent 裁决。

变更：`resource_incompatible`（format/fields 不符）从一票否决降为**记录不判死**，
违规经既有通道全量可观测；仅 `resource_missing`（required 上游整体缺失）保持 fatal。

| 落点 | 变更 |
| --- | --- |
| `resource_contract.py` | 新增 `fatal_resource_contract_violations`（仅 required+missing 判 fatal） |
| `coordinator.py` input 门 | 形态不符记录进 node_contract_errors / node_input_gaps 后放行下游；缺失仍阻断 |
| `coordinator.py` output 门 | 移除 assert，形态不符仅记录（契约已注入子 Agent 指令"## 资源契约"） |
| `coordinator.py` delivery/下游传播 | 非 fatal 契约违规照常以 resource_gap 透出（workflow 终态 partial） |
| `call_sub_agent.py` input 门 | 同上；形态不符以缺口提示注入子 Agent 上下文 |
| 测试 | 新增 3 个降档语义测试；`test_bad_output_…` 翻转为新语义 |

**保留的校验（未删除任何检查器，只拆 fatal 出口）**：提交时校验（打回修复）、
deliverables 机械核对、result_schema/x-evidence-references、资源契约 input missing 预检、
四种过程失败（异常/超时/取消/预算耗尽且始终未提交）、重试机制、delivery_checklist（observe）、
task_contract 定义校验、血缘校验、缓存复用校验。

**明确不改（已确认）**：station 逐小时明细无数据源属客观缺口，子代理如实声明 + 节点按
resource_missing 语义处理，不接运维口径工具补数（监测/运维两套体系不混用）。

## 3. 失败语义终态（方向，第二/三步完成后达成）

- **节点失败 = 过程失败**，仅四种：子代理异常崩溃、超时、被取消、预算耗尽且始终未提交结构化结果。
- **节点成功 = 正常提交了结构化结果**：字段违规、契约形态不符、自报 gaps 一律降为记录
  （metadata.validation_errors / node_contract_errors / delivery.gaps / 子代理自报 data_gaps），
  由父 Agent 按交付摘要与缺口裁决是否定向续用子会话补做（call_sub_agent session_id / steer）。
- 提交时校验保留——它是交付过程的打回机制（过程判断），不是结果合格性判死。

## 4. 第二步：事后校验 fatal 摘除（待观察数据）

- **前置观察（1–2 周真实 DAG）**：统计修复轮后仍有 validation_errors 的节点数
  （即"若本步已实施，节点本不会失败"的 would-have-failed 率）；
  同时统计提交时校验打回后轮内修复成功的比例（证明前移层有效覆盖）。
- **实施内容**：`_result_failed` 不再因 validation_errors 判死（降为 metadata 记录）；
  修复轮触发收窄为"未提交结构化结果"。
- **回退条件**：observe 期间出现"违规信封被父侧误当合格结果整合导致返工"的真实案例，
  或子代理交付质量指标（delivery.gaps 环比）恶化 → 保持现状并复盘。
- **实施方式**：独立提交，`git revert` 单步可回滚。

## 5. 第三步（可选）：修复轮触发收窄

仅在第二步稳定后评估：修复轮只剩"未提交"推送场景，"已提交但违规"不再修复。
预算影响：每次失败的修复轮约 1 分钟/几千 token。

## 6. 观察指标与查询

```sql
-- 节点失败按原因分类（error 前缀区分：结构化协议校验 / resource contract / 其他）
SELECT substr(ts,1,10) AS day, task_id,
       CASE WHEN payload LIKE '%结构化协议校验%' THEN 'protocol'
            WHEN payload LIKE '%resource contract%' THEN 'contract'
            ELSE 'other' END AS kind, count(*)
FROM workflow_events WHERE event_type='node.failed' GROUP BY 1,3;
```

- `assistant_runs/<user>/delegation_*.json`：`kind=workflow` 的 status 分布（failed 率）；
  `result.data.delivery.gaps` 中 `resource_gap` 条数（形态不符透出量）与 deliverable 标志。
- 子代理质量信号：结果信封 `data_gaps` 自报率、`node_contract_errors` 计数。

## 7. 决策记录

| # | 决策 | 日期 |
| --- | --- | --- |
| D1 | 产物形态要求合理但不判死；缺数据直接失败返回原因；结果合格性父 Agent 裁决 | 2026-11-05 |
| D2 | 站点逐小时明细不接运维口径工具（两套体系不混用），客观缺口如实声明 | 2026-11-05 |
| D3 | input 契约 required+missing 保留 fatal（下游零产物空跑浪费轮次），形态不符降档 | 2026-11-05 |
| D4 | 分阶段放宽：第一步契约降档先行，第二步事后校验 fatal 摘除需 observe 数据支撑 | 2026-11-05 |
| D5 | 专家分析类节点默认超时上调（初版 720/900/720，后按 D6 统一）；
      WORKFLOW_SCHEMA_DESCRIPTION 补编排引导（下限 900s，声明更小值会被抬到下限） | 2026-11-05 |
| D6 | **所有分析子 agent 超时下限 900s**：共享 expert_meteorology / expert_analysis /
      expert_component（含兜底 expert）默认与下限统一 900s，编排写更小值也抬到下限；
      广东 gd_ops_regular_analysis 420→900、gd_ops_risk_analysis 480→900 | 2026-11-05 |
| D7 | 图表呈现通道对齐：紧凑节点视图保留子信封图表声明形状（type/path/description）、
      新增 published_charts（chart-image 资源 resource_id/label/path）；schema 补
      [[chart:<resource_id>]] 引用引导；report 整合契约补"成稿前取图入包"一步。
      不新增平行资源机制——统一资源目录数据完整（父会话 156 资源、51 个
      chart-image 实证在册），修的是目录到模型上下文/渲染契约的投影 | 2026-11-05 |

## 8. 补充归因（2026-11-05 上午，超时预算类）

`qingyuan-oct-pollution-tracing`（09:23）失败与验收无关——验收降档已见效
（4 个数据节点全部一次通过，对比 11-04 夜间首轮 3/4 被打回）。本轮失败是**编排
参数类**：assistant 给专家分析节点写的 timeout_seconds（300/360s）小于其真实
运行时长（expert_meteorology 493s、expert_analysis 705s，见 round2 实测），
`asyncio.timeout` 在分析中途取消子代理，0 次 submit_result 尝试。重试扩档
（×1.5 → 450/540s）仍不够。同日 round2 由 assistant 重编排为 1200s 后双节点成功。

教训归类：**编排参数类失败**（超时/预算写小）与验收类失败分开观察；第一步的
验收降档不会引入此类失败。观察 SQL 中 timeout 类失败的特征串为
`workflow node timed out after`。

## 9. 补充归因（2026-11-05 中午，图表呈现通道）

`qingyuan-oct2026-traceability`（report 整合者 DAG，11:14）全部节点成功，子代理按
goal 产出图表并交付（PNG 落盘、子会话资源登记、信封 artifacts/deliverables 声明、
resource_refs 收集、父会话发布 resource_key=chart-image 全部正确——父会话 156 个
资源中 51 个 chart-image 在册），但父 Agent 视角"图一张没有"。根因是**统一资源目录
到模型上下文/渲染契约的投影缺口**，与资源目录无关：

1. compact 节点视图 artifacts 白名单字段（kind/name/url/resource_id）与子信封图表
   声明形状（type/path/description）不匹配 → 压缩成空对象，父侧看不到图表证据；
2. chart_urls 提取只认 /api/image/ URL 与 visuals，execute_python+matplotlib 落盘
   的图没有 URL → DAG 面板节点卡片无图可渲染；
3. [[chart:]] 别名只为父自己本轮产出的图绑定，workflow 发布的子图没有别名。

父侧因此反复自我修正（v2/v3/v4 多轮 refine，meteo-quant-v4 纯文字交付）。
修复（D7）：compact 视图保留图表声明形状 + published_charts 成列 + schema 引导
（[[chart:<resource_id>]] 经 finalizer 自动换 visual_id 渲染）+ report 整合契约
补"成稿前取图入包"。观察指标：report 会话中 published_charts 非空但最终报告
图片数为 0 的案例数（预期归零）。
