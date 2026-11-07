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
- 最多 **3 轮**（含视觉自评修复）。仍有非阻断（low）问题且正文结构完整可交付并说明；
  仍有 high 或 `docx_no_heading` → 退回最简结构（H1/H2 + 段落 + 表格）重来。

## 5. 视觉自评（确定性 gate 通过后必须执行）

validate_office（docx）返回 `render.montage_path` 与 `render.page_pngs`。
**结构检查拦不住排版问题**——gate 通过后必须亲自看图：

1. `read_file(path=<montage_path>, as_multimodal_attachment=true)` 挂载全文总览
2. 疑似页（总览中观感异常的）逐页 `read_file(path=<page_png>, as_multimodal_attachment=true)` 挂载
3. 检查清单（判定基线：用户会不会接受）：

| 维度 | 检查点 |
|---|---|
| 跨页排版 | 无孤行（标题落页尾/单行落页首）；表格未在行中间断裂；图片未溢出页宽 |
| 版面 | 页边距均匀；段落间距一致；无大段空白 |
| 字体 | 全文中文一致（宋体混入 = eastasia 未设，回 code-recipes §1 修）；标题层级观感清晰 |
| 表格 | 表头完整可见；列宽合理无挤压换行；隔行底色正确 |
| 图片 | 居中、宽度统一（5.8in）；图题紧贴图下 |

4. fail 项修复后重生成 + 重新 validate_office + 重新自评
5. **交付标准：确定性 gate passed 且视觉自评无 fail 页**；目录域未更新的占位提示不算 fail（打开后 F9 更新，见 code-recipes §4 说明）
