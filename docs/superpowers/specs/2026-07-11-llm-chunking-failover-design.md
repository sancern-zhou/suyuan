# 在线智能分块统一 LLM Failover 设计

## 背景

`DocumentProcessor._call_online_llm()` 当前直接使用 `httpx` 调用由 `LLM_PROVIDER` 选出的单一接口，只在同一接口上重试两次。它没有使用系统统一的 `LLMService`，因此 `LLM_FALLBACKS`、provider 冷却、统一并发限制和请求超时配置均不生效。当前配置为 `glm` 时，分块器还会落入默认 OpenAI 分支，造成日志 provider 与实际接口不一致。

## 目标

- 在线智能分块复用统一 `LLMService` 和 `LLM_FALLBACKS` 候选链。
- 主模型发生连接失败、超时、限流、可恢复服务端错误等情况时自动尝试下一候选模型。
- 全部候选失败后，保持现有行为，降级为句子分块。
- 本地 `QWEN` 分块模式和图谱抽取流程不变。
- 分块调用遵守统一 provider/model 并发、冷却和请求超时策略。

## 方案

### 调用边界

`DocumentProcessor._call_llm_api(prompt, "online")` 继续作为智能分块内部入口，但 `_call_online_llm()` 不再自行解析 provider 配置和发送 HTTP 请求。它创建或获取 `LLMService`，通过统一文本生成接口提交以下消息：

- system：要求文档分析助手直接返回 JSON，不输出解释。
- user：现有分块提示词。
- temperature：保持 `0.1`。

统一服务以 `LLM_PROVIDER` 为主候选，以 `LLM_FALLBACKS` 的声明顺序追加候选。候选切换、错误分类、冷却和恢复 provider 状态均由 `LLMService` 负责。

### 返回值兼容

智能分块现有上层解析器需要原始文本。新调用层应返回模型响应文本，不改变分块 JSON 的解析、修复、合并小块和拆分大块逻辑。

如果统一服务仅提供适合该场景的 JSON 返回接口，则由适配层将结构化结果序列化为 JSON 文本，保证 `_call_online_llm()` 的返回契约仍为 `str`。优先使用保留原始文本语义的非流式文本接口，避免重复 JSON 解析。

### 故障与降级

候选切换规则沿用 `llm_failover.should_fallback()`：

- 自动切换：连接异常、未知网络错误、超时、429、可恢复 5xx、计费或格式类候选故障。
- 不跨模型掩盖：上下文超限等需要上层处理的错误。
- 所有候选失败：异常返回到现有 `chunk_with_llm()`，记录 `llm_chunk_failed`，随后执行 `falling_back_to_sentence_chunking`。

不在 `DocumentProcessor` 内再次实现候选级重试，避免“每个模型长时间重试后才切换”。单候选内部是否重试由统一服务管理。

### 可观测性

保留现有 `llm_chunking_started`、`llm_chunk_failed` 和句子分块降级日志。模型切换使用统一日志：

- `llm_fallback_candidate_failed`
- `llm_fallback_candidate_succeeded`
- provider 冷却相关日志

日志中的 provider/model 必须对应实际请求目标。

## 测试与验收

1. 在线分块调用统一 `LLMService`，不再直接创建 `httpx.AsyncClient`。
2. 主候选 GLM 抛出连接异常时，按配置调用下一候选并返回其结果。
3. 下一候选成功时不触发句子分块降级。
4. 所有候选失败时仍触发现有句子分块降级。
5. `local` 模式继续调用 `_call_local_llm()`。
6. 现有文档处理、知识库和 LLM failover 测试保持通过。

## 非目标

- 不修改知识图谱抽取模型优先级。
- 不改变知识库的分块策略配置结构。
- 不引入新的 provider 配置项。
- 不调整文档上传 API 或前端界面。
