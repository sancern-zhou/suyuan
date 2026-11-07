---
name: Word 文档创作技能
description: 用 execute_python 编写 python-docx 代码自由创作高质量可交付 Word 文档（技术方案/数据说明/纪要/信函等非公文文档）：标题层级、表格图片、页码目录规范，配合 validate_office 渲染验收闭环。
aliases: [Word设计, Word制作, 文档生成, python-docx, 自由Word]
required_tools: [read_file, execute_python, validate_office]
enabled: true
---

# Word 文档创作技能（docx_authoring）

## 概述

用 execute_python 直接编写 python-docx 代码生成自由版式的 Word 交付文档，
并用 validate_office 做渲染级验收。适用于结构化报告管线不适配的非公文场景。

## 分工红线（必须遵守）

| 场景 | 用哪个 |
|---|---|
| 正式公文/政务报告（QMD 渲染、公文样式） | create_report_package |
| 需要用户在会话内多轮编辑的文档 | 办公编辑工具链 |
| 技术方案、数据说明、会议纪要、信函、材料汇编 | 本技能（execute_python + python-docx） |

## 工作流（必须按序执行）

1. read_file 读参考文档（首次必读，路由见文末表格；禁止凭记忆套用规范）
2. execute_python 生成 DOCX：输出路径必须 `artifact_path("主题_YYYYMMDD.docx")`
3. validate_office 验收：读取 `data.gate` 与 `data.structured_issues`
4. 按修复对照表修复，重新生成并重新验收，最多 3 轮
5. `gate.status == "passed"` 才算交付（PDF 页图随资源组自动发布）

## 红线

- 输出必须经 `artifact_path()`，禁止自拼 data registry 路径
- 交付前 `gate.status` 必须为 `passed`；`qa_failed` 不得交付
- 全文至少 1 个标题，标题层级禁止跳级（H1→H3）；标题必须用标准 Heading 样式
- 中文字体统一 Noto Sans CJK SC（Normal 样式 + eastasia 节点，见 code-recipes），
  validate_office 传 `expected_fonts: ["Noto Sans CJK SC"]` 校验
- 表格/图片为文档主体时仍需标题结构（空文档会被判 `docx_empty_document`）
- 图片宽度统一 5.8 英寸（与平台占位符替换宽度一致）

## 参考文档（read_file 渐进读取）

| 文档 | 何时读 |
|---|---|
| backend/docs/skills/docx_authoring/references/design-rules.md | 开始设计前：页面/字体/标题层级/表格图片规范 |
| backend/docs/skills/docx_authoring/references/code-recipes.md | 写代码前：python-docx 配方（样式/目录字段/表格/图片/页码） |
| backend/docs/skills/docx_authoring/references/qa-loop.md | 验收与修复：gate 字段解读、issue→修复对照表 |
| backend/docs/skills/docx_authoring/references/output-contract.md | 交付前：命名、归档、迭代复用约定 |
