# 江苏运维平台工作流与 Agent 能力定位及落地方案

> 适用项目：江苏省运维审核管理服务平台  
> 文档状态：实施基线  
> 编写日期：2026-09-11

## 1. 目标

在现有运维平台和江苏智能体平台之上，明确哪些能力应固化为定时/事件工作流，哪些能力应保留为 Agent 交互分析，哪些能力采用混合模式，避免把原平台的页面和接口简单搬进聊天框。

总体原则：

```text
工作流负责固定事实、规则计算、状态推进和结果落库
Agent 负责目标理解、动态取证、解释归因、建议和成果表达
人工负责高风险业务确认
```

## 2. 当前实现基础

当前江苏项目已经具备以下基础能力：

- `projects/jiangsu-ops/project.yaml` 已配置“小值/苏小环”协调入口、专业模式、关键词路由和任务关注项。
- `backend/app/services/jiangsu_smart_event_automation.py` 已实现智能事件扫描、证据采集、队列、重试和并发控制。
- `backend/app/services/jiangsu_smart_event.py` 和 `backend/app/tools/jiangsu/smart_event_workspace.py` 已提供事件工作区和证据上下文。
- `backend/app/tools/jiangsu/fault_diagnosis.py` 已提供告警、工单、站房环境和质控历史取证工具。
- `backend/app/tools/jiangsu/work_order_dispatch.py` 已提供工单草案、字段校验、审计和人工确认机制。
- `backend/app/services/ops_work_order_audit_engine.py` 及 `backend/app/services/ops_audit/` 已提供工单审核计算和问题清单生成能力。
- `projects/jiangsu-ops/skills/工单轨迹合理性分析/SKILL.md` 已定义月度签到轨迹分析 SOP。
- `backend/app/services/jiangsu_feedback_loop.py` 已提供事项、人工决策、业务动作和复查结果的反馈闭环。
- `frontend/src/components/coordinator/CoordinatorHome.vue`、`CoordinatorCommandCenter.vue` 和 `TaskSchedulerCenter.vue` 已提供统一入口、工作区和任务中心的前端基础。

当前主要缺口是：业务能力仍以单个工具或通用 Prompt 任务暴露，轨迹分析等固定任务尚未具备独立的工作流执行类型，命令中心部分内容仍属于场景演示，工作流结果与 Agent 会话尚未形成统一回流链路。

## 3. 能力定位原则

### 3.1 适合工作流的特征

满足以下大多数条件时，应优先工作流化：

- 输入范围和触发周期相对固定。
- 数据源和步骤可以提前定义。
- 指标、规则和筛选条件需要稳定复现。
- 输出对象和字段结构稳定。
- 需要定时运行、事件触发、失败重试和幂等。
- 结果需要写入待办、报告或业务状态。
- 结果可以被人工或后续业务动作验证。

仅有“流程复杂”不能作为工作流化依据。还需要同时满足“流程变化率低”和“输出变化率低”。如果业务规则相对稳定，但管理者经常要求改变分析维度、排序方式、解释深度或报告结构，应保留 Agent 主导。

### 3.2 适合 Agent 的特征

满足以下特征时，应保留 Agent 主导：

- 用户目标、时间范围或分析维度不确定。
- 需要自然语言澄清和多轮追问。
- 取证路径需要根据中间结果动态调整。
- 需要跨领域综合解释和不确定性表达。
- 同一事实需要面向不同角色生成不同表述。
- 主要产出是分析意见，而不是修改业务状态。

### 3.3 混合模式

复杂运维场景采用以下边界：

```text
工作流确定事实
  -> Agent 解释事实和提出建议
  -> 人工确认高风险动作
  -> 工作流执行、复查和关闭
```

Agent 不应直接决定数据剔除、责任认定、工单关闭或设备控制；这些动作必须进入业务接口、审批和审计链路。

