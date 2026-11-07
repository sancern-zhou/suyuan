# QA 闭环协议（qa-loop）

生成 → 渲染验收 → 修复 → 重验收。**没有经过本闭环的 DOCX 不算交付物。**

## 1. 验收调用

```json
validate_office({
  "path": "<上次 artifact_path 返回的 file_path>",
  "expected_fonts": ["Noto Sans CJK SC"]
})
```

## 2. 结果解读

- `gate.status`：`passed`（可交付）/ `needs_revision`（按表修复后重验）/
  `qa_failed`（渲染或校验流程异常——先修环境/文件，不得跳过验收交付）。
- `structured_issues[]`：`type/severity/message` + docx 类 issue 附 `page` 级证据。
- `render.page_count / page_pngs`：渲染页图路径，用于人工复核排版细节
  （孤行、表格跨页断裂、图片溢出——这些 QA 不判，页图复核兜底）。

## 3. 修复对照表（issue type → 动作）

| type | 动作 |
|---|---|
| docx_no_heading | 用 `doc.add_heading(text, level)` 建立标题结构，级别从 1 开始 |
| docx_heading_level_jump | 补中间级别标题或调整层级为逐级递减 |
| docx_empty_document | 检查段落/表格是否真的写入（常见：只写了样式没 add 内容） |
| rendered_blank_page | 删除多余分页符/空段落；检查图片是否真的嵌入成功 |
| expected_font_missing | Normal 与 Heading 样式补 eastasia 字体（code-recipes §1） |
| font_detection_unavailable | fitz 缺失（环境问题）：结构检查仍有效，渲染复核降级为说明 |
| rendered_qa_unavailable | soffice 转换失败：检查文件能否被 python-docx 重新打开，重存后再验 |
| validation_error | 按异常信息定位；常见为文件损坏或路径错误 |

## 4. 迭代纪律

- 每轮：修改生成代码 → execute_python 重新生成（覆盖同一 artifact_path 文件）→ 重新 validate_office。
- 最多 **3 轮**。仍有非阻断（low）问题且正文结构完整可交付并说明；
  仍有 high 或 `docx_no_heading` → 退回最简结构（H1/H2 + 段落 + 表格）重来。
- 长文档（>8 页）每轮抽看首/尾/表格页的 page_png 复核跨页排版。
