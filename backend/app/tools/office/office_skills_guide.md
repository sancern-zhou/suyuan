# Office 工具入口

当前助手模式不再暴露底层 Word 编辑工具或 Office XML 解包/打包工具。本文件只作为 Office 任务路由索引，具体流程以专项指南为准。

## 工具路由

- 高质量、从零生成、需要反复底层编辑的 PPT：阅读 `backend/app/tools/office/editable_ppt/references/index.md`，使用 `manage_editable_ppt`，也可以直接用 `read_file` / `edit_file` 修改项目中的 JSON、JS 和资源文档。
- 兼容旧流程或继续修改 PPT Master 项目：阅读 `backend/app/tools/office/PPT操作指南.md`，使用 `create_pptx_with_ppt_master`、`validate_pptx`。
- 正式业务 PPT：先读 `backend/app/tools/office/ppt_master_references/index.md`，再按任务渐进读取所需设计规则。
- Excel 读取、创建、修改、公式和图表：阅读 `backend/app/tools/office/Excel操作指南.md`，使用 `execute_python` 配合 `openpyxl`、`pandas`、`xlsxwriter`。
- Word 读取：使用 `read_file` 或 `read_docx`。当前助手模式不暴露既有 Word 文档编辑工具。

## 硬性约束

- 新建正式业务 PPT 且要求高质量、原生可编辑或多轮完善时，优先使用 `manage_editable_ppt`；旧 PPT Master 工具保持可用。
- 长 PPT 不要一次内联提交完整 `slide_plan`：超过 8 页、shapes 很多或图表/表格很多时，先生成骨架，再用 `create_pptx_with_ppt_master(operation="append"/"replace"/"patch")` 每批 3-5 页续改；短批次可用 `batch_slides` + `after_slide`，长批次先 `write_file` 写 JSON，再传 `slide_plan_path` 或 `plan_patch_path`；每批必须基于上一批返回的最新 `data.next_revision_base_plan_path` 或 `data.slide_plan_path`。
- 续改 PPT Master 生成物时，读取上一版 `slide_plan.v*.json`，由 Agent 编写局部 `plan_patch`，调用 `create_pptx_with_ppt_master(operation="patch")` 合并并重绘。
- PPT 图表图片必须在创建 PPT 时通过 `outline[].chart.image_path`、`outline[].chart.path` 或 `outline[].visual.image_path` 传入，不要先生成 mock PPT 再猜槽位替换。
- PPT 生成后必须读取 `qa_status`、`quality_gate` 和 `validation.montage_path`；如生成了 montage，总览图必须再调用 `read_file(path=validation.montage_path, as_multimodal_attachment=true)` 做原生多模态视觉质量检查。
- 工具约束统一维护在 `backend/app/tools/office/ppt_master_references/`，不要从 `backend/docs/skills/` 复制或扩展 PPT Master 规则。
- Excel 任务不要寻找专用 Office 工具，直接使用 `execute_python`。
- 不要调用或建议 `word_edit`、`find_replace_word`、`accept_word_changes`、`unpack_office`、`pack_office`；这些工具已退出 Agent 工具体系。
