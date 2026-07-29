# 退役 qwen3 文本模型设计

## 目标

从项目有效配置和运行路径中移除精确的 `qwen3` 文本模型，确保招投标、通用 LLM 和知识库文档处理不再选择或调用该模型。

## 保留范围

视觉和 OCR 链路不属于本次退役范围，继续保留以下配置及调用：

- `QWEN_VL_API_KEY`
- `QWEN_VL_BASE_URL`
- `QWEN_VL_MODEL`
- `QWEN_VISION_MODEL`
- `qwen-vl-ocr`
- `qwen3.7-plus`

## 变更范围

1. 删除本地环境文件中的文本 Qwen 配置：`QWEN_API_KEY`、`QWEN_BASE_URL`、`QWEN_MODEL`。
2. 从全局设置和通用 LLM 服务中移除文本 `qwen` provider 的专属配置与分支，避免通过默认值重新选择 Qwen3 系列文本模型。
3. 招投标 LLM 客户端不再读取 `QWEN_API_KEY`、`QWEN_MODEL`，也不再把文本 Qwen 配置作为密钥、模型或基础地址的回退来源；现有 Tender、Agnes、OpenAI、GLM 和 DashScope 非 `qwen3` 配置保持可用。
4. 移除知识库文档处理中的本地 `qwen3` 分块调用。知识库 LLM 分块统一使用线上模式；API 不再接受 `local` 模式。
5. OCR 密钥解析不再回退到已删除的文本 `qwen_api_key`，只使用视觉/OCR 专属配置及现有 OCR 回退配置。
6. 删除精确 `qwen3` 文本模型的令牌计数映射和遗留元数据名称。

## 运行行为

- 当前主 LLM provider 为 DeepSeek，不受文本 Qwen provider 退役影响。
- 招投标主、备 LLM 继续按各自专用配置运行；如果必要配置缺失，应明确报配置错误，不得静默回退到 `qwen3`。
- 知识库上传接口收到 `llm_mode=local` 时返回参数错误，避免含糊地改用其他模型。
- Qwen 视觉识别和 OCR 继续使用专属 `QWEN_VL_*`、`QWEN_VISION_MODEL` 配置。

## 错误处理

- 已退役的文本 `qwen` provider 不再被列为受支持 provider。
- 遗留部署若仍设置 `LLM_PROVIDER=qwen`，启动或配置加载时应给出不支持的 provider 错误，而不是选择默认模型。
- 招投标不得因环境中残留 `QWEN_*` 变量而选中 `qwen3`。

## 验证策略

采用测试先行：

1. 增加招投标配置测试，证明设置残留文本 `QWEN_*` 时客户端也不会选择它们。
2. 增加知识库模式测试，证明 `local` 不再是有效 LLM 分块模式。
3. 增加设置/LLM provider 测试，证明文本 `qwen` provider 已退役。
4. 运行相关测试集。
5. 扫描生产代码、有效配置与环境模板，确认不存在精确 `qwen3` 文本模型；扫描时明确排除日志、历史数据和本设计文档。
6. 单独验证视觉/OCR 模型配置仍可解析为原有值。

## 非目标

- 不移除 Qwen 视觉或 OCR 能力。
- 不迁移历史日志、数据库错误记录或既有审计证据。
- 不修改与本次模型退役无关的 LLM provider 行为。
- 不处理工作区中已有的其他未提交修改。
