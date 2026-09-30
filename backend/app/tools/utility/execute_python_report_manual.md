# execute_python 报告与 Office 交付规范

工具 Schema 要求 Agent 在使用 execute_python 生成 QMD、报告包素材、DOCX、PPTX、PDF 或其他正式交付文件前，通过 read_file 阅读本文件。该要求由 Agent 按任务场景执行，工具运行时代码不检测阅读状态，也不会因此阻断执行。

工具 Schema 已说明所有场景共同遵守的沙箱、输入文件、artifact_path、自动发布和错误状态规则。本文件只补充报告生产和 Office 文件交付流程。

## 正式报告标准流程

正式报告不要通过 execute_python 直接生成最终 DOCX，也不要在 Python 中自行实现 QMD、HTML、Word 之间的格式转换。

标准流程：

1. 明确报告对象、问题、时间范围、统计口径、交付格式和关键假设。
2. 使用查询工具和 execute_python 完成数据校验、计算、表格及通用静态图；专用业务图使用 create_business_chart。
3. 准备 report.qmd 内容，图片在报告包中使用 assets/... 相对路径。
4. 将真实图片资源交给 create_report_package.assets，由报告包工具复制并规范化引用。
5. 调用 create_report_package 生成 reports/{report_id}/report.qmd 和预览。
6. 检查最终 HTML/Word 的数字、图表、目录、图注和版式，再向用户交付。

正式报告必须遵循事实、推断、建议分层；数字必须来自工具结果或已读取来源，不得编造。报告应附数据来源、口径、关键假设和局限性。

## 报告包路径

标准结构：

    backend/backend_data_registry/reports/{report_id}/report.qmd

不要写成 reports/{report_id}.qmd，也不要自行拼接 sessions/...、缓存 ID 或 /api/image/... 为报告素材路径。

正式报告通过 create_report_package 收口。execute_python 主要负责计算、静态图、表格和其他中间素材。

## 一次性 Word

只有用户明确要求一次性 Word，且不需要 HTML/QMD 同源报告包时，才直接使用 python-docx。

应使用公共公文样式函数：

- apply_government_report_style
- add_government_title
- add_government_heading
- add_government_paragraph
- add_government_table
- add_government_image
- resolve_report_image_path

默认公文样式：标题小标宋或宋体 fallback、二号居中；正文仿宋三号、首行缩进 2 字符、固定 28 磅行距；一级标题黑体三号，二级标题楷体三号，三级标题仿宋加粗三号；页边距上 3.7 cm、下 3.5 cm、左右 2.8 cm。

一次性 Word 示例：

    from docx import Document
    from app.services.report.government_docx_style import (
        apply_government_report_style,
        add_government_title,
        add_government_paragraph,
    )

    document = Document()
    apply_government_report_style(document)
    add_government_title(document, "报告")
    add_government_paragraph(document, "正文内容。")
    output_path = artifact_path("report.docx")
    document.save(output_path)
    print(output_path)

图片文件必须通过 input_files 声明，并使用校验后的路径或 resolve_report_image_path；输出 DOCX 仍须使用 artifact_path。

## Excel、PPTX 和 PDF 交付

- 生成 Excel 时遵守 execute_python_data_manual.md；修改已有 Excel 优先使用 openpyxl。
- 生成报告图时遵守 execute_python_chart_manual.md。
- PPTX、PDF、DOCX 和 XLSX 交付文件统一使用 artifact_path(filename)。
- 不要把临时目录、宿主机绝对路径或数据注册表路径作为最终交付链接。
- 生成后应重新打开或解析文件，检查页数、工作表、关键文字、图表、图片和文件可读性。

## 输出结果

- file_path：主交付文件，后续必须原样复用。
- files：本次生成的全部归档文件。
- generated_artifacts：自动发布状态；auto_published=true 表示无需再次发布。
- pdf_preview：Office/PDF 预览信息。
- resources：统一会话资源声明。

不要再次调用 publish_session_file，不要根据文件名猜资源路径。需要资源 ID 时使用 list_session_resources。

## 报告质检

- 摘要、正文、表格和图表数字一致。
- 单位、时间范围、平均时间和统计口径一致。
- 每个结论有数据支撑和来源，推断不能写成事实。
- 图表与正文论点对应，图例、单位、标准线和图注清晰。
- 无 TODO、占位文字、损坏链接、缺失图片或未处理异常。
- HTML/Word/PDF 中标题层级、分页、表格宽度和图片尺寸可读。
- success=false 或存在 preview_error 时，不能声称报告交付成功。
