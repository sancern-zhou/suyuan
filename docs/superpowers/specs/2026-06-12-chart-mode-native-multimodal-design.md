# Chart Mode Native Multimodal Design

## Goal

图表模式中的所有图片附件使用与社交模式一致的原生多模态模型输入方式，并固定使用支持多模态的模型调用路径。

## Scope

- 用户上传到图表模式的参考图片走原生 image content block。
- 前端图表模式自动附带的 Draw.io 画板 PNG 快照走原生 image content block。
- 工具返回的 `multimodal_attachment` 图片在图表模式下一轮继续走原生 image content block。
- 非图片附件仍只作为文本附件信息进入上下文。
- 非 `social` / `chart` 模式不改变现有行为。

## Architecture

复用现有社交模式多模态管线。新增一个小的模式判断 helper，例如 `supports_native_multimodal(mode)`，将 `social` 和 `chart` 作为支持原生多模态的模式集合。`ReActAgent` 只在支持模式下把附件传给 `ReActLoop`，`AgentRuntime` 在首轮持久化内容、流式 planner、非流式 fallback 中使用同一 helper 构造 Anthropic image content blocks。

模型选择保持与现有 Anthropic-compatible planner 调用一致，但图表模式必须固定到多模态模型配置，不能再因默认图表模式或 model tier 选择到纯文本模型。实现时优先沿用现有 `llm_provider` / `llm_model` / `auto_profile` 机制，给图表模式选择与社交模式一致的多模态 profile 或模型。

## Prompt Changes

图表模式提示词不再把“调用 `read_file(path, analysis_type=\"chart\")` 或 `analyze_image`”作为用户参考图片的默认第一步。提示词应明确：本轮上传图片和画板快照已经作为原生多模态输入提供，模型应直接基于可见图片理解图表样式、配色和布局。只有当需要读取历史文件路径或工具生成的本地图片时，才使用 `read_file(as_multimodal_attachment=true)` 将图片挂载到下一轮。

Draw.io 的 XML 仍是编辑权威状态；PNG 快照只用于视觉参考和质量检查。

## Testing

- 单元测试图表模式带图片附件时，`ReActLoop` 接收到 `attachments`，并且会选择多模态模型 profile。
- 单元测试图表模式 planner 的 `user_content` 是包含 `text` 和 `image` block 的 Anthropic content blocks。
- 单元测试非多模态模式带图片附件时仍不会构造 image block。
- 单元测试图表 prompt 不再要求参考图片默认调用 `read_file(path, analysis_type=\"chart\")` 或 `analyze_image`。

## Risks

- 如果多模态模型不支持某些工具调用参数，图表模式可能暴露模型兼容性问题；应使用与社交模式已验证一致的模型调用机制。
- 本地图片 base64 会增加当前轮上下文体积；沿用现有图片大小限制和 fallback 行为。