混合模式也不等于把整个场景做成固定工作流。对于输出变化快的场景，建议采用“Agent 主流程 + 确定性分析服务”的形式：数据获取、指标计算和规则校验由代码保证稳定，结果组织、比较、解释和报告内容由 Agent 按用户目标动态生成。

## 4. 江苏场景定位矩阵

| 场景 | 推荐方式 | 工作流职责 | Agent 职责 |
| --- | --- | --- | --- |
| 全省站点异常扫描 | 工作流 | 定时拉取告警、断数、离线、巡检，去重、分级、入队 | 生成态势摘要和重点说明 |
| 智能事件证据采集 | 混合 | 事件归并、证据采集、快照、重试、队列状态 | 根据证据诊断和生成处置建议 |
| 运维轨迹月度分析 | Agent 主导 + 分析服务 | 提供取数、指标计算、规则筛选和证据引用服务 | 按用户目标组织维度、解释线索、归纳单位问题、调整报告输出 |
| 工单批量审核 | 混合 | 确定审核范围、规则审核、问题清单、报告和待办 | 语义复核、证据说明、整改建议 |
| 网络巡检汇总 | 工作流 | 汇总全网巡检状态、异常城市和站点 | 解释变化和排序原因 |
| 数据质量巡检 | 工作流 | 缺测、断数、有效率、接收率和新鲜度检查 | 生成异常摘要和影响说明 |
| 报告生成与分发 | 工作流为主 | 按模板生成和投递 PDF、Excel、PPT | 面向受众调整摘要和表达 |
| 结果复查 | 工作流 | 延时查询恢复状态、更新闭环、重新打开 | 解释复查结果 |
| 江苏问数生图 | Agent | 可提供受控查询和产物服务 | 理解问题、补全参数、分析和制图 |
| 站点复杂故障诊断 | Agent + 工作流 | 固化取证、草案校验、审批、执行和复查 | 动态决定取证路径和候选根因 |
| 污染过程/来源研判 | Agent | 提供数据和成果工具 | 综合监测、气象、轨迹和知识证据 |
| 知识库问答 | Agent | 提供检索、文档阅读和引用接口 | 检索、上下文阅读和可追溯回答 |
| 设备反控 | 工作流包裹执行 | 权限、确认、执行、回执、复查和审计 | 理解用户意图并生成操作草案 |

## 5. 运维轨迹分析的具体定位

现有“工单轨迹合理性分析”虽然有月度执行节奏和固定数据来源，但管理问题、分析维度和报告重点会持续调整，不建议现在改造成完整的固定工作流。更合适的定位是 Agent 主导，配套确定性轨迹分析服务。

### 5.1 分析服务步骤

```text
获取上月人员、单位、站点和签到数据
  -> 解析人员/单位/责任站点关系
  -> 计算跨市、距离、频次、间隔和覆盖指标
  -> 按规则识别待核查线索
  -> 按人员和单位聚合结构化结果
  -> 返回可供 Agent 使用的结构化证据和规则命中
  -> Agent 根据用户目标生成摘要、比较和报告
```

### 5.2 分析服务输出

每个分析周期应保存：

- 分析月份和数据范围；
- 数据记录数、缺失情况和数据新鲜度；
- 人员、运维单位、责任站点的稳定标识；
- 覆盖站点数、覆盖城市数、跨市次数、远距离签到次数和相邻到站间隔；
- 重复到站、覆盖失衡和跨区域串单等规则命中项；
- 原始签到记录或业务记录引用；
- “待核查线索”结论，不输出“违规”或“造假”结论；
- 分析服务版本和证据快照 ID；是否创建待办、生成何种报告由 Agent 根据具体任务决定。

### 5.3 Agent 的主要职责

Agent 只接收工作流生成的结构化结果，负责：

- 解释某人员或单位为何被标记；
- 归纳跨人员、跨区域的共性模式；
- 提出属地承接、同路合并、专项治理等管理建议；
- 根据用户追问展开人员、单位或区域分析；
- 生成领导简报或管理层摘要。

