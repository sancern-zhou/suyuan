---
name: Archify 图技能
description: 为 suyuan 项目助手模式生成和校验架构、工作流、序列、数据流和生命周期图；优先使用已安装的 Archify 包完成 JSON authoring、验证、交付和预览。
---

# Archify 图技能

## 概述
用于在 suyuan 项目助手模式中把自然语言需求、Mermaid 草稿或仓库证据整理成可校验的 standalone HTML 图。优先调用已安装的 Archify 包 `$CODEX_HOME/skills/archify`；当图必须反映真实代码时，先读取仓库证据，再写候选 JSON。

## 适用场景
- 架构图、工作流图、序列图、数据流图、生命周期图
- Mermaid `flowchart`、`sequenceDiagram`、`stateDiagram` 的转换或美化
- 需要输出可交互 HTML、PNG、JPEG、WebP、SVG 或 WebM
- 需要基于仓库事实而不是凭空绘图

## 工作流
1. 先判断图的类型：`architecture`、`workflow`、`sequence`、`dataflow` 或 `lifecycle`。
2. 只读取一个匹配 schema、一个 example 和必要的参考说明；不要先看渲染器实现。
3. 图必须反映真实代码时，先用 `read_file`、`search_files`、`grep` 或 `list_directory` 收集仓库证据。
4. 先写候选 JSON，再做验证；不要先规划精确坐标。
5. 默认使用 `meta.quality_profile: "showcase"`，主路径清晰，分支短，标签少。
6. 每次修改后立刻验证，最终交付前再次验证。
7. 只有在最终验证通过后才执行交付。

## 命令
- 选择类型或查看导引：`node "$CODEX_HOME/skills/archify/bin/archify.mjs" guide "<scenario>" --json`
- 校验候选：`node "$CODEX_HOME/skills/archify/bin/archify.mjs" validate <type> <candidate.json> --quality showcase --json`
- 交付 HTML：`node "$CODEX_HOME/skills/archify/bin/archify.mjs" deliver <type> <candidate.json> <output.html> --quality showcase --json`
- 交付后做浏览器检查：`node "$CODEX_HOME/skills/archify/bin/archify.mjs" visual-check <output.html> --json`
- 品牌标识需要时：`node "$CODEX_HOME/skills/archify/bin/archify.mjs" brands "<name>" --json`

## 说明
- 如果需要更细的字段约束、交付契约或视觉检查规范，读取 `$CODEX_HOME/skills/archify/references/authoring-contract.md` 和 `$CODEX_HOME/skills/archify/references/delivery-contract.md`。
- 不把这个 skill 当成通用写作模板；它只负责图的 authoring、validation 和 delivery 工作流。
