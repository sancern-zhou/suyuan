# Draw.io 连线自动避让部分成功与降级渲染设计

## 背景

当前 `create_drawio_board` 在候选持久化前对全部连线执行自动避让。路由器遇到第一条无法安全避让的连线时会抛出 `DrawioRoutingError`，导致整张候选画板创建失败。Agent 随后根据错误重新生成完整 XML，但 Agent 的修复是概率性的；即使 XML 有细微变化，只要问题几何关系未改变，同一失败仍会连续发生。

最近一次实际故障中，路由器把模块背景和标题误判为障碍物，第一条连线 `edge_start_query` 被判定为端点受困。后续连线没有获得处理机会，三次 Agent 重试均未生成候选画板。这种硬门禁显著降低画板生成成功率，并增加等待时间和 Token 消耗。

本设计将自动避让从“候选创建硬门禁”调整为“非阻断的尽力优化”：能够安全避让的连线继续获得优化，无法避让的连线保留原始路径，任何路由失败都不得单独阻止候选生成和前端预览。

## 目标

- 自动避让按连线独立执行，单条失败不影响其他连线。
- 能够避让的连线写入安全端口和显式折点。
- 无法避让的连线保持 Agent 提交的原始样式、端点和几何路径。
- 路由器局部或整体失败时，画板仍能持久化、预览、截图和接受。
- 返回完整、结构化的路由诊断，供审计和人工修订使用。
- Agent 不因非阻断路由警告自动重新生成整张画板。
- XML 和画板结构错误继续作为硬失败处理。

## 非目标

- 不保证每条连线都不穿过节点。
- 不由路由器自动移动业务节点。
- 不删除自动避让功能。
- 不在本次调整中设计新的前端连线编辑器。
- 不让路由警告替代截图后的整体视觉复核。

## 方案选择

### 方案一：完全删除自动避让

优点是实现和行为最简单，路由器不会再影响生成成功率。缺点是失去已能正常工作的自动优化能力，所有连线质量完全依赖 Agent 和 diagrams.net 默认渲染。

### 方案二：允许 Agent 修复一次后降级

首次路由失败返回完整信息，Agent 获得一次重新生成机会；第二次失败再保留原始 XML。该方案仍引入额外模型调用、等待时间和 Token 消耗，而且不能保证 Agent 的修改触及真正根因。

### 方案三：逐条尽力避让并立即降级

路由器逐条处理连线。单条成功就保留优化结果，单条失败就恢复该条原始连线，并继续处理后续连线。工具最终仍返回成功候选，同时附带完整警告。

采用方案三。它同时保留自动避让收益和候选生成成功率，并消除对 Agent 概率性重试的依赖。

## 总体流程

```text
Agent 候选 XML
  -> XML 规范化与结构校验
  -> 逐条自动避让
       -> 成功：写入安全端口和折点
       -> 已安全：保留现有路径
       -> 失败：恢复该条原始路径，记录 routing_issue
  -> 路由后置验证
       -> 只回滚验证失败的已路由连线
  -> 静态画板质量检查
  -> 持久化候选
  -> 前端预览
  -> 截图与视觉复核
  -> 接受候选或按用户需求局部修订
```

路由器整体出现异常时，工具回退到进入路由器前的规范化 XML，然后继续执行静态质量检查和候选持久化。

## 逐条连线隔离

路由开始前保存每条连线的原始 XML 元素副本。每条连线独立经历以下过程：

1. 解析端点、现有折点和样式。
2. 判断现有路径是否已经安全。
3. 必要时搜索正交通道并生成显式端口、折点。
4. 对生成路径立即执行节点碰撞验证。
5. 成功时提交该条路由结果。
6. 失败时恢复该条原始元素，记录结构化问题，并继续下一条连线。

单条失败包括但不限于：

- 端点受困；
- 找不到安全正交通道；
- 不支持的连线样式发生碰撞；
- 路由后仍与节点相交；
- 该条连线处理期间发生非预期异常。

失败连线不会加入“已安全连线”集合，也不会阻断后续连线的节点安全搜索。连线之间的交叉仍只是次级优化指标，不得高于候选生成成功率。

## 路由后置验证与回滚

全部连线处理完成后，路由器重新序列化并解析候选 XML，验证系统声称已经安全处理的连线。

如果后置验证发现已路由连线仍穿过节点：

1. 仅恢复对应连线的原始 XML 元素；
2. 将该连线计为降级连线；
3. 生成 `post_route_intersection` 问题；
4. 重新生成最终 XML 和指标；
5. 不抛出导致整图失败的异常。

保留原始路径的降级连线允许存在节点穿越。其剩余相交数量作为警告指标，不参与候选持久化门禁。

## 路由状态与指标

候选返回以下路由状态之一：

- `applied`：所有可处理连线均安全完成，未发生降级。
- `partial`：部分连线安全完成，部分连线保留原始路径。
- `fallback`：路由器整体异常，完整使用进入路由器前的规范化 XML。
- `not_needed`：候选没有需要自动处理的连线。

路由指标至少包括：

```json
{
  "edge_count": 21,
  "safe_edge_count": 18,
  "rerouted_edge_count": 7,
  "unchanged_safe_edge_count": 11,
  "degraded_edge_count": 3,
  "remaining_intersection_count": 3,
  "edge_edge_crossing_count": 1,
  "max_route_offset": 80
}
```

计数关系应保持可解释：`safe_edge_count + degraded_edge_count == edge_count`。`safe_edge_count` 包含重新路由成功和原本已安全的连线。

