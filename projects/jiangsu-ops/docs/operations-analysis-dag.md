# 运维监管分析内部 DAG

入口保持 `operations_analysis`。简单指标直接查询，确定性统计使用现有工具；多专题报告、复杂风险交叉核验才委派。日常监管和风险防范分别加载技能、分别成稿。

| 内部模式 | 输入 | 职责 | 边界 |
| --- | --- | --- | --- |
| jiangsu_ops_data | 对象、日期、指标口径或已有数据 | 批量准备可复用数据，检查覆盖和分母 | 不解释风险、不成稿 |
| jiangsu_ops_regular_analysis | 共享数据、一个监管问题 | 确定性核算、异常清单、管理解释与必要图表 | 没有业务查询工具 |
| jiangsu_ops_risk_analysis | 共享数据、一个风险假设 | 支持证据、反证、替代解释、缺口与必要图表 | 不查询、不认定违规或责任 |
| jiangsu_ops_evidence | 明确对象、最小窗口、待核验事项 | 只读补查实时记录和单据 | 不全网扫描、不派单、不提交审核、不反控 |

子模式仅由此父模式调用，不出现在前台，不再次委派。共享层读取项目配置，其他项目不加载这些能力。执行时强制相应结果结构和证据引用关系，调用者不能以自定义宽松结果 schema 绕过校验。

## 分配原则

1. 固定日期、省控站点范围、数据截至时间、指标口径和交付目标。
2. 同源批量准备数据；已取得数据直接复用。多个专题需要同一来源时共享一个资源，不按城市、日期机械拆节点。
3. 每个分析节点只回答一个问题，计算、证据摘要、所需图表最多三项交付。必须共享中间计算状态的任务合并，独立问题并行。
4. 用 `dependencies` 传递结果与资源引用；可使用 `input_contracts`/`output_contract` 校验真实字段、单位、时间、粒度及对象元信息。元信息缺失不能假定满足契约。
5. 已知条件使用 `when`；首轮结束后只有具体缺口影响结论时才补图。追加核验节点，再按需追加依赖旧分析与新证据的修订分析节点，不重跑旧节点。
6. 父模式只检查口径、覆盖和具体冲突，复用图表并成稿，不固定增加全面复核 Agent。

## 节点任务契约

每个节点提供 `task_contract`，含 `protocol_version: workflow.v1`、`task_type: expert_analysis`、`question`、`scope`、`required_evidence`、`deliverables`。

`scope` 写明 `time_range`、`objects` 和 `metric_definitions`；`context` 提供适用技能口径、阈值、实际输入资源引用和图表需求。不是让子 Agent 自行重新加载和执行一整份报告技能。

结果含 `status/findings/evidence/uncertainties/data_gaps`。每条 finding 的 `evidence_ids` 指向 evidence 中唯一 ID，每条 evidence 含真实来源与可定位的 `locator`。风险 finding 额外要求 `counter_evidence`、`alternative_explanations`；没有反证也应说明查验范围和限制。

通用静态图使用 `execute_python`，专用业务图使用 `create_business_chart`；在分析节点中完成并发布，资源/图表引用放入 `artifacts`。数据准备与核验节点仅交付其数据和证据。所有内部技术引用由父模式转成报告中的业务语言。

## 预算和降级

最多并发3、累计12节点、3次节点重试、2次补图、1200秒累计执行时间。节点另有轮次/超时上限，重试不能突破角色上限。资源和结构化修复受节点时间预算限制。预算是首版运行约束，尚未通过真实生产性能评测调整。

关键节点失败限制完整交付；辅助节点可 `required=false`，下游需显式 `dependency_policy=allow_partial` 才能消费部分结果。缺失不能写成零或没有风险。补图使用原 `workflow_id`、上次返回的 `revision` 和明确原因，不通过另建工作流规避预算。

## 验证范围

自动测试覆盖模式隔离、工具注册、委派边界、证据引用、反证结构、预算、真实调度器的并行分析和追加补证。调度测试以可控子执行器替代模型与业务接口，验证流程行为；不代表实际报告质量或生产加速收益。

上线前用月度监管和高值窗口风险两类真实任务与直接路径对照，观察耗时、模型调用与Token、重复取数、数字一致性、证据完整性和人工复核结果。

SQL 契约由 `projects/jiangsu-ops/data-ops/sync/datasets/*.yaml` 生成并随代码跟踪，从项目根执行：

```bash
PYTHONPATH=backend python projects/jiangsu-ops/data-ops/sync/gen_tool_contract.py --check
```
