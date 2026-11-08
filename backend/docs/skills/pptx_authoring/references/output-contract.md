# 交付契约（output-contract）

## 1. 输出路径与命名

- 交付文件必须 `out = artifact_path("主题_YYYYMMDD.pptx")` 获取路径后保存；
  工具会自动归档并把真实路径返回在 `file_path`。禁止自拼 data registry 路径。
- 命名：`{中文主题}_{YYYYMMDD}.pptx`，如 `许昌市空气质量分析_20261107.pptx`；
  同一主题迭代**复用首次返回的 file_path 覆盖保存**，不要每轮新建文件名。

## 2. 页面结构建议

封面 → 目录 → （章节隔页 + 2–4 内容页）×N → 结尾页。汇报型 deck 内容页 8–20 页；
短答复型（单问题快答）4–6 页。每页都过 design-rules 密度红线。

## 3. 图表嵌入约定

- 专用业务图型（平台已支持的图）：必须 `create_business_chart` 生成，取其返回的
  `file_path`，用 `add_image_fit` 按宽等比嵌入；禁止用 matplotlib/python-pptx 重绘替代。
- 通用图优先 python-pptx 原生图表（收件人可编辑）；matplotlib 仅用于原生不支持的
  形式（箱线/小提琴/复杂注释图），必须套统一报告主题（REPORT_THEME/SERIES_COLORS）。
- 图片文件路径只能来自工具返回值（create_business_chart 的 file_path 或
  read_file 声明过的输入），不得自行推断。

## 4. 资源发布

- `validate_pptx` 验收通过时会把 pptx 主文件 + PDF + 页图 + montage 作为同一资源组
  声明并随工具结果自动发布；`gate.status == "passed"` 后即完成交付，无需再手动
  publish_session_file（仅当用户要求把文件另存到会话工作区时使用）。
- 多文件交付（PPT + 附表等）每份文件单独 artifact_path + 单独验收。

## 5. 汇报口径

向用户汇报时说明：页数、QA 结论（gate.status 与分数）、未解决的低级别问题（如有）。
