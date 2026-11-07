# 交付契约（output-contract）

## 1. 输出路径与命名

- 交付文件必须 `out = artifact_path("主题_YYYYMMDD.docx")`；禁止自拼路径。
- 命名：`{中文主题}_{YYYYMMDD}.docx`；同一主题迭代**复用首次 file_path 覆盖保存**。

## 2. 文档结构建议

短答复（说明/纪要）：标题 + 2–3 个 H1 小节 + 结论，1–3 页。
完整文档（技术方案/数据说明）：封面信息（标题+日期+单位）→ 目录（>3 页时）→
概述 → 主体章节 → 结论/建议 → 附表。

## 3. 图表嵌入约定

- 专用业务图型必须 create_business_chart 生成，取返回 `file_path` 用
  `add_figure`（5.8in 宽）嵌入；禁止重绘。
- matplotlib 通用图须套统一报告主题。

## 4. 资源发布

- execute_python 保存 .docx 后会自动生成 PDF 预览；validate_office 通过后把
  docx 主文件 + report.json + PDF/页图作为同一资源组自动发布，
  `gate.status == "passed"` 即完成交付，无需手动 publish_session_file。
- 多文件交付（文档 + 附表 xlsx）每份单独 artifact_path + 单独验收。

## 5. 汇报口径

向用户说明：页数、QA 结论（gate.status 与问题数）、目录域需打开后更新（如含 TOC）、
未解决的低级别问题（如有）。
