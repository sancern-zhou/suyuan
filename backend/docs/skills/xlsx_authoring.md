---
name: Excel 表格设计技能
description: 用 execute_python + openpyxl 设计高质量可交付 Excel（台账/汇总表/附表）：sheet 组织、表头样式、列宽与数字格式规范，继承 data_manual Excel 规则，配合 validate_office 读回校验闭环。
aliases: [Excel设计, Excel制作, 表格生成, openpyxl, 台账]
required_tools: [read_file, execute_python, validate_office]
enabled: true
---

# Excel 表格设计技能（xlsx_authoring）

## 概述

在 execute_python_data_manual.md 的 Excel 基础规则（保样式改表、公式保留、
读回核验）之上，补设计层规范与 QA 验收闭环，用于新建交付级表格。

## 分工红线（必须遵守）

| 场景 | 用哪个 |
|---|---|
| 中间结构化数据 / 工具间传递 | `save_data(...)`，禁止用临时 Excel 当交换协议 |
| 修改现有 Excel | 按 data_manual 规则（openpyxl 保样式，先查表头/冻结/合并） |
| 新建交付表格（台账/汇总/附表） | 本技能（execute_python + openpyxl + 设计规范） |
| 超 10 万行数据导出 | 改用 CSV/分表，并在汇报中说明 |

## 工作流（必须按序执行）

1. read_file 读参考文档（首次必读；data_manual 的 Excel 规则同样有效）
2. execute_python 生成 XLSX：输出路径必须 `artifact_path("主题_YYYYMMDD.xlsx")`
3. validate_office 验收：读取 `data.gate` 与 `data.structured_issues`
4. 按修复对照表修复，重新生成并重新验收，最多 3 轮
5. `gate.status == "passed"` 才算交付

## 红线

- 输出必须经 `artifact_path()`；修改现有文件同样
- 交付前 `gate.status` 必须为 `passed`
- 每个表首行为表头 + 冻结首行（`freeze_panes="A2"`）；表名 ≤31 字符且不含 `\ / * ? : [ ]`
- 可计算的值用公式，禁止全部硬编码成数值（data_manual 继承）
- 数据区禁止合并单元格（排序/筛选/透视全部失效）；合并只允许用于表头装饰
- 列宽显式设置（中文按 2 字符宽估算），禁止留默认宽度装长内容
- 单 sheet 建议 ≤5 万行（前端 SheetJS 解析限制）

## 参考文档（read_file 渐进读取）

| 文档 | 何时读 |
|---|---|
| backend/docs/skills/xlsx_authoring/references/design-rules.md | 开始设计前：sheet 组织/表头样式/列宽/数字格式 |
| backend/docs/skills/xlsx_authoring/references/code-recipes.md | 写代码前：openpyxl 样式配方（字体/填充/边框/冻结/筛选/数字格式） |
| backend/docs/skills/xlsx_authoring/references/qa-loop.md | 验收与修复：gate 字段解读、issue→修复对照表 |
| backend/docs/skills/xlsx_authoring/references/output-contract.md | 交付前：命名、归档、EXCEL_SAVED 预览说明 |