## 工具结果协议

路由部分失败时，`create_drawio_board` 仍返回成功：

```json
{
  "status": "success",
  "success": true,
  "data": {
    "candidate_version_id": "candidate-version-id",
    "routing_status": "partial",
    "routing_metrics": {
      "edge_count": 21,
      "safe_edge_count": 18,
      "rerouted_edge_count": 7,
      "unchanged_safe_edge_count": 11,
      "degraded_edge_count": 3,
      "remaining_intersection_count": 3
    },
    "routing_issues": [
      {
        "code": "unroutable_edge",
        "edge_id": "edge_start_query",
        "source_id": "start",
        "target_id": "query_data",
        "cause": "source_terminal_trapped",
        "blocking_node_ids": ["alert_module_bg", "alert_module_title"],
        "preserved_original_edge": true,
        "failure_fingerprint": "edge_start_query:source_terminal_trapped:alert_module_bg,alert_module_title",
        "repair_actions": [
          {
            "action": "relayout_terminal",
            "cell_id": "start",
            "avoid_cell_ids": ["alert_module_bg", "alert_module_title"]
          }
        ]
      }
    ]
  },
  "summary": "画板已生成；18 条连线安全，3 条保留原始路径。"
}
```

为兼容现有消费者，可以暂时保留单数 `routing_issue`，其值等于 `routing_issues[0]`。新代码以 `routing_issues` 为权威字段。

候选质量报告保留路由状态、指标和问题列表，使截图和接受阶段仍可查看创建阶段的诊断信息。路由问题是警告，不得把候选的 `quality_status` 直接改为失败。

## 错误边界

以下错误继续返回 `success=false`：

- XML 无法解析；
- 单元 ID 重复；
- 连线端点不存在；
- 节点几何数据无效；
- 静态质量检查发现结构性错误；
- 候选持久化失败。

以下问题返回 `success=true` 并附带路由警告：

- 单条或多条连线无法避让；
- 端点被节点或背景包围；
- 不支持的连线样式发生碰撞；
- 路由后仍有局部节点穿越；
- 单条连线处理异常；
- 路由器整体异常。

路由器整体异常时使用 `routing_status=fallback`，`routing_issues` 至少包含一个 `router_internal_error`，并明确说明使用了原始规范化 XML。

## Agent 行为

画板工作流提示应明确：

- `routing_status=partial` 或 `fallback` 是成功候选，不是重新生成指令；
- Agent 应继续截图、视觉检查和接受流程；
- 禁止仅因为存在 `routing_issues` 再次调用 `create_drawio_board`；
- 只有用户明确要求整理连线，或截图显示连线严重影响可读性时，才基于当前候选做局部编辑；
- 局部编辑不得无原因重建整张图。

通用工具循环保护不再承担路由失败去重职责，因为路由警告不会触发自动重试。

## 前端行为

- 工具卡片显示创建成功，而不是“工具执行失败”。
- 候选画板立即进入预览。
- `partial` 或 `fallback` 可以显示非阻断警告摘要，但不得覆盖或隐藏画板。
- 截图、版本历史和接受候选流程与完整成功候选一致。
- 前端无需理解每一种 `routing_issue` 才能渲染候选。

## 可观测性

每个候选记录一条汇总日志，避免按连线刷屏：

```text
drawio_routing_completed
status=partial
edge_count=21
rerouted=7
unchanged_safe=11
degraded=3
remaining_intersections=3
```

日志附带 `session_id`、`agent_run_id`、候选标识和失败指纹列表，但不重复记录完整 XML。单条问题保存在工具结果和候选质量报告中。

建议监控：

- `routing_status` 分布；
- 部分降级候选比例；
- 整体回退比例；
- 每个候选的降级连线数量；
- 高频 `failure_fingerprint`；
- 路由耗时。

## 测试策略

### 路由单元测试

- 第一条连线失败后，后续连线仍继续避让。
- 多条连线中只有失败连线保持原始 XML。
- 成功连线写入安全端口和显式折点。
- 已经安全的连线保持安全并计入正确指标。
- 后置验证失败只回滚对应连线。
- 降级连线的剩余节点穿越只产生警告。
- 路由器整体异常返回完整原始规范化 XML。
- 使用最近事故中的完整 XML 建立回归用例，候选结果应为 `partial` 或 `applied`，不得抛出整图失败。

### 工具集成测试

- 部分路由失败时仍调用候选持久化服务。
- `success=true`、`routing_status=partial` 和完整 `routing_issues` 同时返回。
- 整体路由异常时仍持久化原始规范化 XML。
- 路由指标进入候选质量报告。
- XML 解析、重复 ID、无效端点和持久化错误仍为硬失败。

### Agent 与前端测试

- `partial` 和 `fallback` 不触发 Agent 自动重试。
- Agent 继续调用截图与候选接受工具。
- 前端在带路由警告时仍预览候选。
- 工具卡片显示成功和非阻断警告，而非执行失败。
- 版本历史、恢复和接受流程不受路由状态影响。

## 验收标准

- 任意单条连线自动避让失败都不会阻止其他连线处理。
- 任意路由失败都不会单独阻止候选持久化和前端预览。
- 可以安全避让的连线仍获得自动优化。
- 无法避让的连线保持原始路径，不被删除或错误改写。
- 候选成功结果包含完整路由状态、指标和问题列表。
- Agent 不因非阻断路由问题重复生成整张画板。
- 结构性 XML 错误仍被可靠阻断。
- 最近事故 XML 的回归测试通过，并且只产生部分降级或完整成功结果。