签到是离散到站事件，不是连续 GPS 轨迹。工作流和 Agent 均不得据此推断完整行车路线、离站时间、在站时长或违规事实。

## 6. 第一批工作流

第一批工作流只选择流程和输出都相对稳定的场景。轨迹分析不在其中，先作为 Agent 场景保留。

### 6.1 `jiangsu_network_inspection_summary`

- 触发：每日或每小时定时。
- 结果：全网巡检状态、异常城市和站点统计、固定格式的摘要和待办候选。
- 首要目标：验证固定口径的定时工作流、幂等和结果回流。

### 6.2 `jiangsu_station_event_evidence_refresh`

- 触发：事件产生、证据过期或定时复查。
- 复用：`jiangsu_smart_event_automation.py`、`jiangsu_smart_event.py` 和现有江苏取证工具。
- 流程：事件归并 -> 证据采集 -> 证据快照 -> 重试和状态更新。
- 工作流只负责事实和证据准备；诊断、处置建议和工单草案仍由 Agent 完成。

### 6.3 `jiangsu_task_verification_refresh`

- 触发：待复查任务到期或业务结果事件到达。
- 结果：查询监测恢复、工单状态或现场结果，更新事项为已闭环、重新打开或需要补证。
- 该流程步骤和状态迁移固定，适合优先工作流化。

### 6.4 `jiangsu_work_order_audit_batch`

- 触发：每日、每周或按运维单位定时。
- 复用：`ops_work_order_audit_engine.py` 和 `backend/app/services/ops_audit/`。
- 流程：确定范围 -> 抽取工单和附件 -> 确定性审核 -> 语义候选复核 -> 最终问题清单 -> 待办 -> 正式报告。
- 最终问题清单仍以现有审核技能和人工复核协议为正式口径。

## 7. 工作流任务模型改造

当前 `backend/app/api/scheduled_task_routes.py` 的任务模型主要是 `prompt + execution_mode + tool_names + schedule/event`，建议增加：

```text
execution_kind: agent | workflow
workflow_id: Optional[str]
workflow_version: Optional[str]
input_schema: Optional[dict]
result_schema: Optional[dict]
approval_policy: Optional[dict]
```

示例：

```json
{
  "name": "江苏站点证据定期刷新",
  "execution_kind": "workflow",
  "workflow_id": "jiangsu_station_event_evidence_refresh",
  "workflow_version": "v1",
  "trigger_type": "schedule",
  "schedule_type": "monthly",
  "input_schema": {"month": "previous_month"},
  "approval_policy": {"create_task_review": true, "business_action": "manual"}
}
```

执行器分为两条路径：

```text
ScheduledTask
  +-- execution_kind=agent    -> 现有 Agent 执行器
  +-- execution_kind=workflow -> WorkflowRunner
```

`WorkflowRunner` 必须提供固定步骤、输入输出校验、重试、幂等、结构化结果保存、产物生成、待办创建和审计记录。

## 8. 建议的代码结构

```text
backend/app/workflows/
  __init__.py
  registry.py
  models.py
  runner.py
  context.py
  errors.py

backend/app/workflows/jiangsu/
  network_inspection_summary.py
  station_event_evidence_refresh.py
  task_verification_refresh.py
  work_order_audit_batch.py
```

工作流通过注册表暴露：

```python
WORKFLOW_REGISTRY.register(
    "jiangsu_station_event_evidence_refresh",
    JiangsuStationEventEvidenceRefreshWorkflow(),
)
```

工作流内部复用现有工具，不重新实现接口：

```text
workflow
  -> JiangsuAttendanceRecordsTool
  -> JiangsuStationDirectoryTool
  -> JiangsuWorkOrderTrackAnalysisTool
  -> submit_task_review
  -> create_report_package
```

## 9. Agent 与工作流的数据契约

工作流传给 Agent 的输入应为结构化证据包：

