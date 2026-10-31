---
name: Agent工作流编排细则
description: 使用 run_agent_workflow 编排 DAG 前的领域拆分、并行/合并判据、图表随节点产出、预算调优与结果消费细则。编排多节点取数/研判/分阶段报告任务前查看；单一取数或一次性委派不需要本技能。
aliases:
  - 工作流编排细则
  - DAG编排细则
  - 编排领域拆分
required_tools:
  - run_agent_workflow
---

# Agent 工作流编排细则

工具描述只保留硬约束；本技能承载编排方法论。首次编排 DAG 前通读一次即可。

## 领域拆分规则

- **监测历史取数按层级拆分**：站点小时/日数据与站点目录拆 `query_monitoring_station`；城市口径与全国对比拆 `query_monitoring_city`。层级混合拆成站点+城市两个节点；层级不明确先向用户确认口径，禁止用 `query_monitoring` 兜底（报告 DAG 已禁用该节点）。
- **气象与预报**：气象实况/预报与空气质量预报数据拆 `query_forecast`，与监测节点可并行。
- **组分数据**：广东省超级站组分数据（离子/碳组分/地壳元素/VOCs）取数拆 `query_component`。
- **专家研判三分**：气象条件、输送通道、静稳/边界层形势拆 `expert_meteorology`；浓度特征、超标统计、成因研判拆 `expert_analysis`；组分化学、SOC/OFP 与来源指向拆 `expert_component`。三者可并行，交叉归因（如气象导致组分累积）由父 Agent 在整合阶段完成，整合阶段禁止重新取数。
- **报告编排硬禁令**：报告 DAG 禁止综合问数（query / query_monitoring）与综合 expert 子节点；监测历史按层级拆 `query_monitoring_station`（站点）或 `query_monitoring_city`（城市）。
- **DAG 通用禁令**：query、expert、report 主模式不作子节点；当前父 Agent 是唯一整合与成稿者。

## 并行与合并判据

- **同域多节点并行是默认模式**：同一领域的多个独立子分析拆成多个同 mode 节点（如 3 个 expert_analysis 分别做相关性/超标统计/时空对比，task_id 不同即可）。并行节点总耗时 ≈ 最慢节点；合并则全部串行相加。
- **合并判据**：共享同一份输入文件不是合并理由（各分支可各自 load_data，重复读取是秒级成本）；只有必须共享同一份中间计算状态（同一样本集/同一对齐表）才能保持可比时才合并。样本一致性用任务书统一过滤口径解决；有依赖的子分析用 dependencies 表达（如归因节点依赖分段节点）。
- **同源数据只取一次**：同一数据源由一个节点获取，后续节点通过 dependencies 复用其 file_path；专家节点已有 query 系上游产出时禁止重复取数。

## 图表随节点并行产出

报告需要的分析图表（分箱图、相关性热力图、时序对比等）必须在对应子节点的 goal/task_contract 中明确要求，由子 Agent 在分析的同时一并生成。子节点交付的图表文件会在上游产物清单中回传，父 Agent 只做复用与排版，禁止在 DAG 完成后再由父 Agent 重新绘制分析图表——那是串行追加的整段时间。

## 预算调优

- 固定问数工作流由运行时控制为最多 20 轮（acquire 4 + normalize 15 + deliver 1），失败项最多补查一次；DAG 可为问数节点收紧 max_iterations，但运行时会把低于 8 的值抬到 8。任务书写清时间范围、区域与指标口径即可，不要在任务书里教写 SQL。
- 交付物粒度：每个节点承载 2~3 项强耦合必交物（最多 5 项）；一个专家节点只回答一个分析问题；计算结果、对应图表和证据摘要可算同一问题的交付物。专家节点 task_contract.deliverables 最多 3 项，超过必须拆成多个并行节点。
- 首试给紧凑预算，把余量留给重试：重试自动续用子会话、迭代与超时各放大 50%（迭代封顶 120、超时封顶 1 小时）。
- 聚合、分箱、相关性等含图表的计算密集专家节点请放宽首试预算：max_iterations≥25、timeout_seconds≥1200。

## 结果消费

- 工具返回每个节点的紧凑 result_envelope（status/summary/findings/evidence/data_gaps）与血缘清单；findings 是报告取数来源，其中的数值可直接引用。
- 各节点完整结果已落盘并在 full_results.path：assistant 助手通过 read_session_resource 读取已登记资源，或用 manage_assistant_runs 读取委派结果；其他有文件权限的模式用 read_file 一次整读，禁止分页反复读同一文件。
- 据此判断覆盖范围与缺口并整合结论，不对子节点过程做重复全量复核。

## 条件、辅助节点与资源契约（简要）

- 条件节点用 when 声明 source_task_id（必须是直接依赖）、path（上游结果点分路径）、op、value；支持 all/any/not 组合；条件为假跳过该分支，缺少比较证据会报告失败，不猜测真假。
- 辅助节点显式 required=false；下游只有 dependency_policy=allow_partial 才能消费部分上游，且至少一个成功上游。收到 partial 时参考 delivery.gaps，交付已有成果并说明缺口；不能把缺失数据当零、编造结论或默认重新取数。
- input_contracts 按 source_task_id 校验上游资源，output_contract 校验本节点产物；可约束 kind/format/fields/units/granularity/time_range/scope。字段尽可能从文件核对；缺失元数据不会自动假定满足要求。
