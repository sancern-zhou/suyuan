# 有界增量编排

普通同源、同粒度查询优先直接批量完成。DAG 用于有明确依赖、专业分工或上下文隔离收益的任务；子 Agent 保持精简，不再次委派。

父 Agent 查看一轮结果的 `data_gaps` 后，可以在同一父会话、同一模式下追加任务：

```json
{
  "workflow": {"workflow_id": "air-analysis"},
  "extension": {
    "expected_revision": 0,
    "reason": "现有证据缺少同期气象，影响成因判断",
    "nodes": [
      {"task_id": "weather", "target_mode": "query_forecast", "goal": "补充同期气象数据"},
      {
        "task_id": "analysis-with-weather",
        "target_mode": "expert_analysis",
        "goal": "结合原监测数据和新增气象完成成因研判",
        "dependencies": ["air", "weather"],
        "task_contract": {"question": "成因是否受气象影响", "deliverables": ["结论与证据"]}
      }
    ]
  }
}
```

这个示例假设 expert 父模式已完成原节点 `air`。query 父模式只允许问数子节点。初始返回 `revision=0`，每次成功追加后递增；失败的校验不更改图。再次补图使用最新 revision。重复 ID、未知依赖、环、模式越权和超预算均拒绝。图节点只能追加，已经完成的结果、血缘和子会话保持不变；补充分析创建新节点，不修改旧分析节点。

补图从当前父会话的持久化快照加载，不接受外部传入快照。当前实现支持两轮之间补图，不支持正在运行的图热修改。注册运行所有权后再检查快照版本；检查点写入完成后才释放运行所有权。持久化故障仍采用现有 fail-soft 策略，无法获得可信快照时不承诺可补图。

首次创建可设置 `workflow.budget`，后续补图不能更改它：

| 字段 | 默认值 | 统计口径 |
| --- | ---: | --- |
| timeout_seconds | 3600 | 所有运行轮次累计活动时长，含并发等待与退避，不含离线停机 |
| max_nodes | 32 | 原节点加全部追加节点 |
| max_retries | 16 | 调度器实际执行同一节点的额外次数，跨恢复累计 |
| max_extensions | 3 | 成功追加批次 |

默认值是可配置的运行保护上限，并非实测的效率路由阈值。节点内部的工具重试、结果契约修复属于一次子 Agent 执行，受节点迭代和时长约束，不计作调度器重试；当前没有全工作流 Token 硬上限。

总时长耗尽会取消并等待活动子任务退出，保留已完成结果，返回 `failed`、`node_errors.__budget__` 和 `budget_state.exhausted`。总重试次数耗尽会拒绝额外执行，现有并行任务可以完成；结束后同样保留成果且不可恢复或补图。节点数或追加次数超限只拒绝该次定义/追加，不破坏原成果。累计计数和时间通过快照恢复，API 对已耗尽工作流返回 409。

历史定义未显式提供 budget 时，其序列化及指纹保持兼容。工具同时接受简写节点和持久化的 payload 嵌套格式，避免后台 worker 恢复时误判缺少 target_mode/goal。

本轮只完成确定性的功能与回归检查。后续统一验证应覆盖真实父 Agent 自主选择路径、缺口驱动补图、文件资源复用以及时间/Token/准确性比较；受控工具测试不能代替生产 ReAct 链路效果验证。

## 条件分支

