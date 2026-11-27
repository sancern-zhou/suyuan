# Workflow 资源契约格式不符误标 partial 问题说明（2026-11-08）

> 历史分析。下文 `warnings/gaps` 分流方案未实施，已由
> `backend/app/agent/workflow/ORCHESTRATION.md` 的“2026-11-08 交付验收简化定案”取代：DAG 的
> input/output resource contracts 已整体移除，终态只由真实节点执行状态决定。


对应 [`assistant-delegation-polling-incident-20261108.md`](assistant-delegation-polling-incident-20261108.md) 问题清单第 3 项（workflow 假阴性 partial）的深入分析与修复方案。本文档只做分析定案，代码修复另行提交。

## 背景

- **2026-11-05（清源项目教训）**：qy-weather / qy-station 两节点因"子代理交付 json 而契约写 csv"被废掉整个节点。据此做了节点级收窄（`fatal_resource_contract_violations`，`backend/app/agent/workflow/resource_contract.py:317`）：仅 `required` 上游资源**整体缺失**（`resource_missing`）保持 fatal；形态不符（`resource_incompatible`，format/fields 与契约不一致）只记录不判死。
- **2026-11-08（本次事故）**：简报 workflow 三个节点全部 succeeded、产物齐全，但某节点交付 json、契约写 csv，整个 workflow 终态仍被标为 `partial`。主 Agent 看到 partial 误以为缺了内容，thinking 里自己发现了真相（"partial only due to resource contract format mismatches, not actual missing content"），仍花大量轮次核实"缺什么"。

**收窄只做了一半：节点级不判死了，workflow 级终态判定没有同步收窄。**

## 因果链（代码证据）

```
编排模型声明契约 format:"csv"
        │  子模式实际交付 .json（产出格式由交付管道固定，模型改不了）
        ▼
coordinator.py:859  节点完成后 check_resource_contracts([output_contract], result_handles(...))
        ▼
resource_contract.py:270  "format: expected csv, got json" → code="resource_incompatible"
        ▼
fatal_resource_contract_violations()：非 fatal，节点照常 succeeded（coordinator.py:862 注释）
        ▼
coordinator.py:446-448  非 fatal 违规收进 delivery()["gaps"]（status="resource_gap"）
        ▼
coordinator.py:627-628  incomplete = any(failed/blocked) or bool(self.delivery()["gaps"])
                        self.status = ... "partial" if incomplete else "succeeded"
        ▼
coordinator.py:475  partial → next_actions=["deliver_with_gaps","extend_missing_evidence"]
run_agent_workflow.py:141  工具描述："收到 partial 时按 delivery.gaps 交付…说明缺口"
run_agent_workflow.py:994  status + delivery.gaps 原样返回主 Agent
        ▼
主 Agent 误判缺证据，烧 turns 排查
```

## 根因分层

1. **直接原因：两处语义脱节。** 11-05 的收窄只在节点级原谅形态不符，`_run()` 终态判定的 `bool(gaps)` 没有同步——节点说"这不是失败"，workflow 聚合却把它当"未完成"。

2. **深层 A：`delivery.gaps` 语义过载。** 三种异质项混在同一数组、参与同一布尔：

   | gaps 来源 | 性质 | 是否该参与 incomplete |
   |---|---|---|
   | failed/blocked 节点 | 真缺 | 该（已被第一项覆盖） |
   | `resource_missing`（含 optional） | 资源没产出，真缺但可选 | 该——"visible and partial"是有意设计（见下） |
   | `resource_incompatible`（json vs csv） | 资源在、内容在，只是格式与声明不符 | 不该——是"注意项"不是"缺口" |

3. **深层 B：format 声明在受理期就注定不可满足。** 契约是编排模型的"愿望"，实际产出格式由子模式交付管道固定（query 系固定 json envelope、office 出 docx/xlsx）。这与 `_CONSTRAINTS_WITHOUT_PRODUCER`（granularity/time_range 等无生产通道的键在解析期直接拒绝，`resource_contract.py:24`）是同一类病，但 format 没做子模式能力对照。

## 方案评审记录（含另一 Agent 修法的边界确认）

