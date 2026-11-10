# 工单审核自我迭代机制设计（阶段 1）

> 状态：设计中/分阶段实施。本文记录共识与已落地的部分，作为后续实施的依据。
> 范围：`backend/app/services/ops_audit/**` 审核引擎的迭代优化闭环。

## 1. 背景与问题

工单审核（`ops_audit`）已具备完整执行链路：确定性规则 + 语义复核 + 人工确认面板 + 报告产出。
现状存在"软迭代已有、硬迭代缺失"的结构性问题：

- **已有的软迭代**：人工反馈经记忆整合写入案例库（`cases.jsonl`），下次语义复核以
  `agent_case_guidance` 注入 prompt 作参考——仅是软指导，不改变任何规则本体。
- **缺失的硬迭代**：规则配置（`configs/*.yaml`、语义口径）只能人工修改；同类误报
  反复出现，反馈从不回写规则。

目标：建立"信号采集 → 台账 → 月度复盘（只读报告）"闭环。阶段 1 不自动修改任何规则，
但让每次人工修改都有数据依据；自动生效留待阶段 2 按数据逐步放开。

## 2. 为什么不是"塞进周审任务"或"全自动优化"

- 复盘需要跨期聚合反馈，周审是单期窗口；定时任务跑完无审批交互窗口。
- 周审是执行任务、复盘是改规则任务，耦合会让周审 prompt 膨胀且失败面叠加。
- 样本量小（周审节奏），小样本自动改规则极易过拟合；审核域漏报比误报更隐蔽，
  用户反馈以 exclude 为主，自动优化会系统性放松规则。
- 规则配置的版本管理依赖 git，LLM 直接改文件不可审计。

结论：**定时触发的独立机制 + 人工审批护栏，自动化程度分阶段放开**。

## 3. 三通道信号输入

三通道覆盖信号空间的不同象限，互补而非互斥：

| | 系统报了 | 系统没报 |
|---|---|---|
| 不该报（误报） | 通道1 exclude | — |
| 该报（正确/漏报） | 通道1 include（正样本） | **只有通道2 能覆盖** |
| 数据错/漂移 | 通道3 分诊 | 通道3 间接暴露 |

### 通道1：面板逐项裁决（已存在，已接台账）

人工确认面板（`HumanFeedbackPanel` → `POST /api/agent/{session_id}/human-feedback`
→ `apply_human_feedback`）产生结构化强监督：`include → confirmed`、
`exclude → rejected`、`pending → 不落账`（无信号）。include 是置信度校准的
正样本证据，与 exclude 同等入账。

结构性盲区：只能纠正"系统怀疑过的"，规则未触发的漏报不经过面板。

### 通道2：用户核对清单对账（阶段 1 步骤②）

用户线下核对后**主动提交问题清单文档**（ops 会话上传，Excel/Word/文本）。
核心是对账而非落账——清单与当期审核结果逐单比对才产生信号：

| 清单项 | 审核结果 | 台账 outcome |
|---|---|---|
| 说有问题 | 报了同类问题 | `confirmed` |
| 说有问题 | 没报 | `missed`（最稀缺信号） |
| 说没问题 | 报了问题 | `rejected` |
| 未提及 | 报了问题 | 仅"全量核对"声明下 `tacit_confirmed`（低权重） |
| 未提及 | 报了问题 | 部分清单 → 不入账（无信息量） |
| 工单号不在期次 | — | `unmatched`（回显提示） |

关键机制：

- **全量/部分声明**决定 tacit 信号是否成立；`tacit_confirmed` 必须与显式判定分开计权
  （声称全量核对但未细看是常态）。
- **匹配粒度是（工单 × 问题项）对**，不是工单级。
- **对账以确定性 join 为主**（order_code + 问题类型），语义匹配仅兜底——对账数错了
  下游全歪。
- 对不上 rule_id 的 missed 项本身就是"候选新规则"证据（台账 rule_id=null 的语义）。
- 对账结果回显会话，用户口头纠正同样落账；原始文件 + 解析 JSON 归档 execution 目录。

### 通道3：回库校验分诊（阶段 1 步骤③，随月度复盘）

性质是自动化的证据一致性验证，不是人类反馈：对台账 `rejected` 项重取该工单当前
源库数据比对 evidence，三分类：

- `verified`：源数据一致，判定站得住 → rejected 才是纯口径问题；
- `data_drifted`：源数据变了（工单事后被改/补录）→ 回流数据管道问题清单，**不是规则问题**；
- `evidence_mismatch`：引用错数据 → 规则实现 bug 信号。

价值：给通道1 做归因分诊，防止把数据管道问题误当规则问题去"优化规则"。
放在复盘任务内按月批处理（只对台账记录回查，控 DB 负载），不独立成任务。

## 4. 指标定义（长期跟踪）

| 指标 | 定义 | 可计算条件 |
|---|---|---|
| 识别率（查全） | `confirmed / (confirmed + missed)` | 任何时候（部分清单也可算） |
| 错误率（1−查准） | `rejected / (confirmed + rejected + tacit_confirmed)` | **仅全量声明**；部分清单显示"不适用" |

- 始终带分子分母显示（"78%（14/18）"），防小样本过度解读；趋势用滚动窗口
  （如近 8 期累计计数再算比率）。
- 按规则族分解是复盘的定位器。
- 面板通道产生平行比率（面板排除率/确认率），与清单指标交叉验证：两通道背离
  本身是信号（如确认疲劳）。

