# 统一资源预览、下载与报告导出设计

## 目标

统一资源目录同时负责“看什么”和“拿走什么”，不再由 PDF、HTML、Markdown、Office 等渲染器各自维护下载协议。所有具有 `download` 能力的文件都在右侧预览顶部获得明确下载入口；预览衍生物与原始文件严格区分。

QMD 正式报告在同一资源组内提供 QMD 源文件、可携带完整依赖的 HTML、DOCX 等交付格式。DOCX 必须复用现有 `quarto_report_renderer.render_docx()`，包括政府公文参考模板、图片段落归一化和最终样式处理。

## 资源组语义

- `primary`：用户真正拥有的原始文件。Word 输入附件的主资源是 DOC/DOCX，QMD 报告的主资源是 `report.qmd`。
- `preview`：只服务前端显示。Word/PPT 的 PDF、QMD 的 Quarto HTML 都是预览资源，不替代原始下载。
- `rendition`：由主资源导出的可下载格式，例如 QMD 报告导出的 DOCX 或独立 HTML。
- 前端预览顶部始终从资源组解析操作：默认下载 `primary`，不能把当前 `preview` 当作原始文件下载。

## 通用预览操作栏

`ResourcePreviewHost` 增加统一操作栏，所有渲染器复用：

- 主资源具有 `download` 时显示“下载原始文件”或带格式的标签，如“下载 DOCX”“下载 HTML”“下载 Markdown”。
- 同组已有可下载 `rendition` 时显示格式选择，下载对应资源。
- PDF iframe 保留浏览器内置工具栏；统一操作栏明确标注“下载原始 DOCX”等原始格式操作，避免与保存当前 PDF 预览混淆。
- 下载继续使用统一资源 `download_url`、鉴权请求和 Blob，不恢复 `/api/office`、`download-word` 等旧接口。
- 图片、PDF、HTML、Markdown、QMD、表格和普通文件只要具有 `download` 能力，均可通过同一操作栏下载。

## QMD 预览与多格式导出

QMD 报告支持以下交付格式：

1. QMD：直接下载主资源 `report.qmd`。
2. HTML：预览使用目录型 HTML 资源，以 `report.html` 为入口并提供 `report_files`、图片等关联资产；导出由 Quarto `--embed-resources` 生成独立 HTML rendition，避免离线文件缺少依赖。
3. Word：通过统一资源 render action 按需调用现有 `render_docx()`，生成 `report.docx` 后作为同组 `rendition` 登记并下载。

PDF 只有在资源组已经存在 PDF rendition 时才出现在格式选择中。本次不新增未经验证的 Quarto PDF/LaTeX 生产链路。

## 统一资源动作

QMD 主资源声明 `render` 能力。服务端从可信资源身份生成 render action URL，前端不得传入本地路径或 report id。

`POST /api/sessions/{session_id}/resources/{resource_id}/render` 接受受限格式 `docx` 或 `html`：

- 校验当前用户对会话具有写权限；
- 校验资源是 active、primary、role=report、format=qmd；
- 从服务端 locator 解析标准报告包，拒绝报告根目录外路径；
- DOCX 复用 `quarto_report_renderer.render_docx()`；HTML 生成独立可下载文件；
- 使用 `attach_resources` 将结果登记为同组 `rendition`；重复导出稳定覆盖同一资源键；
- 返回统一资源版本和变更资源 ID，前端刷新目录后下载新 rendition。

导出失败不产生半成品资源，前端在操作栏展示明确错误并允许重试。

## QMD HTML 预览修复

当前日志显示 `report.html` 以单文件资源提供，浏览器请求 `report_files/...` 连续返回 404。修复后，QMD 的 HTML preview 声明为目录 artifact，入口为 `report.html`，统一内容接口据此授权并服务相对资产。QMD 主文件仍是同组 primary。

## 会话恢复与兼容边界

- 会话恢复只读取统一资源目录；操作栏和格式列表由恢复后的资源组重新计算。
- 已生成的 rendition 恢复后可直接下载，不重复渲染。
- 新发布或重新发布的报告使用目录型 HTML preview；不读取旧预览机制。
- 不恢复历史 `/api/office`、报告专用下载接口或前端格式专用 URL 拼接。

## 验证

- Word 输入附件：显示 PDF 预览并保留内置工具栏，统一按钮明确下载 DOCX 原始文件。
- HTML、Markdown、PDF、图片等资源：具有 download 能力时均显示统一下载入口并保留原扩展名。
- QMD：Quarto HTML 的 CSS/JS/图片请求成功；可下载 QMD；首次导出 Word 生成 DOCX rendition，第二次复用稳定资源；恢复会话后仍可下载。
- 权限、非法格式、非 QMD 资源和越界报告路径被拒绝。
- 构建产物继续不含 `/office-documents`、`/visualizations`、`/api/office` 等旧机制。