评审过的修法：终态判定时 gaps 只统计"致命缺口（failed/blocked 节点、fatal 的 resource_missing）"，非致命契约违规留在 gaps 里作信息展示、不参与 incomplete。

**根因定位一致，但排除范围过宽，不可直接采纳**：

- 把 optional 的 `resource_missing` 也移出 incomplete，会破坏既有测试锁定的设计：
  `resource_contract_test.py:167 test_optional_contract_gap_is_visible_and_partial`（上游零产出、契约 `required=False` → 断言 `status == "partial"`）、`:178 test_optional_output_gap_reaches_downstream_context` 同。可选资源缺失是**真缺口**（那部分证据确实没拿到），partial + `deliver_with_gaps` 让父侧显式带缺口交付，语义正确，本次事故也未涉及此类误报。测试名即设计意图："visible **and partial**"。
- "fatal 的 resource_missing 参与判定"是冗余项：fatal missing 在节点执行前抛 `ResourceContractError`（coordinator.py:804-806）→ 节点 failed → 已被 `any(node.status in {"failed","blocked"})` 覆盖。
- "违规留在 gaps 作信息展示"不如分流：`gaps` 继续混装"真缺口"与"格式注意项"，父侧提示词（`run_agent_workflow.py:141`）与 `delivery_checklists.py:117` 均按"缺口"语义读 gaps，格式注意项混入后仍可能被模型再次当缺口解释（事故 thinking 已演示过一次）。

## 修复方案（按 code 分流，不是按"非致命"一刀切）

1. **`delivery()` 分流**（coordinator.py:446-448）：`code == "resource_incompatible"` 的违规移出 `gaps`，放入新数组 `warnings`（同结构，含 details，保持可见性——下游消费格式时知道实际是 json 不是 csv）；`resource_missing`（含 optional）留在 `gaps`，维持 partial 语义与既有测试不变。
2. **`_run()` 判定收窄**（coordinator.py:627-628）：`incomplete` 不再被 `resource_incompatible` 贡献。效果：节点全 succeeded + 仅格式不符 → `status="succeeded"` + `delivery.warnings=[...]`。
3. **自动联动无需改动**：`next_actions`（coordinator.py:475）按 status 分支，status 转 succeeded 后不再建议 `extend_missing_evidence`；`deliverable/complete` 同步正确。
4. **裁决权不变**：warnings 仍进 snapshot 并经 `delivery` 透传（run_agent_workflow.py:994），父 Agent 若确需 csv（如面向用户交付表格），仍可定向续用子会话补做——与 11-05"由父 Agent 裁决"的设计一致，只是不再被假阴性逼迫。
5. **保留不动**：`node_input_gaps`（coordinator.py:540/798）向下游节点的信息性提示——不参与状态判定，继续提供"上游格式与契约不符"的执行上下文。

**治本（可选二期）**：DAG 受理期做 format 与 target_mode 产出契约的能力对照（describe_mode 已有该数据），注定不可满足的 format 声明解析期拒绝、编排模型当场改稿——对齐"不让必死的契约进入运行期"的既有哲学。

## 测试影响面

- `test_optional_contract_gap_is_visible_and_partial` / `test_optional_output_gap_reaches_downstream_context`：构造的是 **missing**，不受影响，仍 partial。
- `test_required_output_contract_mismatch_records_but_node_succeeds`（resource_contract_test.py:229-230，在 gaps 里找 csv）：需改为在 `warnings` 里断言。
- `test_bad_output_is_flagged_but_not_fatal_and_bad_cache_not_reused:208`、`test_required_input_contract_mismatch_no_longer_blocks_downstream:234`：宽松断言 `in {"succeeded","partial"}`，兼容。
- 新增回归：节点全 succeeded + format mismatch → `status=="succeeded"` 且 `delivery.warnings` 有记录、`gaps` 无该项。

## 状态

- 方案已定案（按 code 分流），代码修复待实施。
- 同日已实施：事故修复方向 1/2（委派阻塞等待 + 轮次边界回灌 + 熔断改道），见 `backend/tests/test_assistant_delegation_wait.py` 与提交记录。
