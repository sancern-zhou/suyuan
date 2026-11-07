---
name: PPT 设计与生成技能
description: 用 execute_python 编写 python-pptx 代码自由创作高质量可交付 PPTX：版式系统、字号阶梯、环保主题配色与图表规范，配合 validate_pptx 渲染验收闭环（生成→检查→修复）。
aliases: [PPT设计, PPT制作, 幻灯片生成, python-pptx, 自由PPT]
required_tools: [read_file, execute_python, validate_pptx]
enabled: true
---

# PPT 设计与生成技能（pptx-authoring）

## 概述

当结构化 PPT 工具的版式词汇表无法满足表达需求，或需要完全自由的高质量创作时，
用 execute_python 直接编写 python-pptx 代码生成 PPTX，并用 validate_pptx 做渲染级验收。
本技能提供设计规范（防止"能生成但难看"）与迭代协议（防止"一次成型不检查"）。

## 与现有 PPT 工具的分工

| 场景 | 用哪个 |
|---|---|
| 标准汇报结构（封面/目录/章节/图表页） | create_pptx_with_ppt_master |
| 多轮可编辑源码项目交付 | manage_editable_ppt |
| 自由版式、特殊定制、上述工具不适配 | 本技能（execute_python + python-pptx） |

## 工作流（必须按序执行）

1. read_file 读参考文档（首次必读，路由见文末表格；禁止凭记忆套用规范与阈值）
2. execute_python 生成 PPTX：输出路径必须 `artifact_path("主题_YYYYMMDD.pptx")`
3. validate_pptx 验收：读取 `data.gate` 与 `data.structured_issues`
4. 按修复对照表修复，重新生成并重新验收，最多 3 轮
5. gate 通过后对 `visual_review.worst_pages` 与 montage 用
   `read_file(png_path, as_multimodal_attachment=true)` 挂载做视觉自评（标准见 qa-loop §5）

## 红线

- 输出必须经 `artifact_path()`，禁止自拼 data registry 路径写文件
- 交付前 `gate.status` 必须为 `passed` 且视觉自评无 fail 页；`qa_failed`（渲染/验证异常）不得交付
- 每页正文 ≤620 字且 ≤20 行；内容页标题 ≥24pt；最小字号 ≥10pt；层级差 ≥8pt
- 内容页（封面/目录/章节隔页除外）至少 1 个视觉元素（图表/图片/表格/形状卡片）
- 已支持的专用业务图型必须 create_business_chart 生成后嵌入，禁止用 Python 重绘替代
- 中文字体统一 Noto Sans CJK SC（服务器渲染与 QA 字体检测一致），设置方法见 code-recipes

## 参考文档（read_file 渐进读取）

| 文档 | 何时读 |
|---|---|
| backend/docs/skills/pptx_authoring/references/design-rules.md | 开始设计前：画布栅格、字号阶梯、配色、版式库、图表规范 |
| backend/docs/skills/pptx_authoring/references/code-recipes.md | 写代码前：python-pptx 配方（中文字体/文本/卡片/原生图表/表格/图片） |
| backend/docs/skills/pptx_authoring/references/qa-loop.md | 验收与修复：gate 字段解读、issue→修复对照表 |
| backend/docs/skills/pptx_authoring/references/output-contract.md | 交付前：命名、归档、迭代复用、图表嵌入约定 |