参考固定检出的 LangGraph v1.2.13（`2d942085e214ef6b99b6f54ed4d544a7c7c5ac56`）中 [StateGraph.add_conditional_edges](https://github.com/langchain-ai/langgraph/blob/2d942085e214ef6b99b6f54ed4d544a7c7c5ac56/libs/langgraph/langgraph/graph/state.py) 和 [BranchSpec._finish](https://github.com/langchain-ai/langgraph/blob/2d942085e214ef6b99b6f54ed4d544a7c7c5ac56/libs/langgraph/langgraph/graph/_branch.py)：在上游完成后读取结果，再决定分支。这里使用可序列化的 `when` 条件，适配已有父会话、Redis worker 和检查点体系；未新增 LangGraph 运行依赖。

```json
{
  "task_id": "cause-analysis",
  "dependencies": ["air", "weather"],
  "when": {
    "source_task_id": "air",
    "path": "data.result_envelope.outputs.exceedance_count",
    "op": "gt",
    "value": 0
  },
  "dependency_policy": "allow_partial"
}
```

这是路由字段片段，完整节点仍需 target_mode、goal 等字段。上游 result_schema 应要求用于路由的字段。路径相对于完整节点结果，支持字典字段与列表下标。来源必须是直接依赖。比较支持 eq/ne/gt/ge/lt/le/contains/nonempty/exists，也可用 all/any/not 组合。条件为假时标记 `skipped`，严格依赖其结果的后续节点也跳过；缺少比较证据或数值类型不匹配时失败，不能把未知证据当作条件为假。`exists` 是显式判断字段是否存在的例外。

默认 dependency_policy=all_success；分支汇合或辅助证据缺失时，显式设置 allow_partial，等待所有上游结束后仅传入成功结果，且必须有至少一个成功上游。未选择的分支属于正常跳过，不计失败。路由决定与跳过状态写入快照；恢复和补图保持已有成果。

## 部分失败与交付

`required` 默认为 true。辅助任务显式设 false；它失败后，严格依赖仍被阻断，只有 allow_partial 下游可以继续。下游未标记为可选而又无法执行时，仍会使工作流失败，不能通过一个辅助节点的设置绕过关键证据要求。

返回值区分：

| 工作流状态 | 工具 success | delivery.deliverable | delivery.complete |
| --- | --- | --- | --- |
| succeeded | true | true | true |
| partial | true | true | false |
| failed / cancelled | false | false | false |

partial 表示已有可交付成果，避免被通用工具错误处理误判为整次调用失败；不代表任务全部完成。`delivery` 给出可用节点、失败/阻断/可选资源缺口、跳过节点、剩余可重试节点与建议行动。下游收到缺口上下文，必须说明结论限制，不得把缺失数值当作零。没有任何成功成果、关键节点失败或总预算耗尽时仍返回 failed。

前端显示“部分完成”和证据缺口；恢复按钮受剩余尝试及累计预算限制。后台 worker、Redis 终态和 SSE 同样支持 partial。父 Agent 可以交付带限制的结论，也可以在同一父会话追加补充任务。当前只支持这些父 Agent 决策与交互，不包含运行中等待用户选择的 interrupt/resume 输入协议。

## 输入与输出资源契约

input_contracts 按直接依赖来源约束资源；output_contract 约束节点交付。每份契约必须由同一个资源满足，不能把不同文件的字段拼成虚构的完整数据集。例如：

```json
{
  "input_contracts": [{
    "source_task_id": "air",
    "kind": "data",
    "format": "csv",
    "fields": ["time", "pm25"],
    "units": {"pm25": "ug/m3"},
    "granularity": "hour",
    "time_range": {"start": "2026-10-01", "end": "2026-10-02"},
    "scope": {"city": "xuchang"}
  }]
}
```

文件存在性、格式和字段尽可能从实际文件确认：CSV 头最多读 64KiB；JSON 最多解析 2MiB，支持记录列表和 records/rows/data 包装。其他格式及大型 JSON 的字段依赖目录元数据，兼容现有查询和 Python 产物的 `metadata.data_shape.columns`。单位、粒度、时间覆盖和范围来自资源 `metadata.data_contract`，不根据预期契约生成元数据或自动换算。没有可信元数据时，显式要求的约束不能视为满足。

调度前先校验句柄与文件；下游资源导入后再根据真实目录校验，失效资源不能以请求句柄冒充导入成功。元数据和上游来源信息在导入及父节点资源发布时保留。必需契约失败不会启动下游模型或自动同条件重试，违反项写入 node_contract_errors；契约 required=false 时允许继续但必须报告缺口，最终为 partial。

缓存签名包含路由及资源契约。无效资源会使缓存及依赖它的缓存失效；涉及会话目录契约的节点不能单凭缓存描述符证明目录仍有效，需要重新执行核验/导入。已经完成的检查点成果仍按增量编排规则保留。旧定义未使用这些新字段时，原定义指纹保持兼容。
