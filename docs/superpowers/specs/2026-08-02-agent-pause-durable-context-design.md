# Agent 暂停后的持久化上下文设计

## 背景

当前“暂停”主要由前端中止 SSE、后端撤销 run ownership 并取消 asyncio task 实现。前端可以冻结已显示内容，但后端通常在暂停轨迹落盘前就失去写权限。因此，刷新会话或开始下一轮对话时，Agent 可能看不到暂停前已经展示的分析过程、工具调用、工具结果和部分回答。

暂停必须成为上一轮对话的正式终态。用户暂停后的输入是普通的新一轮对话，不是 steering，也不恢复旧 run；新 run 必须从同一会话中读取上一轮完整的用户可见执行轨迹和“用户主动暂停”的事实。

本设计采用现有会话 transcript 增强方案，不新增事件表，也不兼容旧会话格式。

## 目标

- 点击暂停后，界面立即停止分析状态并允许用户输入、发送下一轮消息。
- 后端立即停止旧 run 的 LLM 流、异步工具执行和后续写入。
- 暂停前的用户可见分析、工具调用、工具结果、资源引用和部分回答持久化到会话 transcript。
- transcript 最后持久化唯一的 `user_pause` 事件。
- 下一轮是新的普通 run，但 LLM 上下文包含上一轮完整轨迹和暂停事实。
- 已完成工具不重复执行；未闭合工具有明确的 `interrupted` 或 `unknown` 结果。
- 暂停、新分析和迟到网络请求发生竞争时，不误杀新 run，也不读取残缺历史。

## 非目标

- 不恢复旧 run 的 Python 调用栈、LLM 请求或工具协程。
- 不把暂停后的输入解释为 steering 或追加指令。
- 不保存模型私有原始 reasoning/thinking；只保存已经通过 SSE 展示给用户的分析摘要。
- 不保证同步线程或外部系统中已经发生的副作用可以回滚。
- 不处理旧 transcript 的迁移或兼容。
- 不提供进程崩溃前尚未落盘事件的完整恢复；该能力需要未来引入 append-only 运行事件表。

## 核心语义

暂停只终止继续执行，不能删除执行记忆。会话顺序必须表现为：

```text
旧 run 最后一个已接收事件
  → 暂停快照
  → user_pause
  → 新一轮 user 消息
  → 新 run
```

新 run 不继承旧 run 的执行控制状态，只继承规范化的会话上下文。

## 组件设计

### 1. 服务端 RunHandle 快照

每个运行中的 `RunHandle` 维护一个仅由服务端更新的有序快照缓冲，至少包含：

- `session_id`
- `run_id`
- 单调递增的 `event_sequence`
- 本轮用户输入
- 用户可见 `thought`/计划摘要
- `tool_use` 的工具名、参数和调用 ID
- `tool_result` 的结果、错误状态和资源引用
- 累积的 `streaming_text`
- 当前迭代、任务状态和最后事件时间
- 暂停状态、暂停完成屏障和暂停错误

前端数据不能作为执行事实来源。前端只负责发出暂停意图并展示服务端已经流出的内容。

### 2. 暂停状态机

运行状态转换为：

```text
running → pause_requested → finalizing → paused
```

进入 `pause_requested` 后：

- 立即设置 `cancel_event`。
- 立即丢弃流式工具执行器并取消旧 run 的 asyncio task。
- 普通 ownership 写入立即关闭，禁止旧 run 继续发布资源或提交工具结果。
- 暂停收尾器保留一次仅限 transcript 的提交权限。
- transcript 提交成功后彻底撤销 ownership，并释放暂停完成屏障。

暂停请求只作用于明确的 `session_id + run_id`。目标 run 已结束或已被替换时返回幂等结果，不能取消当前新 run。

### 3. 暂停 transcript

暂停收尾使用服务端快照生成上一轮 transcript。暂停轮次与正常完成轮次使用不同的持久化入口；暂停入口保留用户可见 `thought`，正常完成行为不在本需求中改变。

部分回答保存为非流式 assistant 消息：

```json
{
  "type": "final",
  "content": "暂停前已经生成的部分回答",
  "data": {
    "partial": true,
    "frozen_from": "paused",
    "run_id": "run_xxx"
  }
}
```

最后追加用户暂停事件：

```json
{
  "type": "user_pause",
  "role": "user",
  "content": "用户主动暂停了上一轮分析",
  "data": {
    "run_id": "run_xxx",
    "reason": "user_paused",
    "paused_at": "2026-08-02T12:00:00+08:00",
    "last_event_sequence": 17
  }
}
```

以 `run_id + type=user_pause` 作为幂等键，同一 run 只能生成一个暂停事件。

### 4. 工具轨迹规范化

- 已完成工具保存配对的原生 `tool_use` 和 `tool_result`。
- 已确定被取消的工具补充 `status=interrupted` 的合成结果。
- 无法确认是否完成或可能已有外部副作用的工具补充 `status=unknown` 的合成结果。
- 下一轮对 `unknown` 工具只能先查询或对账，不能直接重试。
- 大型工具结果继续使用现有瘦身逻辑和统一资源引用，避免把完整二进制或超大 JSON 塞入模型上下文。
- 已完成工具的调用 ID、结果和资源引用必须保留，使下一轮不会因为缺少上下文而重复执行。