```json
{
  "scenario": "operations_analysis",
  "scope": {"month": "2026-08", "province": "江苏省"},
  "facts": [],
  "rule_hits": [],
  "data_quality": {},
  "evidence_refs": [],
  "boundaries": [
    "签到记录不是连续 GPS 轨迹",
    "结果仅代表待核查线索"
  ]
}
```

Agent 返回值也必须结构化：

```json
{
  "summary": "...",
  "management_findings": [],
  "recommendations": [],
  "uncertainties": [],
  "follow_up_questions": []
}
```

工作流只接受通过 schema 校验的字段，不直接把 Agent 自由文本作为业务状态或最终审核结论。

## 10. 实施顺序

### 阶段一：轨迹分析确定性分析服务

1. 明确月度输入、指标和证据输出 schema。
2. 将指标计算、规则命中和人员聚合从 Prompt 执行中拆出。
3. 生成稳定 `subject_id` 和证据快照 ID。
4. 提供 Agent 可调用的结构化分析服务。
5. 由 Agent 根据具体管理问题决定是否创建待办和生成何种报告。

验收标准：

- 相同输入得到相同分析结果；
- 每条线索可追溯到原始记录；
- Agent 可以按不同问题复用同一份分析结果；
- 结果明确标识待核查边界；
- Agent 生成的报告和待办引用分析服务的证据快照。

### 阶段二：工作流任务类型和调度器

1. 扩展定时任务模型和 API。
2. 新增 `WorkflowRunner` 和项目工作流白名单。
3. 增加执行记录、版本、重试和幂等字段。
4. 在任务中心展示工作流状态和产物。

验收标准：

- 工作流和 Agent 任务可以共存；
- 事件触发和定时触发都可用；
- 失败可重试，超时可恢复；
- 执行过程和业务产物可审计。

### 阶段三：接入苏小环

首页展示轨迹分析服务的最新数据范围、待核查线索数、涉及人员和单位数及最近分析结果。用户追问时，Agent 读取结构化分析结果，并按当前问题生成摘要、比较或报告。

### 阶段四：迁移智能事件和工单审核

复用轨迹工作流建立的任务状态、证据引用、待办、报告、人工反馈和复查机制，逐步将智能事件和批量工单审核迁移到同一套工作流协议。

## 11. 高风险动作边界

所有写操作采用：

```text
prepare -> review -> approve -> execute -> verify
```

必须人工确认的动作包括：

- 正式派发、修改或关闭工单；
- 关闭告警；
- 数据剔除或修正；
- 责任单位或违规事实认定；
- 设备反控；
- 对外发送正式通知。

已有 `work_order_dispatch.py` 的草案、字段校验、审计和执行后复查机制应作为其他写操作的参考实现。

## 12. 成功指标

第一阶段重点不是模型准确率，而是闭环完整性：

- 至少 90% 的工作流事项能关联来源、结构化结果、人工决策和业务结果；
- 重复执行不产生重复待办或重复业务动作；
- 关键状态变化均有审计事件；
- 轨迹分析能区分数据不足、待核查线索和人工确认结果；
- 每周能输出工作流运行成功率、耗时、待办处理率和反馈问题清单。

后续再按场景增加准确率、误报率、人工修改率、闭环时长和建议采纳率等指标。

## 13. 最终结论

第一批实施顺序确定为：

```text
网络巡检汇总工作流
  -> 事件证据刷新工作流
  -> 任务复查工作流
  -> 工作流任务模型和调度器
  -> 苏小环结果回流
  -> 工单批量审核工作流

运维轨迹分析单独走 Agent 主导路线：先建设确定性分析服务，再由 Agent 按不同管理问题调用和组织输出。
```

工作流解决稳定运行和业务闭环，Agent 解决理解、推理和表达。两者通过结构化证据包、任务 ID、待办和产物关联，而不是通过一段不可验证的自然语言串联。
