# 浏览器制品预览 URL 统一路由设计

## 背景

后端工具与历史会话中的文档预览地址既有 `/api/...`，也有已经带外部网关前缀的
`/api/suyuan/...`。普通 API 调用经过 `authFetch` 时会自动映射网关前缀，但 PDF、
HTML 和 SVG 等预览由 iframe 或浏览器资源元素直接加载，不经过 `authFetch`。

在当前 Nginx 路由中，只有 `/api/suyuan/**` 会代理到业务后端；裸 `/api/**` 会落入
SPA fallback 并返回 `index.html`。因此 PPT、Word 和 PDF 的 iframe 会显示系统首页，
历史 HTML、报告和 SVG 预览也存在相同风险。

## 目标

- 所有浏览器直接加载的内部制品 URL 遵循同一网关路由规则。
- 修复 PPT、Word、PDF、HTML、报告和 SVG 预览，不针对单一文件类型拼接路径。
- 兼容历史会话保存的裸 `/api/**` 和同源绝对 API 地址。
- 已带运行时网关前缀的 URL 不重复转换。
- 外部 URL、`blob:` 和 `data:` URL 保持原样。
- Excel 的认证 API 请求和图片的认证 Blob 加载流程保持不变。

## 设计

### 统一边界

以 `frontend/src/utils/artifactRelatedFiles.js` 中的 `normalizeArtifactUrl` 作为浏览器
制品 URL 的统一解析边界。该函数复用认证模块已有的 `gatewayUrl`，不另建 PPT、PDF
或 HTML 专用拼接逻辑。

解析顺序如下：

1. 空值和非字符串原样返回。
2. `blob:`、`data:` 及非 API 外部 URL 原样返回。
3. 同源绝对 URL 若其 pathname 以 `/api/` 开头，抽取 pathname、query 和 hash。
4. 裸 `/api` 或 `/api/**` 通过 `gatewayUrl` 映射到运行时 API base。
5. 已等于运行时 API base，或已经以该 base 开头的 URL 原样返回。

`OfficeDocumentPanel` 已在标准化文档时集中处理 `pdf_url`、`html_url` 和 `svg_url`，
因此它继续只消费解析后的 URL。相关制品下载条目也复用同一函数。

### 部署与安全边界

不新增 Nginx 的裸 `/api/**` 代理规则，避免绕开系统既定的 `/api/suyuan/**` 网关
边界。后端的内部资源路径可以保持部署无关；前端根据运行时 `VITE_API_BASE_URL`
生成浏览器实际访问路径。

本次仅修复路径路由契约。图片继续使用现有认证 Blob 加载器，Excel 继续使用
`authFetch`。不在本次改动中重构 iframe 的认证载荷机制。

## 测试

先增加失败测试并确认当前实现会把裸 `/api/**` 原样返回，随后覆盖：

- PPT/Word/PDF 使用的 `/api/office/pdf/{id}`。
- HTML/报告使用的 `/api/reports/...` 和 `/api/html-artifacts/...`。
- SVG 资源地址。
- 已带 `/api/suyuan/**` 的地址不重复添加前缀。
- 同源绝对旧地址保留 query/hash 后正确映射。
- 外部 HTTP(S)、`blob:`、`data:` 地址不改变。
- 相关附件下载 URL 使用同一解析规则。

完成后运行资源 URL 单元测试、Office 面板相关测试和前端构建，并通过实际 Nginx
入口验证解析后的 PPT PDF URL 返回 `application/pdf` 而不是 `text/html`。

## 非目标

- 不修改 PPT、Word 或 PDF 的生成与转换逻辑。
- 不开放裸 `/api/**` Nginx 代理。
- 不迁移数据库中已有的历史 URL。
- 不改变分享链接和外部公共 URL。