存储：当期指标随对账归档 execution 目录；时序追加
`memory/ops/audit/ledger/metrics_history.jsonl`。

## 5. 反馈台账（已实现 v1）

统一 append-only JSONL：`<data_registry>/memory/ops/audit/ledger/feedback_ledger.jsonl`。

```json
{"schema_version": "ops_audit_feedback_ledger.v1", "recorded_at": "...",
 "channel": "panel|checklist|db_recheck",
 "outcome": "confirmed|rejected|missed|tacit_confirmed|verified|data_drifted|evidence_mismatch",
 "explicit": true,
 "order_code": "...", "rule_id": "rf_xxx|null", "issue_id": "...", "item_id": "...",
 "execution_ref": "<task_id>/<execution_id>|null",
 "station_id": "...", "original_judgment": "rule_detected|pending_semantic_review|...",
 "reason": "...", "feedback_id": "...", "reviewer": {...},
 "source_ref": "final_issue_list 路径", "snapshot_ref": "面板打开时的 issue list sha256"}
```

约定：

- `rule_id=null` 表示规则目录未覆盖的信号（候选新规则），是合法且有语义的值。
- `execution_ref` 从产物路径解析（`scheduled_tasks/executions/{task_id}/{execution_id}`），
  交互式运行为 null，`source_ref`/`snapshot_ref` 兜底回溯。
- 模块：`backend/app/services/ops_audit/feedback_ledger.py`
  （`append_records` / `query_records` / `read_records` / `aggregate_by_rule` /
  `derive_execution_ref` / `normalize_record`）。
- 面板落账在 `apply_human_feedback`（service 层，原子重写成功后 best-effort 追加，
  失败仅告警不阻断反馈——原始判定仍存于 `last_human_feedback` 与会话 metadata）。

## 6. 月度复盘定时任务（阶段 1 步骤③）

唯一新增定时任务：`projects/guangdong/scheduled_tasks/gd_ops_audit_monthly_retrospective.json`
（每月 1 日 07:00，`execution_mode: custom`，`skill_id: ops_audit_retrospective`，
`history_learning.enabled: true`——跨月记忆防止重复提交上月已否决的提案）。

内部两层，沿用审核引擎"确定性在前、LLM 在后"的哲学：

1. **统计层（代码）**：`ops_audit_retrospective_stats` 工具产出 stats JSON——指标时序
   汇总、按 rule_id 人工推翻率、confidence 分布 vs 实际结局、missed+null 规则聚合、
   通道3 回库分诊。**不让 LLM 数数。**
2. **叙事层（LLM）**：`backend/docs/skills/ops_audit_retrospective.md` 技能指引复盘
   agent 读统计 → 写 markdown 报告。报告契约：开篇 KPI → 分流清单（口径问题 /
   数据管道问题 / 候选新规则 / 校准参考）→ 变更建议（带证据链、预期影响面、
   建议改动的配置文件）。**只读红线：不修改 configs/*.yaml、不调 run_rules。**

## 7. 阶段路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| 1-① | 反馈台账 + 通道1 面板落账 | **已实现**（2026-11-11） |
| 1-② | 通道2 对账工具 `ops_audit_reconcile_checklist` + 指标统计 | 待实施 |
| 1-③ | 月度复盘任务 + 通道3 回库分诊 | 待实施（原料依赖①②攒数据） |
| 2 | 提案 → 重放验证 → 审批（复用 task_review 状态机）→ 确定性生效 | 数据攒够后设计 |
| 3 | 低风险白名单自动生效 + 例库向量检索（bge-m3/Qdrant 基建现成，但吸取长期向量记忆因检索无效被移除的教训，先用重放验证证明增益） | 视阶段2 数据 |

阶段 2 的重放验证是安全性的核心护栏：规则引擎确定性 + 语义复核工件全落盘，
任何提案可在上期真实数据上重放出精确影响面（"采纳后上周 213 单中 7 条判定改变"）。

## 8. 分支归属与测试

- 共享层（先提交 main，再回合 `project/guangdong`）：
  `backend/app/services/ops_audit/**`、`backend/app/tools/**`、`backend/docs/**`、
  `backend/tests/**`。
- 项目分支：`projects/guangdong/scheduled_tasks/gd_ops_audit_monthly_retrospective.json`。
- 测试：`backend/tests/test_ops_audit_feedback_ledger.py`（台账与面板落账）；
  通道2 落地时补对账分类矩阵表驱动测试与指标 gating 测试（部分清单不算错误率、
  tacit 权重分离）。

## 9. 阶段 1-① 实施记录

- 新增 `backend/app/services/ops_audit/feedback_ledger.py`：台账存储/查询/聚合。
- 修改 `backend/app/services/ops_audit/review_artifacts.py`：
  `apply_human_feedback` 在两个裁决循环中以变更前状态构造台账记录
  （`_panel_ledger_record` 捕获 original_judgment），持久化成功后
  `_append_feedback_ledger` best-effort 追加，返回值新增 `feedback_ledger_count`。
- 新增 `backend/tests/test_ops_audit_feedback_ledger.py`（7 用例）；
  `backend/tests/test_ops_audit_review_artifacts.py` 增加 autouse fixture
  隔离台账路径（避免测试记录写入真实 data registry）。
- 已知环境限制：本机 `D:\conda\envs\backend_py311` 缺 `anthropic`，语义复核链路
  相关测试无法收集，属环境问题；改动涉及且可收集的 27 个测试全部通过。