### 5. LLM 上下文投影

恢复暂停会话时，将 transcript 按原顺序投影为：

```text
原用户消息
用户可见分析/计划
完整且配对的工具调用与结果
暂停前部分回答
用户暂停事件
新用户消息
```

`user_pause` 是历史事实，不转换为 steering、续跑命令或新的任务指令。新 run 像普通对话一样重新规划。

显示 transcript 与 LLM 投影职责分离：显示层保留完整用户可见事件；LLM 投影层输出符合模型协议的消息，对未闭合工具调用补齐结果，并避免把 UI 伪协议文本当成新的工具调用。

## API 与前端交互

### 暂停请求

暂停请求必须携带当前 `run_id`。后端返回是否接收、目标 run 状态和暂停屏障标识。接口快速确认请求已接收，不等待数据库提交完成才允许前端更新 UI。

前端点击暂停后立即：

1. 捕获 `session_id + run_id`。
2. 冻结当前可见输出。
3. 把旧 run 加入忽略列表。
4. 设置 `isAnalyzing=false` 并解除画板只读。
5. 保存 `pendingPausedRunId`。
6. 发出暂停请求。
7. 后端确认已接收后关闭旧 SSE；请求失败时也关闭 SSE，但保留 `pendingPausedRunId`。

下一轮分析请求携带 `previous_paused_run_id`。后端必须先等待或完成该 run 的暂停屏障，再加载会话并注册新 run。屏障完成后，前端清除 `pendingPausedRunId`。

## 并发与顺序保证

- 暂停请求使用期望 `run_id`，迟到请求不能误杀新 run。
- 同一个 run 的暂停收尾是幂等操作。
- 新 run 注册必须位于旧 run 暂停 transcript 提交之后。
- 旧 run 进入 `pause_requested` 后不能再提交普通资源写入。
- 暂停收尾使用专用提交权限，避免“先 revoke、后保存”导致 transcript 丢失。
- SSE 断开和显式暂停并发触发时，共享同一个暂停收尾任务；显式 `user_pause` 原因优先于普通 `client_disconnected`。
- 前端继续通过 ignored run IDs 拒绝旧 run 的迟到事件。

## 失败处理

- 暂停接口失败：前端仍立即停止展示和旧 SSE，但下一轮通过 `previous_paused_run_id` 再次要求完成暂停收尾。
- transcript 暂时写入失败：保留内存快照并有限重试，不允许新 run 静默读取残缺历史。
- 重试后仍失败：新轮请求返回 `pause_checkpoint_failed`；前端保留用户草稿并重试或明确提示。
- 工具不响应取消：主 run 不再等待，工具状态记为 `unknown`，其迟到写入被 ownership 拒绝。
- 目标 run 不存在：暂停接口返回幂等的“已结束”；如果对应 `user_pause` 尚未写入且服务端仍有快照，则完成补写。

## 测试策略

### 后端单元测试

- RunHandle 按事件顺序累计可见轨迹和部分回答。
- 暂停保存可见 thought、工具调用、工具结果、部分回答和唯一 `user_pause`。
- 已完成工具保持配对；未闭合工具获得 `interrupted` 或 `unknown` 结果。
- 暂停提交权限在普通 ownership 关闭后仍能且只能提交一次 transcript。
- 重复暂停幂等。
- 不匹配或迟到的 run ID 不会取消新 run。
- 暂停屏障完成前不能注册同 session 的新 run。
- LLM 投影包含暂停前轨迹和暂停事实，不包含私有 reasoning。

### 后端集成测试

- 运行中暂停后，数据库 transcript 顺序正确。
- 暂停后立即发新消息，新 run 读取到完整暂停快照。
- SSE 断开与显式暂停竞争时只写一个 `user_pause`。
- 暂停落盘失败时新 run 不使用残缺历史。
- 恢复会话后工具结果和资源引用仍可用，已完成工具不被重新执行。

### 前端测试

- 点击暂停后无需等待网络响应即可输入和发送。
- 暂停请求携带捕获的旧 `run_id`。
- 旧 run 迟到事件不能修改冻结内容。
- 暂停未确认时，新分析请求携带 `previous_paused_run_id`。
- 暂停失败不会清空用户下一轮草稿。
- 刷新和恢复会话后显示完整暂停轨迹及暂停标记。

### 验证与部署

- 后端测试在 `conda activate /root/miniconda3/envs/backend_py311` 环境运行。
- 前端测试通过后，在 `/home/xckj/suyuan/frontend` 执行 `npm run build:standalone`。
- 构建产物必须包含统一资源接口，且不包含 `/office-documents` 或 `/visualizations` 旧接口。
- 如部署正式静态资源，重新加载 `suyuan-nginx` 并验证页面暂停/恢复流程。

## 验收标准

暂停后刷新页面、重新打开会话或开始新的普通对话轮次，Agent 仍能准确引用暂停前的用户可见分析步骤、工具调用、工具结果、资源成果和部分回答；它明确知道上一轮由用户主动暂停，不会把新输入当作 steering，也不会重复已经完成的副作用操作。点击暂停后，用户无需等待后端落盘即可输入和发送下一轮消息。
